from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .ic_support import ICSupportIntegrityError, default_ic_support_root


# Compatibility path for the original STM32F1 profile. New production lookup uses
# DEVICE_BASIC_GLOB and the registry below.
DEVICE_BASIC_RELATIVE_PATH = Path("device-basic/stm32f1-device-basic-v1.json")
DEVICE_BASIC_GLOB = "*-device-basic-v1.json"

_REQUIRED_FIELDS = (
    "icpn",
    "base_device",
    "package",
    "pin_count",
    "flash",
    "ram",
    "operating_vdd",
    "io_supply",
    "vdda",
    "operating_temperature",
)
_CATALOG_OWNED_FIELDS = (
    "icpn",
    "base_device",
    "package",
    "pin_count",
    "flash",
    "operating_temperature",
)
_PROFILE_OWNED_FIELDS = ("ram", "operating_vdd")
_NULLABLE_UNENRICHED_FIELDS = ("io_supply", "vdda")
_TEMPERATURE_RE = re.compile(r"^(-?\d+)\s+to\s+(-?\d+)\s+C$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ICSupportIntegrityError(message)


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ICSupportIntegrityError(
            f"cannot read Manufacturer Device Basic Profile: {path}"
        ) from exc
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
    io_supply_v: dict[str, float] | None
    vdda_v: dict[str, float] | None
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
            # Fixed IC Information contract: these keys are always present.
            # null means no direct Product Selector/eStore evidence was admitted.
            "io_supply_v": copy.deepcopy(self.io_supply_v),
            "vdda_v": copy.deepcopy(self.vdda_v),
            "operating_temperature_c": copy.deepcopy(self.operating_temperature_c),
            "evidence": copy.deepcopy(self.evidence),
            "programming_profile_authority": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }


