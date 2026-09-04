from __future__ import annotations

from plasma_manager.server import PlasmaManagerHandler


def test_manager_allowlists_only_site_configuration_contract_routes() -> None:
    assert PlasmaManagerHandler._managed_route_allowed("GET", "/api/settings/sites")
    assert PlasmaManagerHandler._managed_route_allowed("POST", "/api/settings/sites/1")
    assert PlasmaManagerHandler._managed_route_allowed("POST", "/api/settings/sites/8")

    assert not PlasmaManagerHandler._managed_route_allowed("POST", "/api/settings/sites")
    assert not PlasmaManagerHandler._managed_route_allowed("GET", "/api/settings/sites/1")
    assert not PlasmaManagerHandler._managed_route_allowed("PATCH", "/api/settings/sites/1")
    assert not PlasmaManagerHandler._managed_route_allowed("POST", "/api/settings/sites/1/extra")
    assert not PlasmaManagerHandler._managed_route_allowed("GET", "/api/settings/arbitrary")
