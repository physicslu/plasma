"""Host-only regression: a selected ST Job is not gated by Microchip Catalog.

Device Catalog is required for Device discovery and Microchip Level 0 denial;
it is not a programming-runtime prerequisite for unrelated exact ICPNs.
No PPU, Z2, USB, FPGA, OpenOCD or DUT is accessed.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from plasma_web import gateway
from plasma_web.device_catalog import DeviceCatalogIntegrityError


def _catalog_unavailable():
    raise DeviceCatalogIntegrityError("production Device Catalog absent in slim PPU")


def test_exact_st_target_does_not_open_unrelated_microchip_catalog(monkeypatch):
    # Use the actual installed IC Support contract; no hardcoded target bypass.
    resolved = gateway.get_default_ic_support_resolver().require_exact("STM32F103C8T6")
    assert resolved.expected_catalog["manufacturer"] == "STMicroelectronics"
    monkeypatch.setattr(gateway, "get_default_device_catalog", _catalog_unavailable)
    gateway._reject_unmapped_microchip_raw_job_target("STM32F103C8T6")


@pytest.mark.parametrize("vendor", ["STMicroelectronics", "NXP Semiconductors"])
def test_vendor_neutral_short_circuit_comes_from_resolved_ic_support(monkeypatch, vendor):
    called = []
    class Resolver:
        def resolve_exact(self, icpn):
            called.append(icpn)
            return SimpleNamespace(expected_catalog={"manufacturer": vendor})
    monkeypatch.setattr(gateway, "get_default_ic_support_resolver", Resolver)
    monkeypatch.setattr(gateway, "get_default_device_catalog", _catalog_unavailable)
    gateway._reject_unmapped_microchip_raw_job_target("arbitrary-selected-exact-icpn")
    assert called == ["arbitrary-selected-exact-icpn"]


@pytest.mark.parametrize("manufacturer", [None, "Microchip"])
def test_microchip_or_unresolved_target_retains_full_catalog_gate(monkeypatch, manufacturer):
    class Resolver:
        def resolve_exact(self, icpn):
            if manufacturer is None:
                return None
            return SimpleNamespace(expected_catalog={"manufacturer": manufacturer})
    monkeypatch.setattr(gateway, "get_default_ic_support_resolver", Resolver)
    monkeypatch.setattr(gateway, "get_default_device_catalog", _catalog_unavailable)
    with pytest.raises(DeviceCatalogIntegrityError, match="Production Catalog absent|Device Catalog absent"):
        gateway._reject_unmapped_microchip_raw_job_target("PIC32MX270F256B-I/SP")


def test_microchip_no_mapping_remains_rejected_without_fake_success(monkeypatch):
    class Resolver:
        def resolve_exact(self, _):
            return SimpleNamespace(expected_catalog={"manufacturer": "Microchip"})
    class Catalog:
        def resolve(self, vendor, target):
            assert vendor == "Microchip"
            assert target == "MICROCHIP-EXACT-ICPN"
            return SimpleNamespace(mapping_status="no_mapping")
    monkeypatch.setattr(gateway, "get_default_ic_support_resolver", Resolver)
    monkeypatch.setattr(gateway, "get_default_device_catalog", lambda: Catalog())
    with pytest.raises(ValueError, match="lookup-only"):
        gateway._reject_unmapped_microchip_raw_job_target("MICROCHIP-EXACT-ICPN")
