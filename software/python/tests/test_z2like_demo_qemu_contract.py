from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOST = ROOT / "scripts" / "z2like-demo-qemu.py"
TARGET = ROOT / "scripts" / "z2like-demo-qemu-target.py"
KIT = ROOT / "scripts" / "z2like-demo-qemu-kit.py"
INSTALLER = ROOT / "scripts" / "z2like-demo-qemu-installer.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_swpc_is_single_environment_and_qemu_is_canonical_demo_backend():
    source = HOST.read_text(encoding="utf-8")
    assert '"simulation_environment": "SWPC"' in source
    assert '"canonical_backend": "QEMU ARMv7 simulated Z2"' in source
    assert '"engineering_surrogate": "swpc-z2like remains separate"' in source
    assert "swpc-z2like:            engineering surrogate only" in source


def test_qemu_target_is_private_and_does_not_reuse_swpc_surrogate_ports():
    source = HOST.read_text(encoding="utf-8")
    assert '"--network",\n        NETWORK' in source
    assert '"--ip",\n        ppu_ip' in source
    assert 'f"{scripts}:/sim:ro"' in source
    assert '"PortBindings"' in source
    assert 'if bindings:' in source
    assert 'host_ports_published_by_qemu' in source
    # Public access terminates at the dedicated Console, never at QEMU Gateway/Bootstrap.
    assert "CONSOLE_PORT = 18390" in source
    assert "MANAGER_PORT = 18380" in source
    assert "never expose QEMU :18080/:18081 directly" in source


def test_manager_uses_private_http_gateway_and_bootstrap_composition():
    source = HOST.read_text(encoding="utf-8")
    assert 'endpoint = f"http://{ppu_ip}:{GATEWAY_PORT}"' in source
    assert "registry_state_path" in source
    assert "plasma_manager.bootstrap_server --config" in source
    assert '"ppus: []\\n"' in source
    assert 'method="POST"' in source
    # Runtime registry add creates a pending PPU; config seeding would incorrectly create commissioned.
    assert 'body={"alias": alias, "endpoint": endpoint}' in source


def test_qemu_target_keeps_bootstrap_alive_for_activation_rollback():
    source = TARGET.read_text(encoding="utf-8")
    assert "failed_release" in source
    assert "Activation failure must not kill Bootstrap" in source
    assert "wait for the rollback/current-link transition" in source
    assert '"--kit-tool",\n            str(kit_tool)' in source
    assert '"--port",\n            str(BOOTSTRAP_PORT)' in source


def test_simulation_reuses_kit_local_deployment_coordinator_and_installer_core():
    source = KIT.read_text(encoding="utf-8")
    assert 'kit_scripts = verified.root / "scripts"' in source
    assert 'coordinator = kit_scripts / "ppu-bootstrap-deployment.py"' in source
    assert 'installer_core = kit_scripts / "ppu-z2-installer-core.py"' in source
    assert 'CORE_OVERRIDE: str(installer_core)' in source
    assert '"python_artifact_execution": "not_executed_in_qemu-simulation"' in source


def test_simulation_installer_requires_explicit_armv7_marker_and_core_binding(monkeypatch: pytest.MonkeyPatch):
    source = INSTALLER.read_text(encoding="utf-8")
    assert "PLASMA_Z2LIKE_DEMO_QEMU_TARGET" in source
    assert "PLASMA_Z2LIKE_DEMO_INSTALLER_CORE" in source
    assert 'machine not in {"armv7", "armv7l"}' in source
    assert '"systemd_qualified": False' in source
    assert '"Plasma-owned Python installation"' in source
    assert '"real IC programming"' in source

    host = _load(HOST, "plasma_z2like_demo_host_test")
    subnet, ppu_ip = host._validate_topology("172.30.77.0/24", "172.30.77.2")
    assert subnet == "172.30.77.0/24"
    assert ppu_ip == "172.30.77.2"
    with pytest.raises(host.DemoError):
        host._validate_topology("172.30.77.0/24", "172.30.78.2")


def test_simulation_does_not_claim_physical_z2_or_reboot_qualification():
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (HOST, TARGET, KIT, INSTALLER)
    )
    for boundary in (
        "PYNQ-Z2 hardware",
        "systemd/DAC",
        "reboot persistence",
        "PS-to-PL",
        "Site electrical",
        "target power",
        "real IC programming",
    ):
        assert boundary in combined
