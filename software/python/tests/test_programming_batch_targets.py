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
import hashlib
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
        platform_gate=None, **gateway_kw):
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
        workflow, journal_path=tmp_path / "batches.json", platform_gate=platform_gate,
        sleep=lambda _s: None,
        spawn=spawn_batch or (lambda target: target()), poll_interval_s=0.0)
    return batches, workflow, gateways, coordinators


def body(targets, **extra):
    return {"icpn": ICPN, "targets": targets, "operations": FULL,
            "image_base64": base64.b64encode(image()).decode(),
            "image_filename": "app.bin", **extra}


def with_start(workflow, targets, **extra):
    """A canonical Batch body carrying the Manager-issued start it must have.

    The start is issued for the Batch's first Target. Which PPU issued it is
    deliberately not what the Manager validates against the Target Set order
    - that is its own test below.
    """
    if "start_id" not in extra:
        extra["start_id"] = workflow.issue_batch_start(
            targets[0]["ppu_alias"], {"kind": "batch"})["start"]["start_id"]
    return body(targets, **extra)


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
    batches, workflow, gateways, _c = rig(tmp_path)
    # Carry a real start so the refusal is about the Target Set, nothing else.
    start_id = workflow.issue_batch_start("z2", {"kind": "batch"})["start"]["start_id"]
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(with_start(workflow, targets, start_id=start_id))
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
    batches, workflow, _g, _c = rig(tmp_path, aliases=("z2",))
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(with_start(workflow, [one("z2", 2)],
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
    started = batches.start_batch(with_start(workflow, [one("z2", 2, 3), one("z2b", 2)]))
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
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"),
                                    per_alias={"z2": {"job_final": "failed"}})
    started = batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    assert batch["outcome"] == "FAIL"
    assert units_of(batch) == [("z2", 2, "FAIL", "FINISHED"), ("z2b", 2, "PASS", "FINISHED")]
    assert len(gateways["z2b"].posts) == 1  # the unrelated PPU still ran


def test_an_unknown_outcome_latches_its_own_ppu_only(tmp_path):
    batches, workflow, gateways, _c = rig(
        tmp_path, aliases=("z2", "z2b"), per_alias={"z2": {"post_raises": True}})
    started = batches.start_batch(with_start(workflow, [one("z2", 2, 3), one("z2b", 2)]))
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
    batches, workflow, gateways, coordinators = rig(tmp_path, aliases=("z2", "z2b"))
    original = coordinators["z2"].assets

    def recovery_required(alias):
        return {**original(alias), "state": "RECOVERY_REQUIRED"}

    coordinators["z2"].assets = recovery_required
    started = batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    # Some Targets ran and one never could: that is PARTIAL, not FAIL.
    assert batch["outcome"] == "PARTIAL"
    assert units_of(batch) == [("z2", 2, "BLOCKED", "BLOCKED"), ("z2b", 2, "PASS", "FINISHED")]
    assert batch["units"][0]["reason"] == "ADMISSION_PPU_RECOVERY_REQUIRED"
    assert gateways["z2"].posts == [] and len(gateways["z2b"].posts) == 1


def test_a_blocked_target_spends_no_retry_budget_and_misses_no_threshold(tmp_path):
    batches, workflow, _g, coordinators = rig(tmp_path, aliases=("z2", "z2b"),
                                        per_alias={"z2b": {"job_final": "failed"}})
    original = coordinators["z2"].assets
    coordinators["z2"].assets = lambda alias: {**original(alias), "state": "RECOVERY_REQUIRED"}
    started = batches.start_batch(with_start(workflow, 
        [one("z2", 2), one("z2b", 2)], retry_limit=0,
        stop_policy={"kind": "failed_sites", "threshold": 2}))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    # One BLOCKED and one FAIL: the threshold of 2 definite failures is NOT met.
    assert [u["outcome"] for u in batch["units"]] == ["BLOCKED", "FAIL"]
    assert batch["units"][0]["attempts"] == []
    assert batch["outcome"] == "FAIL"


def test_a_batch_whose_targets_are_all_blocked_is_still_admitted(tmp_path):
    batches, workflow, gateways, coordinators = rig(tmp_path, aliases=("z2", "z2b"))
    for alias in ("z2", "z2b"):
        original = coordinators[alias].assets
        coordinators[alias].assets = (
            lambda _a, original=original: {**original(_a), "state": "RECOVERY_REQUIRED"})
    start_id = workflow.issue_batch_start("z2", {"kind": "batch"})["start"]["start_id"]
    started = batches.start_batch(with_start(workflow, [one("z2", 2, 3), one("z2b", 2)], start_id=start_id))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    # A Batch nobody can run is still a Batch: admitted, journalled and
    # reconcilable, with every Target carrying its own reason.
    assert batch["outcome"] == "BLOCKED" and batch["execution_status"] == "COMPLETED"
    assert [u["outcome"] for u in batch["units"]] == ["BLOCKED"] * 3
    assert all(u["reason"] == "ADMISSION_PPU_RECOVERY_REQUIRED" for u in batch["units"])
    assert all(u["failure_domain"] == "TARGET_NOT_READY" for u in batch["units"])
    assert all(u["attempts"] == [] for u in batch["units"])
    assert gateways["z2"].posts == [] and gateways["z2b"].posts == []
    # The start was consumed by the admission; replaying it is a 409, and the
    # Batch is findable by read-only reconciliation.
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(with_start(workflow, [one("z2", 2)], start_id=start_id))
    assert caught.value.code == "programming_start_not_startable"
    reconciled = batches.reconcile_start("z2", start_id)["reconciliation"]
    assert reconciled["state"] == "TERMINAL_CONFIRMED"
    assert reconciled["batch"]["batch_id"] == batch["batch_id"]


def test_an_invalid_specification_is_refused_even_when_no_ppu_is_ready(tmp_path):
    batches, workflow, gateways, coordinators = rig(tmp_path, aliases=("z2",))
    original = coordinators["z2"].assets
    coordinators["z2"].assets = lambda _a: {**original(_a), "state": "RECOVERY_REQUIRED"}
    # Every PPU is unready, but the request itself is illegal. An unusable
    # specification must never be mistaken for a legitimately BLOCKED Batch.
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch({**with_start(workflow, [one("z2", 2)]),
                             "operations": ["erase", "verify"]})
    assert caught.value.code == "operations_invalid"
    assert batches._batches == {} and gateways["z2"].posts == []


def test_an_unknown_target_refuses_the_whole_batch(tmp_path):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2",))
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(with_start(workflow, [one("z2", 2), one("absent", 2)]))
    assert caught.value.code == "ppu_not_found"
    assert batches._batches == {} and gateways["z2"].posts == []


def test_the_stop_policy_counts_sites_across_ppus(tmp_path):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"), job_final="failed")
    started = batches.start_batch(with_start(workflow, 
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
    started = batches.start_batch(with_start(workflow, [one("z2", 2, 3), one("z2b", 2)]))
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
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
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
    batches, workflow, _g, _c = rig(tmp_path, aliases=("z2", "z2b"))
    started = batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    batch_id = started["batch"]["batch_id"]
    with pytest.raises(ProgrammingError) as caught:
        batches.status("z2", batch_id)
    assert caught.value.code == "programming_batch_not_found"
    assert batches.status_batch(batch_id)["batch"]["batch_id"] == batch_id


def test_the_alias_entry_refuses_a_target_set(tmp_path):
    batches, workflow, _g, _c = rig(tmp_path, aliases=("z2",))
    with pytest.raises(ProgrammingError) as caught:
        batches.start("z2", body([one("z2", 2)]))
    assert caught.value.code == "invalid_request" and batches._batches == {}


# --------------------------------------------------- journal and crash recovery

LEGACY_SCHEMA = "plasma.manager.programming-batch-journal.v1"


def legacy_batch(batch_id, *, outcome="PASS", attempts=None, state="finished"):
    return {
        "schema": "plasma.manager.programming-batch.v1",
        "batch_id": batch_id, "ppu_alias": "z2", "site_id": 2, "start_id": None,
        "operations": FULL, "source": "image", "icpn": ICPN,
        "policy": {"repeat": 1, "retry_limit": 0, "stop_policy": {"kind": "never"}},
        "state": state, "outcome": outcome, "reason": None, "stop_requested": False,
        "attempts": attempts if attempts is not None else [
            {"attempt": 1, "plan_id": "p", "run_id": "r", "job_id": "j",
             "job_binding_sha256": "b", "state": "finished", "outcome": outcome,
             "reason": None, "safe_off": True, "retry": None,
             "started_at": "t", "finished_at": "t"}],
        "created_at": "t", "updated_at": "t",
    }


def write_legacy(path, batches):
    path.write_text(json.dumps({"schema": LEGACY_SCHEMA, "batches": batches}),
                    encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_v1_journal_is_read_and_never_written(tmp_path):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    path = tmp_path / "legacy.json"
    digest = write_legacy(path, [legacy_batch("a" * 32)])
    reloaded = ProgrammingBatchCoordinator(workflow, journal_path=path,
                                           spawn=lambda target: target())
    batch = reloaded.status("z2", "a" * 32)["batch"]
    # Normalised into the one canonical model, in memory.
    assert batch["targets"] == [{"ppu_alias": "z2", "site_ids": [2]}]
    assert batch["outcome"] == "PASS" and batch["migrated_from"].endswith("batch.v1")
    assert batch["units"][0]["attempts"][0]["job_key"] == {
        "batch_id": "a" * 32, "ppu_alias": "z2", "site_id": 2, "attempt": 1}
    # The original is untouched: same bytes, same digest, still v1, still there.
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == LEGACY_SCHEMA
    assert reloaded._legacy_path == path and reloaded._v2_path == path.with_name(
        "legacy.json.v2")

    # A new Batch writes v2 beside it, and still does not touch v1.
    reloaded.start_batch(with_start(workflow, [one("z2", 2)]))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    v2 = json.loads((tmp_path / "legacy.json.v2").read_text(encoding="utf-8"))
    assert v2["schema"].endswith("journal.v2")
    # The legacy Batch is not copied into v2: v1 stays its only record.
    assert [b["batch_id"] for b in v2["batches"]] != ["a" * 32]
    assert "a" * 32 not in {b["batch_id"] for b in v2["batches"]}


def test_a_second_restart_reads_both_journals_once(tmp_path):
    batches, workflow, _g, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    path = tmp_path / "legacy.json"
    digest = write_legacy(path, [legacy_batch("a" * 32)])
    first = ProgrammingBatchCoordinator(workflow, journal_path=path,
                                        spawn=lambda target: target())
    new_id = first.start_batch(with_start(workflow, [one("z2", 2)]))["batch"]["batch_id"]
    second = ProgrammingBatchCoordinator(workflow, journal_path=path,
                                         spawn=lambda target: target())
    assert set(second._batches) == {"a" * 32, new_id}      # each loaded once
    assert second.status_batch("a" * 32)["batch"]["outcome"] == "PASS"
    assert second.status_batch(new_id)["batch"]["outcome"] == "PASS"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("attempts, outcome, reason", [
    # Journalled and provably never submitted.
    ([{"attempt": 1, "plan_id": "p", "run_id": None, "job_id": None,
       "job_binding_sha256": "b", "state": "planned", "outcome": None, "reason": None,
       "safe_off": None, "retry": None, "started_at": "t", "finished_at": None}],
     "BLOCKED", "MANAGER_RESTARTED_BEFORE_SUBMISSION"),
    # Submitted, result never seen: never reduced to BLOCKED.
    ([{"attempt": 1, "plan_id": "p", "run_id": "r", "job_id": "j",
       "job_binding_sha256": "b", "state": "running", "outcome": None, "reason": None,
       "safe_off": None, "retry": None, "started_at": "t", "finished_at": None}],
     "OUTCOME_UNKNOWN", "MANAGER_RESTARTED_DURING_ATTEMPT"),
])
def test_a_v1_interrupted_attempt_is_judged_not_guessed(tmp_path, attempts, outcome, reason):
    _b, workflow, gateways, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    path = tmp_path / "legacy.json"
    digest = write_legacy(path, [legacy_batch("c" * 32, outcome=None, state="running",
                                              attempts=attempts)])
    reloaded = ProgrammingBatchCoordinator(workflow, journal_path=path)
    batch = reloaded.status("z2", "c" * 32)["batch"]
    assert (batch["outcome"], batch["units"][0]["reason"]) == (outcome, reason)
    assert gateways["z2"].posts == []            # nothing was resubmitted
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def write_v2(path, batches):
    path.write_text(json.dumps({"schema": "plasma.manager.programming-batch-journal.v2",
                                "batches": batches}), encoding="utf-8")


def test_the_same_batch_in_both_journals_is_loaded_once(tmp_path):
    _b, workflow, _g, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    path = tmp_path / "legacy.json"
    record = legacy_batch("d" * 32, outcome="PASS")
    write_legacy(path, [record])
    # The same transaction, told the same way by both files, is no conflict.
    write_v2(path.with_name("legacy.json.v2"), [migrate_batch_record(record)])
    reloaded = ProgrammingBatchCoordinator(workflow, journal_path=path)
    assert reloaded.status_batch("d" * 32)["batch"]["outcome"] == "PASS"
    assert "d" * 32 not in reloaded._legacy_ids   # the v2 writer owns it now


@pytest.mark.parametrize("v2_outcome", ["FAIL", "PASS", None])
def test_two_journals_that_disagree_about_a_batch_fail_closed(tmp_path, v2_outcome):
    _b, workflow, _g, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    path = tmp_path / "legacy.json"
    write_legacy(path, [legacy_batch("d" * 32, outcome="OUTCOME_UNKNOWN")])
    write_v2(path.with_name("legacy.json.v2"),
             [migrate_batch_record(legacy_batch("d" * 32, outcome=v2_outcome))])
    # There is no safe winner: taking the later writer can bury an
    # OUTCOME_UNKNOWN an operator still has to reconcile, and taking the older
    # one can lose a Job that really ran.
    with pytest.raises(RuntimeError, match="disagree about a transaction identity"):
        ProgrammingBatchCoordinator(workflow, journal_path=path)


def test_a_start_id_claimed_by_two_batches_fails_closed(tmp_path):
    _b, workflow, _g, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    path = tmp_path / "legacy.json"
    first_batch = legacy_batch("e" * 32)
    second_batch = legacy_batch("f" * 32)
    first_batch["start_id"] = second_batch["start_id"] = "0" * 32
    write_legacy(path, [first_batch, second_batch])
    # One start admits at most one Batch. Two is an identity that cannot be
    # proven, whichever file each came from.
    with pytest.raises(RuntimeError, match="is claimed by"):
        ProgrammingBatchCoordinator(workflow, journal_path=path)


def test_a_start_id_split_across_the_two_journals_fails_closed(tmp_path):
    _b, workflow, _g, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    path = tmp_path / "legacy.json"
    legacy_one = legacy_batch("e" * 32)
    legacy_one["start_id"] = "0" * 32
    write_legacy(path, [legacy_one])
    other = migrate_batch_record(legacy_batch("f" * 32))
    other["start_id"] = "0" * 32
    write_v2(path.with_name("legacy.json.v2"), [other])
    with pytest.raises(RuntimeError, match="is claimed by"):
        ProgrammingBatchCoordinator(workflow, journal_path=path)


@pytest.mark.parametrize("raw", [
    '{"schema": "plasma.manager.programming-batch-journal.v9", "batches": []}',
    '{"schema": "plasma.manager.programming-batch-journal.v1"}',
    '{"schema": "plasma.manager.programming-batch-journal.v1", "batches": {}}',
    "{not json",
])
def test_a_journal_that_cannot_be_trusted_fails_closed(tmp_path, raw):
    _b, workflow, _g, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    path = tmp_path / "legacy.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(RuntimeError, match="journal is unreadable"):
        ProgrammingBatchCoordinator(workflow, journal_path=path)


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
    started = batches.start_batch(with_start(workflow, [one("z2", 2, 3), one("z2b", 2)]))
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
    started = batches.start_batch(with_start(workflow, [one("z2", 2, 3), one("z2b", 2)]))
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


# ---------------------------------------------------------- failure domains

def break_assets(coordinators, alias, state=None, raises=None):
    """Make one PPU's Active Set read refuse, or fail outright."""
    original = coordinators[alias].assets

    def assets(_alias):
        if raises is not None:
            raise raises
        return {**original(_alias), "state": state}

    coordinators[alias].assets = assets


def break_gateway(gateways, alias, exc):
    """Make one PPU's Gateway unreachable, as a network fault would."""
    original = gateways[alias].relay

    def relay(method, path, **kw):
        if method == "GET" and path.startswith("/api/status?site="):
            raise exc
        return original(method, path, **kw)

    gateways[alias].relay = relay


@pytest.mark.parametrize("fault, domain, reason_fragment", [
    ("busy", "TARGET_NOT_READY", "SITE_NOT_READY_OR_BUSY"),
    ("recovery", "TARGET_NOT_READY", "PPU_RECOVERY_REQUIRED"),
    ("timeout", "TARGET_STATE_UNAVAILABLE", "PPU_STATE_UNREADABLE_TimeoutError"),
    ("unreachable", "TARGET_STATE_UNAVAILABLE", "PPU_STATE_UNREADABLE_ConnectionError"),
    ("platform_unreadable", "TARGET_STATE_UNAVAILABLE", "PPU_STATE_UNREADABLE_RuntimeError"),
])
def test_one_broken_ppu_is_isolated_and_the_healthy_one_still_runs(
        tmp_path, fault, domain, reason_fragment):
    batches, workflow, gateways, coordinators = rig(tmp_path, aliases=("z2", "z2b"))
    if fault == "busy":
        gateways["z2"].busy = True
    elif fault == "recovery":
        break_assets(coordinators, "z2", state="RECOVERY_REQUIRED")
    elif fault == "timeout":
        break_gateway(gateways, "z2", TimeoutError("ppu timed out"))
    elif fault == "unreachable":
        break_gateway(gateways, "z2", ConnectionError("runtime unreachable"))
    else:
        break_assets(coordinators, "z2", raises=RuntimeError("platform state unreadable"))
    started = batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    broken, healthy = batch["units"]
    # Nothing was submitted for the broken PPU, so the doubt stays local to it.
    assert broken["outcome"] == "BLOCKED" and broken["attempts"] == []
    assert broken["failure_domain"] == domain
    assert reason_fragment in broken["reason"]
    assert healthy["outcome"] == "PASS"
    assert gateways["z2"].posts == [] and len(gateways["z2b"].posts) == 1
    # A single PPU's fault is never promoted to a shared control failure.
    assert batch["failure_domain"] is None
    assert batch["outcome"] == "PARTIAL"


def test_a_ppu_that_goes_quiet_after_submitting_is_unknown_not_blocked(tmp_path):
    batches, workflow, gateways, _c = rig(
        tmp_path, aliases=("z2", "z2b"), per_alias={"z2": {"post_raises": True}})
    started = batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    lost, healthy = batch["units"]
    # A Job may have reached it. That is never reduced to BLOCKED, and it is
    # never resent.
    assert lost["outcome"] == "OUTCOME_UNKNOWN"
    assert lost["failure_domain"] == "TARGET_TRANSACTION_UNKNOWN"
    assert len(gateways["z2"].posts) == 1
    assert healthy["outcome"] == "PASS"
    assert workflow._unknown_latched("z2") is not None
    assert workflow._unknown_latched("z2b") is None


SHARED_GATES = [
    ("authority", lambda alias: ("SHARED_CONTROL_FAILURE", "AUTHORITY_CONTROL_UNUSABLE")),
    ("policy", lambda alias: ("SHARED_CONTROL_FAILURE", "MANAGER_CONTROL_PLANE_UNAVAILABLE")),
]


@pytest.mark.parametrize("label, gate", SHARED_GATES, ids=[s[0] for s in SHARED_GATES])
def test_a_shared_control_failure_stops_the_whole_batch_at_admission(tmp_path, label, gate):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"), platform_gate=gate)
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    # Not one PPU's problem: nothing is admitted and nothing is submitted.
    assert caught.value.code == "manager_shared_control_failure"
    assert caught.value.status == 503
    assert batches._batches == {}
    assert gateways["z2"].posts == [] and gateways["z2b"].posts == []


def test_a_shared_control_failure_mid_batch_submits_nothing_further(tmp_path):
    seen = {"n": 0}

    def gate(alias):
        # Two admission checks and the first Site's execution check pass;
        # the shared control then fails before the second PPU is operated.
        seen["n"] += 1
        return None if seen["n"] <= 3 else ("SHARED_CONTROL_FAILURE", "SCHEDULER_STATE_CORRUPT")

    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"), platform_gate=gate)
    started = batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    assert batch["failure_domain"] == "SHARED_CONTROL_FAILURE"
    done, stopped = batch["units"]
    assert done["outcome"] == "PASS"                      # evidence already earned is kept
    assert stopped["outcome"] is None                     # never guessed into a failure
    assert stopped["status"] == "SKIPPED"
    assert stopped["reason"].startswith("SHARED_CONTROL_FAILURE_")
    assert len(gateways["z2"].posts) == 1 and gateways["z2b"].posts == []
    assert batch["outcome"] == "PARTIAL"


def test_a_gate_that_cannot_be_executed_is_shared_not_local(tmp_path):
    def gate(alias):
        raise RuntimeError("fleet poller is not configured")

    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"), platform_gate=gate)
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    # "I could not tell" is never read as "only this PPU is affected".
    assert caught.value.code == "manager_shared_control_failure"
    assert "GATE_NOT_EXECUTABLE_RuntimeError" in caught.value.message
    assert gateways["z2"].posts == [] and gateways["z2b"].posts == []


def test_a_journal_that_cannot_be_written_stops_submission_and_says_so(tmp_path):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"))
    original = batches._persist_locked
    state = {"writes": 0}

    def persist():
        state["writes"] += 1
        # The journal fails once the first Site has been recorded.
        if state["writes"] > 3:
            raise OSError("journal device is full")
        original()

    batches._persist_locked = persist
    started = batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)]))
    batch = batches.status_batch(started["batch"]["batch_id"])["batch"]
    assert batch["failure_domain"] == "SHARED_CONTROL_FAILURE"
    # The Batch does not claim a state it could not store.
    assert batch["journal_persisted"] is False
    assert gateways["z2b"].posts == []          # nothing further was submitted
    assert batch["units"][1]["outcome"] is None


