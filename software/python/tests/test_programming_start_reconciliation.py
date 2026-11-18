"""Host-only: Manager Start Outcome Reconciliation (negative acceptance).

Real ``BundleProgrammingWorkflow`` + ``ProgrammingBatchCoordinator`` with a
fake Bootstrap coordinator and a fake PPU Gateway. No PPU, FPGA or DUT. Every
case models a Console that never saw the Start answer and only holds the
Manager-issued ``start_id``. A PASS here proves the reconciliation contract
only, never a device result.
"""
from __future__ import annotations

import json

import pytest

from plasma_manager import programming
from plasma_manager.programming import CONFIRM_TOKEN, ProgrammingError, VOID_TOKEN
from plasma_manager.programming_batch import ProgrammingBatchCoordinator

from .test_bundle_programming_workflow import (
    ALIAS, FakeCoordinator, FakeGateway, OPS_RESOURCE_SHA, READ_BODY, image, make, ops_body,
    ops_workflow,
)

FULL = ["erase", "program", "verify"]
UNRECORDED = "0" * 32


def rec(target, start_id):
    """Reconciliation is Manager-owned and names no PPU (PR-C, ADR 5.8)."""
    return target.reconcile_start(start_id)["reconciliation"]


def lost_read_start(workflow):
    """Plan + start; the caller only keeps the plan (the answer was lost)."""
    planned = workflow.plan(ALIAS, READ_BODY)["plan"]
    workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    return planned


def batch_rig(tmp_path, *, spawn_batch=None, **gateway_kw):
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway = FakeGateway(image=image(), coordinator=coord,
                          resource_for=lambda _a: OPS_RESOURCE_SHA, **gateway_kw)
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    batches = ProgrammingBatchCoordinator(
        workflow, journal_path=tmp_path / "batches.json", sleep=lambda _s: None,
        spawn=spawn_batch or (lambda target: target()), poll_interval_s=0.0)
    return batches, workflow, gateway


def issue(workflow):
    return workflow.issue_batch_start({"kind": "batch"})["start"]["start_id"]


def start_batch(batches, request):
    """A single-Target canonical Batch, as the Console sends one."""
    site = request.get("site_id", 2)
    rest = {key: value for key, value in request.items() if key != "site_id"}
    return batches.start_batch({**rest, "targets": [{"ppu_alias": ALIAS, "site_ids": [site]}]})


# ------------------------------------------------- answer lost, run was admitted

def test_lost_answer_while_the_job_is_still_running_is_accepted_running(tmp_path):
    held: list = []
    workflow, _c, gateway = ops_workflow(tmp_path)
    workflow.spawn = held.append  # admitted; the Job has not finished
    planned = lost_read_start(workflow)
    view = rec(workflow, planned["plan_id"])
    assert (view["state"], view["kind"], view["outcome"]) == ("ACCEPTED_RUNNING", "run", None)
    assert view["run"]["plan"]["plan_id"] == planned["plan_id"]
    assert view["identity"] == {
        "ppu_alias": ALIAS, "site_id": 2, "ppu_id": planned["job_binding"]["ppu_id"],
        "operation": "read", "operations": None,
        "job_binding_sha256": planned["job_binding_sha256"]}
    assert view["read_only"] is True and view["auto_retry"] == "DISABLED"
    assert gateway.posts == []


@pytest.mark.parametrize("gateway_kw, outcome", [
    ({}, "PASS"),
    ({"job_final": "failed"}, "FAIL"),
])
def test_lost_answer_after_a_definite_result_is_terminal_confirmed(tmp_path, gateway_kw, outcome):
    workflow, _c, gateway = ops_workflow(tmp_path, **gateway_kw)
    planned = lost_read_start(workflow)
    view = rec(workflow, planned["plan_id"])
    assert (view["state"], view["outcome"]) == ("TERMINAL_CONFIRMED", outcome)
    assert view["run"]["job_submission_count"] == 1 and len(gateway.posts) == 1
    assert view["identity"]["job_binding_sha256"] == planned["job_binding_sha256"]


