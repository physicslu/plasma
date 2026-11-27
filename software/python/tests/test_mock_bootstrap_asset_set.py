"""U10 Mock side: a Mock PPU pins the Active Set its PPU Bootstrap B3 really
published, through the same ``ppu_asset_set.py`` helper a Z2 Runtime uses, and
a Mock Route that names a real ICPN still never qualifies on a physical Site."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.errors import PlasmaError
from plasma_manager.programming import _StepFailure
from plasma_opf import bundle_v3
from plasma_server import mock_resources
from plasma_server.site_manager import SiteManager

ROOT = Path(__file__).resolve().parents[3]
CONTROL_PLANE = ROOT / "scripts"
PRODUCTION_ROUTES = ROOT / "data" / "opf" / "programming-routes"
REAL_ICPN = "STM32F103C8T6"


def _config(tmp_path: Path) -> PlasmaConfig:
    return PlasmaConfig(
        server=ServerConfig(output_root=tmp_path / "out", log_root=tmp_path / "log"),
        sites=[SiteConfig(id=site_id, enabled=True, interface="mock", target=REAL_ICPN,
                          operation_timeout_s=5.0, mock={"flash_size": 4096})
               for site_id in (1, 2)])


def test_wires_the_production_helper_over_the_bootstrap_product_root(tmp_path: Path) -> None:
    manager = SiteManager(_config(tmp_path))
    product = tmp_path / "product"
    mock_resources.install_bootstrap_asset_set(
        manager, product_root=product, control_plane=CONTROL_PLANE)
    reader = manager._active_asset_set_reader
    resolver = manager._active_resource_resolver
    assert reader.func.__name__ == "read_active" and reader.args == (product,)
    assert resolver.func.__name__ == "read_active_resource_identity"
    assert resolver.args == (product,)
    # No B3 activation yet: nothing is VERIFIED, admission fails closed.
    assert manager.active_resources_snapshot()["state"] == "UNAVAILABLE"
    assert reader()["state"] != "ACTIVE"


def test_never_on_a_ppu_with_a_non_mock_site() -> None:
    manager = SimpleNamespace(
        config=SimpleNamespace(sites=[SimpleNamespace(interface="mock"),
                                      SimpleNamespace(interface="openocd")]),
        _active_resource_resolver=None, _active_asset_set_reader=None)
    with pytest.raises(PlasmaError, match="MOCK_ASSET_SET_REQUIRES_MOCK_SITES"):
        mock_resources.install_bootstrap_asset_set(
            manager, product_root=Path("/nonexistent"), control_plane=CONTROL_PLANE)
    assert manager._active_resource_resolver is None


def test_never_replaces_an_existing_wiring(tmp_path: Path) -> None:
    manager = SiteManager(_config(tmp_path))
    mock_resources.install_mock_resources(manager)
    with pytest.raises(PlasmaError, match="MOCK_RESOURCES_ALREADY_WIRED"):
        mock_resources.install_bootstrap_asset_set(
            manager, product_root=tmp_path / "product", control_plane=CONTROL_PLANE)


def test_a_relative_product_root_is_refused(tmp_path: Path) -> None:
    manager = SiteManager(_config(tmp_path))
    with pytest.raises(PlasmaError, match="MOCK_ASSET_SET_PRODUCT_ROOT_NOT_ABSOLUTE"):
        mock_resources.install_bootstrap_asset_set(
            manager, product_root=Path("product"), control_plane=CONTROL_PLANE)


# ------------------------------------------- a real ICPN never leaks to hardware


def _readiness(site_interface: str, row_interface: str) -> dict:
    from plasma_manager.programming import BundleProgrammingWorkflow

    status = {
        "ppu": {"ppu_id": "ppu-x", "execution": {"busy": False, "active_job_count": 0}},
        "sites": [{"site_id": 1, "enabled": True, "state": "idle", "current_job_id": None,
                   "queued_jobs": 0, "interface": row_interface}],
    }
    responses = {"/api/health/ready": {"ok": True, "execution": "ready"},
                 "/api/status?site=1": status}
    workflow = SimpleNamespace(_gateway_get=lambda client, path: responses[path],
                               _batch_session=lambda alias, owner: None,
                               monotonic=lambda: 0.0)
    return BundleProgrammingWorkflow._readiness_checked(workflow, object(), 1, site_interface,
                                                        None, None)


def test_a_mock_route_with_a_real_icpn_never_qualifies_on_a_physical_site() -> None:
    route = mock_resources.mock_route(icpn=REAL_ICPN, flash_base=0x08000000,
                                      flash_size=1024 * 1024, erase_granularity=1024)
    assert route.icpn == REAL_ICPN and route.site_interface == "mock"
    with pytest.raises(_StepFailure) as raised:
        _readiness(route.site_interface, "openocd")
    assert raised.value.args[0] == "SITE_INTERFACE_NOT_READY"


def test_production_routes_carry_no_mock_route() -> None:
    for route in bundle_v3.load_routes(PRODUCTION_ROUTES):
        assert route.capabilities["driver_abi"] != mock_resources.MOCK_DRIVER_ABI
        assert route.site_interface == "openocd"


def test_a_mock_and_a_physical_route_for_one_icpn_are_never_guessed_between() -> None:
    physical = bundle_v3.load_routes(PRODUCTION_ROUTES)
    mock = mock_resources.mock_route(icpn=REAL_ICPN)
    both = bundle_v3.resolve_routes((*physical, mock), icpn=REAL_ICPN,
                                    operations=["erase", "program", "verify"])
    # The Manager refuses more than one match (programming_route_ambiguous).
    assert len(both) == 2


@pytest.mark.parametrize("socket, actions", [(None, None), ("control.sock", "actions.json")])
def test_runtime_entrypoint_requires_the_socket_and_no_package_actions(
        tmp_path: Path, monkeypatch, socket, actions) -> None:
    from plasma_server import runtime_server

    monkeypatch.setattr(runtime_server, "load_config", lambda path: _config(tmp_path))
    with pytest.raises(SystemExit, match="requires --runtime-control-socket"):
        asyncio.run(runtime_server._run(
            tmp_path / "ppu.yaml", socket and tmp_path / socket, actions and tmp_path / actions,
            (tmp_path / "product", CONTROL_PLANE)))
