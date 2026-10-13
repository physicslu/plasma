from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


IC_SUPPORT_ROOT_ENV = "PLASMA_IC_SUPPORT_ROOT"
IC_SUPPORT_RELATIVE_ROOT = Path("data/ic-support")
EXPECTED_PROFILE_KINDS = (
    "programming",
    "programming_route",
    "memory_geometry",
    "package_hardware",
    "option",
    "security",
)
PROFILE_DIRECTORY_KIND = {
    "programming": "programming",
    "programming-route": "programming_route",
    "memory-geometry": "memory_geometry",
    "package-hardware": "package_hardware",
    "option": "option",
    "security": "security",
}
EXPECTED_CATALOG_FIELDS = (
    "manufacturer",
    "base_device",
    "package",
    "pin_count",
    "flash_size",
    "openocd_target_config",
)
MANUFACTURER_BASELINE_DIRNAME = "manufacturer-baseline"
MANUFACTURER_BASELINE_GLOB = "*-manufacturer-only-v1.json"


class ICSupportIntegrityError(RuntimeError):
    """Checked-in IC Support data is incomplete, contradictory, or malformed."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_ic_support_root() -> Path:
    configured = os.environ.get(IC_SUPPORT_ROOT_ENV)
    if configured:
        return Path(configured).expanduser().resolve()

    source_tree_root = (_repository_root() / IC_SUPPORT_RELATIVE_ROOT).resolve()
    if source_tree_root.is_dir():
        return source_tree_root

    raise ICSupportIntegrityError(
        f"{IC_SUPPORT_ROOT_ENV} must point to repository-owned IC Support data "
        "when Plasma runs from an installed Python package"
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ICSupportIntegrityError(message)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ICSupportIntegrityError(f"cannot read IC Support JSON: {path}") from exc
    _require(isinstance(payload, dict), f"{path}: top-level JSON must be an object")
    return payload


def _validate_programming_route_data(profile_id: str, data: dict[str, Any]) -> None:
    vocabulary = data.get("context_vocabulary")
    routes = data.get("routes")
    _require(
        isinstance(vocabulary, dict) and set(vocabulary) == {"icp", "offline_socket"},
        f"{profile_id}: programming context vocabulary must be exactly icp/offline_socket",
    )
    _require(isinstance(routes, list) and routes, f"{profile_id}: routes must be a non-empty array")

    route_ids: set[str] = set()
    for index, route in enumerate(routes):
        owner = f"{profile_id}: routes[{index}]"
        _require(isinstance(route, dict), f"{owner} must be an object")
        route_id = route.get("route_id")
        _require(isinstance(route_id, str) and route_id, f"{owner}.route_id is required")
        _require(route_id not in route_ids, f"{profile_id}: duplicate route_id {route_id!r}")
        route_ids.add(route_id)

        contexts = route.get("contexts")
        _require(
            isinstance(contexts, dict) and set(contexts) == {"icp", "offline_socket"},
            f"{route_id}: contexts must be exactly icp/offline_socket",
        )
        for context_name, context in contexts.items():
            _require(isinstance(context, dict), f"{route_id}: {context_name} context must be an object")
            _require(
                isinstance(context.get("supported"), bool),
                f"{route_id}: {context_name}.supported must be boolean",
            )

        transport = route.get("transport")
        _require(isinstance(transport, dict), f"{route_id}: transport must be an object")
        _require(
            isinstance(transport.get("type"), str) and transport["type"],
            f"{route_id}: transport.type is required",
        )

        entry = route.get("entry_requirements")
        _require(isinstance(entry, dict), f"{route_id}: entry_requirements must be an object")
        required_signals = entry.get("required_signals")
        optional_signals = entry.get("optional_control_signals")
        strap_states = entry.get("strap_states")
        reset_sequence = entry.get("reset_sequence")
        timing = entry.get("timing_requirements")
        _require(
            isinstance(required_signals, list) and all(isinstance(item, str) and item for item in required_signals),
            f"{route_id}: required_signals must be an array of logical signal names",
        )
        _require(
            isinstance(optional_signals, list) and all(isinstance(item, str) and item for item in optional_signals),
            f"{route_id}: optional_control_signals must be an array",
        )
        _require(isinstance(strap_states, list), f"{route_id}: strap_states must be an array")
        seen_straps: set[str] = set()
        for strap_index, strap in enumerate(strap_states):
            _require(isinstance(strap, dict), f"{route_id}: strap_states[{strap_index}] must be an object")
            signal = strap.get("signal")
            state = strap.get("state")
            _require(isinstance(signal, str) and signal, f"{route_id}: strap signal is required")
            _require(signal not in seen_straps, f"{route_id}: duplicate strap signal {signal!r}")
            seen_straps.add(signal)
            _require(state in {"high", "low"}, f"{route_id}: strap state must be high or low")
            _require(signal in required_signals, f"{route_id}: strap signal {signal!r} must also be required")
        _require(isinstance(reset_sequence, dict), f"{route_id}: reset_sequence must be an object")
        _require(
            isinstance(reset_sequence.get("required"), bool),
            f"{route_id}: reset_sequence.required must be boolean",
        )
        _require(
            isinstance(entry.get("power_cycle_required"), bool),
            f"{route_id}: power_cycle_required must be boolean",
        )
        _require(isinstance(timing, dict), f"{route_id}: timing_requirements must be an object")
        _require(
            isinstance(route.get("entry_sequence"), list) and route["entry_sequence"],
            f"{route_id}: entry_sequence must be non-empty",
        )
        _require(
            isinstance(route.get("exit_sequence"), list) and route["exit_sequence"],
            f"{route_id}: exit_sequence must be non-empty",
        )
        _require(
            route.get("runtime_implemented") is False,
            f"{route_id}: pilot route must not claim runtime implementation",
        )
        if strap_states:
            _require(
                contexts["offline_socket"]["supported"] is True,
                f"{route_id}: strap-controlled route must support offline_socket",
            )
            _require(
                contexts["icp"]["supported"] is False,
                f"{route_id}: strap-controlled route cannot be ICP-supported in Programming Route v1",
            )


@dataclass(frozen=True, slots=True)
class ResolvedProfile:
    profile_id: str
    kind: str
    status: str
    scope: dict[str, Any]
    data: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, path: Path, expected_kind: str) -> "ResolvedProfile":
        profile_id = payload.get("profile_id")
        kind = payload.get("kind")
        status = payload.get("status")
        scope = payload.get("scope")
        data = payload.get("data")
        evidence = payload.get("evidence")
        _require(isinstance(profile_id, str) and profile_id, f"{path}: profile_id is required")
        _require(kind == expected_kind, f"{path}: kind {kind!r} does not match {expected_kind!r}")
        _require(isinstance(status, str) and status, f"{path}: profile status is required")
        _require(isinstance(scope, dict), f"{profile_id}: scope must be an object")
        _require(isinstance(data, dict), f"{profile_id}: data must be an object")
        if expected_kind == "programming_route":
            _validate_programming_route_data(profile_id, data)
        _require(isinstance(evidence, list) and evidence, f"{profile_id}: evidence must be non-empty")
        normalized_evidence: list[dict[str, Any]] = []
        for index, item in enumerate(evidence):
            _require(isinstance(item, dict), f"{profile_id}: evidence[{index}] must be an object")
            normalized_evidence.append(copy.deepcopy(item))
        return cls(
            profile_id=profile_id,
            kind=kind,
            status=status,
            scope=copy.deepcopy(scope),
            data=copy.deepcopy(data),
            evidence=tuple(normalized_evidence),
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "kind": self.kind,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ResolvedManufacturerProfile:
    baseline_id: str
    status: str
    target: dict[str, Any]
    source_policy: dict[str, Any]
    device_profile: dict[str, Any]
    programming_profile: dict[str, Any]
    program_model: dict[str, Any]
    qualification_boundary: dict[str, Any]
    canonical_file_sha256: str

    @classmethod
    def from_files(cls, baseline_path: Path, lock_path: Path) -> "ResolvedManufacturerProfile":
        try:
            raw = baseline_path.read_bytes()
        except OSError as exc:
            raise ICSupportIntegrityError(f"cannot read manufacturer baseline: {baseline_path}") from exc
        baseline = _load_object(baseline_path)
        lock = _load_object(lock_path)

        baseline_id = baseline.get("baseline_id")
        status = baseline.get("status")
        target = baseline.get("target")
        source_policy = baseline.get("source_policy")
        device_profile = baseline.get("device_profile")
        programming_profile = baseline.get("programming_profile")
        program_model = baseline.get("program_model")
        qualification_boundary = baseline.get("qualification_boundary")
        digest = hashlib.sha256(raw).hexdigest()

        _require(isinstance(baseline_id, str) and baseline_id, f"{baseline_path}: baseline_id is required")
        _require(status == "frozen_manufacturer_only", f"{baseline_id}: baseline must be frozen manufacturer-only")
        _require(isinstance(target, dict), f"{baseline_id}: target must be an object")
        _require(isinstance(target.get("icpn"), str) and target["icpn"], f"{baseline_id}: exact target ICPN is required")
        _require(isinstance(source_policy, dict), f"{baseline_id}: source_policy must be an object")
        _require(
            source_policy.get("derivation_authority") == "manufacturer_official_only",
            f"{baseline_id}: manufacturer-only derivation authority is required",
        )
        _require(isinstance(device_profile, dict), f"{baseline_id}: device_profile must be an object")
        _require(isinstance(programming_profile, dict), f"{baseline_id}: programming_profile must be an object")
        _require(isinstance(program_model, dict), f"{baseline_id}: program_model must be an object")
        _require(isinstance(qualification_boundary, dict), f"{baseline_id}: qualification_boundary must be an object")
        _require(
            qualification_boundary.get("hardware_runtime_ready") is False
            and qualification_boundary.get("physical_programming_qualified") is False,
            f"{baseline_id}: manufacturer profile must not claim hardware qualification",
        )
        _require(
            lock.get("baseline_id") == baseline_id,
            f"{baseline_id}: manufacturer baseline lock identity mismatch",
        )
        _require(
            lock.get("canonical_file_sha256") == digest,
            f"{baseline_id}: manufacturer baseline digest drift",
        )

        operating = device_profile.get("operating_electrical")
        programming_electrical = programming_profile.get("programming_electrical")
        _require(isinstance(operating, dict), f"{baseline_id}: operating electrical characteristics are required")
        _require(isinstance(operating.get("vdd_v"), dict), f"{baseline_id}: operating VDD range is required")
        _require(
            isinstance(programming_electrical, dict),
            f"{baseline_id}: programming electrical conditions are required",
        )
        _require(
            isinstance(programming_electrical.get("vdd_programming_v"), dict),
            f"{baseline_id}: programming VDD range is required",
        )
        _require(
            isinstance(device_profile.get("memory_map"), dict),
            f"{baseline_id}: Device Profile memory map is required",
        )
        interfaces = programming_profile.get("interfaces")
        _require(isinstance(interfaces, dict) and interfaces, f"{baseline_id}: programming interfaces are required")

        return cls(
            baseline_id=baseline_id,
            status=status,
            target=copy.deepcopy(target),
            source_policy=copy.deepcopy(source_policy),
            device_profile=copy.deepcopy(device_profile),
            programming_profile=copy.deepcopy(programming_profile),
            program_model=copy.deepcopy(program_model),
            qualification_boundary=copy.deepcopy(qualification_boundary),
            canonical_file_sha256=digest,
        )

    @property
    def icpn(self) -> str:
        return str(self.target["icpn"])

    def to_selected_profile_payload(self) -> dict[str, Any]:
        interfaces = copy.deepcopy(self.programming_profile["interfaces"])
        return {
            "schema_version": "1.0.0",
            "status": "manufacturer_profile_available",
            "manufacturer_baseline": {
                "baseline_id": self.baseline_id,
                "status": self.status,
                "sha256": self.canonical_file_sha256,
                "authority": self.source_policy["derivation_authority"],
                "sources": copy.deepcopy(self.source_policy.get("locked_sources", [])),
            },
            "device": {
                "identity": copy.deepcopy(self.device_profile["identity"]),
                "operating_electrical": copy.deepcopy(self.device_profile["operating_electrical"]),
                "memory_map": copy.deepcopy(self.device_profile["memory_map"]),
            },
            "programming": {
                "interfaces": interfaces,
                "electrical": copy.deepcopy(self.programming_profile["programming_electrical"]),
                "flash_geometry": copy.deepcopy(self.programming_profile["flash_geometry"]),
                "flash_controller": copy.deepcopy(self.programming_profile["flash_controller"]),
                "special_constraints": copy.deepcopy(self.programming_profile["special_constraints"]),
                "program_model": copy.deepcopy(self.program_model),
            },
            "plasma_compatibility": {
                "site_electrical_compatibility": "not_evaluated",
                "socket_compatibility": "not_evaluated",
                "hardware_runtime_ready": False,
                "physical_programming_qualified": False,
            },
        }


@dataclass(frozen=True, slots=True)
class ResolvedICSupport:
    icpn: str
    binding_set_id: str
    binding_status: str
    expected_catalog: dict[str, Any]
    profiles: dict[str, ResolvedProfile]
    revision_overrides: tuple[dict[str, Any], ...]
    manufacturer_profile: ResolvedManufacturerProfile | None = None

    def profile(self, kind: str) -> ResolvedProfile:
        try:
            return self.profiles[kind]
        except KeyError as exc:
            raise ICSupportIntegrityError(f"{self.icpn}: missing resolved {kind!r} profile") from exc

    @property
    def programming_profile(self) -> ResolvedProfile:
        return self.profile("programming")

    @property
    def memory_geometry_profile(self) -> ResolvedProfile:
        return self.profile("memory_geometry")

    @property
    def openocd_target_config(self) -> str:
        return str(self.expected_catalog["openocd_target_config"])

    def to_selected_profile_payload(self) -> dict[str, Any] | None:
        if self.manufacturer_profile is None:
            return None
        payload = self.manufacturer_profile.to_selected_profile_payload()
        payload["icpn"] = self.icpn
        payload["catalog_identity"] = {
            "base_device": self.expected_catalog["base_device"],
            "package": self.expected_catalog["package"],
            "pin_count": self.expected_catalog["pin_count"],
            "flash_size": self.expected_catalog["flash_size"],
        }
        route_profile = self.profile("programming_route")
        package_profile = self.profile("package_hardware")
        payload["programming"]["programming_route_profile"] = route_profile.to_summary()
        payload["programming"]["context_vocabulary"] = copy.deepcopy(
            route_profile.data["context_vocabulary"]
        )
        payload["programming"]["routes"] = copy.deepcopy(route_profile.data["routes"])
        payload["programming"]["package_signal_map"] = copy.deepcopy(
            package_profile.data.get("logical_signal_map", {})
        )
        payload["ic_support"] = {
            "binding_set_id": self.binding_set_id,
            "binding_status": self.binding_status,
            "profiles": {
                kind: self.profiles[kind].to_summary()
                for kind in EXPECTED_PROFILE_KINDS
            },
        }
        return payload

    def to_runtime_payload(self) -> dict[str, Any]:
        """Return a browser/log-safe resolution summary, not executable driver state."""
        return {
            "icpn": self.icpn,
            "binding_set_id": self.binding_set_id,
            "binding_status": self.binding_status,
            "base_device": self.expected_catalog["base_device"],
            "package": self.expected_catalog["package"],
            "pin_count": self.expected_catalog["pin_count"],
            "flash_size": self.expected_catalog["flash_size"],
            "profiles": {
                kind: self.profiles[kind].to_summary()
                for kind in EXPECTED_PROFILE_KINDS
            },
            "backends": {
                "openocd": {
                    "state": "target_mapped",
                    "target_config": self.openocd_target_config,
                },
                "plasma_native": {
                    "state": "algorithm_profile_available_runtime_not_implemented",
                    "programming_profile_id": self.programming_profile.profile_id,
                    "runtime_implemented": False,
                },
            },
            "runtime_ready": False,
        }


class ICSupportResolver:
    """Resolve exact ICPNs into reusable technical profiles.

    The resolver owns knowledge resolution only. It deliberately does not claim
    that an OpenOCD command template or Plasma Native PPU driver is implemented
    merely because a Programming Profile exists.
    """

    def __init__(self, records: dict[str, ResolvedICSupport], *, root: Path) -> None:
        self._records = dict(records)
        self.root = root

    @property
    def size(self) -> int:
        return len(self._records)

    @property
    def exact_icpns(self) -> tuple[str, ...]:
        return tuple(sorted(record.icpn for record in self._records.values()))

    @classmethod
    def from_root(cls, root: Path) -> "ICSupportResolver":
        resolved_root = root.expanduser().resolve()
        profiles_root = resolved_root / "profiles"
        bindings_root = resolved_root / "bindings"
        _require(profiles_root.is_dir(), f"IC Support profiles directory not found: {profiles_root}")
        _require(bindings_root.is_dir(), f"IC Support bindings directory not found: {bindings_root}")

        profiles: dict[str, ResolvedProfile] = {}
        for dirname, expected_kind in PROFILE_DIRECTORY_KIND.items():
            directory = profiles_root / dirname
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.json")):
                profile = ResolvedProfile.from_payload(
                    _load_object(path),
                    path=path,
                    expected_kind=expected_kind,
                )
                _require(profile.profile_id not in profiles, f"duplicate IC Support profile_id: {profile.profile_id}")
                profiles[profile.profile_id] = profile
        _require(profiles, f"no IC Support profiles found under {profiles_root}")

        manufacturer_profiles: dict[str, ResolvedManufacturerProfile] = {}
        manufacturer_root = resolved_root / MANUFACTURER_BASELINE_DIRNAME
        if manufacturer_root.exists():
            for baseline_path in sorted(manufacturer_root.glob(MANUFACTURER_BASELINE_GLOB)):
                lock_path = baseline_path.with_name(
                    baseline_path.name.removesuffix(".json") + ".lock.json"
                )
                _require(lock_path.is_file(), f"{baseline_path}: manufacturer baseline lock is required")
                manufacturer_profile = ResolvedManufacturerProfile.from_files(
                    baseline_path,
                    lock_path,
                )
                key = manufacturer_profile.icpn.casefold()
                _require(
                    key not in manufacturer_profiles,
                    f"duplicate manufacturer profile for exact ICPN: {manufacturer_profile.icpn}",
                )
                manufacturer_profiles[key] = manufacturer_profile

        records: dict[str, ResolvedICSupport] = {}
        for path in sorted(bindings_root.glob("*.json")):
            payload = _load_object(path)
            binding_set_id = payload.get("binding_set_id")
            binding_status = payload.get("status")
            bindings = payload.get("bindings")
            _require(isinstance(binding_set_id, str) and binding_set_id, f"{path}: binding_set_id is required")
            _require(isinstance(binding_status, str) and binding_status, f"{path}: binding status is required")
            _require(isinstance(bindings, list) and bindings, f"{path}: bindings must be a non-empty array")

            for index, entry in enumerate(bindings):
                _require(isinstance(entry, dict), f"{path}: bindings[{index}] must be an object")
                icpn = entry.get("icpn")
                expected_catalog = entry.get("expected_catalog")
                profile_refs = entry.get("profiles")
                revision_overrides = entry.get("revision_overrides")
                _require(isinstance(icpn, str) and icpn.strip(), f"{path}: binding ICPN is required")
                canonical_icpn = icpn.strip()
                key = canonical_icpn.casefold()
                _require(key not in records, f"duplicate IC Support binding for exact ICPN: {canonical_icpn}")
                _require(isinstance(expected_catalog, dict), f"{canonical_icpn}: expected_catalog is required")
                for field in EXPECTED_CATALOG_FIELDS:
                    value = expected_catalog.get(field)
                    _require(value is not None and value != "", f"{canonical_icpn}: expected_catalog.{field} is required")
                _require(isinstance(profile_refs, dict), f"{canonical_icpn}: profiles object is required")
                _require(
                    set(profile_refs) == set(EXPECTED_PROFILE_KINDS),
                    f"{canonical_icpn}: profile kinds must be exactly {list(EXPECTED_PROFILE_KINDS)}",
                )
                _require(isinstance(revision_overrides, list), f"{canonical_icpn}: revision_overrides must be an array")
                normalized_overrides: list[dict[str, Any]] = []
                for override_index, override in enumerate(revision_overrides):
                    _require(
                        isinstance(override, dict),
                        f"{canonical_icpn}: revision_overrides[{override_index}] must be an object",
                    )
                    normalized_overrides.append(copy.deepcopy(override))

                selected: dict[str, ResolvedProfile] = {}
                for kind in EXPECTED_PROFILE_KINDS:
                    profile_id = profile_refs[kind]
                    _require(isinstance(profile_id, str) and profile_id, f"{canonical_icpn}: {kind} profile_id is required")
                    _require(profile_id in profiles, f"{canonical_icpn}: dangling IC Support profile {profile_id!r}")
                    profile = profiles[profile_id]
                    _require(
                        profile.kind == kind,
                        f"{canonical_icpn}: profile {profile_id!r} has kind {profile.kind!r}, expected {kind!r}",
                    )
                    selected[kind] = profile

                manufacturer_profile = manufacturer_profiles.get(key)
                if manufacturer_profile is not None:
                    target = manufacturer_profile.target
                    _require(
                        target.get("manufacturer") == expected_catalog["manufacturer"],
                        f"{canonical_icpn}: manufacturer profile manufacturer does not match catalog binding",
                    )
                    _require(
                        target.get("base_device") == expected_catalog["base_device"],
                        f"{canonical_icpn}: manufacturer profile base_device does not match catalog binding",
                    )
                    baseline_flash = (
                        manufacturer_profile.device_profile
                        .get("memory_map", {})
                        .get("main_flash", {})
                        .get("size_bytes")
                    )
                    expected_flash = str(expected_catalog["flash_size"])
                    _require(
                        isinstance(baseline_flash, int) and f"{baseline_flash // 1024} KiB" == expected_flash,
                        f"{canonical_icpn}: manufacturer profile Flash size does not match catalog binding",
                    )

                records[key] = ResolvedICSupport(
                    icpn=canonical_icpn,
                    binding_set_id=binding_set_id,
                    binding_status=binding_status,
                    expected_catalog=copy.deepcopy(expected_catalog),
                    profiles=selected,
                    revision_overrides=tuple(normalized_overrides),
                    manufacturer_profile=manufacturer_profile,
                )

        _require(records, f"no IC Support exact-ICPN bindings found under {bindings_root}")
        return cls(records, root=resolved_root)

    def resolve_exact(self, icpn: str) -> ResolvedICSupport | None:
        if not isinstance(icpn, str) or not icpn.strip():
            return None
        return self._records.get(icpn.strip().casefold())

    def require_exact(self, icpn: str) -> ResolvedICSupport:
        resolved = self.resolve_exact(icpn)
        if resolved is None:
            raise KeyError(f"no evidence-backed IC Support binding for exact ICPN: {icpn}")
        return resolved

    def summary(self) -> dict[str, Any]:
        programming_profiles = sorted(
            {record.programming_profile.profile_id for record in self._records.values()}
        )
        programming_route_profiles = sorted(
            {record.profile("programming_route").profile_id for record in self._records.values()}
        )
        return {
            "resolved_exact_icpns": self.size,
            "programming_profiles": len(programming_profiles),
            "programming_profile_ids": programming_profiles,
            "programming_route_profiles": len(programming_route_profiles),
            "programming_route_profile_ids": programming_route_profiles,
            "manufacturer_selected_profiles": sum(
                1 for record in self._records.values()
                if record.manufacturer_profile is not None
            ),
            "native_ppu_runtime_ready_exact_icpns": 0,
            "exact_icpns": list(self.exact_icpns),
        }


@lru_cache(maxsize=4)
def _resolver_for_root(root: str) -> ICSupportResolver:
    return ICSupportResolver.from_root(Path(root))


def get_default_ic_support_resolver() -> ICSupportResolver:
    return _resolver_for_root(str(default_ic_support_root()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve evidence-backed Plasma IC Support")
    parser.add_argument("--summary", action="store_true", help="print resolver summary JSON")
    parser.add_argument("--icpn", help="resolve one exact ICPN")
    args = parser.parse_args()
    resolver = get_default_ic_support_resolver()
    if args.icpn:
        resolved = resolver.resolve_exact(args.icpn)
        payload: dict[str, Any] = (
            resolved.to_runtime_payload()
            if resolved is not None
            else {"icpn": args.icpn, "resolved": False, "runtime_ready": False}
        )
    else:
        payload = resolver.summary()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ICSupportIntegrityError as exc:
        print(f"IC Support runtime resolver FAIL: {exc}")
        raise SystemExit(1)