def test_lost_answer_of_an_unknown_run_stays_unknown_until_the_operator_acknowledges(tmp_path):
    workflow, _c, gateway = ops_workflow(tmp_path, post_raises=True)
    planned = lost_read_start(workflow)
    view = rec(workflow, planned["plan_id"])
    assert view["state"] == "OUTCOME_UNKNOWN" and view["acknowledged"] is False
    assert view["reason"] == "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT"
    run_id = view["unknown_run_id"]
    assert run_id == view["run"]["run_id"]
    # Asking again, any number of times, acknowledges and resubmits nothing.
    for _ in range(5):
        assert rec(workflow, planned["plan_id"])["acknowledged"] is False
    assert len(gateway.posts) == 1
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": workflow.plan(ALIAS, READ_BODY)["plan"]["plan_id"],
                               "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_outcome_unknown_unresolved"
    # Only the existing explicit acknowledge changes it; the run stays UNKNOWN.
    workflow.acknowledge(ALIAS, run_id, {"acknowledge": programming.ACK_TOKEN})
    view = rec(workflow, planned["plan_id"])
    assert (view["state"], view["acknowledged"]) == ("OUTCOME_UNKNOWN", True)


# ---------------------------------------------------- the start never arrived

def test_a_start_that_never_arrived_is_pending_while_the_plan_can_still_be_started(tmp_path):
    workflow, _c, gateway = ops_workflow(tmp_path)
    clock = [1000.0]
    workflow.monotonic = lambda: clock[0]
    planned = workflow.plan(ALIAS, READ_BODY)["plan"]
    view = rec(workflow, planned["plan_id"])
    assert (view["state"], view["reason"]) == ("ACCEPTANCE_PENDING", "START_STILL_ADMISSIBLE")
    assert view["expires_in_s"] == programming.PLAN_TTL_S and view["run"] is None
    # ... and it really is still admissible: a delayed request is admitted.
    workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    assert rec(workflow, planned["plan_id"])["state"] == "TERMINAL_CONFIRMED"
    assert len(gateway.posts) == 1


def test_an_expired_or_evicted_plan_that_was_never_consumed_is_not_accepted(tmp_path):
    workflow, _c, gateway = ops_workflow(tmp_path)
    clock = [1000.0]
    workflow.monotonic = lambda: clock[0]
    planned = workflow.plan(ALIAS, READ_BODY)["plan"]
    clock[0] += programming.PLAN_TTL_S + 1
    view = rec(workflow, planned["plan_id"])
    assert (view["state"], view["reason"]) == (
        "NOT_ACCEPTED", "START_NEVER_ADMITTED_AND_NO_LONGER_ADMISSIBLE")
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_plan_not_found" and gateway.posts == []


def test_manager_restart_before_the_run_was_journalled_is_not_accepted(tmp_path):
    workflow, coord, gateway = ops_workflow(tmp_path)
    planned = workflow.plan(ALIAS, READ_BODY)["plan"]
    restarted, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    view = rec(restarted, planned["plan_id"])
    # Evidence: the journalled issue record was never consumed and the plan
    # (memory only) cannot be started any more. Not "the plan is gone".
    assert (view["state"], view["kind"]) == ("NOT_ACCEPTED", "run")
    assert view["identity"]["job_binding_sha256"] == planned["job_binding_sha256"]
    with pytest.raises(ProgrammingError):
        restarted.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    assert gateway.posts == []


def test_manager_restart_after_the_run_was_journalled_is_outcome_unknown(tmp_path):
    held: list = []
    workflow, coord, gateway = ops_workflow(tmp_path)
    workflow.spawn = held.append
    planned = lost_read_start(workflow)
    restarted, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    view = rec(restarted, planned["plan_id"])
    assert (view["state"], view["reason"]) == ("OUTCOME_UNKNOWN", "MANAGER_RESTARTED_DURING_RUN")
    assert view["acknowledged"] is False and view["unknown_run_id"] == view["run"]["run_id"]
    assert gateway.posts == []


