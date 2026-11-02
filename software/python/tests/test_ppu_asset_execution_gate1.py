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


def _b3_fpga_receipt_fixture(tmp_path):
    """Exercise #1261's actual B3 Coordinator with a mock Root loader."""
    from .test_ppu_b3_fpga_load_gate1 import (
        Harness, fpga_bundle, load_request, loaded, assets,
    )

    archive, digest, bin_sha, _manifest = fpga_bundle(tmp_path)
    h = Harness(tmp_path)
    h.outcome = lambda sha: {
        **loaded(sha, bin_sha),
        "fpga_manifest_sha256": assets.resolve_staged_fpga_handoff(
            h.co.paths.product_root, sha,
        )["fpga_image"]["manifest_sha256"],
    }
    receipt = h.co.execute_bundle_v3_install(load_request(archive, digest))
    assert h.events.count("root:bundle-load") == 1
    assert receipt["fpga_load"]["result"] == "fpga_loaded"

    class Local:
        bundle_authority_policy = tmp_path / "master-authority-for-b3.json"

    provision_fixture_grant(Local, archive.read_bytes())
    bundle = contract.verify_host_only_artifact(
        archive, expected_sha256=digest,
        source_commit=SOURCE, target_profile=TARGET,
    )
    fpga = next(p for p in bundle.packages if p.kind == "fpga-image")
    request = execution.AssetExecutionRequest(
        asset_set_sha256=digest,
        package_id=fpga.id,
        package_version=fpga.version,
        package_kind=fpga.kind,
        package_identity_sha256=contract.bundle_package_identity(fpga),
    )
    plan = execution.prepare_asset_execution(
        h.co.paths.product_root, Local.bundle_authority_policy, request,
    )
    return h, plan, receipt


def test_asset_execution_binds_existing_b3_receipt_not_a_second_loader(tmp_path):
    h, plan, receipt = _b3_fpga_receipt_fixture(tmp_path)
    binding = execution.validate_fpga_b3_receipt(
        h.co.paths.product_root, plan, receipt,
    )
    assert binding["status"] == "RECEIPT_MATCHED_ONLY"
    assert binding["package_identity_sha256"] == plan["package_identity_sha256"]
    assert binding["asset_set_sha256"] == plan["asset_set_sha256"]
    assert binding["hardware_evidence"] == "NOT_INDEPENDENTLY_VERIFIED"
    assert binding["runtime_site_readmission"] == "REQUIRED"
    assert binding["ready"] is False
    # Receipt validation must not cause another FPGA Manager/Root invocation.
    assert h.events.count("root:bundle-load") == 1


@pytest.mark.parametrize("field,value", [
    ("schema", "plasma.ppu.b3-deployment-receipt.v1"),
    ("stage", "bundle_install_only"),
    ("result", "FAIL"),
    ("archive_sha256", "f" * 64),
    ("runtime_site_readmission", "NOT_REQUIRED"),
    ("dut", "PASS"),
    ("fpga", "NOT_RUN"),
])
def test_asset_execution_refuses_nonmatching_b3_envelope(
    tmp_path, field, value,
):
    h, plan, receipt = _b3_fpga_receipt_fixture(tmp_path)
    forged = dict(receipt)
    forged[field] = value
    with pytest.raises(
        execution.AssetExecutionDenied, match="ASSET_EXECUTION_B3_RECEIPT_MISMATCH",
    ):
        execution.validate_fpga_b3_receipt(h.co.paths.product_root, plan, forged)


@pytest.mark.parametrize("part,key,value", [
    ("fpga_load", "identity", "NOT_RUN"),
    ("fpga_load", "requested", False),
    ("fpga_load", "result", "recovery_required"),
    ("fpga_load", "auto_restore", True),
    ("fpga_load", "fpga_image_id", "spoofed"),
    ("fpga_load", "fpga_bin_sha256", "f" * 64),
    ("fpga_load", "fpga_manifest_sha256", "f" * 64),
    ("active_asset_set", "asset_set_sha256", "f" * 64),
    ("active_asset_set", "generation", 0),
    ("transaction", "state", "recovery_required"),
])
def test_asset_execution_refuses_forged_b3_image_and_journal(
    tmp_path, part, key, value,
):
    h, plan, receipt = _b3_fpga_receipt_fixture(tmp_path)
    forged = {**receipt, part: {**receipt[part], key: value}}
    code = ("ASSET_EXECUTION_B3_IMAGE_MISMATCH"
            if key in {"fpga_image_id", "fpga_bin_sha256", "fpga_manifest_sha256"}
            else "ASSET_EXECUTION_B3_RECEIPT_MISMATCH")
    with pytest.raises(execution.AssetExecutionDenied, match=code):
        execution.validate_fpga_b3_receipt(h.co.paths.product_root, plan, forged)


def test_asset_execution_b3_binding_requires_authorized_fpga_plan(tmp_path):
    h, plan, receipt = _b3_fpga_receipt_fixture(tmp_path)
    for changed in (
        {**plan, "status": "NOT_AUTHORIZED"},
        {**plan, "package_kind": "python"},
        {**plan, "action": "shell"},
    ):
        with pytest.raises(execution.AssetExecutionDenied,
                           match="ASSET_EXECUTION_B3_PLAN_INVALID"):
            execution.validate_fpga_b3_receipt(
                h.co.paths.product_root, changed, receipt,
            )
