"""Vendor-neutral Programming Qualification registry.

Provider-specific evidence loaders validate source, version, driver, geometry and
operation evidence. This registry derives Catalog Level 0/1/2/3 without exposing
legacy phase-prefixed fields. Catalog Level never grants Job/Batch execution authority.
"""
from __future__ import annotations

from copy import deepcopy
from functools import cached_property, lru_cache
from typing import Any, Protocol

from .backend_candidate_registry import BackendCandidateRegistry, get_default_backend_candidate_registry
from .device_catalog import (
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    DeviceCatalogRecord,
    get_default_device_catalog,
)
from .openocd_software_qualification import get_default_openocd_software_qualification_registry
from .nxp_kl25_qualification import get_default_nxp_kl25_qualification_provider
from .microchip_saml1x_route_evidence import admitted_saml1x_official_programming_routes
from .microchip_pic32mx_route_evidence import admitted_pic32mx_openocd_devid_routes
from .nxp_mcxa_route_evidence import admitted_nxp_mcxa_official_programming_routes
from .physical_compatibility import (
    PhysicalCompatibilityRegistry,
    get_default_physical_compatibility_registry,
)
from .family_ready import FamilyReadyRegistry, get_default_family_ready_registry


IDENTIFIED = "IDENTIFIED"
CATALOG_LEVEL_DISCOVERED = "DISCOVERED"
CATALOG_LEVEL_CANDIDATE = "PROGRAMMING_CANDIDATE"
CATALOG_LEVEL_PROGRAMMABLE = "PROGRAMMABLE"
CATALOG_LEVEL_VERIFIED = "PLASMA_VERIFIED"
PROGRAMMING_STATES = frozenset({"UNKNOWN", "CANDIDATE", "BLOCKED", "SUPPORTED", "UNSUPPORTED"})


class CandidateRouteEvidenceProvider(Protocol):
    """Read-only source-backed research candidate; never an executable backend."""

    def lookup(self, record: DeviceCatalogRecord) -> dict[str, Any] | None: ...


class ProgrammingQualificationProvider(Protocol):
    @property
    def reviewed_exact_keys(self) -> tuple[tuple[str, str], ...]: ...

    def lookup(self, manufacturer: str, exact_icpn: str) -> dict[str, Any] | None: ...

    def describe(self, manufacturer: str, exact_icpn: str) -> dict[str, Any]: ...


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DeviceCatalogIntegrityError(f"Programming qualification: {reason}")