def test_a_journal_write_failure_at_start_spawns_nothing_and_never_reads_as_running(tmp_path):
    spawned: list = []
    workflow, coord, gateway = ops_workflow(tmp_path)
    workflow.spawn = spawned.append
    planned = workflow.plan(ALIAS, READ_BODY)["plan"]
    real = workflow._persist_locked

    def fail():
        raise OSError("disk full")

    workflow._persist_locked = fail
    with pytest.raises(OSError):
        workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    workflow._persist_locked = real
    assert spawned == [] and gateway.posts == []
    view = rec(workflow, planned["plan_id"])
    assert (view["state"], view["reason"]) == ("OUTCOME_UNKNOWN", "ADMITTED_RECORD_MISSING")
    # The disk never saw the admission: a new process proves "not accepted".
    restarted, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    assert rec(restarted, planned["plan_id"])["state"] == "NOT_ACCEPTED"


# ----------------------------------------- journal missing, corrupt, inconsistent

def test_missing_journal_or_unrecorded_start_is_unknown_never_not_accepted(tmp_path):
    workflow, coord, gateway = ops_workflow(tmp_path)
    planned = lost_read_start(workflow)
    (tmp_path / "runs.json").unlink()
    restarted, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    for start_id in (planned["plan_id"], UNRECORDED):
        view = rec(restarted, start_id)
        assert (view["state"], view["reason"]) == ("OUTCOME_UNKNOWN", "START_NOT_RECORDED")
        assert view["run"] is None and view["identity"] is None


@pytest.mark.parametrize("content", ["{not json", json.dumps({"runs": [{"run_id": 1}]}),
                                     json.dumps({"runs": [], "starts": [{"start_id": "x"}]})])
def test_corrupt_journal_refuses_to_start_the_manager_workflow(tmp_path, content):
    workflow, coord, gateway = ops_workflow(tmp_path)
    lost_read_start(workflow)
    (tmp_path / "runs.json").write_text(content)
    with pytest.raises(RuntimeError):
        make(tmp_path, coordinator=coord, gateway=gateway)


def edit_journal(tmp_path, mutate):
    path = tmp_path / "runs.json"
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize("mutate, reason", [
    # The admission says "consumed" but the run record is gone.
    (lambda d: d.update(runs=[]), "ADMITTED_RECORD_MISSING"),
    # The run exists but its admission disagrees about what was started.
    (lambda d: d["starts"][0].update(job_binding_sha256="f" * 64), "JOURNAL_INCONSISTENT"),
    (lambda d: d["starts"][0].update(site_id=1), "JOURNAL_INCONSISTENT"),
    (lambda d: d["starts"][0].update(run_id="f" * 32), "JOURNAL_INCONSISTENT"),
    (lambda d: d["starts"][0].update(state="ISSUED"), "JOURNAL_INCONSISTENT"),
    (lambda d: d["starts"][0].update(state="VOIDED"), "JOURNAL_INCONSISTENT"),
    (lambda d: d["starts"][0].update(ppu_alias="other"), "START_IDENTITY_MISMATCH"),
    (lambda d: d["runs"][0].update(ppu_alias="other"), "START_IDENTITY_MISMATCH"),
])
def test_inconsistent_journal_is_outcome_unknown(tmp_path, mutate, reason):
    workflow, coord, gateway = ops_workflow(tmp_path)
    planned = lost_read_start(workflow)
    edit_journal(tmp_path, mutate)
    restarted, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    view = rec(restarted, planned["plan_id"])
    assert (view["state"], view["reason"]) == ("OUTCOME_UNKNOWN", reason)
    assert len(gateway.posts) == 1


def test_a_dropped_admission_record_never_reads_as_not_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(programming, "MAX_STARTS_RETAINED", 2)
    workflow, _c, _g = ops_workflow(tmp_path)
    first = workflow.plan(ALIAS, READ_BODY)["plan"]["plan_id"]
    for _ in range(3):
        workflow.plan(ALIAS, READ_BODY)
    workflow._plans.pop(first)
    view = rec(workflow, first)
    assert (view["state"], view["reason"]) == ("OUTCOME_UNKNOWN", "START_NOT_RECORDED")


