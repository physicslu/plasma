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

from .ppu_owner_authorization_fixture import OWNER_TOKEN, owner as owner_module
from .test_ppu_b3_z2_install_gate1 import b3_request, make_coordinator
from .test_ppu_bundle_v3_packages_contract import (
    PARTS, ROOT, bundle_v3, contract, TARGET, SOURCE,
)

modpath = ROOT / "scripts" / "ppu_asset_execution.py"
spec = importlib.util.spec_from_file_location("ppu_asset_execution_gate1", modpath)
assert spec and spec.loader
execution = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = execution
spec.loader.exec_module(execution)


DEVICE = "ppu-device-" + "a" * 24
JOB = "1" * 32


class Owner:
    """Paired-owner execute authorization for one Runtime Job (Host-only)."""

    credential = execution.OwnerCredential(device_id=DEVICE, credential=OWNER_TOKEN)

    def authorize(self, request, **overrides):
        claims = dict(
            credential=OWNER_TOKEN, action=owner_module.EXECUTE, device_id=DEVICE,
            subject_sha256=request.asset_set_sha256, transaction_id=request.job_id,
            package_identity_sha256=request.package_identity_sha256,
        )
        claims.update(overrides)
        return owner_module.issue(**claims)

    def kw(self, request, **overrides):
        return {"authorization": self.authorize(request, **overrides),
                "owner_credential": self.credential}


RESOURCES = b'{"schema":"plasma.ppu.package-resources.v1","sites":[2],"max_runtime_s":120}'


def with_resources(parts, raw=RESOURCES, kinds=("python", "native-c")):
    """Executable Packages declare their Sites/timeout (Stage C-1)."""
    out = []
    for package_id, kind, requires, files in parts:
        if kind in kinds:
            files = {**files, "config/plasma-package-resources.json": raw}
            if kind == "python":
                files.setdefault("python/main.py", b"print('NOT_EXECUTED_IN_C1')\n")
        out.append((package_id, kind, requires, files))
    return out


def lease(request, site_ids=(1, 2)):
    """Runtime Job lease for exactly this authorized Job."""
    @contextmanager
    def scope():
        yield {"job_id": request.job_id, "site_ids": list(site_ids)}
    return scope


def _ready_fixture(tmp_path, parts=None):
    archive, digest = bundle_v3(
        tmp_path / "source", parts=with_resources(PARTS) if parts is None else parts,
        mutate=lambda m: m.__setitem__("actions", ["install", "verify"]),
    )
    co = make_coordinator(tmp_path)
    staged = co.execute_bundle_v3_install(b3_request(archive, digest))
    assert staged["result"] == "PASS" and staged["fpga"] == "NOT_RUN"
    activated = co.activate_staged_asset_set(digest, quiescence_lease=nullcontext)
    assert activated["result"] == "PASS"
    assert activated["fpga"] == "NOT_RUN" and activated["ready"] is False

    bundle = contract.verify_host_only_artifact(
        archive, expected_sha256=digest,
        target_profile=TARGET,
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
            job_id=JOB,
        )
        for kind, p in by_kind.items()
    }
    if parts is None:
        assert set(requests) == {"python", "native-c", "fpga-image"}
    return co, requests, Owner(), archive


@pytest.mark.parametrize("kind,executor_name", [
    ("python", "trusted-python-runtime"),
    ("native-c", "trusted-native-runtime"),
    ("fpga-image", "existing-protected-fpga-loader"),
])
def test_one_authorized_execution_layer_for_all_types(tmp_path, kind, executor_name):
    co, requests, owner, _archive = _ready_fixture(tmp_path)
    plan = execution.prepare_asset_execution(
        co.paths.product_root, requests[kind], **owner.kw(requests[kind]),
    )
    assert plan["status"] == "AUTHORIZED_NOT_EXECUTED"
    assert plan["trusted_executor"] == executor_name
    assert plan["asset_set_sha256"] == requests[kind].asset_set_sha256
    assert plan["package_identity_sha256"] == requests[kind].package_identity_sha256
    assert plan["owner_authorization"]["status"] == "OWNER_AUTHORIZED"
    assert plan["owner_authorization"]["action"] == "asset.execute"
    assert plan["owner_authorization"]["transaction_id"] == JOB
    assert "mac" not in plan["owner_authorization"]
    assert plan["job_id"] == JOB
    assert plan["asset_executed"] is False
    assert plan["fpga_loaded"] is False
    assert plan["ready"] is False
    assert not (co.paths.product_root / "current").exists()
    assert not co.paths.systemd_root.exists()


