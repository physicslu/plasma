"""Host-only regression: Catalog is search metadata, never Job/Batch admission.

An unverified target_device snapshot is not an execution grant.
The Runtime Provider must validate the selected target and operations.
No Z2, FPGA, Driver, OpenOCD or DUT access.
"""
from __future__ import annotations

import pytest

from plasma_web import gateway, legacy_device_selector
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
    monkeypatch.setattr(legacy_device_selector, "get_default_device_catalog", _catalog_unavailable)
    selected = gateway._parse_target_device({"vendor": vendor, "identifier": target})
    assert selected.vendor == vendor
    assert selected.identifier == target
    assert selected.icpn == target
    assert selected.family == ""
    assert selected.identifier_kind == "unverified_exact_target_claim"


@pytest.mark.parametrize("value", [
    {"vendor": "", "identifier": "MCU"},
    {"vendor": "Third Party", "identifier": ""},
    {"vendor": "Third Party", "identifier": "../../etc/passwd"},
    {"vendor": "Third Party", "identifier": "NAME\nBAD"},
    {"vendor": "Third Party", "identifier": "*"},
])
def test_invalid_target_snapshot_rejected_without_catalog(monkeypatch, value):
    monkeypatch.setattr(legacy_device_selector, "get_default_device_catalog", _catalog_unavailable)
    with pytest.raises(ValueError):
        gateway._parse_target_device(value)


def test_catalog_still_required_for_catalog_search_not_programming(monkeypatch):
    monkeypatch.setattr(legacy_device_selector, "get_default_device_catalog", _catalog_unavailable)
    with pytest.raises(DeviceCatalogIntegrityError):
        legacy_device_selector._device_search_payload("STM32", 5, 0)


@pytest.mark.parametrize("target", ["STM32F103C8T6", "MCXN236VKLT",
                                    "ATSAML10E16A-MZTVAO", "thirdparty-mcu-v1"])
@pytest.mark.parametrize("client_id", ["plasma-web", "plasma-web-engineering"])
def test_raw_job_target_and_owner_survive_without_catalog(monkeypatch, target, client_id):
    monkeypatch.setattr(legacy_device_selector, "get_default_device_catalog", _catalog_unavailable)
    handler = object.__new__(gateway.PlasmaWebHandler)
    request = handler._job_request(
        {"site_id": 1, "operation": "erase", "target": target,
         "execution_owner_id": "owner-test"}, client_id=client_id)
    assert request.target == target
    assert request.metadata["execution_owner_id"] == "owner-test"
    assert request.metadata["execution_owner_kind"] == (
        "engineering_session" if client_id == "plasma-web-engineering" else "rest_client")


@pytest.mark.parametrize("target", ["", "*", "../../bad", "a/../bad", "bad\nname",
                                    "bad name", 17, True])
def test_malformed_raw_target_fails_without_catalog(monkeypatch, target):
    monkeypatch.setattr(legacy_device_selector, "get_default_device_catalog", _catalog_unavailable)
    handler = object.__new__(gateway.PlasmaWebHandler)
    with pytest.raises(ValueError):
        handler._job_request({"site_id": 1, "operation": "erase", "target": target},
                             client_id="plasma-web")


def test_production_typed_target_policy_remains_separate(monkeypatch):
    monkeypatch.setattr(legacy_device_selector, "get_default_device_catalog", _catalog_unavailable)
    handler = object.__new__(gateway.PlasmaWebHandler)
    with pytest.raises(ValueError, match="only valid for an Engineering"):
        handler._job_request({"site_id": 1, "operation": "erase",
                              "target_device": {"vendor": "User", "identifier": "user-mcu"}},
                             client_id="plasma-web")