def test_a_shared_failure_starts_no_new_job_and_no_retry(tmp_path):
    def gate(alias):
        return ("SHARED_CONTROL_FAILURE", "AUTHORITY_CONTROL_UNUSABLE")

    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2", "z2b"),
                                    platform_gate=gate, job_final="failed")
    with pytest.raises(ProgrammingError):
        batches.start_batch(with_start(workflow, [one("z2", 2), one("z2b", 2)], retry_limit=3))
    assert gateways["z2"].posts == [] and gateways["z2b"].posts == []
    assert batches._batches == {}


# ------------------------------------------------------- the start is required

def test_the_canonical_resource_requires_a_manager_issued_start(tmp_path):
    batches, workflow, gateways, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(body([one("z2", 2)]))
    # The start_id is the sole idempotency token: a Batch without one could
    # not be reconciled after a lost answer, so it is not a Batch.
    assert caught.value.code == "invalid_request" and caught.value.status == 400
    assert "start_id" in caught.value.message
    assert batches._batches == {} and gateways["z2"].posts == []
    # With one, the same request is admitted.
    admitted = batches.start_batch(with_start(workflow, [one("z2", 2)]))["batch"]
    assert admitted["outcome"] == "PASS" and admitted["start_id"] is not None


def test_the_alias_entry_still_accepts_a_start_that_omits_the_token(tmp_path):
    batches, _w, gateways, _c = rig(tmp_path, aliases=("z2",), sites=(2,))
    # Deployed callers of the compatibility entry do not send one yet, and
    # PR-B does not break them; PR-C migrates them to the canonical resource.
    started = batches.start(
        "z2", {"icpn": ICPN, "site_id": 2, "operations": FULL,
               "image_base64": base64.b64encode(image()).decode(),
               "image_filename": "app.bin", "retry_limit": 0})
    assert started["batch"]["outcome"] == "PASS"
    assert started["batch"]["start_id"] is None
    assert len(gateways["z2"].posts) == 1