@pytest.mark.parametrize("kind", ["python", "native-c", "fpga-image"])
def test_one_dispatch_contract_requires_trusted_runtime_lease_and_adapter(
    tmp_path, kind
):
    co, requests, owner, _archive = _ready_fixture(tmp_path)
    called = []
    hold = {"held": False}

    @contextmanager
    def owner_scope():
        assert hold["held"] is False
        hold["held"] = True
        try:
            yield {"job_id": JOB, "site_ids": [1, 2]}
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
            co.paths.product_root, requests[kind], **owner.kw(requests[kind]),
            trusted_executors={kind: fake_trusted_executor},
        )
    with pytest.raises(execution.AssetExecutionDenied,
                       match="ASSET_EXECUTION_TRUSTED_EXECUTOR_REQUIRED"):
        execution.dispatch_asset_execution(
            co.paths.product_root, requests[kind], **owner.kw(requests[kind]),
            execution_scope=owner_scope,
        )
    assert called == []
    result = execution.dispatch_asset_execution(
        co.paths.product_root, requests[kind], **owner.kw(requests[kind]),
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
    co, requests, owner, _archive = _ready_fixture(tmp_path)
    original = requests["fpga-image"]
    values = dict(original.__dict__)
    values.update(mutation)
    with pytest.raises(execution.AssetExecutionDenied, match=code):
        execution.prepare_asset_execution(
            co.paths.product_root, execution.AssetExecutionRequest(**values),
            **owner.kw(original),
        )


@pytest.mark.parametrize("overrides,code", [
    # Forged / wrong-device / other-Bundle / other-Job / other-Package /
    # other-stage authorizations never reach an executor.
    ({"credential": "forged-not-the-paired-credential-" + "x" * 8},
     "OWNER_AUTHORIZATION_INVALID"),
    ({"device_id": "ppu-device-" + "b" * 24}, "OWNER_AUTHORIZATION_DEVICE_MISMATCH"),
    ({"subject_sha256": "e" * 64}, "OWNER_AUTHORIZATION_SUBJECT_MISMATCH"),
    ({"transaction_id": "2" * 32}, "OWNER_AUTHORIZATION_TRANSACTION_MISMATCH"),
    ({"package_identity_sha256": "d" * 64}, "OWNER_AUTHORIZATION_PACKAGE_MISMATCH"),
    ({"action": "bundle.install", "package_identity_sha256": None},
     "OWNER_AUTHORIZATION_ACTION_MISMATCH"),
])
def test_asset_execution_requires_exact_owner_execute_authorization(
    tmp_path, overrides, code,
):
    co, requests, owner, _archive = _ready_fixture(tmp_path)
    request = requests["python"]
    called = []
    with pytest.raises(execution.AssetExecutionDenied, match=code):
        execution.dispatch_asset_execution(
            co.paths.product_root, request, **owner.kw(request, **overrides),
            execution_scope=lease(request),
            trusted_executors={"python": lambda plan: called.append(plan)},
        )
    assert called == []


def test_asset_execution_b2_b3_receipts_are_not_execute_authority(tmp_path):
    co, requests, owner, _archive = _ready_fixture(tmp_path)
    request = requests["native-c"]
    with pytest.raises(execution.AssetExecutionDenied, match="OWNER_AUTHORIZATION_REQUIRED"):
        execution.prepare_asset_execution(
            co.paths.product_root, request,
            authorization={"status": "OWNER_AUTHORIZED", "action": "bundle.admit"},
            owner_credential=owner.credential,
        )
    with pytest.raises(execution.AssetExecutionDenied,
                       match="ASSET_EXECUTION_OWNER_CREDENTIAL_REQUIRED"):
        execution.prepare_asset_execution(
            co.paths.product_root, request,
            authorization=owner.authorize(request), owner_credential=None,
        )


def test_asset_execution_busy_or_foreign_job_lease_never_dispatches(tmp_path):
    co, requests, owner, _archive = _ready_fixture(tmp_path)
    request = requests["fpga-image"]
    called = []

    @contextmanager
    def busy():
        raise RuntimeError("PPU_JOB_RUNNING")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="PPU_JOB_RUNNING"):
        execution.dispatch_asset_execution(
            co.paths.product_root, request, **owner.kw(request),
            execution_scope=busy,
            trusted_executors={"fpga-image": lambda plan: called.append(plan)},
        )

    @contextmanager
    def other_job():
        yield {"job_id": "9" * 32}

    for scope in (other_job, nullcontext):
        with pytest.raises(execution.AssetExecutionDenied,
                           match="ASSET_EXECUTION_JOB_LEASE_MISMATCH"):
            execution.dispatch_asset_execution(
                co.paths.product_root, request, **owner.kw(request),
                execution_scope=scope,
                trusted_executors={"fpga-image": lambda plan: called.append(plan)},
            )
    assert called == []


def test_asset_execution_corrupted_active_files_cannot_launch_any_kind(tmp_path):
    co, requests, owner, _archive = _ready_fixture(tmp_path)
    staged = co.paths.product_root / "assets" / "staged"
    package_root = staged / requests["fpga-image"].asset_set_sha256 / (
        "payload/packages/fpga-addon"
    )
    image = next(path for path in package_root.rglob("*.bin") if path.is_file())
    image.chmod(0o600)
    image.write_bytes(b"mutated")
    with pytest.raises(Exception, match="ASSET_SET_FILE_MISMATCH"):
        execution.prepare_asset_execution(
            co.paths.product_root, requests["native-c"], **owner.kw(requests["native-c"]),
        )


def test_asset_execution_denies_forged_adapter_receipt(tmp_path):
    co, requests, owner, _archive = _ready_fixture(tmp_path)
    def dishonest(_plan):
        return {"asset_set_sha256": "f" * 64,
                "package_identity_sha256": "f" * 64,
                "package_kind": "fpga-image"}
    with pytest.raises(execution.AssetExecutionDenied,
                       match="ASSET_EXECUTION_EXECUTOR_RECEIPT_UNTRUSTED"):
        execution.dispatch_asset_execution(
            co.paths.product_root, requests["fpga-image"], **owner.kw(requests["fpga-image"]),
            execution_scope=lease(requests["fpga-image"]),
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

    bundle = contract.verify_host_only_artifact(
        archive, expected_sha256=digest,
        target_profile=TARGET,
    )
    fpga = next(p for p in bundle.packages if p.kind == "fpga-image")
    request = execution.AssetExecutionRequest(
        asset_set_sha256=digest,
        package_id=fpga.id,
        package_version=fpga.version,
        package_kind=fpga.kind,
        package_identity_sha256=contract.bundle_package_identity(fpga),
        job_id=JOB,
    )
    plan = execution.prepare_asset_execution(
        h.co.paths.product_root, request, **Owner().kw(request),
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
