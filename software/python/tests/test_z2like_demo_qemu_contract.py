from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOST = ROOT / "scripts" / "z2like-demo-qemu.py"
TARGET = ROOT / "scripts" / "z2like-demo-qemu-target.py"
KIT = ROOT / "scripts" / "z2like-demo-qemu-kit.py"
KIT_BUILDER = ROOT / "scripts" / "z2like-demo-qemu-build-kit.py"
RUNTIME_DEPLOYER = ROOT / "scripts" / "z2like-demo-qemu-deploy.py"
MANAGED_INGRESS = ROOT / "scripts" / "plasmactl-z2like-demo-managed-ingress"
NGINX_EPHEMERAL = ROOT / "scripts" / "z2like-demo-nginx-ephemeral.py"
QEMU_WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-qemu.yml"
PROFILE = ROOT / "scripts" / "plasmactl-z2like-demo"
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


def test_qemu_target_is_private_and_does_not_publish_host_ports():
    source = HOST.read_text(encoding="utf-8")
    assert '"--network",\n        NETWORK' in source
    assert '"--ip",\n        ppu_ip' in source
    assert 'f"{scripts}:/sim:ro"' in source
    assert '"PortBindings"' in source
    assert 'if bindings:' in source
    assert 'host_ports_published_by_qemu' in source
    assert "BOOTSTRAP_PORT = 18081" in source
    assert "GATEWAY_PORT = 18080" in source


def test_public_control_station_is_render_and_swpc_manager_console_are_internal_fixture():
    source = HOST.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")
    assert "Render" in source
    assert "internal maintenance/acceptance" in source
    assert "CONSOLE_PORT = 18390" in source
    assert "MANAGER_PORT = 18380" in source
    assert "route the operator-managed z2like-demo hostname only to" not in source
    assert "z2like-demo.open4th.com (Render Console/BFF + Manager)" in profile
    assert "ppu-managed-lab.open4th.com" in profile
    assert "SWPC 127.0.0.1:18082 managed ingress" in profile
    assert "QEMU ARMv7 simulated Z2 172.30.77.2:18080" in profile


def test_internal_maintenance_manager_uses_private_gateway_and_bootstrap_composition():
    source = HOST.read_text(encoding="utf-8")
    assert 'endpoint = f"http://{ppu_ip}:{GATEWAY_PORT}"' in source
    assert "registry_state_path" in source
    assert "plasma_manager.bootstrap_server --config" in source
    assert '"ppus: []\\n"' in source
    assert 'method="POST"' in source
    assert 'body={"alias": alias, "endpoint": endpoint}' in source


def test_managed_ingress_targets_qemu_not_x86_surrogate():
    source = MANAGED_INGRESS.read_text(encoding="utf-8")
    assert 'qemu_gateway_root="${PLASMA_Z2LIKE_DEMO_GATEWAY_ROOT:-http://172.30.77.2:18080}"' in source
    assert "must not target the SWPC x86_64 surrogate Gateway" in source
    assert 'listen 127.0.0.1:$managed_port' in source
    assert "Cloudflare Access service token remains REQUIRED" in source
    assert "POST /api/settings/ppu-network" in source
    assert "POST /api/settings/gateway" in source
    assert "location / { return 404; }" in source


def test_pr_contracts_job_runs_real_ephemeral_nginx_integration_gate():
    workflow = QEMU_WORKFLOW.read_text(encoding="utf-8")
    harness = NGINX_EPHEMERAL.read_text(encoding="utf-8")
    assert 'scripts/z2like-demo-nginx-ephemeral.py' in workflow
    assert "Install disposable Nginx parser/runtime" in workflow
    assert "Run ephemeral Nginx integration gate" in workflow
    assert "python scripts/z2like-demo-nginx-ephemeral.py" in workflow
    assert 'subprocess.run(\n            ["nginx", "-p", f"{tmp}/", "-c", str(config), "-t"]' in harness
    assert 'f"/__plasma/bootstrap/v1/uploads/{UPLOAD_ID}/chunks"' in harness
    assert 'expect_record("bootstrap", "POST", f"/v1/uploads/{UPLOAD_ID}/chunks")' in harness
    assert 'expect_status(base, "/__plasma/bootstrap/v1/not-allowlisted", 404)' in harness
    assert '"requires_swpc": False' in harness


def test_one_command_profile_has_explicit_fast_forward_and_full_verification():
    source = PROFILE.read_text(encoding="utf-8")
    assert "git pull --ff-only origin main" in source
    assert "merge-base --is-ancestor" in source
    assert "refusing destructive reconciliation" in source
    assert "python3 \"$runtime_deployer\"" in source
    assert "bash \"$managed_backend\" install" in source
    assert "verify_public_path" in source
    assert "/api/manager/registry" in source
    assert "/api/manager/ppu/api/health/ready" in source


def test_persistent_runtime_deployer_preserves_registration_and_platform_gates():
    source = RUNTIME_DEPLOYER.read_text(encoding="utf-8")
    assert 'lifecycle_before not in {"pending", "commissioned", "disabled"}' in source
    assert '_set_lifecycle(manager, args.alias, "disabled"' not in source
    assert '_set_lifecycle(manager, args.alias, "commissioned"' not in source
    assert 'runtime_state_before not in {"runtime_absent", "runtime_active"}' in source
    assert 'maintenance_requires_idle = runtime_state_before == "runtime_active"' in source
    assert "_wait_for_trusted_idle(" in source
    assert 'pairing.get("device_match") is False' in source
    assert "do not retain or print" not in source or 'token = ""' in source
    assert "lifecycle_after != lifecycle_before" in source
    assert '"lifecycle_after": lifecycle_after' in source
    assert '"runtime_state_after": "runtime_active"' in source


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


def test_local_kit_builder_keeps_simulation_python_boundary_explicit():
    source = KIT_BUILDER.read_text(encoding="utf-8")
    assert "ppu-runtime.py" in source
    assert "ppu-release.py" in source
    assert "ppu-z2-installer.py" in source
    assert "simulation-only Python artifact fixture; never production-qualified" in source
    assert '"python_artifact_execution": "not_executed_in_qemu-simulation"' in source
    assert "stdout=subprocess.PIPE" in source
    assert "file=sys.stderr" in source


def test_simulation_validates_release_identity_from_coordinator_evidence():
    kit = _load(KIT, "plasma_z2like_demo_kit_contract_test")
    payload = {
        "result": "PASS",
        "transaction": {"release_id": "0.1.1-deadbeefcafe"},
        "installer_evidence": {"release_id": "0.1.1-deadbeefcafe"},
    }
    assert kit._validated_deployment_release_id(payload) == "0.1.1-deadbeefcafe"
    with pytest.raises(kit.QEMUSimulationKitError):
        kit._validated_deployment_release_id(
            {
                "result": "PASS",
                "transaction": {"release_id": "0.1.1-deadbeefcafe"},
                "installer_evidence": {"release_id": "0.1.1-cafebabefeed"},
            }
        )


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
        path.read_text(encoding="utf-8")
        for path in (HOST, TARGET, KIT, KIT_BUILDER, RUNTIME_DEPLOYER, INSTALLER)
    )
    for boundary in (
        "PYNQ-Z2 hardware",
        "Plasma-owned Python installation",
        "systemd/DAC",
        "reboot persistence",
        "PS-to-PL",
        "Site electrical",
        "target power",
        "real IC programming",
    ):
        assert boundary in combined
