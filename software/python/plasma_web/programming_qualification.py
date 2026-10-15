"""ADR-0002 Phase 2 — vendor-neutral Programming qualification registry.

This is the canonical runtime entry point for Phase 2. Provider-specific evidence
loaders (currently OpenOCD) remain responsible for validating their own source,
version, driver, geometry, and operation evidence. Gateway/UI code must consume
this registry rather than branching on a manufacturer or Programming Provider.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, get_default_device_catalog
from .openocd_software_qualification import get_default_openocd_software_qualification_registry


PHASE = "PROGRAMMING"
PHASE1_IDENTIFIED = "IDENTIFIED"
PROGRAMMING_STATES = frozenset({"UNKNOWN", "CANDIDATE", "SUPPORTED", "UNSUPPORTED"})


class ProgrammingQualificationProvider(Protocol):
    @property
    def reviewed_exact_keys(self) -> tuple[tuple[str, str], ...]: ...

    def lookup(self, manufacturer: str, exact_icpn: str) -> dict[str, Any] | None: ...

    def describe(self, manufacturer: str, exact_icpn: str) -> dict[str, Any]: ...


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DeviceCatalogIntegrityError(f"Programming qualification: {reason}")


class ProgrammingQualificationRegistry:
    """Canonical Phase 2 projection over one or more evidence providers."""

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
                _require(row is not None, f"reviewed exact ICPN missing from Phase 1 Catalog: {key}")
                _require(
                    row.phase1_identity_state == PHASE1_IDENTIFIED,
                    f"Phase 2 record lacks Phase 1 IDENTIFIED prerequisite: {key}",
                )

    def _phase1_record(self, manufacturer: str, exact_icpn: str):
        row = self._catalog.resolve(manufacturer, exact_icpn)
        if row is None or row.phase1_identity_state != PHASE1_IDENTIFIED:
            return None
        return row

    @staticmethod
    def _unknown(phase1_state: str) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "phase": PHASE,
            "state": "UNKNOWN",
            "reviewed": False,
            "phase1_identity_state": phase1_state,
            "provider": None,
            "operations": {},
            "programming": None,
            "selector_visibility_authority": "PHASE1_IDENTIFIED",
            "execution_authorized": False,
            "installed_runtime_attested": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }

    def describe(self, manufacturer: str, exact_icpn: str) -> dict[str, Any]:
        row = self._phase1_record(manufacturer, exact_icpn)
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
            return self._unknown(PHASE1_IDENTIFIED)

        raw = reviewed[0].describe(manufacturer, exact_icpn)
        state = raw.get("software_state")
        _require(state in PROGRAMMING_STATES, f"invalid provider state for {manufacturer}/{exact_icpn}: {state!r}")
        return {
            "schema_version": "1.0.0",
            "phase": PHASE,
            "state": state,
            "reviewed": bool(raw.get("reviewed")),
            "phase1_identity_state": PHASE1_IDENTIFIED,
            "provider": deepcopy(raw.get("provider")),
            "operations": deepcopy(raw.get("operations", {})),
            "programming": deepcopy(raw.get("programming")),
            "selector_visibility_authority": "PHASE1_IDENTIFIED",
            "execution_authorized": False,
            "installed_runtime_attested": bool(raw.get("installed_runtime_attested", False)),
            "hardware_runtime_ready": bool(raw.get("hardware_runtime_ready", False)),
            "physical_programming_qualified": bool(raw.get("physical_programming_qualified", False)),
        }

    def state_for(self, manufacturer: str, exact_icpn: str) -> str:
        return str(self.describe(manufacturer, exact_icpn)["state"])

    @property
    def summary(self) -> dict[str, Any]:
        reviewed = sum(len(provider.reviewed_exact_keys) for provider in self._providers)
        return {
            "phase": PHASE,
            "provider_count": len(self._providers),
            "reviewed_exact_icpns": reviewed,
            "catalog_phase1_identified_exact_icpns": sum(
                1 for row in self._catalog.records
                if row.phase1_identity_state == PHASE1_IDENTIFIED
            ),
            "selector_visibility_authority": "PHASE1_IDENTIFIED",
            "execution_authorized_by_phase2_projection": False,
        }


def get_default_programming_qualification_registry() -> ProgrammingQualificationRegistry:
    catalog = get_default_device_catalog()
    providers: list[ProgrammingQualificationProvider] = []
    openocd = get_default_openocd_software_qualification_registry()
    if openocd is not None:
        providers.append(openocd)
    return ProgrammingQualificationRegistry(catalog, tuple(providers))
