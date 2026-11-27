"""U10 D1: a Route's Site interface comes only from an explicit
(Flash Profile schema, Driver ABI) map. No default; Mock never qualifies on a
physical Site and a physical Route never qualifies on a Mock Site."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from plasma_manager.programming import BundleProgrammingWorkflow, _StepFailure
from plasma_opf import bundle_v3
from plasma_server import mock_resources

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_ROUTES = ROOT / "data" / "opf" / "programming-routes"


def _production_route() -> bundle_v3.ProgrammingRoute:
    routes = bundle_v3.load_routes(PRODUCTION_ROUTES)
    assert routes
    return routes[0]


def _with_abi(route: bundle_v3.ProgrammingRoute, abi: str) -> bundle_v3.ProgrammingRoute:
    return replace(route, capabilities={**route.capabilities, "driver_abi": abi})


def test_production_openocd_route_is_unchanged() -> None:
    route = _production_route()
    assert route.capabilities["driver_abi"] == "plasma_swd:5"
    assert route.site_interface == "openocd"
    assert route.summary()["site_interface"] == "openocd"


def test_mock_driver_abi_requires_a_mock_site() -> None:
    route = mock_resources.mock_route(icpn="MOCK-IC")
    assert route.capabilities["driver_abi"] == mock_resources.MOCK_DRIVER_ABI
    assert route.site_interface == "mock"


def test_map_is_explicit_and_matches_the_mock_constant() -> None:
    assert bundle_v3.SITE_INTERFACE_BY_PROFILE_ABI == {
        (bundle_v3.FLASH_PROFILE_SCHEMA, "plasma_swd:5"): "openocd",
        (bundle_v3.FLASH_PROFILE_SCHEMA, mock_resources.MOCK_DRIVER_ABI): "mock",
    }


@pytest.mark.parametrize("abi", ["plasma_swd:6", "example-swd-abi", "mock-simulated:2", "openocd", ""])
def test_unknown_driver_abi_fails_closed_without_fallback(abi: str) -> None:
    route = _with_abi(_production_route(), abi)
    with pytest.raises(ValueError, match="ROUTE_SITE_INTERFACE_UNSUPPORTED"):
        route.site_interface


@pytest.mark.parametrize("abi", ["plasma_swd:5", mock_resources.MOCK_DRIVER_ABI])
def test_incompatible_profile_schema_fails_closed(abi: str) -> None:
    route = _with_abi(_production_route(), abi)
    route = replace(route, flash_profile={**route.flash_profile,
                                          "schema": "plasma.ppu.other-flash-profile.v1"})
    with pytest.raises(ValueError, match="ROUTE_SITE_INTERFACE_UNSUPPORTED"):
        route.site_interface


def _readiness(site_interface: str, row_interface: str) -> dict:
    status = {
        "ppu": {"ppu_id": "ppu-x", "execution": {"busy": False, "active_job_count": 0}},
        "sites": [{"site_id": 1, "enabled": True, "state": "idle", "current_job_id": None,
                   "queued_jobs": 0, "interface": row_interface}],
    }
    responses = {"/api/health/ready": {"ok": True, "execution": "ready"},
                  "/api/status?site=1": status}
    workflow = SimpleNamespace(
        _gateway_get=lambda client, path: responses[path],
        _batch_session=lambda alias, owner: None,
        monotonic=lambda: 0.0,
    )
    return BundleProgrammingWorkflow._readiness_checked(workflow, object(), 1, site_interface,
                                                        None, None)


def test_mock_route_never_qualifies_on_a_physical_site() -> None:
    with pytest.raises(_StepFailure) as raised:
        _readiness(mock_resources.mock_route(icpn="MOCK-IC").site_interface, "openocd")
    assert raised.value.args[0] == "SITE_INTERFACE_NOT_READY"


def test_physical_route_never_qualifies_on_a_mock_site() -> None:
    with pytest.raises(_StepFailure) as raised:
        _readiness(_production_route().site_interface, "mock")
    assert raised.value.args[0] == "SITE_INTERFACE_NOT_READY"


def test_matching_interfaces_stay_ready() -> None:
    assert _readiness("openocd", "openocd")["state"] == "idle"
    assert _readiness("mock", "mock")["state"] == "idle"
