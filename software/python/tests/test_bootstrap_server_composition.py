from __future__ import annotations

from pathlib import Path

from plasma_manager import bootstrap_server, server

ROOT = Path(__file__).resolve().parents[3]


def test_bootstrap_handler_extends_current_manager_handler():
    assert issubclass(bootstrap_server.BootstrapPlasmaManagerHandler, server.PlasmaManagerHandler)
    assert bootstrap_server.BootstrapPlasmaManagerHandler._parse_bootstrap_route(
        "/api/registry/z2/bootstrap"
    ) == ("z2", "")
    assert bootstrap_server.BootstrapPlasmaManagerHandler._parse_bootstrap_route(
        "/api/registry/z2/bootstrap/uploads/" + "a" * 32 + "/commit"
    ) == ("z2", "uploads/" + "a" * 32 + "/commit")


def test_plasma_manager_entrypoint_uses_composition_layer_not_stale_server_copy():
    pyproject = (ROOT / "software" / "python" / "pyproject.toml").read_text(encoding="utf-8")
    source = (ROOT / "software" / "python" / "plasma_manager" / "bootstrap_server.py").read_text(encoding="utf-8")
    assert 'plasma-manager = "plasma_manager.bootstrap_server:main"' in pyproject
    assert "from . import server as base_server" in source
    assert "class BootstrapPlasmaManagerHandler(base_server.PlasmaManagerHandler)" in source
    assert "base_server.main()" in source
