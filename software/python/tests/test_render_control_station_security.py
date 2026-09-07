from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "render-control-station-start.sh"


def test_public_render_lab_uses_fixed_immutable_manager_registry() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "registry_state_path" not in text
    assert "arbitrary Manager-side HTTP(S) request target" in text
    assert '"ppus": [{"alias": alias, "endpoint": endpoint}]' in text


def test_public_render_lab_requires_https_root_endpoint() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'parsed.scheme != "https"' in text
    assert "must not embed credentials" in text
    assert "must not contain query or fragment" in text
    assert "must identify the restricted ingress root" in text


def test_public_render_lab_runs_control_station_not_local_ppu() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "python -m plasma_manager.server" in text
    assert 'PLASMA_CONTROL_STATION_MODE="managed"' in text
    assert "dist/standalone" in text
    assert "python -m plasma_server.server" not in text
    assert "-m plasma_web.gateway" not in text
