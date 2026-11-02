"""One Asset Execution entry for Python / Native C / FPGA (Host-only).

The callbacks here are test-only trusted adapters. Runtime/Root adapters
are NOT connected to live Z2. No downloaded Python/C code or FPGA is run.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from .ppu_bundle_authority_fixture import provision_fixture_grant
from .test_ppu_b3_z2_install_gate1 import b3_request, make_coordinator
from .test_ppu_bundle_v3_packages_contract import (
    ROOT, bundle_v3, contract, TARGET, SOURCE,
)

modpath = ROOT / "scripts" / "ppu_asset_execution.py"
spec = importlib.util.spec_from_file_location("ppu_asset_execution_gate1", modpath)
assert spec and spec.loader
execution = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = execution
spec.loader.exec_module(execution)


def _ready_fixture(tmp_path):
    archive, digest = bundle_v3(
        tmp_path / "source",
        mutate=lambda m: m.__setitem__("actions", ["install", "verify"]),
    )
    co = make_coordinator(tmp_path)
    staged = co.execute_bundle_v3_install(b3_request(archive, digest))
    assert staged["result"] == "PASS" and staged["fpga"] == "NOT_RUN"
    activated = co.activate_staged_asset_set(digest, quiescence_lease=nullcontext)
    assert activated["result"] == "PASS"
    assert activated["fpga"] == "NOT_RUN" and activated["ready"] is False

    class Local:
        bundle_authority_policy = tmp_path / "master-authority.json"
    provision_fixture_grant(Local, archive.read_bytes())
    bundle = contract.verify_host_only_artifact(
        archive, expected_sha256=digest,
        source_commit=SOURCE, target_profile=TARGET,
    )
    by_kind = {p.kind: p for p in bundle.packages
               if p.kind in {"python", "native-c", "fpga-image"}}
    requests = {
        kind: execution.AssetExecutionRequest(
            asset_set_sha256=digest,
            package_id=p.id,
            package_version=p.version,
            package_kind=p.kind,
            package_identity_sha256=contract.bundle_package_identity(p),
        )
        for kind, p in by_kind.items()
    }
    assert set(requests) == {"python", "native-c", "fpga-image"}
    return co, requests, Local.bundle_authority_policy, archive


@pytest.mark.parametrize("kind,executor_name", [
    ("python", "trusted-python-runtime"),
    ("native-c", "trusted-native-runtime"),
    ("fpga-image", "existing-protected-fpga-loader"),
])
def test_one_authorized_execution_layer_for_all_types(tmp_path, kind, executor_name):
    co, requests, policy, _archive = _ready_fixture(tmp_path)
    plan = execution.prepare_asset_execution(
        co.paths.product_root, policy, requests[kind],
    )
    assert plan["status"] == "AUTHORIZED_NOT_EXECUTED"
    assert plan["trusted_executor"] == executor_name
    assert plan["asset_set_sha256"] == requests[kind].asset_set_sha256
    assert plan["package_identity_sha256"] == requests[kind].package_identity_sha256
    assert plan["master_authority"]["publisher"] == "open4th-test-master"
    assert plan["asset_executed"] is False
    assert plan["fpga_loaded"] is False
    assert plan["ready"] is False
    assert not (co.paths.product_root / "current").exists()
    assert not co.paths.systemd_root.exists()


@pytest.mark.parametrize("kind", ["python", "native-c", "fpga-image"])
def test_one_dispatch_contract_requires_trusted_runtime_lease_and_adapter(
    tmp_path, kind
):
    co, requests, policy, _archive = _ready_fixture(tmp_path)
    called = []
    hold = {"held": False}

    @contextmanager
    def owner_scope():
        assert hold["held"] is False
        hold["held"] = True
        try:
            yield
        finally:
            hold["held"] = False

    def fake_trusted_executor(plan):
        assert hold["held"] is True
        called.append(plan["package_kind"])
        return {
            "asset_set_sha256": plan["asset_set_sha256"],
            "package_identity_sha256": plan["package_identity_sha256"],
            "package_kind": plan["package_kind"],
            "status": "MOCK_NOT_RUN",
        }

    with pytest.raises(execution.AssetExecutionDenied,
                       match="ASSET_EXECUTION_RUNTIME_SCOPE_REQUIRED"):
        execution.dispatch_asset_execution(
            co.paths.product_root, policy, requests[kind],
            trusted_executors={kind: fake_trusted_executor},
        )
    with pytest.raises(execution.AssetExecutionDenied,
                       match="ASSET_EXECUTION_TRUSTED_EXECUTOR_REQUIRED"):
        execution.dispatch_asset_execution(
            co.paths.product_root, policy, requests[kind],
            execution_scope=owner_scope,
        )
    assert called == []
    result = execution.dispatch_asset_execution(
        co.paths.product_root, policy, requests[kind],
        execution_scope=owner_scope,
        trusted_executors={kind: fake_trusted_executor},
    )
    assert result["schema"] == "plasma.ppu.asset-dispatch-receipt.v1"
    assert result["package_kind"] == kind
    assert result["executor_result"]["status"] == "MOCK_NOT_RUN"
    assert called == [kind] and hold["held"] is False


@pytest.mark.parametrize("mutation,code", [
    ({"asset_set_sha256": "f" * 64}, "ASSET_EXECUTION_ACTIVE_SET_MISMATCH"),
    ({"package_identity_sha256": "f" * 64}, "ASSET_EXECUTION_PACKAGE_IDENTITY_MISMATCH"),
    ({"package_id": "nonexistent"}, "ASSET_EXECUTION_PACKAGE_NOT_FOUND"),
    ({"package_version": "2.0"}, "ASSET_EXECUTION_PACKAGE_NOT_FOUND"),
    ({"package_kind": "unknown"}, "ASSET_EXECUTION_REQUEST_DENIED"),
    ({"package_id": "../../bin"}, "ASSET_EXECUTION_REQUEST_DENIED"),
    ({"action": "shell"}, "ASSET_EXECUTION_REQUEST_DENIED"),
])
def test_asset_execution_wrong_identity_kind_or_command_denied(tmp_path, mutation, code):
    co, requests, policy, _archive = _ready_fixture(tmp_path)
    original = requests["fpga-image"]
    values = dict(original.__dict__)
    values.update(mutation)
    with pytest.raises(execution.AssetExecutionDenied, match=code):
        execution.prepare_asset_execution(
            co.paths.product_root, policy, execution.AssetExecutionRequest(**values),
        )


def test_asset_execution_rechecks_current_master_revocation_after_b2_b3(tmp_path):
    co, requests, policy, _archive = _ready_fixture(tmp_path)
    assert execution.prepare_asset_execution(
        co.paths.product_root, policy, requests["fpga-image"],
    )["status"] == "AUTHORIZED_NOT_EXECUTED"
    grants = json.loads(policy.read_text())
    grants["authorizations"][0]["archive_sha256"] = "e" * 64
    policy.write_text(json.dumps(grants))
    called = []
    with pytest.raises(execution.AssetExecutionDenied,
                       match="ASSET_EXECUTION_MASTER_AUTHORITY_DENIED"):
        execution.dispatch_asset_execution(
            co.paths.product_root, policy, requests["fpga-image"],
            execution_scope=nullcontext,
            trusted_executors={"fpga-image": lambda plan: called.append(plan)},
        )
    assert called == []


def test_asset_execution_corrupted_active_files_cannot_launch_any_kind(tmp_path):
    co, requests, policy, _archive = _ready_fixture(tmp_path)
    staged = co.paths.product_root / "assets" / "staged"
    package_root = staged / requests["fpga-image"].asset_set_sha256 / (
        "payload/packages/fpga-addon"
    )
    image = next(path for path in package_root.rglob("*.bin") if path.is_file())
    image.chmod(0o600)
    image.write_bytes(b"mutated")
    with pytest.raises(Exception, match="ASSET_SET_FILE_MISMATCH"):
        execution.prepare_asset_execution(
            co.paths.product_root, policy, requests["native-c"],
        )


def test_asset_execution_denies_forged_adapter_receipt(tmp_path):
    co, requests, policy, _archive = _ready_fixture(tmp_path)
    def dishonest(_plan):
        return {"asset_set_sha256": "f" * 64,
                "package_identity_sha256": "f" * 64,
                "package_kind": "fpga-image"}
    with pytest.raises(execution.AssetExecutionDenied,
                       match="ASSET_EXECUTION_EXECUTOR_RECEIPT_UNTRUSTED"):
        execution.dispatch_asset_execution(
            co.paths.product_root, policy, requests["fpga-image"],
            execution_scope=nullcontext,
            trusted_executors={"fpga-image": dishonest},
        )
