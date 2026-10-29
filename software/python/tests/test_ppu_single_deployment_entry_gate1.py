"""Host-only tests: one Bootstrap deployment endpoint, no SSH/Root/hardware."""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contract = _load("ppu_unified_deployment_gate1", "ppu_unified_deployment.py")
bootstrap = _load("ppu_bootstrap_single_entry_gate1", "ppu-bootstrap-service.py")
coordinator = _load("ppu_bootstrap_single_coordinator_gate1", "ppu-bootstrap-deployment.py")
client = _load("ppu_deploy_single_entry_gate1", "ppu_deploy.py")


@pytest.mark.parametrize("module", ("wordport", "openocd-integration", "abtest"))
def test_swpc_modules_plan_same_bootstrap_api_without_running_z2(module: str) -> None:
    assert module in client.MODULES
    manifest, archive, swpc = client.build_bundle(module, "a" * 40)
    assert manifest["module"] == module
    assert manifest["source_commit"] == "a" * 40
    assert manifest["z2_files"] and swpc
    plan = client.unified_api_plan(module, "a" * 40, archive)
    assert plan["api_path"] == "/v1/deployments"
    assert plan["kind"] == "engineering-module"
    assert plan["module"] == module
    assert plan["artifact_sha256"] == hashlib.sha256(archive).hexdigest()
    assert plan["integration_state"] == "blocked-not-qualified"
    assert plan["no_deployment"] is True
    assert plan["shared_lock"] == str(coordinator.DeploymentPaths().lock)
    assert plan["shared_journal"] == str(coordinator.DeploymentPaths().journal)


def test_console_ps_runtime_uses_existing_bootstrap_request_unchanged() -> None:
    request = {
        "upload_id": "a" * 32, "gateway_host": "127.0.0.1",
        "ppu_id": "ppu-01", "facility_id": "lab", "display_name": "PPU",
    }
    assert bootstrap._deployment_request(request) == request
    assert bootstrap._deployment_request({"kind": "ppu-runtime", **request}) == request
    plan = contract.plan_unified_deployment(
        contract.DeploymentKind.PPU_RUNTIME,
        source_commit="a" * 40, artifact_sha256="f" * 64,
    )
    assert plan.api_path == "/v1/deployments"
    assert plan.state is contract.IntegrationState.EXISTING_RUNTIME


@pytest.mark.parametrize("kind,reason", [
    ("engineering-module", "ENGINEERING_INSTALL_NOT_QUALIFIED"),
    ("fpga-image", "FPGA_IMAGE_INSTALL_NOT_QUALIFIED"),
    ("root-shell", "UNKNOWN_DEPLOYMENT_KIND"),
])
def test_existing_api_rejects_unqualified_installers_before_mutation(kind: str, reason: str) -> None:
    with pytest.raises(bootstrap.BootstrapServiceError, match=reason):
        bootstrap._deployment_request({
            "kind": kind, "module": "wordport",
            "upload_id": "a" * 32,
        })


@pytest.mark.parametrize("module", ["wordport", "openocd-integration", "abtest"])
def test_planned_engineering_request_is_rejected_until_real_backend_is_qualified(
    module: str,
) -> None:
    with pytest.raises(bootstrap.BootstrapServiceError, match="ENGINEERING_INSTALL_NOT_QUALIFIED"):
        bootstrap._deployment_request({
            "kind": "engineering-module",
            "module": module,
            "upload_id": "a" * 32,
        })


def test_runtime_request_rejects_caller_selected_executable_and_provenance() -> None:
    for extra in (
        {"module": "abtest"},
        {"script": "run.py"},
        {"source_commit": "a" * 40},
        {"artifact_sha256": "f" * 64},
    ):
        with pytest.raises(bootstrap.BootstrapServiceError, match="unsupported deployment fields"):
            bootstrap._deployment_request({
                "kind": "ppu-runtime", "upload_id": "a" * 32,
                "gateway_host": "127.0.0.1", "ppu_id": "ppu-01",
                "facility_id": "lab", "display_name": "PPU", **extra,
            })


@pytest.mark.parametrize("kind,module", [
    (contract.DeploymentKind.ENGINEERING_MODULE, None),
    (contract.DeploymentKind.ENGINEERING_MODULE, "any-python"),
    (contract.DeploymentKind.PPU_RUNTIME, "wordport"),
    (contract.DeploymentKind.FPGA_IMAGE, "unreviewed"),
])
def test_single_entry_plan_rejects_unreviewed_module_kinds(kind, module) -> None:
    with pytest.raises(contract.UnifiedDeploymentError):
        contract.plan_unified_deployment(
            kind, module=module, source_commit="a" * 40, artifact_sha256="f" * 64,
        )


@pytest.mark.parametrize("commit,digest", [
    ("z"*40, "a"*64), ("a"*39, "a"*64),
    ("a"*40, "g"*64), ("a"*40, "a"*63),
])
def test_single_entry_source_and_digest_are_exact(commit: str, digest: str) -> None:
    with pytest.raises(contract.UnifiedDeploymentError):
        contract.plan_unified_deployment(
            contract.DeploymentKind.ENGINEERING_MODULE,
            module="wordport", source_commit=commit, artifact_sha256=digest,
        )


def test_shared_transaction_artifacts_and_recovery_contract_preserved() -> None:
    paths = coordinator.DeploymentPaths()
    assert contract.DEPLOYMENT_LOCK == str(paths.lock)
    assert contract.DEPLOYMENT_JOURNAL == str(paths.journal)
    assert "recovery_required" not in coordinator.SAFE_RESTART_STATES
    assert "runtime_active" in coordinator.SAFE_RESTART_STATES
    source = (ROOT / "scripts" / "ppu-bootstrap-deployment.py").read_text()
    assert "fcntl.flock" in source and "LOCK_EX | fcntl.LOCK_NB" in source
    assert 'self.installer.verify_release(' in source
    assert 'self.installer.install_release(' in source
    assert '"rolled_back"' in source and '"recovery_required"' in source


def test_existing_engineering_and_factory_paths_are_retained_for_migration() -> None:
    # Do not delete current engineering deploy or the independent factory
    # recovery mechanism before true Z2 integration/qualifying acceptance.
    legacy = (ROOT / "scripts" / "ppu_deploy_target.py").read_text()
    factory = (ROOT / "scripts" / "ppu-bootstrap-installer.py").read_text()
    root = (ROOT / "scripts" / "z2" / "plasma-path2-root-entry").read_text()
    assert "Z2_ROOT_REQUIRED" in legacy and "HARDWARE_OWNER_BUSY_OR_UNKNOWN" in legacy
    assert "wordport" in legacy and "abtest" in legacy
    assert "plasma-bootstrap.service" in factory
    assert "download|test|restore" in root
