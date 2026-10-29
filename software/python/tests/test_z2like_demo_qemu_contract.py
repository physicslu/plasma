from __future__ import annotations

import importlib.util
import json
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
DEPLOYMENT_DOC = ROOT / "docs" / "deployment" / "z2like-demo-qemu.md"
TODO_DOC = ROOT / "docs" / "development" / "todo.md"


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


def test_internal_maintenance_manager_uses_read_only_connection_registry():
    source = HOST.read_text(encoding="utf-8")
    assert 'endpoint = f"http://{ppu_ip}:{GATEWAY_PORT}"' in source
    assert '"  registry_state_path: null\\n"' in source
    assert '"ppus:\\n"' in source
    assert 'f"  - alias: {json.dumps(alias)}\\n"' in source
    assert 'f"    endpoint: {json.dumps(endpoint)}\\n"' in source
    assert "plasma_manager.bootstrap_server --config" in source
    assert "payload.get(\"mutable\") is not False" in source
    assert 'payload.get("storage") != "config"' in source
    assert "body={\"alias\": alias, \"endpoint\": endpoint}" not in source


def test_maintenance_registry_ownership_is_documented_as_single_owner():
    deployment = DEPLOYMENT_DOC.read_text(encoding="utf-8")
    todo = TODO_DOC.read_text(encoding="utf-8")
    assert "read-only config connection registry" in deployment
    assert "registry_state_path: null" in deployment
    assert "public production control plane remains the sole owner of Programming Registration" in deployment
    assert "manager-registry.json" in deployment
    assert "ignored and is not an authority" in deployment
    # The post-merge live gate has passed; reject the obsolete pending status.
    assert "### Dual Manager Lifecycle Ownership / State Drift" in todo
    assert "Resolved by the fixed read-only SWPC-local maintenance registry" in todo
    assert "post-merge Browser Runtime live qualification" in todo
    assert "programming_registration_owner=public-production-control-plane" in todo
    assert "storage=config" in todo
    assert "mutable=false" in todo


def test_managed_ingress_targets_qemu_not_x86_surrogate():
    source = MANAGED_INGRESS.read_text(encoding="utf-8")
    assert 'qemu_gateway_root="${PLASMA_Z2LIKE_DEMO_GATEWAY_ROOT:-http://172.30.77.2:18080}"' in source
    assert "must not target the SWPC x86_64 surrogate Gateway" in source
    assert 'listen 127.0.0.1:$managed_port' in source
    assert "Cloudflare Access service token remains REQUIRED" in source
    assert "POST /api/settings/ppu-network" in source
    assert "POST /api/settings/gateway" in source
    assert "location = /api/engineering/diagnostics/openocd-control-plane {" in source
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


def test_persistent_runtime_deployer_has_no_local_programming_registration_authority():
    source = RUNTIME_DEPLOYER.read_text(encoding="utf-8")
    assert "_maintenance_connection(" in source
    assert 'payload.get("mutable") is not False' in source
    assert 'payload.get("storage") != "config"' in source
    assert "lifecycle_before" not in source
    assert "lifecycle_after" not in source
    assert '_set_lifecycle(manager, args.alias, "disabled"' not in source
    assert '_set_lifecycle(manager, args.alias, "commissioned"' not in source
    assert 'runtime_state_before not in {"runtime_absent", "runtime_active"}' in source
    assert 'maintenance_requires_idle = runtime_state_before == "runtime_active"' in source
    assert "_wait_for_trusted_idle(" in source
    assert 'pairing.get("device_match") is False' in source
    assert "do not retain or print" not in source or 'token = ""' in source
    assert '"maintenance_registry_storage": "config-read-only"' in source
    assert '"programming_registration_owner": "public-production-control-plane"' in source
    assert '"runtime_state_after": "runtime_active"' in source


def test_qemu_target_keeps_bootstrap_alive_for_activation_rollback():
    source = TARGET.read_text(encoding="utf-8")
    assert "failed_release" in source
    assert "Activation failure must not kill Bootstrap" in source
    assert "wait for the rollback/current-link transition" in source
    assert '"--kit-tool",\n            str(kit_tool)' in source
    assert '"--port",\n            str(BOOTSTRAP_PORT)' in source


