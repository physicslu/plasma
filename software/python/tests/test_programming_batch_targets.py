"""Host-only: the Manager Batch over a Target Set.

Real ``BundleProgrammingWorkflow`` + ``ProgrammingBatchCoordinator``; fake
Bootstrap coordinators and fake PPU Gateways, one per PPU. No PPU, FPGA or
DUT. A PASS here proves the admission, isolation, aggregation and recovery
contract only - never that eight Sites program in parallel, which nothing
here even attempts: execution is sequential by contract.

The Programming Routes shipped in ``data/opf`` declare Site 2 only, so the
multi-Site cases build a Route fixture under ``tmp_path``. Production route
data is never modified.
"""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from plasma_manager.programming import BundleProgrammingWorkflow, ProgrammingError
from plasma_manager.programming_batch import (
    ProgrammingBatchCoordinator, aggregate_outcome, migrate_batch_record,
    parse_policy, parse_targets,
)
from plasma_manager.server import PPUOperationGate
from plasma_opf import bundle_v3

from .test_bundle_programming_workflow import (
    ICPN, ROUTES, FakeCoordinator, FakeGateway, image,
)

FULL = ["erase", "program", "verify"]
ACTIVE_SHA = "e" * 64


def route_fixture(tmp_path, sites=(2, 3)):
    """The shipped Routes, re-declared over more than one Site.

    Only the Site list changes, which changes the Resource Set identity - so
    the fake PPU is told the new identity rather than the shipped one.
    """
    root = tmp_path / "routes"
    root.mkdir(parents=True, exist_ok=True)
    for name in ("z2-site2-stm32f103c8t6.json", "z2-site2-stm32f103c8t6-operations.json"):
        data = json.loads((ROUTES / name).read_text(encoding="utf-8"))
        data["profile"]["capabilities"]["sites"] = list(sites)
        (root / name).write_text(json.dumps(data), encoding="utf-8")
    operations = bundle_v3.load_route(root / "z2-site2-stm32f103c8t6-operations.json")
    return root, bundle_v3.resource_set_sha256(bundle_v3.resource_set_descriptor(operations))


class Registry:
    def __init__(self, aliases, lifecycle="commissioned"):
        self.aliases = dict(aliases)
        self.lifecycle = lifecycle

    def record_by_alias(self, alias):
        endpoint = self.aliases.get(alias)
        if endpoint is None:
            return None
        return SimpleNamespace(alias=alias, endpoint=endpoint, lifecycle=self.lifecycle)


class Coordinators:
    """One Bootstrap view per PPU, so one PPU's state cannot speak for another."""

    def __init__(self, per_alias):
        self.per_alias = per_alias

    def status(self, alias):
        return self.per_alias[alias].status(alias)

    def assets(self, alias):
        return self.per_alias[alias].assets(alias)

    def __getattr__(self, name):
        return getattr(next(iter(self.per_alias.values())), name)


def rig(tmp_path, *, aliases=("z2",), sites=(2, 3), spawn_batch=None, per_alias=None,
        **gateway_kw):
    root, resource_sha = route_fixture(tmp_path, sites)
    coordinators, gateways, endpoints = {}, {}, {}
    for alias in aliases:
        coordinator = FakeCoordinator(active_sha=ACTIVE_SHA)
        kw = {**gateway_kw, **(per_alias or {}).get(alias, {})}
        gateway = FakeGateway(image=image(), coordinator=coordinator,
                              resource_for=lambda _a, sha=resource_sha: sha, **kw)
        endpoint = f"http://192.0.2.{10 + len(endpoints)}:18080"
        coordinators[alias], gateways[alias], endpoints[alias] = coordinator, gateway, endpoint
    by_endpoint = {endpoints[alias]: gateways[alias] for alias in aliases}
    workflow = BundleProgrammingWorkflow(
        coordinator=Coordinators(coordinators), registry=Registry(endpoints),
        gateway_client_factory=lambda endpoint, timeout: by_endpoint[endpoint],
        gate=PPUOperationGate(), request_timeout_s=5.0, routes_root=root,
        journal_path=tmp_path / "runs.json",
        sleep=lambda _s: None, spawn=lambda target: target(), poll_interval_s=0.0)
    batches = ProgrammingBatchCoordinator(
        workflow, journal_path=tmp_path / "batches.json", sleep=lambda _s: None,
        spawn=spawn_batch or (lambda target: target()), poll_interval_s=0.0)
    return batches, workflow, gateways, coordinators


