"""Host-only WO-2 F2 M2: Batch-once preparation and PPU Verified Resource Snapshot.

Manager: real ``BundleProgrammingWorkflow`` + ``ProgrammingBatchCoordinator``
over the fake multi-Site Gateway / Bootstrap of the Batch tests. Calls are
COUNTED (never timed): what a Batch prepares once, what every Cycle still
reads. PPU: the real ``ppu_asset_set`` over a synthetic B3-staged Set, and the
real C-3 Runtime stack for Job Binding admission.

No SWPC, Z2, PL, DUT or OpenOCD hardware is touched; a PASS here is software
evidence only, never a Z2 latency measurement.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from plasma_manager import programming as wf
from plasma_opf import bundle_v3

from .test_ofe1b_resource_reuse_job_image import (
    FW_A, FW_B, assets, c3_route, job_body, route, route_stack, stage_bundle, submit,
)
from .test_c3_rest_flash_cycle import run, short_tmp
from .test_programming_batch_repeat import ScriptedGateway
from .test_programming_batch_targets import rig, with_start

WAIT = 20.0


# ------------------------------------------------------------------ Manager
class Counted:
    """A Batch on the fake PPU with every relevant call counted."""

    def __init__(self, tmp_path, *, sites=(1,), script=None, legacy=False, **policy):
        pending: list = []
        self.batches, self.workflow, gateways, coordinators = rig(
            tmp_path, sites=sites, spawn_batch=pending.append)
        base = gateways["z2"]
        self.gateway = ScriptedGateway(script or {}, image=base.image,
                                       coordinator=base.coordinator,
                                       resource_for=base.resource_for)
        self.bootstrap = coordinators["z2"]
        self.http = Counter()
        relay = self.gateway.relay

        def counted(method, path, **kw):
            self.http[f"{method} {path.split('=')[0]}"] += 1
            return relay(method, path, **kw)

        self.gateway.relay = counted
        self.workflow.gateway_client_factory = lambda _e, _t: self.gateway
        self.batches.sleep = lambda _s: time.sleep(0.001)
        self.local = Counter()
        for name in ("_parse_request", "routes", "prepare"):
            self._count(name)
        if legacy:
            # The pre-M2 call shape: every Cycle plans from scratch.
            plan = self.workflow.plan
            self.workflow.plan = lambda alias, body, **_kw: plan(alias, body)
        started = self.batches.start_batch(with_start(
            self.workflow, [{"ppu_alias": "z2", "site_ids": list(sites)}],
            replace_ic_before_next_cycle=False, **policy))
        self.batch_id = started["batch"]["batch_id"]
        self.run_batch = pending.pop()

    def _count(self, name):
        original = getattr(self.workflow, name)

        def wrapper(*args, **kwargs):
            self.local[name] += 1
            return original(*args, **kwargs)

        setattr(self.workflow, name, wrapper)

    def run(self):
        self.run_batch()
        return self.batches.status_batch(self.batch_id)["batch"]

    def bootstrap_calls(self):
        return Counter(self.bootstrap.calls)

    def cycles(self):
        records = self.batches.cycle_records(self.batch_id, 0, 1000)["records"]
        return [a for r in records if r["type"] == "cycle" for a in r["attempts"]]


@pytest.mark.parametrize("repeat", [3, 100])
def test_immutable_preparation_runs_once_per_batch_not_per_cycle(tmp_path, repeat):
    b = Counted(tmp_path, repeat=repeat)
    batch = b.run()
    assert batch["outcome"] == "PASS" and batch["cycles"]["pass"] == repeat
    # Batch-once: one Route load / resolution, one Image decode for the
    # preparation (+1 for the Batch specification check), one Bundle build.
    assert b.local["prepare"] == 1 and b.local["routes"] == 1
    assert b.local["_parse_request"] == 2 and b.workflow._bundle_builds == 1
    # ...while every Cycle keeps its own plan, start, run, Binding and Job.
    attempts = b.cycles()
    assert len(attempts) == repeat
    for key in ("plan_id", "run_id", "job_id"):
        assert len({a[key] for a in attempts}) == repeat
    assert len(b.gateway.posts) == repeat
    assert all(p["job_binding"]["site_id"] == 1 for p in b.gateway.posts)


@pytest.mark.parametrize("repeat", [3, 20])
def test_per_cycle_call_counts_before_and_after(tmp_path, repeat):
    """M3: one assets read and one reservation pair per PPU/Batch."""
    b = Counted(tmp_path / "after", repeat=repeat)
    assert b.run()["outcome"] == "PASS"
    calls = b.bootstrap_calls()
    assert calls["assets"] == 1 and calls["status"] == repeat
    assert b.http["GET /api/status?site"] == 3 * repeat + 1
    assert b.http["GET /api/health/ready"] == 3 * repeat
    assert b.http["POST /api/resource-reservations"] == 2
    assert b.local["routes"] == 1 and b.local["_parse_request"] == 2


def test_two_sites_share_one_preparation_with_their_own_bindings(tmp_path):
    b = Counted(tmp_path, sites=(1, 2), repeat=3)
    batch = b.run()
    assert batch["outcome"] == "PASS" and batch["cycles"]["pass"] == 6
    assert b.local["prepare"] == 1 and b.workflow._bundle_builds == 1
    by_site = Counter(p["job_binding"]["site_id"] for p in b.gateway.posts)
    assert by_site == {1: 3, 2: 3}
    resources = {p["job_binding"]["resource_set_sha256"] for p in b.gateway.posts}
    assert len(resources) == 1


def test_eight_sites_have_no_global_cycle_barrier(tmp_path):
    """A Site held in its own admission never holds the other seven."""
    sites = tuple(range(1, 9))
    b = Counted(tmp_path, sites=sites, repeat=3)
    original = b.workflow.target_block
    others_done, held = threading.Event(), []

    def slow_site_eight(alias, site, **kw):
        unit = b.batches._batches[b.batch_id]["units"][site - 1]
        if site == 8 and unit["cycle"]["settled"] == 1 and not held:
            held.append(site)
            assert others_done.wait(WAIT), "healthy Sites waited for Site 8"
        return original(alias, site, **kw)

    b.workflow.target_block = slow_site_eight
    runner = threading.Thread(target=b.run, daemon=True)
    runner.start()
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        units = b.batches._batches[b.batch_id]["units"]
        if all(u["cycle"]["settled"] == 3 for u in units[:7]):
            break
        time.sleep(0.005)
    seven_done = all(u["cycle"]["settled"] == 3 for u in b.batches._batches[b.batch_id]["units"][:7])
    site_eight = b.batches._batches[b.batch_id]["units"][7]["cycle"]["settled"]
    others_done.set()
    runner.join(WAIT)
    assert held == [8] and seven_done and site_eight == 1
    batch = b.batches.status_batch(b.batch_id)["batch"]
    assert batch["outcome"] == "PASS" and batch["cycles"]["pass"] == 24
    # Eight concurrent first Cycles still prepared exactly once.
    assert b.local["prepare"] == 1 and b.workflow._bundle_builds == 1


def test_outcome_unknown_is_never_resent_with_preparation(tmp_path):
    b = Counted(tmp_path, script={1: ["success", "lost"]}, repeat=3)
    batch = b.run()
    assert batch["outcome"] == "OUTCOME_UNKNOWN" and len(b.gateway.posts) == 2
    assert b.local["prepare"] == 1


def test_unverified_safe_off_never_starts_the_next_cycle(tmp_path):
    b = Counted(tmp_path, script={1: ["unsafe"]}, repeat=3)
    batch = b.run()
    unit = batch["units"][0]
    assert unit["reason"].startswith("CYCLE_NOT_RELEASED_SAFE_OFF_NOT_VERIFIED")
    assert len(b.gateway.posts) == 1


def test_resource_change_after_plan_is_refused_before_submit(tmp_path):
    """Reused admission evidence is never Job authority: the pre-submit read
    re-proves the PPU Resource identity, and a change stops the POST."""
    b = Counted(tmp_path, repeat=1)
    plan = b.workflow.plan

    def then_change(alias, body, **kw):
        result = plan(alias, body, **kw)
        b.gateway.resource_for = lambda _active: "e" * 64
        return result

    b.workflow.plan = then_change
    batch = b.run()
    assert batch["outcome"] in ("FAIL", "BLOCKED") and b.gateway.posts == []
    assert batch["units"][0]["reason"] == "RESOURCE_IDENTITY_NOT_CONFIRMED"


def _plan_body(site=1, image=FW_A):
    import base64
    from .test_programming_batch_targets import ICPN, FULL
    return {"icpn": ICPN, "site_id": site, "operations": FULL,
            "image_base64": base64.b64encode(image).decode(), "image_filename": "app.bin"}


def test_route_bytes_or_request_change_prepares_again(tmp_path):
    _batches, workflow, _g, _c = rig(tmp_path, sites=(1,))
    holder = wf.BatchPreparation()
    first = workflow._prepared_for(holder, _plan_body(1))
    assert workflow._prepared_for(holder, _plan_body(2)) is first  # Site is not spec
    route_file = next(workflow.routes_root.glob("*.json"))
    route_file.write_text(route_file.read_text() + "\n")  # bytes changed
    second = workflow._prepared_for(holder, _plan_body(1))
    assert second is not first and holder.preparations == 2
    other = workflow._prepared_for(holder, _plan_body(1, image=FW_B))
    assert holder.preparations == 3
    assert other.resources[4]["sha256"] != first.resources[4]["sha256"]


def test_concurrent_lanes_prepare_once_and_see_one_result(tmp_path):
    _batches, workflow, _g, _c = rig(tmp_path, sites=(1,))
    holder = wf.BatchPreparation()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda s: workflow._prepared_for(holder, _plan_body(s)),
                                range(1, 9)))
    assert holder.preparations == 1 and all(r is results[0] for r in results)


@pytest.mark.parametrize("case", ["stale", "other_site", "other_alias", "absent"])
def test_unusable_evidence_falls_back_to_fresh_reads(tmp_path, case):
    _batches, workflow, gateways, coordinators = rig(tmp_path, sites=(1, 2))
    workflow.monotonic = clock = type("Clock", (), {"t": 100.0, "__call__": lambda s: s.t})()
    evidence: dict = {}
    assert workflow.target_block("z2", 1, evidence=evidence) is None
    assert evidence["site"] == 1 and evidence["assets"]["state"] == "ACTIVE"
    if case == "stale":
        clock.t += wf.PLAN_EVIDENCE_MAX_AGE_S + 0.1
    elif case == "other_alias":
        evidence["alias"] = "peer"
    used = None if case == "absent" else evidence
    site = 2 if case == "other_site" else 1
    coordinators["z2"].calls.clear()
    workflow.plan("z2", _plan_body(site), preparation=wf.BatchPreparation(), evidence=used)
    assert coordinators["z2"].calls == ["status", "assets"]


def test_fresh_evidence_skips_only_the_duplicate_reads(tmp_path):
    _batches, workflow, _g, coordinators = rig(tmp_path, sites=(1,))
    evidence: dict = {}
    assert workflow.target_block("z2", 1, evidence=evidence) is None
    coordinators["z2"].calls.clear()
    plan = workflow.plan("z2", _plan_body(1), preparation=wf.BatchPreparation(),
                         evidence=evidence)["plan"]
    # Platform status is still read by the plan itself.
    assert coordinators["z2"].calls == ["status"]
    assert plan["resource"]["reuse"] is True and plan["job_binding"]["site_id"] == 1


def test_a_blocked_verdict_leaves_no_evidence(tmp_path):
    _batches, workflow, gateways, _c = rig(tmp_path, sites=(1,))
    gateways["z2"].busy = True
    evidence = {"alias": "z2", "site": 1}
    assert workflow.target_block("z2", 1, evidence=evidence) is not None
    assert evidence == {}


# ---------------------------------------------------------------------- PPU
@pytest.fixture
def staged(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "_resource_snapshots", {})
    built = bundle_v3.build_user_image_bundle(route(), FW_A)
    stage_bundle(tmp_path, built)
    return tmp_path, built


@pytest.fixture
def verifications(monkeypatch):
    calls = []
    original = assets.verify_staged

    def counted(product_root, sha):
        calls.append(sha)
        return original(product_root, sha)

    monkeypatch.setattr(assets, "verify_staged", counted)
    return calls


def test_snapshot_hit_verifies_fully_once_and_returns_the_same_identity(staged, verifications):
    root, built = staged
    first = assets.read_active_resource_identity(root)
    assert len(verifications) == 2  # miss: verification brackets the derivation
    for _ in range(5):
        assert assets.read_active_resource_identity(root) == first
    assert len(verifications) == 2 + 5  # hit: one FULL verification per call
    assert first["resource_set_sha256"] == built.resource_set_sha256
    # Consumers cannot mutate the Snapshot.
    first["resource_set"]["packages"].clear()
    assert assets.read_active_resource_identity(root)["resource_set"]["packages"]


def test_different_profile_or_active_switch_never_uses_another_snapshot(staged):
    root, built = staged
    a = assets.read_active_resource_identity(root)
    other = bundle_v3.build_user_image_bundle(route(driver_abi="plasma_swd:6"), FW_A)
    stage_bundle(root, other, generation=2)
    b = assets.read_active_resource_identity(root)
    assert b["asset_set_sha256"] == other.archive_sha256 != a["asset_set_sha256"]
    assert b["resource_set_sha256"] != a["resource_set_sha256"]
    assert b["generation"] == 2 and len(assets._resource_snapshots) == 2


def test_generation_change_is_reported_from_the_fresh_read(staged):
    root, built = staged
    assets.read_active_resource_identity(root)
    stage_bundle(root, built, generation=7)  # same Set re-activated (B3 / recovery)
    assert assets.read_active_resource_identity(root)["generation"] == 7


def test_tamper_with_same_size_and_mtime_fails_after_a_hit(staged):
    root, built = staged
    assets.read_active_resource_identity(root)
    stage = root / "assets/staged" / built.archive_sha256
    victim = next(p for p in (stage / "payload/packages").rglob("*.json"))
    info = victim.stat()
    raw = bytearray(victim.read_bytes())
    raw[-2] = ord(" ") if raw[-2] != ord(" ") else ord("\t")
    victim.write_bytes(bytes(raw))
    os.utime(victim, ns=(info.st_atime_ns, info.st_mtime_ns))
    assert victim.stat().st_size == info.st_size and victim.stat().st_mtime_ns == info.st_mtime_ns
    with pytest.raises(assets.AssetSetError, match="ASSET_SET_FILE_MISMATCH"):
        assets.read_active_resource_identity(root)


@pytest.mark.parametrize("target", ["file", "staged_dir"])
def test_symlink_or_path_replacement_fails_after_a_hit(staged, tmp_path_factory, target):
    root, built = staged
    assets.read_active_resource_identity(root)
    stage = root / "assets/staged" / built.archive_sha256
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    if target == "file":
        victim = next((stage / "payload/packages").rglob("*.json"))
        copy = elsewhere / victim.name
        shutil.copy2(victim, copy)
        victim.unlink()
        victim.symlink_to(copy)
    else:
        moved = elsewhere / "set"
        shutil.move(str(stage), moved)
        stage.symlink_to(moved, target_is_directory=True)
    with pytest.raises(assets.AssetSetError):
        assets.read_active_resource_identity(root)


def test_restart_or_disabled_snapshot_derives_again_with_the_same_result(staged, verifications,
                                                                          monkeypatch):
    root, _built = staged
    first = assets.read_active_resource_identity(root)
    assets._resource_snapshots.clear()  # Runtime restart: memory only
    assert assets.read_active_resource_identity(root) == first
    monkeypatch.setattr(assets, "RESOURCE_SNAPSHOT_MAX", 0)
    assets._resource_snapshots.clear()
    verifications.clear()
    assert assets.read_active_resource_identity(root) == first
    assert len(verifications) == 2 and assets._resource_snapshots == {}


def test_manifest_swapped_during_derivation_is_never_stored(staged, monkeypatch):
    root, built = staged
    manifest = root / "assets/staged" / built.archive_sha256 / "manifest.json"
    original = assets._verified_active
    calls = []

    def swap_after_verification(product_root):
        result = original(product_root)
        calls.append(1)
        if len(calls) == 1:
            manifest.write_bytes(manifest.read_bytes() + b" ")
        return result

    monkeypatch.setattr(assets, "_verified_active", swap_after_verification)
    with pytest.raises(assets.AssetSetError, match="ACTIVE_SET_CHANGED"):
        assets.read_active_resource_identity(root)
    assert assets._resource_snapshots == {}


def test_concurrent_status_reads_agree_and_store_one_snapshot(staged):
    root, _built = staged
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _i: assets.read_active_resource_identity(root),
                                range(32)))
    assert all(r == results[0] for r in results)
    assert len(assets._resource_snapshots) == 1


def test_runtime_loads_the_helper_once_and_a_snapshot_never_admits_a_bad_binding():
    async def scenario():
        with short_tmp() as folder:
            stack, built = route_stack(folder)
            async with stack:
                reader = stack.manager._active_asset_set_reader
                resolver = stack.manager._active_resource_resolver
                assert reader.func.__globals__ is resolver.func.__globals__
                snapshots = resolver.func.__globals__["_resource_snapshots"]
                resource = bundle_v3.resource_set_descriptor(c3_route())
                _status, ppu = await stack.api("GET", "/api/status?site=2")
                assert ppu["ppu"]["active_resources"]["state"] == "VERIFIED"
                assert len(snapshots) == 1  # the Snapshot is warm
                for path, value in ((("job_binding", "resource_set_sha256"), "0" * 64),
                                    (("job_binding", "site_id"), 3),
                                    (("profile",), "other-profile")):
                    body = json.loads(json.dumps(job_body(resource, FW_A)))
                    target = body
                    for part in path[:-1]:
                        target = target[part]
                    target[path[-1]] = value
                    status, refused = await submit(stack, body)
                    assert status != 202, (path, refused)
                assert stack.sim.argvs == []
                status, job = await submit(stack, job_body(resource, FW_A))
                assert status == 202 and job["state"] == "success", job
                assert len(stack.sim.argvs) == 1
    run(scenario())