def test_qemu_target_waits_for_server_before_gateway_startup():
    source = TARGET.read_text(encoding="utf-8")
    start = source.index("server = subprocess.Popen(")
    wait = source.index('_wait_tcp("127.0.0.1", SERVER_PORT, 30.0, server)')
    gateway = source.index("gateway = subprocess.Popen(", start)
    assert start < wait < gateway
    assert "process exited before TCP readiness" in source
    assert "TCP readiness deadline exceeded" in source


def test_simulation_reuses_kit_local_deployment_coordinator_and_installer_core():
    source = KIT.read_text(encoding="utf-8")
    assert 'kit_scripts = verified.root / "scripts"' in source
    assert 'coordinator = kit_scripts / "ppu-bootstrap-deployment.py"' in source
    assert 'installer_core = kit_scripts / "ppu-z2-installer-core.py"' in source
    assert 'CORE_OVERRIDE: str(installer_core)' in source
    assert "_install_openocd_from_verified_kit" in source
    assert 'argv.extend(["--api-transaction-id", api_transaction_id])' in source
    assert 'verified.root / "scripts" / "openocd-runtime.py"' in source
    assert '"openocd_artifact_sha256": openocd_sha' in source
    assert '"openocd_hardware_runtime_ready": openocd_evidence.get("hardware_runtime_ready")' in source
    assert '"python_artifact_execution": "not_executed_in_qemu-simulation"' in source


def test_qemu_kit_cli_accepts_bounded_bootstrap_api_correlation_only():
    kit = _load(KIT, "ppu_qemu_bootstrap_api_contract")
    args = kit._parser().parse_args([
        "deploy", "fixture-kit.tar.gz", "--sidecar", "fixture.sha256",
        "--gateway-host", "127.0.0.1", "--ppu-id", "ppu-01",
        "--facility-id", "lab", "--api-transaction-id", "f" * 32,
    ])
    assert args.api_transaction_id == "f" * 32
    assert args.command == "deploy"


def test_qemu_kit_rejects_invalid_api_correlation_before_kit_io(monkeypatch):
    kit = _load(KIT, "ppu_qemu_bootstrap_api_invalid_contract")
    monkeypatch.setattr(kit, "_require_simulation_target", lambda: None)
    with pytest.raises(kit.QEMUSimulationKitError, match="transaction identity is invalid"):
        kit.deploy(
            kit_artifact=Path("nonexistent-kit.tar.gz"),
            sidecar=Path("nonexistent-kit.sha256"),
            gateway_host="127.0.0.1",
            ppu_id="ppu-test",
            facility_id="lab",
            display_name="simulated PPU",
            product_root=Path("/nonexistent-ppu"),
            api_transaction_id="untrusted-transaction-id",
        )


def test_local_kit_builder_keeps_simulation_python_boundary_explicit():
    source = KIT_BUILDER.read_text(encoding="utf-8")
    assert "ppu-runtime.py" in source
    assert "ppu-release.py" in source
    assert "ppu-z2-installer.py" in source
    assert "simulation-only Python artifact fixture; never production-qualified" in source
    assert '"python_artifact_execution": "not_executed_in_qemu-simulation"' in source
    assert '"openocd_hardware_runtime_ready": False' in source
    assert "openocd-runtime.py" in source
    assert "build-openocd-runtime.sh" in source
    assert "linux-armv7l.tar.gz" in source
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


def _simulation_openocd_identity(payload_sha256: str) -> dict[str, object]:
    return {
        "result": "PASS",
        "runtime_id": "0.12.0-9ea7f3d647c8",
        "openocd_version": "0.12.0",
        "source_commit": "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c",
        "architecture": "armv7l",
        "payload_sha256": payload_sha256,
        "hardware_runtime_ready": False,
    }