def test_a_record_naming_another_ppu_than_the_run_leaks_nothing(tmp_path):
    workflow, _c, _g = ops_workflow(tmp_path)
    planned = lost_read_start(workflow)
    # The PPU is an ANSWER, read off the run and the journalled record, never
    # a question the caller asks with. When the two disagree, the Manager
    # proves nothing and says so rather than picking one of them.
    workflow._starts[planned["plan_id"]]["ppu_alias"] = "other"
    view = rec(workflow, planned["plan_id"])
    assert (view["state"], view["reason"]) == ("OUTCOME_UNKNOWN", "START_IDENTITY_MISMATCH")
    assert view["run"] is None and view["identity"] is None


def test_reconciliation_names_no_ppu_and_refuses_no_caller(tmp_path):
    workflow, _c, _g = ops_workflow(tmp_path)
    # A Batch start belongs to no PPU, so an unrecorded ID cannot be refused
    # as "not this PPU's": it is simply unprovable, which is never NOT_ACCEPTED.
    view = rec(workflow, UNRECORDED)
    assert (view["state"], view["reason"]) == ("OUTCOME_UNKNOWN", "START_NOT_RECORDED")
    assert view["ppu_alias"] is None and view["identity"] is None


# ------------------------------------------------- read-only and Site-idle proof

def test_reconciliation_is_read_only_and_never_contacts_the_ppu(tmp_path):
    workflow, _c, gateway = ops_workflow(tmp_path, post_raises=True)
    planned = lost_read_start(workflow)
    journal = (tmp_path / "runs.json").read_bytes()
    posts = len(gateway.posts)
    calls: list = []
    real = gateway.relay
    gateway.relay = lambda *a, **k: calls.append(a) or real(*a, **k)
    for start_id in (planned["plan_id"], UNRECORDED):
        for _ in range(20):
            rec(workflow, start_id)
    assert calls == [] and len(gateway.posts) == posts
    assert (tmp_path / "runs.json").read_bytes() == journal
    assert len(workflow._runs) == 1 and not next(iter(workflow._runs.values())).acknowledged


def test_site_idle_never_changes_an_unknown_reconciliation(tmp_path):
    workflow, _c, gateway = ops_workflow(tmp_path, post_raises=True)
    planned = lost_read_start(workflow)
    gateway.post_raises = False
    # The Site reads idle with no Job (retry_block's own device check passes
    # apart from the latch), yet the original transaction stays UNKNOWN.
    assert workflow.retry_block(ALIAS, 2) == "OUTCOME_UNKNOWN_UNRESOLVED"
    assert workflow._readiness(gateway, 2, None)["state"] == "idle"
    assert rec(workflow, planned["plan_id"])["state"] == "OUTCOME_UNKNOWN"


def test_read_unknown_blocks_programming_and_programming_unknown_blocks_read(tmp_path):
    for first, then in ((READ_BODY, ops_body(FULL)), (ops_body(FULL), READ_BODY)):
        root = tmp_path / first.get("operation", "programming")
        workflow, _c, gateway = ops_workflow(root, post_raises=True)
        planned = workflow.plan(ALIAS, first)["plan"]
        workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
        gateway.post_raises = False
        other = workflow.plan(ALIAS, then)["plan"]
        with pytest.raises(ProgrammingError) as caught:
            workflow.start(ALIAS, {"plan_id": other["plan_id"], "confirm": CONFIRM_TOKEN})
        assert caught.value.code == "programming_outcome_unknown_unresolved"
        batches = ProgrammingBatchCoordinator(workflow, journal_path=root / "batches.json",
                                              spawn=lambda target: target())
        start_id = issue(workflow)
        # Partial admission: the Batch request is valid, so it is admitted and
        # journalled. The latch is that PPU's readiness, so its only Target is
        # BLOCKED and no Job is submitted.
        admitted = start_batch(batches, {**ops_body(FULL), "start_id": start_id})["batch"]
        assert admitted["outcome"] == "BLOCKED"
        assert admitted["units"][0]["reason"] == "ADMISSION_OUTCOME_UNKNOWN_UNRESOLVED"
        assert len(gateway.posts) == 1
        # That admission consumed the start. Replaying it is still a 409.
        with pytest.raises(ProgrammingError) as caught:
            start_batch(batches, {**ops_body(FULL), "start_id": start_id})
        assert caught.value.code == "programming_start_not_startable"
        assert len(gateway.posts) == 1
        assert rec(workflow, planned["plan_id"])["state"] == "OUTCOME_UNKNOWN"
        # The refused start was never admitted and says so.
        assert rec(workflow, other["plan_id"])["state"] == "ACCEPTANCE_PENDING"


