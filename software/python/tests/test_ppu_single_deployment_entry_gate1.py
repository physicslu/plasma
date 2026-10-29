"""Host-only tests: one Bootstrap deployment endpoint, no SSH/Root/hardware."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

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
        {"api_transaction_id": "f" * 32},
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
    assert bootstrap.COORDINATOR_SAFE_RESTART_STATES == coordinator.SAFE_RESTART_STATES
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


def _coordinator_record(paths, state: str) -> Path:
    paths.state_root.mkdir(parents=True, exist_ok=True)
    record = paths.coordinator_journal
    record.write_text(json.dumps({
        "schema_version": 1, "transaction_id": "coord-tx-01",
        "sequence": 3, "state": state,
    }), encoding="utf-8")
    record.chmod(0o600)
    return record


@pytest.mark.parametrize("state", sorted(bootstrap.COORDINATOR_SAFE_RESTART_STATES))
def test_bootstrap_api_preflight_accepts_only_safe_coordinator_journal(tmp_path: Path, state: str) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    bootstrap._admit_coordinator_journal(paths)  # First install has no journal.
    _coordinator_record(paths, state)
    bootstrap._admit_coordinator_journal(paths)


@pytest.mark.parametrize("state", [
    "received", "verifying", "staging", "activating", "recovery_required", "unexpected",
])
def test_bootstrap_api_preflight_rejects_active_or_unsafe_coordinator_state(
    tmp_path: Path, state: str,
) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    record = _coordinator_record(paths, state)
    original = record.read_bytes()
    with pytest.raises(bootstrap.BootstrapServiceError, match="active, unknown or requires recovery"):
        bootstrap._admit_coordinator_journal(paths)
    assert record.read_bytes() == original  # Never rewrite the Coordinator journal.


def test_bootstrap_api_preflight_rejects_corrupt_or_untrusted_journal(tmp_path: Path) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    journal = _coordinator_record(paths, "runtime_active")
    journal.chmod(0o644)
    with pytest.raises(bootstrap.BootstrapServiceError, match="private regular file"):
        bootstrap._admit_coordinator_journal(paths)
    journal.chmod(0o600)
    journal.write_text("not json", encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapServiceError, match="unreadable"):
        bootstrap._admit_coordinator_journal(paths)
    journal.write_text(" " * (bootstrap.MAX_COORDINATOR_JOURNAL_BYTES + 1), encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapServiceError, match="oversized"):
        bootstrap._admit_coordinator_journal(paths)
    # A character-limited read can admit a journal exceeding the byte budget.
    multibyte_journal = {
        "schema_version": 1, "transaction_id": "x", "sequence": 1,
        "state": "runtime_active", "padding": "é" * (bootstrap.MAX_COORDINATOR_JOURNAL_BYTES // 2),
    }
    encoded = json.dumps(multibyte_journal, ensure_ascii=False).encode("utf-8")
    assert len(encoded) > bootstrap.MAX_COORDINATOR_JOURNAL_BYTES
    journal.write_bytes(encoded)
    with pytest.raises(bootstrap.BootstrapServiceError, match="oversized"):
        bootstrap._admit_coordinator_journal(paths)
    journal.write_text(json.dumps({"schema_version": 1, "transaction_id": "x", "sequence": 0,
                                   "state": "runtime_active"}), encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapServiceError, match="identity is invalid"):
        bootstrap._admit_coordinator_journal(paths)
    journal.write_text(json.dumps({"schema_version": 1, "transaction_id": "x", "sequence": 1,
                                   "state": []}), encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapServiceError, match="active, unknown or requires recovery"):
        bootstrap._admit_coordinator_journal(paths)
    journal.unlink()
    journal.symlink_to(tmp_path / "not-owned-journal")
    with pytest.raises(bootstrap.BootstrapServiceError, match="unavailable"):
        bootstrap._admit_coordinator_journal(paths)


def test_bootstrap_api_rejects_coordinator_recovery_before_queueing(tmp_path: Path) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    _coordinator_record(paths, "recovery_required")
    upload_id = "a" * 32
    upload = bootstrap._upload_paths(paths, upload_id)
    upload.meta.parent.mkdir(parents=True, exist_ok=True)
    upload.meta.write_text('{"state":"committed"}', encoding="utf-8")
    server = object.__new__(bootstrap.BootstrapHTTPServer)
    server.bootstrap_paths = paths
    server.deployment_thread = None
    server.mutation_lock = threading.RLock()
    request = {"upload_id": upload_id, "gateway_host": "127.0.0.1",
               "ppu_id": "ppu-01", "facility_id": "lab", "display_name": "PPU"}
    with pytest.raises(bootstrap.BootstrapServiceError, match="requires recovery"):
        server.start_deployment(request)
    assert not paths.deployment_record.exists()  # No queued API transaction was created.


def _active_runtime_journal(paths, *, state="runtime_active", kind="ppu-runtime",
                            release_id="0.4.0-abcdef123456", tx="new-coord-tx",
                            api_id="f" * 32) -> Path:
    path = _coordinator_record(paths, state)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(transaction_id=tx, kind=kind, release_id=release_id,
                api_transaction_id=api_id)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_host_only_api_coordinator_transaction_reconciliation(tmp_path: Path) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    _active_runtime_journal(paths)
    api_id = "f" * 32
    binding = bootstrap._reconcile_runtime_result(
        paths, api_transaction_id=api_id,
        previous_coordinator_id="old-coord-tx",
        runner_result={"result": "PASS", "kit_release_id": "0.4.0-abcdef123456"},
    )
    assert binding == {
        "api_transaction_id": api_id,
        "coordinator_transaction_id": "new-coord-tx",
        "coordinator_release_id": "0.4.0-abcdef123456",
        "coordinator_state": "runtime_active",
    }
    # The helper is read-only; the real worker separately persists the result.
    assert not paths.deployment_record.exists()


@pytest.mark.parametrize("override", [
    {"state": "recovery_required"},
    {"state": "activating"},
    {"kind": "engineering-module"},
    {"release_id": "wrong-release"},
    {"tx": "old-coord-tx"},
    {"api_id": "e" * 32},
    {"api_id": None},
])
def test_host_only_reconciliation_rejects_mismatched_journal(tmp_path: Path, override: dict) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    journal = _active_runtime_journal(paths, **override)
    before = journal.read_bytes()
    with pytest.raises(bootstrap.BootstrapServiceError, match="not reconciled"):
        bootstrap._reconcile_runtime_result(
            paths, api_transaction_id="f" * 32,
            previous_coordinator_id="old-coord-tx",
            runner_result={"result": "PASS", "kit_release_id": "0.4.0-abcdef123456"},
        )
    assert journal.read_bytes() == before


def test_host_only_reconciliation_rejects_missing_or_untrusted_evidence(tmp_path: Path) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    good_result = {"result": "PASS", "kit_release_id": "0.4.0-abcdef123456"}
    with pytest.raises(bootstrap.BootstrapServiceError, match="receipt is missing"):
        bootstrap._reconcile_runtime_result(
            paths, api_transaction_id="f" * 32,
            previous_coordinator_id=None, runner_result=good_result,
        )
    journal = _active_runtime_journal(paths)
    for api_id, result, message in [
        ("not-a-transaction", good_result, "transaction identity"),
        ("f" * 32, {"result": "FAIL", "kit_release_id": "0.4.0-abcdef123456"}, "prove success"),
        ("f" * 32, {"result": "PASS"}, "release identity"),
    ]:
        with pytest.raises(bootstrap.BootstrapServiceError, match=message):
            bootstrap._reconcile_runtime_result(
                paths, api_transaction_id=api_id,
                previous_coordinator_id=None, runner_result=result,
            )
    journal.chmod(0o644)
    with pytest.raises(bootstrap.BootstrapServiceError, match="private regular file"):
        bootstrap._reconcile_runtime_result(
            paths, api_transaction_id="f" * 32,
            previous_coordinator_id=None, runner_result=good_result,
        )


def _host_only_server(paths, runner):
    server = object.__new__(bootstrap.BootstrapHTTPServer)
    server.bootstrap_paths = paths
    server.deployment_thread = None
    server.mutation_lock = threading.RLock()
    server.deployment_runner = runner
    return server


def _submit_host_only_runtime(server, paths):
    upload_id = "a" * 32
    upload = bootstrap._upload_paths(paths, upload_id)
    upload.meta.parent.mkdir(parents=True, exist_ok=True)
    upload.meta.write_text('{"state":"committed"}', encoding="utf-8")
    response = server.start_deployment({
        "upload_id": upload_id, "gateway_host": "127.0.0.1",
        "ppu_id": "ppu-01", "facility_id": "lab", "display_name": "PPU",
    })
    assert server.deployment_thread is not None
    server.deployment_thread.join(timeout=5)
    assert not server.deployment_thread.is_alive()
    return response, bootstrap._deployment_api_record(paths)


def test_api_worker_persists_exact_coordinator_receipt(tmp_path: Path) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    handoff = []

    def runner(paths, upload_id, request):
        handoff.append(dict(request))
        assert upload_id == "a" * 32
        _active_runtime_journal(paths, api_id=request["api_transaction_id"])
        return {"result": "PASS", "kit_release_id": "0.4.0-abcdef123456"}

    server = _host_only_server(paths, runner)
    initial, completed = _submit_host_only_runtime(server, paths)
    assert initial["transaction_id"] == handoff[0]["api_transaction_id"]
    assert completed["state"] == "succeeded"
    assert completed["result"]["coordinator_receipt"] == {
        "api_transaction_id": initial["transaction_id"],
        "coordinator_transaction_id": "new-coord-tx",
        "coordinator_release_id": "0.4.0-abcdef123456",
        "coordinator_state": "runtime_active",
    }


def test_bootstrap_runner_passes_internal_api_id_to_verified_kit(tmp_path: Path, monkeypatch) -> None:
    kit_tool = tmp_path / "ppu-bootstrap-kit.py"
    kit_tool.write_text("# inert fixture", encoding="utf-8")
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap", kit_tool=kit_tool)
    upload = bootstrap._upload_paths(paths, "a" * 32)
    upload.meta.parent.mkdir(parents=True, exist_ok=True)
    upload.meta.write_text('{"state":"committed"}', encoding="utf-8")
    upload.committed.write_bytes(b"fixture")
    upload.sidecar.write_text("fixture", encoding="utf-8")
    commands = []

    def fake_run(argv, **kwargs):
        commands.append(list(argv))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"result": "PASS", "kit_release_id": "v1"}),
        )

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    request = {"api_transaction_id": "f" * 32, "gateway_host": "127.0.0.1",
               "ppu_id": "ppu-01", "facility_id": "lab", "display_name": "PPU"}
    assert bootstrap.run_deployment_subprocess(paths, "a" * 32, request)["result"] == "PASS"
    assert commands[0][-2:] == ["--api-transaction-id", "f" * 32]
    with pytest.raises(bootstrap.BootstrapServiceError, match="internal Bootstrap API transaction"):
        bootstrap.run_deployment_subprocess(paths, "a" * 32, {**request, "api_transaction_id": None})
    assert len(commands) == 1


@pytest.mark.parametrize("failure", ["missing", "wrong-api", "wrong-release", "stale-id", "exception"])
def test_api_worker_requires_recovery_on_unreconciled_result(tmp_path: Path, failure: str) -> None:
    paths = bootstrap.ServicePaths(state_root=tmp_path / "bootstrap")
    if failure == "stale-id":
        _active_runtime_journal(paths, api_id=None)

    def runner(paths, upload_id, request):
        if failure == "exception":
            raise RuntimeError("engine exited after possible activation")
        if failure != "missing":
            _active_runtime_journal(
                paths,
                api_id=("e" * 32 if failure == "wrong-api" else request["api_transaction_id"]),
                release_id=("different-release" if failure == "wrong-release" else "0.4.0-abcdef123456"),
            )
        return {"result": "PASS", "kit_release_id": "0.4.0-abcdef123456"}

    server = _host_only_server(paths, runner)
    _, completed = _submit_host_only_runtime(server, paths)
    assert completed["state"] == "recovery_required"
    assert completed["error_code"] == "coordinator_result_unreconciled"
    assert completed["result"] is None
    with pytest.raises(bootstrap.BootstrapServiceError, match="requires explicit recovery"):
        server.start_deployment({
            "upload_id": "a" * 32, "gateway_host": "127.0.0.1",
            "ppu_id": "ppu-01", "facility_id": "lab", "display_name": "PPU",
        })