class ManufacturerDeviceBasicResolver:
    def __init__(
        self,
        *,
        profile_id: str,
        manufacturer: str,
        family: str,
        groups: dict[str, dict[str, Any]],
        bindings: dict[str, str],
        path: Path,
    ) -> None:
        self.profile_id = profile_id
        self.manufacturer = manufacturer
        self.family = family
        self._groups = copy.deepcopy(groups)
        self._bindings = {
            key.casefold(): (key, value) for key, value in bindings.items()
        }
        self.path = path

    @property
    def size(self) -> int:
        return len(self._bindings)

    @property
    def bound_icpns(self) -> tuple[str, ...]:
        return tuple(sorted(original for original, _group in self._bindings.values()))

    @classmethod
    def from_file(cls, path: Path) -> "ManufacturerDeviceBasicResolver":
        payload = _load(path)
        _require(
            payload.get("schema_version") == "1.0.0",
            "device basic profile: unsupported schema_version",
        )
        profile_id = payload.get("profile_id")
        _require(
            isinstance(profile_id, str)
            and profile_id
            and profile_id.endswith("-device-basic-v1"),
            "device basic profile: unexpected profile_id",
        )
        _require(
            payload.get("status") == "manufacturer_device_basic_available",
            "device basic profile: unexpected status",
        )
        manufacturer = payload.get("manufacturer")
        family = payload.get("family")
        _require(
            manufacturer == "STMicroelectronics",
            "device basic profile: manufacturer drift",
        )
        _require(
            isinstance(family, str) and family.startswith("STM32"),
            "device basic profile: family drift",
        )
        _require(
            tuple(payload.get("fields", [])) == _REQUIRED_FIELDS,
            "device basic profile: field contract drift",
        )

        source_policy = payload.get("source_policy")
        _require(
            isinstance(source_policy, dict),
            "device basic profile: source_policy is required",
        )
        _require(
            source_policy.get("allowed_authority") == "STMicroelectronics official",
            "device basic profile: ST official authority is required",
        )
        allowed_surfaces = source_policy.get("allowed_surfaces")
        _require(
            isinstance(allowed_surfaces, list)
            and set(allowed_surfaces) == {"st_product_selector", "st_estore"},
            "device basic profile: source surface contract drift",
        )
        prohibited = set(source_policy.get("prohibited_derivation_sources", []))
        _require(
            {"OpenOCD", "family_name_inference", "programming_guide", "datasheet"}
            <= prohibited,
            "device basic profile: prohibited derivation boundary drift",
        )

        composition = payload.get("composition")
        _require(
            isinstance(composition, dict),
            "device basic profile: composition contract is required",
        )
        _require(
            tuple(composition.get("catalog_owned_fields", []))
            == _CATALOG_OWNED_FIELDS,
            "device basic profile: catalog-owned field contract drift",
        )
        _require(
            tuple(composition.get("profile_owned_fields", []))
            == _PROFILE_OWNED_FIELDS,
            "device basic profile: profile-owned field contract drift",
        )
        _require(
            tuple(composition.get("nullable_unenriched_fields", []))
            == _NULLABLE_UNENRICHED_FIELDS,
            "device basic profile: nullable field contract drift",
        )

        groups = payload.get("groups")
        bindings = payload.get("bindings")
        _require(
            isinstance(groups, dict) and groups,
            "device basic profile: groups are required",
        )
        _require(
            isinstance(bindings, dict) and bindings,
            "device basic profile: bindings are required",
        )

        validated_groups: dict[str, dict[str, Any]] = {}
        for group_id, group in groups.items():
            _require(
                isinstance(group_id, str) and group_id,
                "device basic profile: invalid group_id",
            )
            _require(isinstance(group, dict), f"{group_id}: group must be an object")
            series = group.get("series")
            flash_size = group.get("flash_size")
            ram_size = group.get("ram_size")
            vdd = group.get("operating_vdd_v")
            evidence = group.get("evidence")
            _require(
                isinstance(series, str) and series.startswith(family),
                f"{group_id}: invalid series",
            )
            _require(
                isinstance(flash_size, str) and flash_size.endswith(" KiB"),
                f"{group_id}: invalid Flash size",
            )
            _require(
                isinstance(ram_size, str) and ram_size.endswith(" KiB"),
                f"{group_id}: invalid RAM size",
            )
            _require(
                isinstance(vdd, dict)
                and isinstance(vdd.get("min"), (int, float))
                and isinstance(vdd.get("max"), (int, float))
                and float(vdd["min"]) < float(vdd["max"]),
                f"{group_id}: invalid operating VDD",
            )
            _require(isinstance(evidence, dict), f"{group_id}: evidence is required")
            _require(
                evidence.get("authority") == "STMicroelectronics official",
                f"{group_id}: non-ST authority",
            )
            surface = evidence.get("source_surface")
            _require(
                surface in {"st_product_selector", "st_estore"},
                f"{group_id}: unsupported source surface",
            )
            url = evidence.get("selector_url")
            if surface == "st_product_selector":
                _require(
                    isinstance(url, str)
                    and url.startswith("https://www.st.com/")
                    and "/products.html" in url,
                    f"{group_id}: selector_url must be an official ST Product Selector URL",
                )
                _require(
                    evidence.get("evidence_strength")
                    == "official_product_selector_observation",
                    f"{group_id}: evidence strength drift",
                )
            else:
                _require(
                    isinstance(url, str) and url.startswith("https://estore.st.com/"),
                    f"{group_id}: selector_url must be an official ST eStore URL",
                )
                _require(
                    evidence.get("evidence_strength") == "official_estore_observation",
                    f"{group_id}: evidence strength drift",
                )
            _require(
                evidence.get("content_lock") is None,
                f"{group_id}: v1 observation must not fake a content lock",
            )
            validated_groups[group_id] = copy.deepcopy(group)

        validated_bindings: dict[str, str] = {}
        for icpn, group_id in bindings.items():
            _require(
                isinstance(icpn, str) and icpn,
                "device basic binding exact ICPN required",
            )
            _require(
                isinstance(group_id, str) and group_id in validated_groups,
                f"{icpn}: dangling group_id",
            )
            key = icpn.casefold()
            _require(
                key not in {item.casefold() for item in validated_bindings},
                f"duplicate device basic binding: {icpn}",
            )
            validated_bindings[icpn] = group_id

        binding_count = payload.get("binding_count")
        _require(
            isinstance(binding_count, int) and binding_count > 0,
            "device basic profile: binding_count is required",
        )
        _require(
            len(validated_bindings) == binding_count,
            f"{profile_id} must bind {binding_count} exact ICPNs, got {len(validated_bindings)}",
        )
        return cls(
            profile_id=profile_id,
            manufacturer=manufacturer,
            family=family,
            groups=validated_groups,
            bindings=validated_bindings,
            path=path,
        )

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
        binding = self._bindings.get(icpn.strip().casefold())
        if binding is None:
            return None
        owner = icpn.strip()
        _original_icpn, group_id = binding
        group = self._groups[group_id]
        _require(
            manufacturer == self.manufacturer,
            f"{owner}: Production Catalog manufacturer drift",
        )
        _require(family == self.family, f"{owner}: Production Catalog family drift")
        _require(
            series == group["series"],
            f"{owner}: Production Catalog series drift",
        )
        _require(
            flash_size == group["flash_size"],
            f"{owner}: Production Catalog Flash drift",
        )
        for label, value in (
            ("base_device", base_device),
            ("package", package),
            ("pin_count", pin_count),
            ("temperature_grade", temperature_grade),
        ):
            _require(
                isinstance(value, str) and value,
                f"{owner}: Production Catalog {label} missing",
            )
        assert series is not None
        assert base_device is not None
        assert package is not None
        assert pin_count is not None
        assert flash_size is not None
        assert temperature_grade is not None
        return ResolvedDeviceBasicProfile(
            profile_id=self.profile_id,
            icpn=owner,
            manufacturer=self.manufacturer,
            family=self.family,
            series=series,
            base_device=base_device,
            package=package,
            pin_count=pin_count,
            flash_size=flash_size,
            ram_size=str(group["ram_size"]),
            operating_vdd_v={
                "min": float(group["operating_vdd_v"]["min"]),
                "max": float(group["operating_vdd_v"]["max"]),
            },
            io_supply_v=None,
            vdda_v=None,
            operating_temperature_c=_temperature_range(temperature_grade, owner),
            evidence=copy.deepcopy(group["evidence"]),
        )


