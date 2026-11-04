"""Host-only regression: Catalog is search metadata, never Job/Batch admission.

An unverified target_device snapshot is not an execution grant.
The Runtime Provider must validate the selected target and operations.
No Z2, FPGA, Driver, OpenOCD or DUT access.
"""
from __future__ import annotations

import pytest

from plasma_core.enums import Operation
from plasma_core.errors import PlasmaError
from plasma_server.execution_router import _default_compiler_registry
from plasma_web import gateway
from plasma_web.device_catalog import DeviceCatalogIntegrityError


def _catalog_unavailable():
    raise DeviceCatalogIntegrityError("Production Catalog omitted from slim PPU")


@pytest.mark.parametrize("vendor,target", [
    ("STMicroelectronics", "STM32F103C8T6"),
    ("Microchip", "ATSAML10E16A-MZTVAO"),
    ("NXP Semiconductors", "MCXN236VKLT"),
    ("Independent Device", "thirdparty-mcu-v1"),
])
def test_target_device_is_unverified_claim_without_catalog(monkeypatch, vendor, target):
    monkeypatch.setattr(gateway, "get_default_device_catalog", _catalog_unavailable)
    selected = gateway._parse_target_device({"vendor": vendor, "identifier": target})
    assert selected.vendor == vendor
    assert selected.identifier == target
    assert selected.icpn == target
    assert selected.family == ""
    assert selected.identifier_kind == "unverified_exact_target_claim"


def test_microchip_l0_cannot_bypass_runtime_operation_admission_when_catalog_missing(monkeypatch):
    monkeypatch.setattr(gateway, "get_default_device_catalog", _catalog_unavailable)
    raw_icpn = "ATSAML10E16A-MZTVAO"
    claim = gateway._parse_target_device({"vendor": "Microchip", "identifier": raw_icpn})
    assert claim.icpn == raw_icpn
    # The current default Runtime has no admitted Compiler for this Microchip
    # target; the Backend must reject it regardless of any Catalog contents.
    registry = _default_compiler_registry()
    for operation in (Operation.ERASE, Operation.PROGRAM, Operation.VERIFY, Operation.READ):
        with pytest.raises(PlasmaError, match="no admitted compiler binding"):
            registry.select(claim.icpn, operation)


@pytest.mark.parametrize("value", [
    {"vendor": "", "identifier": "MCU"},
    {"vendor": "Third Party", "identifier": ""},
    {"vendor": "Third Party", "identifier": "../../etc/passwd"},
    {"vendor": "Third Party", "identifier": "NAME\nBAD"},
    {"vendor": "Third Party", "identifier": "*"},
])
def test_invalid_target_snapshot_rejected_without_catalog(monkeypatch, value):
    monkeypatch.setattr(gateway, "get_default_device_catalog", _catalog_unavailable)
    with pytest.raises(ValueError):
        gateway._parse_target_device(value)


def test_catalog_still_required_for_catalog_search_not_programming(monkeypatch):
    monkeypatch.setattr(gateway, "get_default_device_catalog", _catalog_unavailable)
    with pytest.raises(DeviceCatalogIntegrityError):
        gateway._device_search_payload("STM32", 5, 0)
