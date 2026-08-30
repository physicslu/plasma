from __future__ import annotations

import argparse
import copy
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


class ICSupportIntegrityError(RuntimeError):
    """Checked-in IC Support data is incomplete, contradictory, or malformed."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_ic_support_root() -> Path:
    configured = os.environ.get(IC_SUPPORT_ROOT_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (_repository_root() / IC_SUPPORT_RELATIVE_ROOT).resolve()


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
class ResolvedICSupport:
    icpn: str
    binding_set_id: str
    binding_status: str
    expected_catalog: dict[str, Any]
    profiles: dict[str, ResolvedProfile]
    revision_overrides: tuple[dict[str, Any], ...]

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

                records[key] = ResolvedICSupport(
                    icpn=canonical_icpn,
                    binding_set_id=binding_set_id,
                    binding_status=binding_status,
                    expected_catalog=copy.deepcopy(expected_catalog),
                    profiles=selected,
                    revision_overrides=tuple(normalized_overrides),
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
        return {
            "resolved_exact_icpns": self.size,
            "programming_profiles": len(programming_profiles),
            "programming_profile_ids": programming_profiles,
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
