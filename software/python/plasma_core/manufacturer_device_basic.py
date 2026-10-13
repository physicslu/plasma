from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .ic_support import ICSupportIntegrityError, default_ic_support_root


DEVICE_BASIC_RELATIVE_PATH = Path("device-basic/stm32f1-device-basic-v1.json")
_REQUIRED_FIELDS = (
    "icpn",
    "base_device",
    "package",
    "pin_count",
    "flash",
    "ram",
    "operating_vdd",
    "operating_temperature",
)
_TEMPERATURE_RE = re.compile(r"^(-?\d+)\s+to\s+(-?\d+)\s+C$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ICSupportIntegrityError(message)


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ICSupportIntegrityError(f"cannot read Manufacturer Device Basic Profile: {path}") from exc
    _require(isinstance(payload, dict), f"{path}: top-level JSON must be an object")
    return payload


def _temperature_range(value: str, owner: str) -> dict[str, int]:
    match = _TEMPERATURE_RE.fullmatch(value.strip())
    _require(match is not None, f"{owner}: unsupported operating temperature {value!r}")
    low, high = int(match.group(1)), int(match.group(2))
    _require(low < high, f"{owner}: invalid operating temperature range")
    return {"min": low, "max": high}


@dataclass(frozen=True, slots=True)
class ResolvedDeviceBasicProfile:
    profile_id: str
    icpn: str
    manufacturer: str
    family: str
    series: str
    base_device: str
    package: str
    pin_count: str
    flash_size: str
    ram_size: str
    operating_vdd_v: dict[str, float]
    operating_temperature_c: dict[str, int]
    evidence: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "status": "manufacturer_device_basic_available",
            "profile_id": self.profile_id,
            "icpn": self.icpn,
            "manufacturer": self.manufacturer,
            "family": self.family,
            "series": self.series,
            "base_device": self.base_device,
            "package": self.package,
            "pin_count": self.pin_count,
            "flash_size": self.flash_size,
            "ram_size": self.ram_size,
            "operating_vdd_v": copy.deepcopy(self.operating_vdd_v),
            "operating_temperature_c": copy.deepcopy(self.operating_temperature_c),
            "evidence": copy.deepcopy(self.evidence),
            "programming_profile_authority": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }


