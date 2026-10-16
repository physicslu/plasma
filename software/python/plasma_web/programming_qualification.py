"""Vendor-neutral Programming Qualification registry.

Provider-specific evidence loaders validate source, version, driver, geometry and
operation evidence. This registry derives Catalog Level 0/1/2 without exposing
legacy phase-prefixed fields. Catalog Level never grants Job/Batch execution authority.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, get_default_device_catalog
from .openocd_software_qualification import get_default_openocd_software_qualification_registry


IDENTIFIED = "IDENTIFIED"
CATALOG_LEVEL_DISCOVERED = "DISCOVERED"
CATALOG_LEVEL_CANDIDATE = "PROGRAMMING_CANDIDATE"
CATALOG_LEVEL_PROGRAMMABLE = "PROGRAMMABLE"
PROGRAMMING_STATES = frozenset({"UNKNOWN", "CANDIDATE", "BLOCKED", "SUPPORTED", "UNSUPPORTED"})


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
    ) -> None:
        self._catalog = catalog
        self._providers = providers

        seen: set[tuple[str, str]] = set()
        for provider in providers:
            for key in provider.reviewed_exact_keys:
                _require(key not in seen, f"multiple providers claim the same reviewed exact ICPN: {key}")
                seen.add(key)
                row = catalog.resolve(key[0], key[1])
                _require(row is not None, f"reviewed exact ICPN missing from canonical identity store: {key}")
                _require(
                    row.identity_state == IDENTIFIED,
                    f"Programming Qualification lacks IDENTIFIED exact ICPN prerequisite: {key}",
                )

    def _identity_record(self, manufacturer: str, exact_icpn: str):
        row = self._catalog.resolve(manufacturer, exact_icpn)
        if row is None or row.identity_state != IDENTIFIED:
            return None
        return row

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
            "selector_visible": False,
            "execution_authorized": False,
            "installed_runtime_attested": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
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
            has_programming_route = row.mapping_status == "mapped" and bool(row.target_config)
            return self._unknown(
                IDENTIFIED,
                has_programming_route=has_programming_route,
            )

        raw = reviewed[0].describe(manufacturer, exact_icpn)
        state = raw.get("software_state")
        _require(state in PROGRAMMING_STATES, f"invalid provider state for {manufacturer}/{exact_icpn}: {state!r}")
        programmable = state == "SUPPORTED"
        return {
            "schema_version": "2.0.0",
            "registry_id": raw.get("registry_id"),
            "state": state,
            "reviewed": bool(raw.get("reviewed")),
            "identity_state": IDENTIFIED,
            "catalog_level": 2 if programmable else 1,
            "catalog_level_state": CATALOG_LEVEL_PROGRAMMABLE if programmable else CATALOG_LEVEL_CANDIDATE,
            "provider": deepcopy(raw.get("provider")),
            "operations": deepcopy(raw.get("operations", {})),
            "programming": deepcopy(raw.get("programming")),
            "selector_visible": programmable,
            "execution_authorized": False,
            "installed_runtime_attested": bool(raw.get("installed_runtime_attested", False)),
            "hardware_runtime_ready": bool(raw.get("hardware_runtime_ready", False)),
            "physical_programming_qualified": bool(raw.get("physical_programming_qualified", False)),
        }

    def state_for(self, manufacturer: str, exact_icpn: str) -> str:
        return str(self.describe(manufacturer, exact_icpn)["state"])

    @property
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
            and row.mapping_status == "mapped"
            and bool(row.target_config)
        } | reviewed_keys
        return {
            "provider_count": len(self._providers),
            "reviewed_exact_icpns": len(reviewed_keys),
            "catalog_level_0_or_higher_discovered_exact_icpns": len(discovered_keys),
            "catalog_level_0_only_exact_icpns": len(discovered_keys - route_keys),
            "catalog_level_1_or_higher_exact_icpns": len(route_keys),
            "catalog_level_2_programmable_exact_icpns": len(supported_keys),
            "selector_visibility_rule": "CATALOG_LEVEL_2_PROGRAMMABLE",
            "execution_authorized_by_catalog_projection": False,
        }


def get_default_programming_qualification_registry() -> ProgrammingQualificationRegistry:
    catalog = get_default_device_catalog()
    providers: list[ProgrammingQualificationProvider] = []
    openocd = get_default_openocd_software_qualification_registry()
    if openocd is not None:
        providers.append(openocd)
    return ProgrammingQualificationRegistry(catalog, tuple(providers))
