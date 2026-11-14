from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any


IC_SUPPORT_ROOT_ENV = "PLASMA_IC_SUPPORT_ROOT"
IC_SUPPORT_RELATIVE_ROOT = Path("data/ic-support")
EXPECTED_PROFILE_KINDS = (
    "programming",
    "memory_geometry",
    "package_hardware",
    "option",
    "security",
)
PROFILE_DIRECTORY_KIND = {
    "programming": "programming",
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
SOCKET_DESIGN_DIRNAME = "socket-design"


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


def _validate_package_hardware_profile(
    profile: "ResolvedProfile",
    *,
    icpn: str,
    expected_catalog: dict[str, Any],
) -> None:
    data = profile.data
    expected_package = str(expected_catalog["package"])
    expected_pin_count = int(expected_catalog["pin_count"])

    if profile.status != "pilot_socket_design_input_ready":
        _require(
            data.get("package") == expected_package,
            f"{icpn}: package hardware profile does not match catalog package",
        )
        _require(
            int(data.get("pin_count", -1)) == expected_pin_count,
            f"{icpn}: package hardware profile does not match catalog pin count",
        )
        return

    scope_icpn = profile.scope.get("exact_icpn")
    _require(
        scope_icpn == icpn,
        f"{icpn}: socket-design-input profile must be scoped to the exact ICPN",
    )
    _require(
        profile.scope.get("package") == expected_package
        and int(profile.scope.get("pin_count", -1)) == expected_pin_count,
        f"{icpn}: socket-design-input scope does not match catalog package identity",
    )

    package = data.get("package")
    _require(isinstance(package, dict), f"{icpn}: socket package data must be an object")
    _require(
        int(package.get("pin_count", -1)) == expected_pin_count,
        f"{icpn}: socket package pin count mismatch",
    )
    for field in ("type", "body_size_mm", "lead_span_mm", "lead_pitch_mm", "pin1_reference"):
        _require(package.get(field) not in (None, ""), f"{icpn}: socket package {field} is required")

    minimum = data.get("pin_level_minimum_programming_hardware")
    _require(isinstance(minimum, dict), f"{icpn}: minimum programming hardware is required")
    _require(
        minimum.get("status") == "socket_design_input_ready",
        f"{icpn}: minimum programming hardware must be socket_design_input_ready",
    )
    contacts = minimum.get("mandatory_contacts")
    _require(isinstance(contacts, list) and contacts, f"{icpn}: mandatory contacts are required")
    declared_count = minimum.get("mandatory_contact_count")
    _require(
        declared_count == len(contacts),
        f"{icpn}: mandatory contact count does not match contact list",
    )

    seen_pins: set[int] = set()
    seen_roles: set[str] = set()
    for index, contact in enumerate(contacts):
        _require(isinstance(contact, dict), f"{icpn}: mandatory contact {index} must be an object")
        package_pin = contact.get("package_pin")
        role = contact.get("role")
        _require(
            isinstance(package_pin, int) and 1 <= package_pin <= expected_pin_count,
            f"{icpn}: mandatory contact {index} has invalid package pin",
        )
        _require(package_pin not in seen_pins, f"{icpn}: duplicate mandatory package pin {package_pin}")
        _require(isinstance(role, str) and role, f"{icpn}: mandatory contact {package_pin} role is required")
        seen_pins.add(package_pin)
        seen_roles.add(role)

    _require(
        {"target_power", "target_ground", "analog_power_required", "analog_ground_required",
         "debug_data_bidirectional", "debug_clock_input", "recovery_reset_active_low"}.issubset(seen_roles),
        f"{icpn}: socket-design-input profile is missing a required programming contact role",
    )

    power = data.get("power_and_reset")
    _require(isinstance(power, dict), f"{icpn}: power/reset design rules are required")
    _require(
        power.get("all_main_power_and_ground_contacts_required") is True,
        f"{icpn}: all main power/ground contacts must be explicitly required",
    )
    _require(
        power.get("target_vdd_v") == {"min": 2.0, "max": 3.6},
        f"{icpn}: unexpected target VDD range in socket-design input",
    )

    boundaries = data.get("design_boundaries")
    _require(isinstance(boundaries, dict), f"{icpn}: design boundaries are required")
    _require(
        boundaries.get("socket_design_input_complete") is True
        and boundaries.get("socket_model_selected") is False
        and boundaries.get("site_electrical_compatibility") == "not_evaluated"
        and boundaries.get("socket_compatibility") == "not_evaluated"
        and boundaries.get("hardware_runtime_ready") is False
        and boundaries.get("physical_programming_qualified") is False
        and boundaries.get("hil_required_before_l3") is True,
        f"{icpn}: socket-design input must not claim physical hardware qualification",
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
    socket_design_input_profile: ResolvedProfile | None = None
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
    def package_hardware_profile(self) -> ResolvedProfile:
        return self.profile("package_hardware")

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
        payload["ic_support"] = {
            "binding_set_id": self.binding_set_id,
            "binding_status": self.binding_status,
            "profiles": {
                kind: self.profiles[kind].to_summary()
                for kind in EXPECTED_PROFILE_KINDS
            },
        }
        return payload

    def to_socket_design_input_payload(self) -> dict[str, Any]:
        """Return evidence-backed design input without claiming a verified Socket."""
        profile = self.socket_design_input_profile or self.package_hardware_profile
        data = profile.data
        if data.get("design_readiness") != "socket_design_input_ready":
            return {
                "schema_version": "1.0.0",
                "icpn": self.icpn,
                "status": "socket_design_input_not_ready",
                "package_hardware_profile": profile.to_summary(),
                "hardware_runtime_ready": False,
                "physical_programming_qualified": False,
            }

        return {
            "schema_version": "1.0.0",
            "icpn": self.icpn,
            "status": "socket_design_input_ready",
            "catalog_identity": {
                "base_device": self.expected_catalog["base_device"],
                "package": self.expected_catalog["package"],
                "pin_count": self.expected_catalog["pin_count"],
            },
            "package_hardware_profile": profile.to_summary(),
            "design_input": copy.deepcopy(data),
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }

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
            "hardware_design": {
                "package_hardware_profile_id": self.package_hardware_profile.profile_id,
                "socket_design_input_profile_id": (
                    self.socket_design_input_profile.profile_id
                    if self.socket_design_input_profile is not None
                    else None
                ),
                "socket_design_input_state": (
                    self.socket_design_input_profile.data.get("design_readiness", "not_ready")
                    if self.socket_design_input_profile is not None
                    else "not_ready"
                ),
                "hardware_runtime_ready": False,
                "physical_programming_qualified": False,
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

                _validate_package_hardware_profile(
                    selected["package_hardware"],
                    icpn=canonical_icpn,
                    expected_catalog=expected_catalog,
                )

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

        socket_root = resolved_root / SOCKET_DESIGN_DIRNAME
        if socket_root.exists():
            legacy_sources_payload = _load_object(resolved_root / "evidence" / "sources.json")
            legacy_sources = legacy_sources_payload.get("sources")
            _require(
                isinstance(legacy_sources, list) and legacy_sources,
                "IC Support source registry must contain sources",
            )
            known_source_ids = {
                str(item.get("source_id"))
                for item in legacy_sources
                if isinstance(item, dict) and isinstance(item.get("source_id"), str)
            }

            socket_sources_payload = _load_object(socket_root / "evidence" / "sources.json")
            _require(
                socket_sources_payload.get("schema_version") == "1.0.0"
                and socket_sources_payload.get("status") == "engineering_design_input",
                "Socket design source registry contract drift",
            )
            socket_sources = socket_sources_payload.get("sources")
            _require(
                isinstance(socket_sources, list) and socket_sources,
                "Socket design source registry must contain sources",
            )
            for index, source in enumerate(socket_sources):
                _require(
                    isinstance(source, dict)
                    and isinstance(source.get("source_id"), str)
                    and source["source_id"],
                    f"Socket design source[{index}] requires source_id",
                )
                _require(
                    source.get("authority") == "manufacturer_official",
                    f"Socket design source {source['source_id']} must be manufacturer-official",
                )
                source_id = str(source["source_id"])
                _require(
                    source_id not in known_source_ids,
                    f"duplicate Socket design source_id: {source_id}",
                )
                known_source_ids.add(source_id)

            socket_profiles: dict[str, ResolvedProfile] = {}
            socket_profiles_root = socket_root / "profiles"
            _require(socket_profiles_root.is_dir(), "Socket design profiles directory is required")
            for path in sorted(socket_profiles_root.glob("*.json")):
                profile = ResolvedProfile.from_payload(
                    _load_object(path),
                    path=path,
                    expected_kind="package_hardware",
                )
                _require(
                    profile.status == "pilot_socket_design_input_ready",
                    f"{profile.profile_id}: unexpected Socket design profile status",
                )
                _require(
                    profile.profile_id not in socket_profiles,
                    f"duplicate Socket design profile_id: {profile.profile_id}",
                )
                for index, evidence in enumerate(profile.evidence):
                    source_id = evidence.get("source_id")
                    _require(
                        source_id in known_source_ids,
                        f"{profile.profile_id}: evidence[{index}] references unknown source {source_id!r}",
                    )
                socket_profiles[profile.profile_id] = profile

            applied_socket_icpns: set[str] = set()
            socket_bindings_root = socket_root / "bindings"
            _require(socket_bindings_root.is_dir(), "Socket design bindings directory is required")
            for path in sorted(socket_bindings_root.glob("*.json")):
                payload = _load_object(path)
                _require(
                    payload.get("schema_version") == "1.0.0"
                    and payload.get("status") == "design_input_only",
                    f"{path}: Socket design binding-set contract drift",
                )
                bindings = payload.get("bindings")
                _require(
                    isinstance(bindings, list) and bindings,
                    f"{path}: Socket design bindings must be non-empty",
                )
                for index, binding in enumerate(bindings):
                    _require(
                        isinstance(binding, dict),
                        f"{path}: Socket design binding[{index}] must be an object",
                    )
                    icpn = binding.get("icpn")
                    profile_id = binding.get("profile_id")
                    _require(
                        isinstance(icpn, str) and icpn.strip(),
                        f"{path}: Socket design binding[{index}] requires exact ICPN",
                    )
                    canonical_icpn = icpn.strip()
                    key = canonical_icpn.casefold()
                    _require(
                        key in records,
                        f"{canonical_icpn}: Socket design overlay requires an existing exact IC Support binding",
                    )
                    _require(
                        canonical_icpn not in applied_socket_icpns,
                        f"duplicate Socket design overlay for exact ICPN: {canonical_icpn}",
                    )
                    _require(
                        isinstance(profile_id, str) and profile_id in socket_profiles,
                        f"{canonical_icpn}: dangling Socket design profile {profile_id!r}",
                    )
                    profile = socket_profiles[profile_id]
                    record = records[key]
                    _validate_package_hardware_profile(
                        profile,
                        icpn=canonical_icpn,
                        expected_catalog=record.expected_catalog,
                    )
                    records[key] = replace(record, socket_design_input_profile=profile)
                    applied_socket_icpns.add(canonical_icpn)

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
        return {
            "resolved_exact_icpns": self.size,
            "programming_profiles": len(programming_profiles),
            "programming_profile_ids": programming_profiles,
            "manufacturer_selected_profiles": sum(
                1 for record in self._records.values()
                if record.manufacturer_profile is not None
            ),
            "socket_design_input_ready_exact_icpns": sum(
                1 for record in self._records.values()
                if record.socket_design_input_profile is not None
                and record.socket_design_input_profile.data.get("design_readiness")
                == "socket_design_input_ready"
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
    parser.add_argument(
        "--socket-design-input",
        action="store_true",
        help="with --icpn, emit evidence-backed Socket design input rather than runtime summary",
    )
    args = parser.parse_args()
    resolver = get_default_ic_support_resolver()
    if args.icpn:
        resolved = resolver.resolve_exact(args.icpn)
        if resolved is None:
            payload: dict[str, Any] = {
                "icpn": args.icpn,
                "resolved": False,
                "runtime_ready": False,
            }
        elif args.socket_design_input:
            payload = resolved.to_socket_design_input_payload()
        else:
            payload = resolved.to_runtime_payload()
    else:
        _require(
            not args.socket_design_input,
            "--socket-design-input requires --icpn",
        )
        payload = resolver.summary()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ICSupportIntegrityError as exc:
        print(f"IC Support runtime resolver FAIL: {exc}")
        raise SystemExit(1)
