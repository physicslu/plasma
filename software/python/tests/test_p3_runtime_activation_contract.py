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


def test_gateway_activation_is_ppu_level_and_revision_bound() -> None:
    source = (ROOT / "software/python/plasma_web/gateway_phase3.py").read_text(encoding="utf-8")
    controller = (ROOT / "software/python/plasma_web/runtime_activation.py").read_text(encoding="utf-8")
    assert 'SITE_RUNTIME_ACTIVATION_PATH = "/api/settings/sites/activation"' in source
    assert 'configuration["desired_runtime_revision"]' in source
    assert "desired_runtime_revision" in controller
    assert "RUNTIME_ACTIVATION_REVISION_CONFLICT" in controller
    assert "RUNTIME_ACTIVATION_IDENTITY_CONFLICT" in controller


def test_z2_installer_preserves_existing_desired_state_and_bounds_privilege() -> None:
    path = ROOT / "scripts/ppu-z2-installer.py"
    spec = importlib.util.spec_from_file_location("ppu_z2_p3", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = path.read_text(encoding="utf-8")
    assert 'if path == config_path and existing_config.existed:' in source
    assert 'upgrade_preserves_existing_config' in source
    assert 'RUNTIME_ACTIVATION_SERVICE = "plasma-runtime-activation.service"' in source
    assert '"User=root"' in source
    assert '"Group=plasma"' in source
    assert '"RestrictAddressFamilies=AF_UNIX"' in source
    assert '"scope": "restart-plasma-server-only"' in source


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
