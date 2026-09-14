from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SIM = ROOT / "scripts" / "z2like-qemu-sim.py"
INGRESS = ROOT / "scripts" / "plasmactl-z2like-qemu-managed-ingress"


def test_qemu_simulation_script_is_valid_python_and_pinned_armv7() -> None:
    source = SIM.read_text(encoding="utf-8")
    ast.parse(source)
    assert 'ARM_IMAGE = "arm32v7/python:3.12@sha256:' in source
    assert 'CONTAINER_NAME = "plasma-z2like-qemu"' in source
    assert 'NETWORK_NAME = "plasma-z2like-sim"' in source
    assert 'APPLIANCE_IP = "172.29.33.21"' in source
    assert '"--platform", "linux/arm/v7"' in source
    assert '"--network", NETWORK_NAME' in source
    assert '"--ip", APPLIANCE_IP' in source
    assert '"--publish"' not in source


def test_qemu_is_one_swpc_simulation_backend_not_a_second_environment() -> None:
    source = SIM.read_text(encoding="utf-8")
    assert '"simulation_environment": "SWPC"' in source
    assert '"backend": "qemu-armv7"' in source
    assert '"role": "ppu-simulation"' in source
    assert '"z2_equivalent": False' in source
    assert '"real_z2_hil": "not_qualified"' in source
    assert '"systemd_qualified": False' in source
    assert '"fpga_update": False' in source
    assert "swpc-z2like-01" not in source


def test_qemu_bootstrap_uses_current_verifiers_and_armv7_runtime() -> None:
    source = SIM.read_text(encoding="utf-8")
    assert '"ppu-bootstrap.py"' in source
    assert '"ppu-bootstrap-service.py"' in source
    assert '"ppu-bootstrap-kit.py"' in source
    assert '"ppu-z2-installer-core.py"' in source
    assert "self.bootstrap_kit.verify_kit(" in source
    assert "self.installer.verify_release(" in source
    assert "self.installer._copy_release(" in source
    assert '"--engineering-configured-mock"' in source
    assert '("0.0.0.0", BOOTSTRAP_PORT)' in source
    assert '"--host", "0.0.0.0"' in source


def test_qemu_managed_ingress_is_distinct_and_keeps_bootstrap_private() -> None:
    source = INGRESS.read_text(encoding="utf-8")
    assert 'PLASMA_Z2LIKE_QEMU_MANAGED_PORT:-18083' in source
    assert 'PLASMA_SWPC_Z2LIKE_MANAGED_GATEWAY_ROOT="http://172.29.33.21:18080"' in source
    assert 'PLASMA_SWPC_Z2LIKE_MANAGED_BASE_KIND="qemu-armv7"' in source
    assert 'PLASMA_SWPC_Z2LIKE_MANAGED_ALLOW_RUNTIME_ACTIVATION="0"' in source
    assert "Bootstrap remains private on the Docker bridge at 172.29.33.21:18081" in source
    assert "18081 = SWPC x86 surrogate restricted diagnostics" in source
    assert "18082 = SWPC x86 surrogate managed Programming" in source