# ------------------------------------------------------------------------ void

def test_void_makes_an_unstarted_start_provably_not_accepted(tmp_path):
    workflow, coord, gateway = ops_workflow(tmp_path)
    planned = workflow.plan(ALIAS, READ_BODY)["plan"]
    with pytest.raises(ProgrammingError) as caught:
        workflow.void_start(planned["plan_id"], {"void": "yes"})
    assert caught.value.code == "invalid_request"
    view = workflow.void_start(planned["plan_id"], {"void": VOID_TOKEN})["reconciliation"]
    assert (view["state"], view["reason"]) == ("NOT_ACCEPTED", "START_VOIDED_BEFORE_ADMISSION")
    # The delayed Start request arrives after the void: refused, nothing runs.
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_plan_not_found" and gateway.posts == []
    restarted, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    assert rec(restarted, planned["plan_id"])["reason"] == "START_VOIDED_BEFORE_ADMISSION"


def test_an_admitted_start_can_never_be_voided(tmp_path):
    workflow, _c, gateway = ops_workflow(tmp_path, post_raises=True)
    planned = lost_read_start(workflow)
    with pytest.raises(ProgrammingError) as caught:
        workflow.void_start(planned["plan_id"], {"void": VOID_TOKEN})
    assert caught.value.code == "programming_start_not_voidable"
    with pytest.raises(ProgrammingError) as caught:
        workflow.void_start(UNRECORDED, {"void": VOID_TOKEN})
    assert caught.value.code == "programming_start_not_found"
    view = rec(workflow, planned["plan_id"])
    assert view["state"] == "OUTCOME_UNKNOWN" and view["acknowledged"] is False


# ----------------------------------------------------------------------- Batch

def test_batch_start_id_is_issued_by_the_manager_and_admits_exactly_one_batch(tmp_path):
    batches, workflow, gateway = batch_rig(tmp_path)
    with pytest.raises(ProgrammingError):
        workflow.issue_batch_start({})
    start_id = issue(workflow)
    assert rec(batches, start_id)["state"] == "ACCEPTANCE_PENDING"
    started = start_batch(batches, {**ops_body(FULL), "start_id": start_id})
    assert started["batch"]["start_id"] == start_id
    view = rec(batches, start_id)
    assert (view["state"], view["kind"], view["outcome"]) == ("TERMINAL_CONFIRMED", "batch", "PASS")
    assert view["batch"]["batch_id"] == started["batch"]["batch_id"]
    assert view["identity"]["site_id"] == 2
    assert view["identity"]["job_binding_sha256"] == \
        view["batch"]["attempts"][0]["job_binding_sha256"]
    # The same ID again (a duplicated or replayed request) starts nothing.
    for bad in (start_id, UNRECORDED, 7):
        with pytest.raises(ProgrammingError) as caught:
            start_batch(batches, {**ops_body(FULL), "start_id": bad})
        assert caught.value.code == "programming_start_not_startable"
    assert len(gateway.posts) == 1
    assert len(json.loads((tmp_path / "batches.json").read_text())["batches"]) == 1


def test_a_batch_without_a_start_id_is_refused_and_submits_nothing(tmp_path):
    batches, _w, gateway = batch_rig(tmp_path)
    # Since PR-C there is one door and it requires the token: a Batch that
    # could not be reconciled after a lost answer is not admitted at all.
    with pytest.raises(ProgrammingError) as caught:
        start_batch(batches, ops_body(FULL))
    assert caught.value.code == "invalid_request" and caught.value.status == 400
    assert gateway.posts == [] and batches._batches == {}


