from __future__ import annotations

from plasma_manager.server import PlasmaManagerHandler


def test_site_runtime_activation_is_exact_post_only_managed_route() -> None:
    path = "/api/settings/sites/activation"
    assert PlasmaManagerHandler._managed_route_allowed("POST", path) is True
    assert PlasmaManagerHandler._managed_route_allowed("GET", path) is False
    assert PlasmaManagerHandler._managed_route_allowed("PATCH", path) is False
    assert PlasmaManagerHandler._managed_route_allowed("POST", f"{path}/anything") is False
    assert PlasmaManagerHandler._managed_route_allowed("POST", "/api/settings/sites") is False


def test_existing_per_site_desired_write_allowlist_remains_distinct() -> None:
    assert PlasmaManagerHandler._managed_route_allowed("POST", "/api/settings/sites/1") is True
    assert PlasmaManagerHandler._managed_route_allowed("GET", "/api/settings/sites") is True
