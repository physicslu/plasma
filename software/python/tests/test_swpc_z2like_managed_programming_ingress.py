from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INGRESS = ROOT / "utilities" / "plasmactl" / "backends" / "plasmactl-swpc-z2like-managed-ingress"
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
    assert 'legacy_nginx_conf="/etc/nginx/conf.d/plasma-swpc-z2like-ppu.conf"' in base
    assert "retire_legacy_restricted_ingress" in base
    assert 'proxy_port="18081"' not in base
    assert "listen 127.0.0.1:$proxy_port" not in base
    assert '"legacy_restricted_ingress_retired": true' in base


def test_ingress_exposes_programming_and_site_runtime_routes_with_read_only_settings_visibility() -> None:
    source = INGRESS.read_text(encoding="utf-8")
    for route in (
        "location = /api/settings/gateway {",
        "location = /api/settings/ppu-network {",
        "location = /api/settings/sites {",
        "location = /api/settings/sites/activation {",
        "location = /api/mock/runtime {",
        "location = /api/engineering/session {",
        "location = /api/engineering/diagnostics/openocd-control-plane {",
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
