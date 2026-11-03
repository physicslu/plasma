"""Stage C-1: Runtime Job lease adapter + Package resource manifest (Host-only).

The real SiteManager (mock Sites) supplies the dispatch ``execution_scope``.
Executors are test callbacks; no Python/Native C Package is run, no Z2/FPGA/DUT.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager

import pytest

from plasma_core.config import PlasmaConfig, PPUConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_server.site_manager import SiteManager

from .test_ppu_asset_execution_gate1 import (
    JOB, PARTS, Owner, _ready_fixture, contract, execution, lease, with_resources,
)
from .test_ppu_bundle_v3_packages_contract import TARGET, bundle_v3

OK = {"schema": "plasma.ppu.package-resources.v1", "sites": [2], "max_runtime_s": 120}


def raw(value) -> bytes:
    return json.dumps(value).encode()


def config(tmp_path) -> PlasmaConfig:
    return PlasmaConfig(
        ppu=PPUConfig(id="ppu-a", facility_id="lab", model="test", display_name="PPU A"),
        server=ServerConfig(host="127.0.0.1", port=9900, max_supported_sites=8,
                            max_concurrent_jobs=1, max_queue_depth_per_site=16,
                            output_root=tmp_path / "out", log_root=tmp_path / "log"),
        sites=[SiteConfig(id=1, enabled=True, interface="mock"),
               SiteConfig(id=2, enabled=True, interface="mock"),
               SiteConfig(id=3, enabled=False, interface="mock")],
    )


def receipt(plan, **extra):
    return {"asset_set_sha256": plan["asset_set_sha256"],
            "package_identity_sha256": plan["package_identity_sha256"],
            "package_kind": plan["package_kind"], "status": "MOCK_NOT_RUN", **extra}


# --- plasma.ppu.package-resources.v1 ----------------------------------------------

def test_resources_manifest_positive():
    assert execution.validate_package_resources(raw(OK)) == OK
    none = dict(OK, sites=[])
    assert execution.validate_package_resources(raw(none))["sites"] == []


@pytest.mark.parametrize("value", [
    dict(OK, schema="plasma.ppu.package-resources.v0"),
    dict(OK, sites=[0]), dict(OK, sites=[65]), dict(OK, sites=[2, 1]), dict(OK, sites=[2, 2]),
    dict(OK, sites=list(range(1, 10))), dict(OK, sites=[True]), dict(OK, sites="2"),
    dict(OK, max_runtime_s=0), dict(OK, max_runtime_s=3601), dict(OK, max_runtime_s=1.5),
    dict(OK, max_runtime_s=True),
    dict(OK, devmem=True), dict(OK, shell="sh -c"), dict(OK, network=True),
    {k: v for k, v in OK.items() if k != "sites"}, [], "x",
])
def test_resources_manifest_rejects_bad_or_extra_claims(value):
    with pytest.raises(execution.AssetExecutionDenied, match="ASSET_EXECUTION_RESOURCES_INVALID"):
        execution.validate_package_resources(raw(value))


@pytest.mark.parametrize("data", [
    b'{"schema":"plasma.ppu.package-resources.v1","sites":[2],"sites":[1],"max_runtime_s":1}',
    b'{"schema":"plasma.ppu.package-resources.v1","sites":[2],"max_runtime_s":NaN}',
    b"\xff", b"", b"{" * 5000,
])
def test_resources_manifest_rejects_duplicate_nonfinite_or_oversized(data):
    with pytest.raises(execution.AssetExecutionDenied, match="ASSET_EXECUTION_RESOURCES_INVALID"):
        execution.validate_package_resources(data)


def test_bundle_accepts_resources_file_only_at_the_declared_path(tmp_path):
    archive, digest = bundle_v3(tmp_path / "ok", parts=with_resources(PARTS))
    contract.verify_host_only_artifact(archive, expected_sha256=digest,
                                       source_commit=None, target_profile=TARGET)
    # Native C may not smuggle any other config/data file.
    bad = [(i, k, r, {**f, "config/other.json": b"{}"}) if k == "native-c" else (i, k, r, f)
           for i, k, r, f in with_resources(PARTS)]
    archive, digest = bundle_v3(tmp_path / "bad", parts=bad)
    with pytest.raises(contract.UnifiedDeploymentError):
        contract.verify_host_only_artifact(archive, expected_sha256=digest,
                                           source_commit=None, target_profile=TARGET)


# --- prepare / dispatch -------------------------------------------------------------

@pytest.mark.parametrize("kind", ["python", "native-c"])
def test_executable_package_without_resources_cannot_be_planned(tmp_path, kind):
    co, requests, owner, _ = _ready_fixture(tmp_path, parts=PARTS)
    request = requests[kind]
    with pytest.raises(execution.AssetExecutionDenied, match="ASSET_EXECUTION_RESOURCES_REQUIRED"):
        execution.prepare_asset_execution(co.paths.product_root, request, **owner.kw(request))


def test_invalid_resources_in_installed_set_cannot_be_planned(tmp_path):
    co, requests, owner, _ = _ready_fixture(
        tmp_path, parts=with_resources(PARTS, raw=raw(dict(OK, sites=[0]))))
    request = requests["python"]
    with pytest.raises(execution.AssetExecutionDenied, match="ASSET_EXECUTION_RESOURCES_INVALID"):
        execution.prepare_asset_execution(co.paths.product_root, request, **owner.kw(request))


def test_plan_carries_identity_bound_resources_fpga_needs_none(tmp_path):
    co, requests, owner, _ = _ready_fixture(tmp_path)
    for kind in ("python", "native-c"):
        plan = execution.prepare_asset_execution(
            co.paths.product_root, requests[kind], **owner.kw(requests[kind]))
        assert plan["resources"] == OK
        assert any(p.endswith("config/plasma-package-resources.json") for p in plan["relative_files"])
    fpga = execution.prepare_asset_execution(
        co.paths.product_root, requests["fpga-image"], **owner.kw(requests["fpga-image"]))
    assert fpga["resources"] is None


def test_changing_resources_changes_identity_so_old_authorization_fails(tmp_path):
    co_a, req_a, owner, _ = _ready_fixture(tmp_path / "a")
    co_b, req_b, _, _ = _ready_fixture(
        tmp_path / "b", parts=with_resources(PARTS, raw=raw(dict(OK, sites=[1, 2]))))
    assert req_a["python"].package_identity_sha256 != req_b["python"].package_identity_sha256
    # Authorization issued for package A's identity cannot run package B.
    with pytest.raises(execution.AssetExecutionDenied, match="OWNER_AUTHORIZATION_PACKAGE_MISMATCH"):
        execution.prepare_asset_execution(
            co_b.paths.product_root, req_b["python"],
            authorization=owner.authorize(
                req_b["python"], package_identity_sha256=req_a["python"].package_identity_sha256),
            owner_credential=owner.credential)


def test_dispatch_denies_declared_site_outside_lease(tmp_path):
    co, requests, owner, _ = _ready_fixture(tmp_path)
    request = requests["python"]
    called = []
    with pytest.raises(execution.AssetExecutionDenied, match="ASSET_EXECUTION_SITE_NOT_LEASED"):
        execution.dispatch_asset_execution(
            co.paths.product_root, request, **owner.kw(request),
            execution_scope=lease(request, site_ids=(1,)),
            trusted_executors={"python": lambda plan: called.append(plan)})
    assert called == []


# --- SiteManager.package_action_scope ---------------------------------------------

def test_package_action_scope_is_ppu_exclusive_and_released(tmp_path):
    async def scenario():
        manager = SiteManager(config(tmp_path))
        with pytest.raises(PlasmaError):
            with manager.package_action_scope(JOB):
                pass  # not started
        await manager.start()
        try:
            with manager.package_action_scope(JOB) as held:
                assert held == {"job_id": JOB, "owner_kind": "package_action", "site_ids": [1, 2]}
                snap = manager.execution_lease_snapshot()
                assert snap["busy"] is True and snap["owner_kind"] == "package_action"
                with pytest.raises(PlasmaError) as busy:
                    manager.enqueue(JobRequest(site_id=1, operation=Operation.READ, job_id="other-job"))
                assert busy.value.code is ErrorCode.PPU_BUSY
                with pytest.raises(PlasmaError) as second:
                    with manager.package_action_scope("2" * 32):
                        pass
                assert second.value.code is ErrorCode.PPU_BUSY
                for quiesce in (lambda: manager.acquire_runtime_quiesce(2),
                                manager.acquire_asset_set_quiesce):
                    with pytest.raises(PlasmaError) as q:
                        quiesce()
                    assert q.value.code is ErrorCode.PPU_BUSY
            assert manager.execution_lease_snapshot()["busy"] is False
            # Released even when the Package Action fails.
            with pytest.raises(RuntimeError):
                with manager.package_action_scope(JOB):
                    raise RuntimeError("executor failed")
            assert manager.execution_lease_snapshot()["busy"] is False
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_package_action_scope_refuses_while_quiesced_or_bad_job_id(tmp_path):
    async def scenario():
        manager = SiteManager(config(tmp_path))
        await manager.start()
        try:
            for bad in ("", "A" * 32, "1" * 31, None, "g" * 32):
                with pytest.raises(PlasmaError) as exc:
                    with manager.package_action_scope(bad):
                        pass
                assert exc.value.code is ErrorCode.INVALID_ARGUMENT
            q = manager.acquire_runtime_quiesce(2)
            with pytest.raises(PlasmaError) as exc:
                with manager.package_action_scope(JOB):
                    pass
            assert exc.value.code is ErrorCode.PPU_BUSY
            manager.release_runtime_quiesce(q["token"])
            assert manager.execution_lease_snapshot()["busy"] is False
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_dispatch_through_real_site_manager_scope(tmp_path):
    co, requests, owner, _ = _ready_fixture(tmp_path / "set")

    async def scenario():
        manager = SiteManager(config(tmp_path / "rt"))
        await manager.start()
        try:
            seen = []

            def executor(plan):
                snap = manager.execution_lease_snapshot()
                seen.append((plan["resources"], snap["owner_kind"], snap["owner_id"]))
                return receipt(plan)

            request = requests["native-c"]
            result = execution.dispatch_asset_execution(
                co.paths.product_root, request, **owner.kw(request),
                execution_scope=lambda: manager.package_action_scope(request.job_id),
                trusted_executors={"native-c": executor})
            assert result["job_id"] == JOB and result["executor_result"]["status"] == "MOCK_NOT_RUN"
            assert seen == [(OK, "package_action", JOB)]
            assert manager.execution_lease_snapshot()["busy"] is False

            # A running programming Job blocks the Package Action entirely.
            manager._reserve_execution_job(
                JobRequest(site_id=1, operation=Operation.READ, job_id="prog-1", client_id="cli"))
            with pytest.raises(PlasmaError) as busy:
                execution.dispatch_asset_execution(
                    co.paths.product_root, request, **owner.kw(request),
                    execution_scope=lambda: manager.package_action_scope(request.job_id),
                    trusted_executors={"native-c": executor})
            assert busy.value.code is ErrorCode.PPU_BUSY and len(seen) == 1
            manager._release_execution_job("prog-1")

            # The Job lease must be for the authorized Job.
            with pytest.raises(execution.AssetExecutionDenied, match="JOB_LEASE_MISMATCH"):
                execution.dispatch_asset_execution(
                    co.paths.product_root, request, **owner.kw(request),
                    execution_scope=lambda: manager.package_action_scope("3" * 32),
                    trusted_executors={"native-c": executor})
            assert len(seen) == 1 and manager.execution_lease_snapshot()["busy"] is False

            # Declared Site 3 is disabled on this PPU: not leasable.
            co3, req3, owner3, _ = _ready_fixture(
                tmp_path / "s3", parts=with_resources(PARTS, raw=raw(dict(OK, sites=[3]))))
            with pytest.raises(execution.AssetExecutionDenied, match="SITE_NOT_LEASED"):
                execution.dispatch_asset_execution(
                    co3.paths.product_root, req3["python"], **owner3.kw(req3["python"]),
                    execution_scope=lambda: manager.package_action_scope(JOB),
                    trusted_executors={"python": executor})
            assert len(seen) == 1 and manager.execution_lease_snapshot()["busy"] is False
        finally:
            await manager.shutdown()
    asyncio.run(scenario())
