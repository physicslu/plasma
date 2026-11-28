"""Host-only regression: Catalog is search metadata, never Job/Batch admission.

An unverified exact `target` claim is not an execution grant.
The Runtime Provider must validate the selected target and operations.
No Z2, FPGA, Driver, OpenOCD or DUT access.
"""
from __future__ import annotations

import pytest

from plasma_web import gateway, legacy_device_selector
from plasma_web.device_catalog import DeviceCatalogIntegrityError


def _catalog_unavailable():
    raise DeviceCatalogIntegrityError("Production Catalog omitted from slim PPU")


def test_catalog_still_required_for_catalog_search_not_programming(monkeypatch):
    monkeypatch.setattr(legacy_device_selector, "read_selector_view", lambda *_: _catalog_unavailable())
    with pytest.raises(DeviceCatalogIntegrityError):
        legacy_device_selector._device_search_payload("STM32", 5, 0)


@pytest.mark.parametrize("target", ["STM32F103C8T6", "MCXN236VKLT",
                                    "ATSAML10E16A-MZTVAO", "thirdparty-mcu-v1"])
def test_raw_job_target_and_owner_survive_without_catalog(monkeypatch, target):
    monkeypatch.setattr(legacy_device_selector, "read_selector_view", lambda *_: _catalog_unavailable())
    handler = object.__new__(gateway.PlasmaWebHandler)
    request = handler._job_request(
        {"site_id": 1, "operation": "erase", "target": target,
         "execution_owner_id": "owner-test"}, client_id="plasma-web")
    assert request.target == target
    assert request.metadata["execution_owner_id"] == "owner-test"
    assert request.metadata["execution_owner_kind"] == "rest_client"


@pytest.mark.parametrize("target", ["", "*", "../../bad", "a/../bad", "bad\nname",
                                    "bad name", 17, True])
def test_malformed_raw_target_fails_without_catalog(monkeypatch, target):
    monkeypatch.setattr(legacy_device_selector, "read_selector_view", lambda *_: _catalog_unavailable())
    handler = object.__new__(gateway.PlasmaWebHandler)
    with pytest.raises(ValueError):
        handler._job_request({"site_id": 1, "operation": "erase", "target": target},
                             client_id="plasma-web")


def test_typed_target_device_is_not_a_ppu_job_field(monkeypatch):
    monkeypatch.setattr(legacy_device_selector, "read_selector_view", lambda *_: _catalog_unavailable())
    handler = object.__new__(gateway.PlasmaWebHandler)
    with pytest.raises(ValueError, match="target_device is not a PPU Job field"):
        handler._job_request({"site_id": 1, "operation": "erase",
                              "target_device": {"vendor": "User", "identifier": "user-mcu"}},
                             client_id="plasma-web")
