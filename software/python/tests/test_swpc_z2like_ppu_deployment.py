from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "swpc-z2like-ppu-install.sh"


def test_swpc_surrogate_mirrors_z2_ps_ownership_without_claiming_z2_equivalence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "/opt/plasma/python/<version>/bin/python3" in text
    assert "/opt/plasma/releases/${release_id}" in text
    assert "/opt/plasma/current" in text
    assert "/etc/plasma/ppu.yaml" in text
    assert "/etc/systemd/system/plasma-server.service" in text
    assert "/etc/systemd/system/plasma-web.service" in text
    assert 'model: "SWPC-Z2-SURROGATE"' in text
    assert "sites: []" in text
    assert '"z2_equivalent": false' in text
    assert '"hardware_boundary": "closed"' in text


def test_swpc_surrogate_keeps_gateway_private_and_public_ingress_allowlisted() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "gateway --host 127.0.0.1 --port 18080" in text
    assert "listen 127.0.0.1:$proxy_port" in text
    assert "location = /api/health/live" in text
    assert "location = /api/health/ready" in text
    assert "location = /api/node" in text
    assert "location = /api/status" in text
    assert "location = /api/engineering/diagnostics/loopback" in text
    assert "location / { return 404; }" in text
    assert "proxy_set_header Host \\$host;" in text
    assert "--engineering-mock" not in text


def test_swpc_surrogate_requires_clean_source_and_isolated_final_python() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "repository must be clean for qualification staging" in text
    assert 'sys.version_info < (3, 11)' in text
    assert 'sys.version_info.releaselevel != "final"' in text
    assert "--plasma-python must be Plasma-owned under /opt/plasma/python/<version>/bin/python3" in text


def test_swpc_surrogate_fails_closed_on_existing_runtime_ports() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'for port in 9900 18080 "$proxy_port"' in text
    assert 'ss -H -ltn "sport = :$port"' in text
    assert "TCP port %s is already in use" in text
    assert "stop or migrate the owning service explicitly before installation" in text
    assert "systemctl --user stop" not in text
    assert "pkill" not in text
    assert "killall" not in text


def test_swpc_surrogate_refuses_unmanaged_nginx_config() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '# Managed by Plasma SWPC Z2-like lab installer' in text
    assert 'grep -Fxq "$nginx_marker" "$nginx_conf"' in text
    assert "refusing to overwrite unmanaged Nginx config" in text