class ProgrammingQualificationRegistry:
    """Canonical Programming Qualification projection over evidence providers."""

    def __init__(
        self,
        catalog: DeviceCatalog,
        providers: tuple[ProgrammingQualificationProvider, ...],
        *,
        candidate_registry: CandidateRouteEvidenceProvider | None = None,
        candidate_registries: tuple[CandidateRouteEvidenceProvider, ...] = (),
        physical_compatibility: PhysicalCompatibilityRegistry | None = None,
        family_ready: FamilyReadyRegistry | None = None,
    ) -> None:
        self._catalog = catalog
        self._providers = providers
        self._physical_compatibility = physical_compatibility or PhysicalCompatibilityRegistry([])
        self._family_ready = family_ready or FamilyReadyRegistry([])
        # Preserve the existing ST input while allowing independently reviewed
        # manufacturer-neutral adapters. Never silently select among conflicts.
        self._candidate_registries = (
            ((candidate_registry,) if candidate_registry is not None else ())
            + tuple(candidate_registries)
        )
        self._record_by_key = {
            (row.vendor.casefold(), row.identifier.casefold()): row
            for row in catalog.records
        }
        self._identity_by_key = {
            key: row
            for key, row in self._record_by_key.items()
            if row.identity_state == IDENTIFIED
        }

        seen: set[tuple[str, str]] = set()
        for provider in providers:
            for key in provider.reviewed_exact_keys:
                _require(key not in seen, f"multiple providers claim the same reviewed exact ICPN: {key}")
                seen.add(key)
                normalized_key = (key[0].strip().casefold(), key[1].strip().casefold())
                row = self._record_by_key.get(normalized_key)
                _require(row is not None, f"reviewed exact ICPN missing from canonical identity store: {key}")
                _require(
                    row.identity_state == IDENTIFIED,
                    f"Programming Qualification lacks IDENTIFIED exact ICPN prerequisite: {key}",
                )
        for physical_key in self._physical_compatibility.exact_keys:
            row = self._identity_by_key.get(physical_key)
            _require(row is not None, f"L3 configuration lacks admitted exact ICPN: {physical_key}")
            matching = [
                provider for provider in providers
                if provider.lookup(row.vendor, row.identifier) is not None
            ]
            _require(len(matching) == 1
                     and matching[0].describe(row.vendor, row.identifier).get("software_state") == "SUPPORTED",
                     f"L3 configuration requires SUPPORTED L2 provider: {physical_key}")
        for anchor_id, anchor in self._family_ready.anchors.items():
            matching = [
                (key, configuration)
                for key in self._physical_compatibility.exact_keys
                for configuration in self._physical_compatibility.verified_for(*key)
                if configuration["configuration_id"] == anchor_id
                and configuration["verification_type"] == "PPU_SITE"
            ]
            _require(len(matching) == 1, f"Family Ready anchor lacks a unique direct PPU HIL PASS: {anchor_id}")
            key, configuration = matching[0]
            provider = anchor["provider"]
            _require(configuration["identity"]["manufacturer"] == anchor["manufacturer"]
                     and configuration["identity"]["icpn"].startswith(anchor["series"])
                     and configuration["engine"]["provider_id"] == provider["provider_id"]
                     and configuration["engine"]["provider_version"] == provider["version"]
                     and configuration["engine"]["target_config"] == provider["target_config"].removeprefix("tcl/"),
                     f"Family Ready anchor/provider/series mismatch: {anchor_id}")
        for family_key in self._family_ready.exact_keys:
            row = self._identity_by_key.get(family_key)
            _require(row is not None, f"Family Ready lacks admitted exact ICPN: {family_key}")
            matching = [
                provider for provider in providers
                if provider.lookup(row.vendor, row.identifier) is not None
            ]
            _require(len(matching) == 1, f"Family Ready requires one reviewed L2 Provider: {family_key}")
            raw = matching[0].describe(row.vendor, row.identifier)
            derived = self._family_ready.for_exact(row.vendor, row.identifier)
            assert derived is not None
            program = raw.get("programming") or {}
            flash = program.get("flash_geometry") or {}
            authority = derived["provider"]
            _require(raw.get("software_state") == "SUPPORTED"
                     and all((raw.get("provider") or {}).get(field) == authority[field]
                             for field in ("provider_id", "target_config", "flash_driver"))
                     and (raw.get("provider") or {}).get("version") == authority["version"]
                     and program.get("programming_profile_id") == derived["programming_profile_id"]
                     and flash.get("erase_unit_bytes") == derived["erase_unit_bytes"]
                     and not self._physical_compatibility.verified_for(row.vendor, row.identifier),
                     f"Family Ready requires matching SUPPORTED L2 profile and no fake/duplicate direct HIL: {family_key}")

    def _candidate_for(self, row: DeviceCatalogRecord) -> dict[str, Any] | None:
        candidates = [provider.lookup(row) for provider in self._candidate_registries]
        matching = [candidate for candidate in candidates if candidate is not None]
        _require(
            len(matching) <= 1,
            f"multiple candidate routes for {row.vendor}/{row.identifier}; review required",
        )
        return matching[0] if matching else None

    def _identity_record(self, manufacturer: str, exact_icpn: str):
        if not isinstance(manufacturer, str) or not isinstance(exact_icpn, str):
            return None
        return self._identity_by_key.get((manufacturer.strip().casefold(), exact_icpn.strip().casefold()))

    @staticmethod
    def _unknown(identity_state: str, *, has_programming_route: bool = False) -> dict[str, Any]:
        identified = identity_state == IDENTIFIED
        level = 1 if identified and has_programming_route else (0 if identified else None)
        level_state = (
            CATALOG_LEVEL_CANDIDATE if level == 1
            else CATALOG_LEVEL_DISCOVERED if level == 0
            else None
        )
        return {
            "schema_version": "2.0.0",
            "registry_id": None,
            "state": "UNKNOWN",
            "reviewed": False,
            "identity_state": identity_state,
            "catalog_level": level,
            "catalog_level_state": level_state,
            "provider": None,
            "operations": {},
            "programming": None,
            "selector_visible": level is not None and level >= 1,
            "job_selectable": False,
            "execution_authorized": False,
            "installed_runtime_attested": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
            "ppu_ready": False,
            "socket_ready": False,
            "ppu_readiness_source": None,
            "family_ready": None,
            "verified_configurations": [],
        }

    def describe(self, manufacturer: str, exact_icpn: str) -> dict[str, Any]:
        row = self._identity_record(manufacturer, exact_icpn)
        if row is None:
            return self._unknown("NOT_IDENTIFIED")

        reviewed = [
            provider
            for provider in self._providers
            if provider.lookup(manufacturer, exact_icpn) is not None
        ]
        _require(
            len(reviewed) <= 1,
            f"ambiguous reviewed Programming Providers for {manufacturer}/{exact_icpn}",
        )
        if not reviewed:
            candidate = self._candidate_for(row)
            has_programming_route = (
                (row.mapping_status == "mapped" and bool(row.target_config))
                or candidate is not None
            )
            result = self._unknown(
                IDENTIFIED,
                has_programming_route=has_programming_route,
            )
            if candidate is not None:
                result["state"] = "CANDIDATE"
                result["route_evidence"] = "backend_candidate_registry"
            return result

        raw = reviewed[0].describe(manufacturer, exact_icpn)
        state = raw.get("software_state")
        _require(state in PROGRAMMING_STATES, f"invalid provider state for {manufacturer}/{exact_icpn}: {state!r}")
        programmable = state == "SUPPORTED"
        configurations = self._physical_compatibility.verified_for(manufacturer, exact_icpn)
        _require(programmable or not configurations,
                 f"L3 evidence cannot promote non-SUPPORTED exact ICPN: {manufacturer}/{exact_icpn}")
        _require(not configurations or all(
            item["identity"]["package"] == row.package
            and item["identity"]["pin_count"] == row.pin_count
            and item["engine"]["provider_id"] == (raw.get("provider") or {}).get("provider_id")
            and item["engine"]["provider_version"] == (raw.get("provider") or {}).get("version")
            for item in configurations
        ), f"L3 configuration/package/provider mismatches L2 authority: {manufacturer}/{exact_icpn}")
        ppu_ready = any(item["verification_type"] == "PPU_SITE" for item in configurations)
        socket_ready = any(item["verification_type"] == "SOCKET_ADAPTER" for item in configurations)
        family = self._family_ready.for_exact(manufacturer, exact_icpn)
        _require(family is None or (programmable and not configurations),
                 f"invalid Family Ready overlap or L2 state: {manufacturer}/{exact_icpn}")
        ppu_source = "DIRECT_HIL" if ppu_ready else ("FAMILY_DERIVED" if family else None)
        ppu_ready = ppu_ready or family is not None
        verified = programmable and (ppu_ready or socket_ready)
        return {
            "schema_version": "2.0.0",
            "registry_id": raw.get("registry_id"),
            "state": state,
            "reviewed": bool(raw.get("reviewed")),
            "identity_state": IDENTIFIED,
            "catalog_level": 3 if verified else (2 if programmable else 1),
            "catalog_level_state": (
                CATALOG_LEVEL_VERIFIED if verified else
                CATALOG_LEVEL_PROGRAMMABLE if programmable else CATALOG_LEVEL_CANDIDATE
            ),
            "provider": deepcopy(raw.get("provider")),
            "operations": deepcopy(raw.get("operations", {})),
            "programming": deepcopy(raw.get("programming")),
            "qualification_gaps": deepcopy(raw.get("qualification_gaps", [])),
            "selector_visible": True,
            "job_selectable": programmable,
            "execution_authorized": False,
            "installed_runtime_attested": bool(raw.get("installed_runtime_attested", False)),
            "hardware_runtime_ready": bool(raw.get("hardware_runtime_ready", False)),
            "physical_programming_qualified": bool(raw.get("physical_programming_qualified", False)),
            "ppu_ready": ppu_ready,
            "socket_ready": socket_ready,
            "ppu_readiness_source": ppu_source,
            "family_ready": family,
            "verified_configurations": configurations,
        }

    def state_for(self, manufacturer: str, exact_icpn: str) -> str:
        return str(self.describe(manufacturer, exact_icpn)["state"])

    @cached_property
    def summary(self) -> dict[str, Any]:
        reviewed_keys: set[tuple[str, str]] = set()
        supported_keys: set[tuple[str, str]] = set()
        for provider in self._providers:
            for manufacturer, exact_icpn in provider.reviewed_exact_keys:
                key = (manufacturer, exact_icpn)
                reviewed_keys.add(key)
                if provider.describe(manufacturer, exact_icpn).get("software_state") == "SUPPORTED":
                    supported_keys.add(key)

        discovered_keys = {
            (row.vendor, row.identifier)
            for row in self._catalog.records
            if row.identity_state == IDENTIFIED
        }
        route_keys = {
            (row.vendor, row.identifier)
            for row in self._catalog.records
            if row.identity_state == IDENTIFIED
            and (
                (row.mapping_status == "mapped" and bool(row.target_config))
                or self._candidate_for(row) is not None
            )
        } | reviewed_keys
        level0_only = len(discovered_keys - route_keys)
        level1_only = len(route_keys - supported_keys)
        level3_keys = {
            key for key in supported_keys
            if self.describe(*key)["catalog_level"] == 3
        }
        family_ready_count = sum(
            self.describe(*key)["ppu_readiness_source"] == "FAMILY_DERIVED"
            for key in level3_keys
        )
        level2_only = len(supported_keys - level3_keys)
        return {
            "provider_count": len(self._providers),
            "reviewed_exact_icpns": len(reviewed_keys),
            "catalog_level_0_or_higher_discovered_exact_icpns": len(discovered_keys),
            "catalog_level_0_only_exact_icpns": level0_only,
            "catalog_level_1_or_higher_exact_icpns": len(route_keys),
            "catalog_level_2_programmable_exact_icpns": len(supported_keys),
            "catalog_level_3_verified_exact_icpns": len(level3_keys),
            "catalog_level_3_direct_hil_exact_icpns": len(level3_keys) - family_ready_count,
            "catalog_level_3_family_ready_exact_icpns": family_ready_count,
            "catalog_level_counts": {
                "0": level0_only,
                "1": level1_only,
                "2": level2_only,
                "3": len(level3_keys),
            },
            "selector_visibility_rule": "CATALOG_LEVEL_1_OR_HIGHER",
            "job_picker_rule": "CATALOG_LEVEL_2_OR_HIGHER",
            "execution_authorized_by_catalog_projection": False,
        }


@lru_cache(maxsize=1)
def get_default_programming_qualification_registry() -> ProgrammingQualificationRegistry:
    catalog = get_default_device_catalog()
    providers: list[ProgrammingQualificationProvider] = []
    openocd = get_default_openocd_software_qualification_registry()
    if openocd is not None:
        providers.append(openocd)
    nxp_kl25 = get_default_nxp_kl25_qualification_provider()
    if nxp_kl25 is not None:
        providers.append(nxp_kl25)
    return ProgrammingQualificationRegistry(
        catalog,
        tuple(providers),
        candidate_registry=get_default_backend_candidate_registry(),
        candidate_registries=(
            admitted_saml1x_official_programming_routes(catalog),
            admitted_pic32mx_openocd_devid_routes(catalog),
            admitted_nxp_mcxa_official_programming_routes(catalog),
        ),
        physical_compatibility=get_default_physical_compatibility_registry(),
        family_ready=get_default_family_ready_registry(),
    )
