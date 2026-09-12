from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "render-control-station-start.sh"


def test_public_render_lab_uses_fixed_immutable_manager_registry() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"registry_state_path":' not in text
    assert "arbitrary Manager-side HTTP(S) request target" in text
    assert '"ppus": [{"alias": alias, "endpoint": endpoint}]' in text


def test_public_render_lab_requires_https_root_endpoint() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'parsed.scheme != "https"' in text
    assert "must not embed credentials" in text
    assert "must not contain query or fragment" in text
    assert "must identify the managed PPU ingress root" in text


def test_public_render_lab_scopes_optional_cloudflare_service_identity_to_ppu_origin() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "PLASMA_RENDER_PPU_ACCESS_CLIENT_ID" in text
    assert "PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET" in text
    assert "requires both PLASMA_RENDER_PPU_ACCESS_CLIENT_ID and PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET" in text
    assert 'export PLASMA_MANAGER_CF_ACCESS_ORIGIN="${ppu_endpoint%/}"' in text
    assert 'export PLASMA_MANAGER_CF_ACCESS_CLIENT_ID="${ppu_access_client_id}"' in text
    assert 'export PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET="${ppu_access_client_secret}"' in text
    assert '"ppus": [{"alias": alias, "endpoint": endpoint}]' in text


def test_public_render_lab_runs_control_station_not_local_ppu() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "python -m plasma_manager.server" in text
    assert 'PLASMA_CONTROL_STATION_MODE="managed"' in text
    assert "dist/standalone" in text
    assert "python -m plasma_server.server" not in text
    assert "-m plasma_web.gateway" not in text
