from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "swpc-z2like-ppu-install.sh"


def test_swpc_surrogate_mirrors_z2_ps_ownership_without_claiming_z2_equivalence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "/opt/plasma/python/<version>/bin/python3" in text
    assert "/opt/plasma/releases/${release_id}" in text
    assert "/opt/plasma/current" in text
    assert 'config_root="/etc/plasma"' in text
    assert 'config_path="$config_root/ppu.yaml"' in text
    assert 'systemd_root="/etc/systemd/system"' in text
    assert 'server_unit="$systemd_root/plasma-server.service"' in text
    assert 'gateway_unit="$systemd_root/plasma-web.service"' in text
    assert 'activation_unit="$systemd_root/plasma-runtime-activation.service"' in text
    assert 'model: "SWPC-Z2-SURROGATE"' in text
    assert "sites: []" in text
    assert '"z2_equivalent": false' in text
    assert '"hardware_boundary": "closed"' in text


def test_swpc_surrogate_keeps_gateway_private_and_public_ingress_allowlisted() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'gateway_host="127.0.0.1"' in text
    assert "listen 127.0.0.1:$proxy_port" in text
    assert "location = /api/health/live" in text
    assert "location = /api/health/ready" in text
    assert "location = /api/node" in text
    assert "location = /api/status" in text
    assert "location = /api/engineering/diagnostics/loopback" in text
    assert "location / { return 404; }" in text
    assert "proxy_set_header Host \\$host;" in text
    assert "--engineering-mock" not in text


def test_swpc_surrogate_site_config_write_boundary_is_gateway_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'install -d -m 0770 -o root -g plasma "$config_root"' in text
    assert 'chmod 0640 "$config_path"' in text
    assert 'chown plasma:plasma "$config_path"' in text
    assert "module.render_systemd_units(" in text
    assert '"runtime_apply_supported": true' in text
    assert '"upgrade_preserves_existing_config": true' in text
    assert "preserving existing canonical Desired configuration" in text


def test_swpc_surrogate_validates_dynamic_canonical_site_ids() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'site_id = entry.get("id")' in text
    assert 'entry.get("site_id")' not in text
    assert "Canonical Site identity is" in text
    assert "not 1 <= maximum <= 8" in text
    assert "len(site_ids) != len(set(site_ids))" in text


def test_swpc_surrogate_reuses_bounded_p3_activation_units() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'server_control_socket="/run/plasma-server/control.sock"' in text
    assert 'runtime_activation_socket="/run/plasma-runtime-activation/helper.sock"' in text
    assert 'module.render_systemd_units(' in text
    assert '"scope": "restart-plasma-server-only"' in text
    assert "systemctl enable --now plasma-server.service plasma-web.service" in text
    assert "systemctl enable --now plasma-runtime-activation.service" not in text


def test_swpc_surrogate_requires_clean_source_and_isolated_final_python() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "repository must be clean for qualification staging" in text
    assert 'sys.version_info < (3, 11)' in text
    assert 'sys.version_info.releaselevel != "final"' in text
    assert "sys.prefix == sys.base_prefix" in text
    assert "base or externally-managed interpreters are not accepted" in text
    assert "PyYAML>=6.0 pre-provisioned" in text
    assert "-m pip install" not in text
    assert "--plasma-python must be Plasma-owned under /opt/plasma/python/<version>/bin/python3" in text


def test_swpc_surrogate_retries_readiness_before_failing_install() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'deadline = time.monotonic() + 10.0' in text
    assert 'timeout=min(1.0, max(0.1, remaining))' in text
    assert 'time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))' in text
    assert 'PPU readiness failed after 10s' in text
    assert '"$plasma_python" - <<\'PY\'' in text
    assert "python3 - <<'PY'" not in text


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
