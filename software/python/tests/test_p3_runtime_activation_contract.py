from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_runtime_activation_helper_is_restart_server_only() -> None:
    source = (ROOT / "software/python/plasma_web/runtime_activation_helper.py").read_text(encoding="utf-8")
    assert '["systemctl", "restart", "plasma-server.service"]' in source
    assert 'required = {"operation", "expected_ppu_id", "quiesce_ttl_s"}' in source
    assert 'request.get("operation") != "restart_server"' in source
    assert "shell=True" not in source
    assert "service" not in 'required = {"operation", "expected_ppu_id", "quiesce_ttl_s"}'


def test_server_quiesce_and_execution_reservation_share_lock() -> None:
    source = (ROOT / "software/python/plasma_server/site_manager.py").read_text(encoding="utf-8")
    assert "with self._execution_lock:" in source
    assert "self._runtime_quiesce.active()" in source
    assert "def acquire_runtime_quiesce" in source
    assert "if self._execution_lease is not None" in source
    assert "PPU is quiesced for controlled runtime activation" in source


def test_gateway_activation_is_ppu_level_revision_bound_and_desired_write_guarded() -> None:
    gateway = (ROOT / "software/python/plasma_web/gateway_phase3.py").read_text(encoding="utf-8")
    controller = (ROOT / "software/python/plasma_web/runtime_activation.py").read_text(encoding="utf-8")
    site_configuration = (ROOT / "software/python/plasma_web/site_configuration.py").read_text(encoding="utf-8")
    assert 'SITE_RUNTIME_ACTIVATION_PATH = "/api/settings/sites/activation"' in gateway
    assert 'configuration["desired_runtime_revision"]' in gateway
    assert "activation_guard=site_configuration.runtime_activation_guard" in gateway
    assert "desired_runtime_revision" in controller
    assert "DESIRED_RUNTIME_REVISION_RE" in controller
    assert "with self.activation_guard():" in controller
    assert "RUNTIME_ACTIVATION_REVISION_CONFLICT" in controller
    assert "RUNTIME_ACTIVATION_IDENTITY_CONFLICT" in controller
    assert "def runtime_activation_guard" in site_configuration
    assert "Site desired configuration cannot change during runtime activation" in site_configuration


def test_manager_runtime_activation_relay_is_exact_allowlist_not_generic_proxy() -> None:
    source = (ROOT / "software/python/plasma_manager/server.py").read_text(encoding="utf-8")
    assert 'r"^/api/settings/sites/activation$"' in source
    assert 'r"^/api/settings/sites/.*$"' not in source
    assert "_managed_route_allowed" in source


def test_z2_installer_preserves_existing_desired_state_and_bounds_privilege() -> None:
    path = ROOT / "scripts/ppu-z2-installer.py"
    spec = importlib.util.spec_from_file_location("ppu_z2_p3", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = path.read_text(encoding="utf-8")
    assert 'if path == config_path and existing_config.existed:' in source
    assert "upgrade_preserves_existing_config" in source
    assert 'RUNTIME_ACTIVATION_SERVICE = "plasma-runtime-activation.service"' in source
    assert '"User=root"' in source
    assert '"Group=plasma"' in source
    assert '"RestrictAddressFamilies=AF_UNIX"' in source
    assert '"PartOf=plasma-web.service"' in source
    assert '"lifecycle_owner": "plasma-web.service"' in source
    assert '"scope": "restart-plasma-server-only"' in source
    assert 'systemctl("enable", "--now", RUNTIME_ACTIVATION_SERVICE)' not in source


def test_release_workflows_ship_both_installer_bootstrap_files() -> None:
    z2 = (ROOT / ".github/workflows/z2-ps-release.yml").read_text(encoding="utf-8")
    ppu = (ROOT / ".github/workflows/ppu-release.yml").read_text(encoding="utf-8")
    for source in (z2, ppu):
        assert "scripts/ppu-z2-installer.py" in source
        assert "scripts/ppu-z2-installer-core.py" in source
        assert "python -m py_compile scripts/ppu-z2-installer.py scripts/ppu-z2-installer-core.py" in source
    assert 'cp scripts/ppu-z2-installer-core.py "$root/scripts/ppu-z2-installer-core.py"' in z2
    assert 'test -f "$root/scripts/ppu-z2-installer-core.py"' in z2
    assert 'installer_core="$output/ppu-z2-installer-core.py"' in ppu
    assert 'sha256sum "$(basename "$installer_core")"' in ppu


def test_web_exposes_one_ppu_level_activation_action() -> None:
    component = (ROOT / "software/web/app/engineering/ppu-runtime-activation.tsx").read_text(encoding="utf-8")
    route = (ROOT / "software/web/app/api/manager/registry/[...path]/route.ts").read_text(encoding="utf-8")
    api = (ROOT / "software/web/app/engineering/ppu-registry-api.ts").read_text(encoding="utf-8")
    assert "Activate Desired Configuration" in component
    assert "All-Site impact" in component
    assert "Server-authoritative admission gate" in component
    assert 'resource: "site-activation"' in route
    assert '"/api/settings/sites/activation"' in route
    assert "activateManagerPpuSiteDesired" in api


def test_p3_does_not_open_hardware_or_protocol_boundary() -> None:
    runtime = (ROOT / "scripts/ppu-runtime.py").read_text(encoding="utf-8")
    assert '"loads_fpga": False' in runtime
    assert '"accesses_pl": False' in runtime
    assert '"changes_target_power": False' in runtime
    assert '"programs_real_ic": False' in runtime
    assert "PROTOCOL_VERSION" not in (ROOT / "software/python/plasma_web/runtime_activation.py").read_text(encoding="utf-8")