class ManufacturerDeviceBasicRegistry:
    def __init__(self, resolvers: list[ManufacturerDeviceBasicResolver]) -> None:
        _require(bool(resolvers), "device basic registry: at least one profile is required")
        self._resolvers = tuple(resolvers)
        self._by_icpn: dict[str, ManufacturerDeviceBasicResolver] = {}
        seen_profiles: set[str] = set()
        seen_families: set[tuple[str, str]] = set()
        for resolver in resolvers:
            _require(
                resolver.profile_id not in seen_profiles,
                f"duplicate device basic profile_id: {resolver.profile_id}",
            )
            seen_profiles.add(resolver.profile_id)
            family_key = (resolver.manufacturer, resolver.family)
            _require(
                family_key not in seen_families,
                f"duplicate device basic family profile: {resolver.family}",
            )
            seen_families.add(family_key)
            for icpn in resolver.bound_icpns:
                key = icpn.casefold()
                _require(
                    key not in self._by_icpn,
                    f"duplicate device basic exact ICPN across profiles: {icpn}",
                )
                self._by_icpn[key] = resolver

    @property
    def size(self) -> int:
        return len(self._by_icpn)

    @property
    def profile_ids(self) -> tuple[str, ...]:
        return tuple(sorted(resolver.profile_id for resolver in self._resolvers))

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
        resolver = self._by_icpn.get(icpn.strip().casefold())
        if resolver is None:
            return None
        return resolver.resolve_exact(
            icpn,
            manufacturer=manufacturer,
            family=family,
            series=series,
            base_device=base_device,
            package=package,
            pin_count=pin_count,
            flash_size=flash_size,
            temperature_grade=temperature_grade,
        )


@lru_cache(maxsize=16)
def _resolver_for_path(path: str) -> ManufacturerDeviceBasicResolver:
    return ManufacturerDeviceBasicResolver.from_file(Path(path))


@lru_cache(maxsize=4)
def _registry_for_root(root: str) -> ManufacturerDeviceBasicRegistry:
    basic_root = Path(root) / "device-basic"
    paths = sorted(basic_root.glob(DEVICE_BASIC_GLOB))
    _require(bool(paths), f"device basic registry: no profiles under {basic_root}")
    return ManufacturerDeviceBasicRegistry(
        [_resolver_for_path(str(path)) for path in paths]
    )


def get_default_manufacturer_device_basic_resolver() -> ManufacturerDeviceBasicRegistry:
    return _registry_for_root(str(default_ic_support_root()))