def body(targets, **extra):
    return {"icpn": ICPN, "targets": targets, "operations": FULL,
            "image_base64": base64.b64encode(image()).decode(),
            "image_filename": "app.bin", **extra}


def one(alias, *sites):
    return {"ppu_alias": alias, "site_ids": list(sites)}


def units_of(batch):
    return [(u["ppu_alias"], u["site_id"], u["outcome"], u["status"]) for u in batch["units"]]


# ---------------------------------------------------------------- Target Set

@pytest.mark.parametrize("targets, code", [
    ([], "invalid_request"),
    ("z2", "invalid_request"),
    ([{"ppu_alias": "z2"}], "invalid_request"),
    ([{"ppu_alias": "z2", "site_ids": []}], "invalid_request"),
    ([{"ppu_alias": "", "site_ids": [2]}], "invalid_request"),
    ([{"ppu_alias": "z2", "site_ids": [2, 2]}], "invalid_request"),
    ([{"ppu_alias": "z2", "site_ids": [0]}], "invalid_request"),
    ([{"ppu_alias": "z2", "site_ids": [True]}], "invalid_request"),
    ([one("z2", 2), one("z2", 3)], "invalid_request"),
])
def test_an_invalid_target_set_refuses_the_whole_batch(tmp_path, targets, code):
    batches, _w, gateways, _c = rig(tmp_path)
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(body(targets))
    assert caught.value.code == code
    assert batches._batches == {} and gateways["z2"].posts == []


def test_a_target_set_is_ordered_and_one_entry_per_ppu():
    parsed = parse_targets({"targets": [one("b", 3, 2), one("a", 2)]})
    assert parsed == ({"ppu_alias": "b", "site_ids": [3, 2]},
                      {"ppu_alias": "a", "site_ids": [2]})


# ------------------------------------------------------------------- policy

def test_the_stop_threshold_is_bounded_by_the_batch_site_count():
    for sites in (1, 2, 5):
        for threshold in range(1, sites + 1):
            policy = parse_policy({"stop_policy": {"kind": "failed_sites",
                                                   "threshold": threshold}}, sites)
            assert policy["stop_policy"]["threshold"] == threshold
        with pytest.raises(ProgrammingError):
            parse_policy({"stop_policy": {"kind": "failed_sites",
                                          "threshold": sites + 1}}, sites)


def test_a_threshold_a_batch_could_never_reach_is_refused(tmp_path):
    batches, _w, _g, _c = rig(tmp_path, aliases=("z2",))
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(body([one("z2", 2)],
                                 stop_policy={"kind": "failed_sites", "threshold": 2}))
    assert caught.value.code == "invalid_request" and batches._batches == {}


# --------------------------------------------------------------- aggregation

@pytest.mark.parametrize("outcomes, expected", [
    (["PASS"], "PASS"),
    (["PASS", "PASS"], "PASS"),
    (["PASS", "FAIL"], "FAIL"),
    (["FAIL", "OUTCOME_UNKNOWN"], "OUTCOME_UNKNOWN"),
    (["PASS", "PASS", "OUTCOME_UNKNOWN"], "OUTCOME_UNKNOWN"),
    (["PASS", "BLOCKED"], "PARTIAL"),
    (["PASS", None], "PARTIAL"),
    (["BLOCKED"], "BLOCKED"),
    (["BLOCKED", None], "BLOCKED"),
    ([None], "BLOCKED"),
])
def test_the_outcome_is_derived_by_priority(outcomes, expected):
    assert aggregate_outcome([{"outcome": o} for o in outcomes]) == expected


def test_no_number_of_passes_dilutes_one_unknown():
    units = [{"outcome": "PASS"} for _ in range(20)] + [{"outcome": "OUTCOME_UNKNOWN"}]
    assert aggregate_outcome(units) == "OUTCOME_UNKNOWN"


# ------------------------------------------------------------- multi-PPU runs

