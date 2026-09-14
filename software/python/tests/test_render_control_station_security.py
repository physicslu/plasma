from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "render-control-station-start.sh"
COLLECTION_ROUTE = REPOSITORY_ROOT / "software" / "web" / "app" / "api" / "manager" / "registry" / "route.ts"
ENTRY_ROUTE = REPOSITORY_ROOT / "software" / "web" / "app" / "api" / "manager" / "registry" / "[...path]" / "route.ts"


def test_public_render_lab_uses_fixed_target_lifecycle_registry() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"registry_state_path": registry_state' in text
    assert 'PLASMA_MANAGER_REGISTRY_POLICY="fixed-lifecycle"' in text
    assert '"ppus": [{"alias": alias, "endpoint": endpoint}]' in text

    collection = COLLECTION_ROUTE.read_text(encoding="utf-8")
    entry = ENTRY_ROUTE.read_text(encoding="utf-8")
    assert 'policy === "fixed-lifecycle"' in collection
    assert 'request.method === "POST"' in collection
    assert "fixed_registry_policy" in collection
    assert 'request.method === "DELETE"' in entry
    assert 'lifecycle !== "disabled" && lifecycle !== "commissioned"' in entry
    assert 'alias !== fixedAlias' in entry
    assert "Fixed-target registry mutation is limited to one lifecycle field" in entry


def test_public_render_lab_requires_https_root_endpoint_and_private_runtime_gateway_host() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'parsed.scheme != "https"' in text
    assert "must not embed credentials" in text
    assert "must not contain query or fragment" in text
    assert "must identify the managed PPU ingress root" in text
    assert "PLASMA_RENDER_PPU_RUNTIME_GATEWAY_HOST" in text
    assert "private non-loopback IPv4 address" in text


def test_public_render_lab_scopes_optional_cloudflare_service_identity_to_ppu_origin() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "PLASMA_RENDER_PPU_ACCESS_CLIENT_ID" in text
    assert "PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET" in text
    assert "requires both PLASMA_RENDER_PPU_ACCESS_CLIENT_ID and PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET" in text
    assert 'export PLASMA_MANAGER_CF_ACCESS_ORIGIN="${ppu_endpoint%/}"' in text
    assert 'export PLASMA_MANAGER_CF_ACCESS_CLIENT_ID="${ppu_access_client_id}"' in text
    assert 'export PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET="${ppu_access_client_secret}"' in text
    assert '"ppus": [{"alias": alias, "endpoint": endpoint}]' in text


def test_public_render_lab_runs_bootstrap_capable_manager_not_local_ppu() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "python -m plasma_manager.bootstrap_server" in text
    assert 'PLASMA_MANAGER_BOOTSTRAP_TRANSPORT="managed-gateway-prefix-v1"' in text
    assert 'PLASMA_MANAGER_BOOTSTRAP_RUNTIME_GATEWAY_HOST="${runtime_gateway_host}"' in text
    assert 'PLASMA_CONTROL_STATION_MODE="managed"' in text
    assert "dist/standalone" in text
    assert "python -m plasma_server.server" not in text
    assert "-m plasma_web.gateway" not in text