def _enable_armv7_simulation_marker(kit, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(kit.TARGET_MARKER, "1")
    monkeypatch.setattr(kit.platform, "system", lambda: "Linux")
    monkeypatch.setattr(kit.platform, "machine", lambda: "armv7l")


def test_simulation_reconciles_only_same_identity_stale_openocd_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _load(KIT, "plasma_z2like_demo_stale_openocd_reconcile_test")
    _enable_armv7_simulation_marker(kit, monkeypatch)
    product_root = tmp_path / "product"
    incoming = _simulation_openocd_identity("b" * 64)
    target = product_root / "programming-engines" / "openocd" / str(incoming["runtime_id"])
    target.mkdir(parents=True)
    retained = dict(incoming)
    retained["payload_sha256"] = "a" * 64
    (target / "plasma-runtime.json").write_text(json.dumps(retained), encoding="utf-8")
    (target / "stale.bin").write_bytes(b"stale")

    evidence = kit._reconcile_simulation_openocd_runtime(product_root, incoming)

    assert evidence["simulation_only"] is True
    assert evidence["action"] == "replaced_stale_verified_payload"
    assert evidence["previous_payload_sha256"] == "a" * 64
    assert evidence["incoming_payload_sha256"] == "b" * 64
    assert not target.exists()


def test_simulation_migrates_same_identity_legacy_openocd_without_payload_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _load(KIT, "plasma_z2like_demo_legacy_openocd_reconcile_test")
    _enable_armv7_simulation_marker(kit, monkeypatch)
    product_root = tmp_path / "product"
    incoming = _simulation_openocd_identity("0" * 64)
    target = product_root / "programming-engines" / "openocd" / str(incoming["runtime_id"])
    (target / "bin").mkdir(parents=True)
    (target / "bin" / "openocd").write_bytes(b"legacy-openocd")
    observed = kit._installed_payload_sha256(target)
    incoming["payload_sha256"] = observed
    retained = dict(incoming)
    retained.pop("payload_sha256")
    (target / "plasma-runtime.json").write_text(json.dumps(retained), encoding="utf-8")

    evidence = kit._reconcile_simulation_openocd_runtime(product_root, incoming)

    assert evidence["simulation_only"] is True
    assert evidence["action"] == "replaced_legacy_unidentified_payload"
    assert evidence["legacy_observed_payload_sha256"] == observed
    assert evidence["legacy_observed_matches_incoming_payload"] is True
    assert not target.exists()


def test_simulation_refuses_malformed_retained_openocd_payload_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _load(KIT, "plasma_z2like_demo_malformed_openocd_identity_test")
    _enable_armv7_simulation_marker(kit, monkeypatch)
    product_root = tmp_path / "product"
    incoming = _simulation_openocd_identity("c" * 64)
    target = product_root / "programming-engines" / "openocd" / str(incoming["runtime_id"])
    target.mkdir(parents=True)
    retained = dict(incoming)
    retained["payload_sha256"] = "invalid"
    (target / "plasma-runtime.json").write_text(json.dumps(retained), encoding="utf-8")

    with pytest.raises(kit.QEMUSimulationKitError, match="payload identity is invalid"):
        kit._reconcile_simulation_openocd_runtime(product_root, incoming)

    assert target.is_dir()

def test_simulation_keeps_matching_openocd_payload_for_installer_integrity_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _load(KIT, "plasma_z2like_demo_matching_openocd_reconcile_test")
    _enable_armv7_simulation_marker(kit, monkeypatch)
    product_root = tmp_path / "product"
    incoming = _simulation_openocd_identity("c" * 64)
    target = product_root / "programming-engines" / "openocd" / str(incoming["runtime_id"])
    target.mkdir(parents=True)
    (target / "plasma-runtime.json").write_text(json.dumps(incoming), encoding="utf-8")

    evidence = kit._reconcile_simulation_openocd_runtime(product_root, incoming)

    assert evidence["action"] == "already_matches_verified_payload"
    assert target.is_dir()


def test_simulation_refuses_cleanup_when_openocd_identity_drifted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = _load(KIT, "plasma_z2like_demo_drifted_openocd_reconcile_test")
    _enable_armv7_simulation_marker(kit, monkeypatch)
    product_root = tmp_path / "product"
    incoming = _simulation_openocd_identity("d" * 64)
    target = product_root / "programming-engines" / "openocd" / str(incoming["runtime_id"])
    target.mkdir(parents=True)
    retained = dict(incoming)
    retained["source_commit"] = "0" * 40
    retained["payload_sha256"] = "e" * 64
    (target / "plasma-runtime.json").write_text(json.dumps(retained), encoding="utf-8")

    with pytest.raises(kit.QEMUSimulationKitError, match="identity mismatch"):
        kit._reconcile_simulation_openocd_runtime(product_root, incoming)

    assert target.is_dir()