def test_lost_batch_answer_running_then_failed(tmp_path):
    held: list = []
    batches, workflow, gateway = batch_rig(tmp_path, spawn_batch=held.append, job_final="failed")
    start_id = issue(workflow)
    start_batch(batches, {**ops_body(FULL), "start_id": start_id})
    assert rec(batches, start_id)["state"] == "ACCEPTED_RUNNING"
    held.pop()()
    view = rec(batches, start_id)
    assert (view["state"], view["outcome"]) == ("TERMINAL_CONFIRMED", "FAIL")
    assert len(gateway.posts) == 1


def test_lost_batch_answer_with_an_unknown_attempt_points_at_the_run_to_acknowledge(tmp_path):
    batches, workflow, gateway = batch_rig(tmp_path, post_raises=True)
    start_id = issue(workflow)
    start_batch(batches, {**ops_body(FULL), "start_id": start_id, "retry_limit": 2})
    view = rec(batches, start_id)
    assert view["state"] == "OUTCOME_UNKNOWN" and view["acknowledged"] is False
    assert view["unknown_run_id"] == view["batch"]["attempts"][0]["run_id"]
    assert len(gateway.posts) == 1  # never retried


def test_batch_start_that_never_arrived_restart_and_void(tmp_path):
    batches, workflow, gateway = batch_rig(tmp_path)
    kept, voided = issue(workflow), issue(workflow)
    view = workflow.void_start(voided, {"void": VOID_TOKEN})["reconciliation"]
    assert view["state"] == "NOT_ACCEPTED"
    with pytest.raises(ProgrammingError) as caught:
        start_batch(batches, {**ops_body(FULL), "start_id": voided})
    assert caught.value.code == "programming_start_not_startable"
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway2 = FakeGateway(image=image(), coordinator=coord,
                           resource_for=lambda _a: OPS_RESOURCE_SHA)
    workflow2, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway2)
    batches2 = ProgrammingBatchCoordinator(workflow2, journal_path=tmp_path / "batches.json",
                                           spawn=lambda target: target())
    assert rec(batches2, kept)["state"] == "NOT_ACCEPTED"
    with pytest.raises(ProgrammingError):
        start_batch(batches2, {**ops_body(FULL), "start_id": kept})
    assert gateway.posts == [] and gateway2.posts == []


def test_batch_admitted_but_its_record_is_gone_is_unknown(tmp_path):
    batches, workflow, gateway = batch_rig(tmp_path)
    start_id = issue(workflow)
    start_batch(batches, {**ops_body(FULL), "start_id": start_id})
    (tmp_path / "batches.json").unlink()
    coord = FakeCoordinator(active_sha="e" * 64)
    workflow2, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    batches2 = ProgrammingBatchCoordinator(workflow2, journal_path=tmp_path / "batches.json")
    view = rec(batches2, start_id)
    assert (view["state"], view["reason"]) == ("OUTCOME_UNKNOWN", "ADMITTED_RECORD_MISSING")


def test_batch_restart_during_an_attempt_is_unknown(tmp_path):
    held: list = []
    batches, workflow, gateway = batch_rig(tmp_path)
    workflow.spawn = held.append
    batches.spawn = held.append
    start_id = issue(workflow)
    start_batch(batches, {**ops_body(FULL), "start_id": start_id})

    class Died(BaseException):
        pass

    def die(_seconds):
        raise Died()

    batches.sleep = die
    with pytest.raises(Died):
        held.pop()()
    coord = FakeCoordinator(active_sha="e" * 64)
    workflow2, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    batches2 = ProgrammingBatchCoordinator(workflow2, journal_path=tmp_path / "batches.json")
    view = rec(batches2, start_id)
    assert (view["state"], view["reason"]) == (
        "OUTCOME_UNKNOWN", "MANAGER_RESTARTED_DURING_ATTEMPT")
    assert view["acknowledged"] is False and view["unknown_run_id"] is not None
    assert gateway.posts == []
