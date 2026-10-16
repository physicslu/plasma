from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .ic_support import default_ic_support_root


class ProgrammingHardwareIntegrityError(RuntimeError):
    """Programming Hardware evidence is ambiguous, malformed, or unsafe."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProgrammingHardwareIntegrityError(reason)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgrammingHardwareIntegrityError(
            f"cannot read Programming Hardware profile: {path}"
        ) from exc
    _require(isinstance(value, dict), f"{path}: top-level JSON must be an object")
    return value


@dataclass(frozen=True, slots=True)
class ProgrammingHardwareProfile:
    profile_id: str
    manufacturer: str
    icpn: str
    base_device: str
    package: str
    pin_count: int
    programming_interface: str
    status: str
    data: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    source_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "manufacturer": self.manufacturer,
            "icpn": self.icpn,
            "base_device": self.base_device,
            "package": self.package,
            "pin_count": self.pin_count,
            "programming_interface": self.programming_interface,
            "status": self.status,
            "data": copy.deepcopy(self.data),
            "evidence": [copy.deepcopy(item) for item in self.evidence],
            "source_path": self.source_path,
            "execution_authorized": False,
            "catalog_level_authority": False,
        }


class ProgrammingHardwareRegistry:
    """Read-only exact-ICPN hardware design-input registry.

    This registry is deliberately independent from ProgrammingQualificationRegistry.
    It never promotes Catalog Levels and never authorizes physical execution.
    """

    def __init__(self, records: dict[str, ProgrammingHardwareProfile]) -> None:
        self._records = dict(records)

    @classmethod
    def from_root(cls, root: Path) -> "ProgrammingHardwareRegistry":
        resolved_root = root.resolve()
        directory = resolved_root / "profiles" / "package-hardware"
        _require(directory.is_dir(), f"package-hardware profile directory not found: {directory}")

        records: dict[str, ProgrammingHardwareProfile] = {}
        for path in sorted(directory.glob("*.json")):
            payload = _load_object(path)
            data = payload.get("data")
            if not isinstance(data, dict):
                continue
            if data.get("design_input_state") != "socket_schematic_ready_not_physically_qualified":
                continue

            profile_id = payload.get("profile_id")
            scope = payload.get("scope")
            evidence = payload.get("evidence")
            status = payload.get("status")
            _require(isinstance(profile_id, str) and profile_id, f"{path}: profile_id is required")
            _require(payload.get("kind") == "package_hardware", f"{profile_id}: package_hardware kind is required")
            _require(isinstance(status, str) and status.startswith("pilot"), f"{profile_id}: pilot status is required")
            _require(isinstance(scope, dict), f"{profile_id}: scope object is required")
            _require(isinstance(evidence, list) and evidence, f"{profile_id}: evidence is required")

            manufacturer = scope.get("manufacturer")
            icpn = scope.get("icpn")
            base_device = scope.get("base_device")
            package = scope.get("package")
            pin_count = scope.get("pin_count")
            interface = scope.get("programming_interface")
            _require(isinstance(manufacturer, str) and manufacturer, f"{profile_id}: manufacturer is required")
            _require(isinstance(icpn, str) and icpn, f"{profile_id}: exact ICPN is required")
            _require(isinstance(base_device, str) and base_device, f"{profile_id}: base_device is required")
            _require(isinstance(package, str) and package, f"{profile_id}: package is required")
            _require(isinstance(pin_count, int) and pin_count > 0, f"{profile_id}: positive pin_count is required")
            _require(isinstance(interface, str) and interface, f"{profile_id}: programming_interface is required")

            physical = data.get("physical_validation")
            _require(isinstance(physical, dict), f"{profile_id}: physical_validation is required")
            for field in (
                "fixture_qualified",
                "hardware_runtime_ready",
                "physical_programming_qualified",
                "hil_pass",
            ):
                _require(
                    physical.get(field) is False,
                    f"{profile_id}: design input must keep {field}=false",
                )

            key = icpn.casefold()
            _require(key not in records, f"duplicate Programming Hardware profile for exact ICPN: {icpn}")
            records[key] = ProgrammingHardwareProfile(
                profile_id=profile_id,
                manufacturer=manufacturer,
                icpn=icpn,
                base_device=base_device,
                package=package,
                pin_count=pin_count,
                programming_interface=interface,
                status=status,
                data=copy.deepcopy(data),
                evidence=tuple(copy.deepcopy(item) for item in evidence),
                source_path=str(path.relative_to(resolved_root)),
            )

        return cls(records)

    @property
    def size(self) -> int:
        return len(self._records)

    @property
    def exact_icpns(self) -> tuple[str, ...]:
        return tuple(sorted((record.icpn for record in self._records.values()), key=str.casefold))

    def resolve_exact(self, icpn: str) -> ProgrammingHardwareProfile | None:
        if not isinstance(icpn, str) or not icpn.strip():
            return None
        return self._records.get(icpn.strip().casefold())

    def require_exact(self, icpn: str) -> ProgrammingHardwareProfile:
        record = self.resolve_exact(icpn)
        if record is None:
            raise KeyError(f"no Programming Hardware design input for exact ICPN: {icpn}")
        return record

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "design_input_exact_icpns": self.size,
            "exact_icpns": list(self.exact_icpns),
            "execution_authorized_by_registry": False,
            "catalog_level_authority": False,
        }


@lru_cache(maxsize=1)
def get_default_programming_hardware_registry() -> ProgrammingHardwareRegistry:
    return ProgrammingHardwareRegistry.from_root(default_ic_support_root())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect exact-ICPN Programming Hardware design input")
    parser.add_argument("--icpn", help="resolve one exact ICPN")
    args = parser.parse_args(argv)
    registry = get_default_programming_hardware_registry()
    if args.icpn:
        profile = registry.resolve_exact(args.icpn)
        payload = profile.to_dict() if profile is not None else {
            "icpn": args.icpn,
            "design_input_available": False,
            "execution_authorized": False,
            "catalog_level_authority": False,
        }
    else:
        payload = registry.summary()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
