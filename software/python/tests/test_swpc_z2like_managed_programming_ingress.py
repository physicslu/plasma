from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INGRESS = ROOT / "scripts" / "plasmactl-swpc-z2like-managed-ingress"
RENDER_START = ROOT / "scripts" / "render-control-station-start.sh"
BASE_INSTALLER = ROOT / "scripts" / "swpc-z2like-ppu-install.sh"


def test_managed_programming_ingress_is_separate_and_loopback_only() -> None:
    source = INGRESS.read_text(encoding="utf-8")
    assert 'PLASMA_SWPC_Z2LIKE_MANAGED_PORT:-18082' in source
    assert 'listen 127.0.0.1:$managed_port;' in source
    assert 'gateway_root="http://127.0.0.1:18080"' in source
    assert "Cloudflare Access service-token" in source
    assert 'location / { return 404; }' in source
    assert "/etc/nginx/conf.d/plasma-swpc-z2like-managed.conf" in source

    base = BASE_INSTALLER.read_text(encoding="utf-8")
    assert 'proxy_port="18081"' in base
    assert "/etc/nginx/conf.d/plasma-swpc-z2like-ppu.conf" in base


def test_ingress_exposes_programming_and_site_runtime_routes_with_read_only_settings_visibility() -> None:
    source = INGRESS.read_text(encoding="utf-8")
    for route in (
        "location = /api/settings/gateway {",
        "location = /api/settings/ppu-network {",
        "location = /api/settings/sites {",
        "location = /api/settings/sites/activation {",
        "location = /api/mock/runtime {",
        "location = /api/engineering/session {",
        "location = /api/jobs {",
        "location = /api/batches {",
        "api/programming-assets/check$",
        "api/programming-assets$",
        "api/jobs$",
        "api/jobs/[^/]+/cancel$",
        "api/jobs/[^/]+/files/[^/]+$",
    ):
        assert route in source

    assert "managed Gateway settings read is unavailable" in source
    assert "managed PPU network settings read is unavailable" in source
    assert "managed ingress unexpectedly allowed PPU network mutation" in source
    assert "managed ingress unexpectedly allowed Gateway settings mutation" in source
    assert "managed ingress unexpectedly exposed PPU network activation" in source


def test_ingress_preserves_explicit_method_boundaries() -> None:
    source = INGRESS.read_text(encoding="utf-8")
    assert "limit_except GET { deny all; }" in source
    assert "limit_except POST { deny all; }" in source
    assert "limit_except GET POST { deny all; }" in source
    assert "managed ingress did not reject GET /api/jobs" in source


def test_render_service_identity_is_optional_but_pairwise_fail_closed_and_not_serialized() -> None:
    source = RENDER_START.read_text(encoding="utf-8")
    assert "PLASMA_RENDER_PPU_ACCESS_CLIENT_ID" in source
    assert "PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET" in source
    assert "requires both PLASMA_RENDER_PPU_ACCESS_CLIENT_ID and PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET" in source
    assert 'export PLASMA_MANAGER_CF_ACCESS_ORIGIN="${ppu_endpoint%/}"' in source
    assert 'export PLASMA_MANAGER_CF_ACCESS_CLIENT_ID="${ppu_access_client_id}"' in source
    assert 'export PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET="${ppu_access_client_secret}"' in source
    assert '"ppus": [{"alias": alias, "endpoint": endpoint}]' in source
    assert '"client_secret"' not in source