def test_two_ppus_each_run_their_own_sites(tmp_path):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"))
    started = batches.start_batch(body([one("z2", 2, 3), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    assert batch["outcome"] == "PASS" and batch["execution_status"] == "COMPLETED"
    assert units_of(batch) == [("z2", 2, "PASS", "FINISHED"), ("z2", 3, "PASS", "FINISHED"),
                               ("z2b", 2, "PASS", "FINISHED")]
    assert batch["counts"]["pass"] == 3 and batch["counts"]["sites"] == 3
    # Each Site is its own Job on its own PPU; nothing is shared but the Image.
    assert len(gateways["z2"].posts) == 2 and len(gateways["z2b"].posts) == 1
    keys = [a["job_key"] for u in batch["units"] for a in u["attempts"]]
    assert keys == [{"batch_id": batch["batch_id"], "ppu_alias": "z2", "site_id": 2, "attempt": 1},
                    {"batch_id": batch["batch_id"], "ppu_alias": "z2", "site_id": 3, "attempt": 1},
                    {"batch_id": batch["batch_id"], "ppu_alias": "z2b", "site_id": 2, "attempt": 1}]


def test_a_failing_ppu_does_not_stop_an_unrelated_one(tmp_path):
    batches, _w, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"),
                                    per_alias={"z2": {"job_final": "failed"}})
    started = batches.start_batch(body([one("z2", 2), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    assert batch["outcome"] == "FAIL"
    assert units_of(batch) == [("z2", 2, "FAIL", "FINISHED"), ("z2b", 2, "PASS", "FINISHED")]
    assert len(gateways["z2b"].posts) == 1  # the unrelated PPU still ran


def test_an_unknown_outcome_latches_its_own_ppu_only(tmp_path):
    batches, workflow, gateways, _c = rig(
        tmp_path, aliases=("z2", "z2b"), per_alias={"z2": {"post_raises": True}})
    started = batches.start_batch(body([one("z2", 2, 3), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    # Safety outranks the PASS next to it.
    assert batch["outcome"] == "OUTCOME_UNKNOWN"
    assert units_of(batch) == [
        ("z2", 2, "OUTCOME_UNKNOWN", "FINISHED"),
        ("z2", 3, None, "SKIPPED"),          # that PPU's remaining Site
        ("z2b", 2, "PASS", "FINISHED"),      # the other PPU continued
    ]
    assert batch["units"][1]["reason"].startswith("PPU_LATCHED_")
    # The lost submission was attempted exactly once and never repeated.
    assert len(gateways["z2"].posts) == 1 and len(gateways["z2b"].posts) == 1
    assert workflow._unknown_latched("z2") is not None
    assert workflow._unknown_latched("z2b") is None


def test_a_blocked_ppu_leaves_the_rest_of_the_batch_running(tmp_path):
    batches, _w, gateways, coordinators = rig(tmp_path, aliases=("z2", "z2b"))
    original = coordinators["z2"].assets

    def recovery_required(alias):
        return {**original(alias), "state": "RECOVERY_REQUIRED"}

    coordinators["z2"].assets = recovery_required
    started = batches.start_batch(body([one("z2", 2), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    # Some Targets ran and one never could: that is PARTIAL, not FAIL.
    assert batch["outcome"] == "PARTIAL"
    assert units_of(batch) == [("z2", 2, "BLOCKED", "BLOCKED"), ("z2b", 2, "PASS", "FINISHED")]
    assert batch["units"][0]["reason"] == "ADMISSION_PPU_RECOVERY_REQUIRED"
    assert gateways["z2"].posts == [] and len(gateways["z2b"].posts) == 1


def test_a_blocked_target_spends_no_retry_budget_and_misses_no_threshold(tmp_path):
    batches, _w, _g, coordinators = rig(tmp_path, aliases=("z2", "z2b"),
                                        per_alias={"z2b": {"job_final": "failed"}})
    original = coordinators["z2"].assets
    coordinators["z2"].assets = lambda alias: {**original(alias), "state": "RECOVERY_REQUIRED"}
    started = batches.start_batch(body(
        [one("z2", 2), one("z2b", 2)], retry_limit=0,
        stop_policy={"kind": "failed_sites", "threshold": 2}))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    # One BLOCKED and one FAIL: the threshold of 2 definite failures is NOT met.
    assert [u["outcome"] for u in batch["units"]] == ["BLOCKED", "FAIL"]
    assert batch["units"][0]["attempts"] == []
    assert batch["outcome"] == "FAIL"


def test_no_target_ready_refuses_the_batch_and_records_nothing(tmp_path):
    batches, _w, gateways, coordinators = rig(tmp_path, aliases=("z2",))
    original = coordinators["z2"].assets
    coordinators["z2"].assets = lambda alias: {**original(alias), "state": "RECOVERY_REQUIRED"}
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(body([one("z2", 2)]))
    # With nothing left to protect, partial admission has nothing to do, and
    # the reason keeps the code it has always been refused with.
    assert caught.value.code == "ppu_recovery_required"
    assert batches._batches == {} and gateways["z2"].posts == []


def test_an_unknown_target_refuses_the_whole_batch(tmp_path):
    batches, _w, gateways, _c = rig(tmp_path, aliases=("z2",))
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(body([one("z2", 2), one("absent", 2)]))
    assert caught.value.code == "ppu_not_found"
    assert batches._batches == {} and gateways["z2"].posts == []


def test_the_stop_policy_counts_sites_across_ppus(tmp_path):
    batches, _w, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"), job_final="failed")
    started = batches.start_batch(body(
        [one("z2", 2, 3), one("z2b", 2)], retry_limit=0,
        stop_policy={"kind": "failed_sites", "threshold": 2}))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    assert [u["outcome"] for u in batch["units"]] == ["FAIL", "FAIL", None]
    assert batch["units"][2]["reason"] == "STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED"
    assert len(gateways["z2"].posts) == 2 and gateways["z2b"].posts == []


# ------------------------------------------------------------- resource reuse

def test_the_bundle_is_built_once_for_every_site_behind_one_route(tmp_path):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"))
    before = workflow._bundle_builds
    started = batches.start_batch(body([one("z2", 2, 3), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    assert batch["outcome"] == "PASS"
    # One Route and one Image: built once, reused for all three Sites.
    assert workflow._bundle_builds == before + 1
    # Reuse is of the computation only - every Site still got its own plan,
    # Job Binding and Job.
    bindings = [a["job_binding_sha256"] for u in batch["units"] for a in u["attempts"]]
    plans = [a["plan_id"] for u in batch["units"] for a in u["attempts"]]
    assert len(set(plans)) == 3
    assert len(set(bindings)) == 2  # Site 2 on two PPUs shares nothing but its Site


# ------------------------------------------------------- compatibility entry

def test_the_alias_entry_is_the_same_engine_and_the_same_record(tmp_path):
    batches, _w, gateways, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    started = batches.start(
        "z2", {"icpn": ICPN, "site_id": 2, "operations": FULL,
               "image_base64": base64.b64encode(image()).decode(),
               "image_filename": "app.bin", "retry_limit": 0})
    batch = batches.status("z2", started["batch"]["batch_id"])["batch"]
    assert batch["outcome"] == "PASS"
    assert batch["targets"] == [{"ppu_alias": "z2", "site_ids": [2]}]
    # The projection the alias-scoped entry has always returned.
    assert batch["ppu_alias"] == "z2" and batch["site_id"] == 2
    assert len(batch["attempts"]) == 1
    # The canonical resource reads the very same Batch.
    assert batches.status_batch(batch["batch_id"])["batch"]["batch_id"] == batch["batch_id"]


def test_a_multi_ppu_batch_is_not_readable_through_the_alias_entry(tmp_path):
    batches, _w, _g, _c = rig(tmp_path, aliases=("z2", "z2b"))
    started = batches.start_batch(body([one("z2", 2), one("z2b", 2)]))
    batch_id = started["batch"]["batch_id"]
    with pytest.raises(ProgrammingError) as caught:
        batches.status("z2", batch_id)
    assert caught.value.code == "programming_batch_not_found"
    assert batches.status_batch(batch_id)["batch"]["batch_id"] == batch_id


def test_the_alias_entry_refuses_a_target_set(tmp_path):
    batches, _w, _g, _c = rig(tmp_path, aliases=("z2",))
    with pytest.raises(ProgrammingError) as caught:
        batches.start("z2", body([one("z2", 2)]))
    assert caught.value.code == "invalid_request" and batches._batches == {}


# --------------------------------------------------- journal and crash recovery

def test_a_v1_journal_is_migrated_on_read_and_its_bytes_are_kept(tmp_path):
    batches, workflow, _g, _c = rig(tmp_path, aliases=("z2",))
    legacy = {
        "schema": "plasma.manager.programming-batch-journal.v1",
        "batches": [{
            "schema": "plasma.manager.programming-batch.v1",
            "batch_id": "a" * 32, "ppu_alias": "z2", "site_id": 2, "start_id": None,
            "operations": FULL, "source": "image", "icpn": ICPN,
            "policy": {"repeat": 1, "retry_limit": 0, "stop_policy": {"kind": "never"}},
            "state": "finished", "outcome": "PASS", "reason": None,
            "stop_requested": False,
            "attempts": [{"attempt": 1, "plan_id": "p", "run_id": "r", "job_id": "j",
                          "job_binding_sha256": "b", "state": "finished",
                          "outcome": "PASS", "reason": None, "safe_off": True,
                          "retry": None, "started_at": "t", "finished_at": "t"}],
            "created_at": "t", "updated_at": "t",
        }],
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    raw = path.read_text(encoding="utf-8")
    reloaded = ProgrammingBatchCoordinator(workflow, journal_path=path)
    batch = reloaded.status("z2", "a" * 32)["batch"]
    assert batch["targets"] == [{"ppu_alias": "z2", "site_ids": [2]}]
    assert batch["outcome"] == "PASS" and batch["migrated_from"].endswith("batch.v1")
    assert batch["units"][0]["attempts"][0]["job_key"] == {
        "batch_id": "a" * 32, "ppu_alias": "z2", "site_id": 2, "attempt": 1}
    # The original evidence is kept, unmodified, beside the migrated journal.
    assert (tmp_path / "legacy.json.v1").read_text(encoding="utf-8") == raw
    assert json.loads(path.read_text(encoding="utf-8"))["schema"].endswith("journal.v2")


def test_a_v1_stop_moves_from_the_outcome_to_the_execution_status():
    migrated = migrate_batch_record({
        "batch_id": "b" * 32, "ppu_alias": "z2", "site_id": 2, "state": "finished",
        "outcome": "STOPPED", "reason": "STOP_REQUESTED_NOTHING_SUBMITTED",
        "stop_requested": True, "attempts": [], "operations": FULL,
        "created_at": "t", "updated_at": "t",
    })
    assert migrated["execution_status"] == "STOPPED"
    assert migrated["outcome"] == "BLOCKED"          # nothing executed
    assert migrated["units"][0]["outcome"] is None   # STOPPED was never a Target outcome


def test_a_restart_judges_every_site_and_resubmits_nothing(tmp_path):
    held = []
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"),
                                          spawn_batch=held.append)
    workflow.spawn = held.append
    started = batches.start_batch(body([one("z2", 2, 3), one("z2b", 2)]))
    batch_job = held.pop()

    class Died(BaseException):
        pass

    batches.sleep = lambda _s: (_ for _ in ()).throw(Died())
    with pytest.raises(Died):
        batch_job()

    reloaded = ProgrammingBatchCoordinator(workflow, journal_path=tmp_path / "batches.json")
    batch = reloaded.status_batch(started["batch"]["batch_id"])["batch"]
    # Site 2 of z2 was in flight: not provably unsent, so never BLOCKED.
    # The Sites after it were never reached: provably unsent, so BLOCKED.
    assert [u["outcome"] for u in batch["units"]] == [
        "OUTCOME_UNKNOWN", "BLOCKED", "BLOCKED"]
    assert batch["units"][0]["reason"] == "MANAGER_RESTARTED_DURING_ATTEMPT"
    assert batch["units"][1]["reason"] == "MANAGER_RESTARTED_BEFORE_SUBMISSION"
    assert batch["outcome"] == "OUTCOME_UNKNOWN"
    assert gateways["z2b"].posts == []  # nothing was submitted for the other PPU


def test_a_stop_mid_batch_leaves_the_running_site_alone_and_queues_nothing(tmp_path):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"))
    original = gateways["z2"].relay
    seen = {}

    def relay(method, path, **kw):
        # The operator presses stop while the first Site's Job is running.
        if method == "GET" and path.startswith("/api/status?job=") and not seen:
            batch_id = next(iter(batches._batches))
            seen["view"] = batches.request_stop_batch(batch_id, {"stop": "STOP_QUEUING"})
        return original(method, path, **kw)

    gateways["z2"].relay = relay
    started = batches.start_batch(body([one("z2", 2, 3), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    assert seen["view"]["batch"]["stop_requested"] is True
    assert seen["view"]["batch"]["outcome"] is None  # the running attempt is not cut
    # The running Site finished for real; every Site after it queued nothing.
    assert units_of(batch) == [("z2", 2, "PASS", "FINISHED"),
                               ("z2", 3, None, "SKIPPED"),
                               ("z2b", 2, None, "SKIPPED")]
    assert all(u["reason"] == "STOP_REQUESTED_NOTHING_SUBMITTED" for u in batch["units"][1:])
    assert batch["execution_status"] == "STOPPED" and batch["outcome"] == "PARTIAL"
    assert len(gateways["z2"].posts) == 1 and gateways["z2b"].posts == []
    assert workflow._active_run("z2") is None
