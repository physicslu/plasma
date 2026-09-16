from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LOCAL_CONTROL_STATION = ROOT / "scripts" / "plasmactl-local-control-station"
LOCAL_CONTROL_STATION_DOC = ROOT / "docs" / "deployment" / "local-control-station.md"
SWPC_INSTALLER = ROOT / "scripts" / "swpc-z2like-ppu-install.sh"


def test_local_control_station_reachable_target_requires_managed_site_surface() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")

    assert "validate_target_control_surface" in source
    assert 'local sites_url="${ppu_endpoint%/}/api/settings/sites"' in source
    assert "target PPU is reachable but managed-control API is unavailable" in source
    assert "configure the full Plasma Gateway endpoint, not a restricted diagnostics/status ingress" in source
    assert "validate_target_control_surface" in source.split("verify_profile()", 1)[1]


def test_swpc_co_resident_control_station_example_uses_full_gateway() -> None:
    script = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    document = LOCAL_CONTROL_STATION_DOC.read_text(encoding="utf-8")

    assert "--ppu-endpoint http://127.0.0.1:18080" in script
    assert "--ppu-endpoint http://127.0.0.1:18080" in document
    assert "127.0.0.1:18081" in document
    assert "retired by Issue #549" in document
    assert "must remain unused" in document


def test_swpc_legacy_host_18081_ingress_is_not_recreated() -> None:
    installer = SWPC_INSTALLER.read_text(encoding="utf-8")

    assert 'legacy_nginx_conf="/etc/nginx/conf.d/plasma-swpc-z2like-ppu.conf"' in installer
    assert "retire_legacy_restricted_ingress" in installer
    assert "listen 127.0.0.1:$proxy_port" not in installer
    assert "location = /api/health/live" not in installer
    assert "location = /api/status" not in installer
    assert "location = /api/settings/sites" not in installer
    assert '"legacy_restricted_ingress_retired": true' in installer