class ManufacturerDeviceBasicResolver:
    def __init__(self, records: dict[str, ResolvedDeviceBasicProfile], *, path: Path) -> None:
        self._records = dict(records)
        self.path = path

    @property
    def size(self) -> int:
        return len(self._records)

    @classmethod
    def from_file(cls, path: Path) -> "ManufacturerDeviceBasicResolver":
        payload = _load(path)
        _require(payload.get("schema_version") == "1.0.0", "device basic profile: unsupported schema_version")
        _require(payload.get("profile_id") == "stm32f1-device-basic-v1", "device basic profile: unexpected profile_id")
        _require(
            payload.get("status") == "manufacturer_device_basic_available",
            "device basic profile: unexpected status",
        )
        _require(payload.get("manufacturer") == "STMicroelectronics", "device basic profile: manufacturer drift")
        _require(payload.get("family") == "STM32F1", "device basic profile: family drift")
        _require(tuple(payload.get("fields", [])) == _REQUIRED_FIELDS, "device basic profile: field contract drift")

        source_policy = payload.get("source_policy")
        _require(isinstance(source_policy, dict), "device basic profile: source_policy is required")
        _require(
            source_policy.get("allowed_authority") == "STMicroelectronics official",
            "device basic profile: ST official authority is required",
        )
        allowed_surfaces = source_policy.get("allowed_surfaces")
        _require(
            isinstance(allowed_surfaces, list)
            and set(allowed_surfaces) == {"st_product_selector", "st_product_page", "st_estore"},
            "device basic profile: source surface contract drift",
        )
        prohibited = set(source_policy.get("prohibited_derivation_sources", []))
        _require(
            {"OpenOCD", "family_name_inference", "programming_guide"} <= prohibited,
            "device basic profile: prohibited derivation boundary drift",
        )

        groups = payload.get("groups")
        bindings = payload.get("bindings")
        _require(isinstance(groups, dict) and groups, "device basic profile: groups are required")
        _require(isinstance(bindings, list) and bindings, "device basic profile: bindings are required")

        validated_groups: dict[str, dict[str, Any]] = {}
        for group_id, group in groups.items():
            _require(isinstance(group_id, str) and group_id, "device basic profile: invalid group_id")
            _require(isinstance(group, dict), f"{group_id}: group must be an object")
            series = group.get("series")
            flash_size = group.get("flash_size")
            ram_size = group.get("ram_size")
            vdd = group.get("operating_vdd_v")
            evidence = group.get("evidence")
            _require(isinstance(series, str) and series.startswith("STM32F1"), f"{group_id}: invalid series")
            _require(isinstance(flash_size, str) and flash_size.endswith(" KiB"), f"{group_id}: invalid Flash size")
            _require(isinstance(ram_size, str) and ram_size.endswith(" KiB"), f"{group_id}: invalid RAM size")
            _require(
                isinstance(vdd, dict)
                and isinstance(vdd.get("min"), (int, float))
                and isinstance(vdd.get("max"), (int, float))
                and float(vdd["min"]) < float(vdd["max"]),
                f"{group_id}: invalid operating VDD",
            )
            _require(isinstance(evidence, dict), f"{group_id}: evidence is required")
            _require(evidence.get("authority") == "STMicroelectronics official", f"{group_id}: non-ST authority")
            _require(
                evidence.get("source_surface") == "st_product_selector_or_product_page",
                f"{group_id}: unsupported source surface",
            )
            for url_key in ("series_selector_url", "representative_product_url"):
                url = evidence.get(url_key)
                _require(
                    isinstance(url, str) and url.startswith("https://www.st.com/"),
                    f"{group_id}: {url_key} must be an official ST URL",
                )
            _require(
                evidence.get("evidence_strength") == "official_product_metadata_observation",
                f"{group_id}: evidence strength drift",
            )
            _require(evidence.get("content_lock") is None, f"{group_id}: v1 observation must not fake a content lock")
            validated_groups[group_id] = copy.deepcopy(group)

        profile_id = str(payload["profile_id"])
        manufacturer = str(payload["manufacturer"])
        family = str(payload["family"])
        records: dict[str, ResolvedDeviceBasicProfile] = {}
        for index, binding in enumerate(bindings):
            _require(isinstance(binding, dict), f"bindings[{index}]: object required")
            icpn = binding.get("icpn")
            group_id = binding.get("group_id")
            expected = binding.get("expected_catalog")
            _require(isinstance(icpn, str) and icpn, f"bindings[{index}]: exact ICPN required")
            _require(isinstance(group_id, str) and group_id in validated_groups, f"{icpn}: dangling group_id")
            _require(isinstance(expected, dict), f"{icpn}: expected_catalog is required")
            _require(expected.get("manufacturer") == manufacturer, f"{icpn}: manufacturer mismatch")
            _require(expected.get("family") == family, f"{icpn}: family mismatch")
            group = validated_groups[group_id]
            _require(expected.get("series") == group["series"], f"{icpn}: series/group mismatch")
            _require(expected.get("flash_size") == group["flash_size"], f"{icpn}: Flash/group mismatch")
            for key in ("base_device", "package", "pin_count", "operating_temperature"):
                _require(isinstance(expected.get(key), str) and expected[key], f"{icpn}: expected_catalog.{key} required")
            key = icpn.casefold()
            _require(key not in records, f"duplicate device basic binding: {icpn}")
            records[key] = ResolvedDeviceBasicProfile(
                profile_id=profile_id,
                icpn=icpn,
                manufacturer=manufacturer,
                family=family,
                series=str(expected["series"]),
                base_device=str(expected["base_device"]),
                package=str(expected["package"]),
                pin_count=str(expected["pin_count"]),
                flash_size=str(expected["flash_size"]),
                ram_size=str(group["ram_size"]),
                operating_vdd_v={"min": float(group["operating_vdd_v"]["min"]), "max": float(group["operating_vdd_v"]["max"])},
                operating_temperature_c=_temperature_range(str(expected["operating_temperature"]), icpn),
                evidence=copy.deepcopy(group["evidence"]),
            )
        _require(len(records) == 280, f"STM32F1 Device Basic Profile must bind 280 exact ICPNs, got {len(records)}")
        return cls(records, path=path)

    def resolve_exact(
        self,
        icpn: str,
        *,
        manufacturer: str,
        family: str,
        series: str | None,
        base_device: str | None,
        package: str | None,
        pin_count: str | None,
        flash_size: str | None,
        temperature_grade: str | None,
    ) -> ResolvedDeviceBasicProfile | None:
        if not isinstance(icpn, str) or not icpn.strip():
            return None
        resolved = self._records.get(icpn.strip().casefold())
        if resolved is None:
            return None
        observed = {
            "manufacturer": manufacturer,
            "family": family,
            "series": series,
            "base_device": base_device,
            "package": package,
            "pin_count": pin_count,
            "flash_size": flash_size,
            "temperature_grade": temperature_grade,
        }
        expected = {
            "manufacturer": resolved.manufacturer,
            "family": resolved.family,
            "series": resolved.series,
            "base_device": resolved.base_device,
            "package": resolved.package,
            "pin_count": resolved.pin_count,
            "flash_size": resolved.flash_size,
            "temperature_grade": f"{resolved.operating_temperature_c['min']} to {resolved.operating_temperature_c['max']} C",
        }
        for field, expected_value in expected.items():
            _require(
                str(observed[field]) == str(expected_value),
                f"{resolved.icpn}: Production Catalog {field} drift: expected {expected_value!r}, got {observed[field]!r}",
            )
        return resolved


@lru_cache(maxsize=4)
def _resolver_for_path(path: str) -> ManufacturerDeviceBasicResolver:
    return ManufacturerDeviceBasicResolver.from_file(Path(path))


def get_default_manufacturer_device_basic_resolver() -> ManufacturerDeviceBasicResolver:
    return _resolver_for_path(str(default_ic_support_root() / DEVICE_BASIC_RELATIVE_PATH))
