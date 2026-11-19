"""Host-only: Manual Repeat v1 (WP-02) on the canonical Manager Batch.

Real ``BundleProgrammingWorkflow`` + ``ProgrammingBatchCoordinator`` with the
fake multi-Site PPU Gateway of ``test_programming_batch_targets``. No PPU,
FPGA or DUT: a PASS here proves Cycle accounting, pause/Continue, Stop and
recovery decisions only - never real programming.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from plasma_manager.programming import ProgrammingError
from plasma_manager.programming_batch import (
    AWAITING_CONTINUE, MAX_REPEAT, ProgrammingBatchCoordinator, parse_policy,
)

from .test_programming_batch_targets import MultiplexGateway, rig, with_start

WAIT = 10.0


class ScriptedGateway(MultiplexGateway):
    """One scripted final state per Job, per Site.

    ``success`` / ``failed`` / ``error`` are terminal Job states; ``lost``
    records the POST and loses its answer (OUTCOME_UNKNOWN); ``unsafe``
    fails without verified SAFE_OFF.
    """

    def __init__(self, script, **kwargs):
        super().__init__(**kwargs)
        self.script = {site: list(items) for site, items in script.items()}

    def relay(self, method, path, **kwargs):
        with self.job_lock:
            if method == "POST" and path == "/api/jobs":
                site = json.loads(kwargs["body"])["job_binding"]["site_id"]
                queue = self.script.get(site) or ["success"]
                final = queue.pop(0) if len(queue) > 1 else queue[0]
                if final == "lost":
                    self.posts.append(json.loads(kwargs["body"]))
                    raise TimeoutError("job POST response lost")
                saved = dict(self.job_kwargs)
                self.job_kwargs.update(job_final="failed" if final == "unsafe" else final,
                                       safe_off=final != "unsafe")
                self.job_final = self.job_kwargs["job_final"]
                try:
                    return super().relay(method, path, **kwargs)
                finally:
                    self.job_kwargs.clear()
                    self.job_kwargs.update(saved)
            return super().relay(method, path, **kwargs)


class Session:
    """One Manual Session driven on a background lane thread."""

    def __init__(self, tmp_path, script=None, *, sites=(1,), **policy):
        pending = []
        self.tmp_path = tmp_path
        self.batches, self.workflow, gateways, _ = rig(
            tmp_path, sites=sites, spawn_batch=pending.append)
        base = gateways["z2"]
        self.gateway = ScriptedGateway(script or {}, image=base.image,
                                       coordinator=base.coordinator,
                                       resource_for=base.resource_for)
        self.workflow.gateway_client_factory = lambda _e, _t: self.gateway
        self.batches.sleep = lambda _s: time.sleep(0.002)
        started = self.batches.start_batch(
            with_start(self.workflow, [{"ppu_alias": "z2", "site_ids": list(sites)}], **policy))
        self.batch_id = started["batch"]["batch_id"]
        self.thread = threading.Thread(target=pending.pop(), daemon=True)
        self.thread.start()

    def view(self):
        return self.batches.status_batch(self.batch_id)["batch"]

    def unit(self, site=1):
        return next(u for u in self.view()["units"] if u["site_id"] == site)

    def until(self, predicate, what="condition", wait=WAIT):
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            batch = self.view()
            if predicate(batch):
                return batch
            time.sleep(0.005)
        raise AssertionError(f"timed out waiting for {what}: {self.view()}")

    def awaiting(self, site=1, seq=None):
        def ready(batch):
            unit = next(u for u in batch["units"] if u["site_id"] == site)
            return (unit["cycle"]["state"] == AWAITING_CONTINUE
                    and (seq is None or unit["cycle"]["continue_seq"] == seq))
        return next(u for u in self.until(ready, f"Site {site} pause")["units"]
                    if u["site_id"] == site)

    def cont(self, site=1, seq=None, actor="capability:test-operator"):
        if seq is None:
            seq = self.unit(site)["cycle"]["continue_seq"]
        return self.batches.continue_site(self.batch_id, {
            "ppu_alias": "z2", "site_id": site, "continue_seq": seq, "actor": actor})

    def done(self, wait=WAIT):
        batch = self.until(lambda b: b["outcome"] is not None, "Batch end", wait)
        self.thread.join(WAIT)
        return batch

    def ledger(self, kind=None):
        records = self.batches.cycle_records(self.batch_id, 0, 1000)["records"]
        return [r for r in records if kind is None or r["type"] == kind]


def job_ids(records):
    return [a["job_id"] for r in records for a in r["attempts"]]


# ------------------------------------------------------------------ policy

@pytest.mark.parametrize("repeat", [1, 2, MAX_REPEAT])
def test_repeat_bounds_accepted(repeat):
    assert parse_policy({"repeat": repeat})["repeat"] == repeat


@pytest.mark.parametrize("repeat", [0, -1, MAX_REPEAT + 1, True, 1.0, "3", None])
def test_illegal_repeat_refuses_the_whole_batch_and_keeps_the_start(tmp_path, repeat):
    batches, workflow, gateways, _ = rig(tmp_path, sites=(1,))
    request = with_start(workflow, [{"ppu_alias": "z2", "site_ids": [1]}], repeat=repeat)
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(request)
    assert caught.value.code == "invalid_request" and gateways["z2"].posts == []
    workflow.require_batch_start(request["start_id"])  # still startable


def test_repeat_10000_is_admitted_per_site_and_reported(tmp_path):
    s = Session(tmp_path, sites=(1, 2), repeat=MAX_REPEAT)
    s.awaiting(1)
    s.awaiting(2)
    view = s.view()
    assert view["policy"]["repeat"] == MAX_REPEAT
    assert view["cycles"]["planned"] == 2 * MAX_REPEAT
    assert view["cycles"]["settled"] == 2 and view["cycles"]["remaining"] == 2 * MAX_REPEAT - 2
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    batch = s.done()
    assert batch["outcome"] == "PARTIAL" and batch["execution_status"] == "STOPPED"
    assert len(s.gateway.posts) == 2


def test_repeat_one_keeps_the_single_flash_contract(tmp_path):
    s = Session(tmp_path)
    batch = s.done()
    unit = batch["units"][0]
    assert batch["outcome"] == "PASS" and unit["outcome"] == "PASS"
    assert unit["cycle"]["settled"] == 1 and unit["cycle"]["remaining"] == 0
    assert unit["cycle"]["continue_seq"] == 0 and unit["cycle"]["disposition"] == "COMPLETED"
    assert len(unit["attempts"]) == 1 and len(s.gateway.posts) == 1
    assert len(s.ledger("cycle")) == 1 and s.ledger("continue") == []


# ------------------------------------------------------- replace-IC continuation

def test_pass_waits_for_replacement_then_one_continue_runs_a_fresh_cycle(tmp_path):
    s = Session(tmp_path, repeat=2)
    unit = s.awaiting()
    assert unit["status"] == AWAITING_CONTINUE and unit["cycle"]["wait_reason"] == "REPLACE_IC"
    assert unit["cycle"]["last"]["outcome"] == "PASS" and len(s.gateway.posts) == 1
    time.sleep(0.05)
    assert len(s.gateway.posts) == 1  # nothing advances without the operator
    answer = s.cont()
    assert answer["duplicate"] is False
    batch = s.done()
    unit = batch["units"][0]
    assert batch["outcome"] == "PASS" and unit["reason"] == "COMPLETED"
    assert (unit["cycle"]["settled"], unit["cycle"]["pass"], unit["cycle"]["fail"]) == (2, 2, 0)
    cycles = s.ledger("cycle")
    assert [c["cycle_index"] for c in cycles] == [1, 2]
    # Each Cycle: its own Cycle, plan, run and Job identity, submitted once.
    for key in ("cycle_id",):
        assert len({c[key] for c in cycles}) == 2
    for key in ("plan_id", "run_id", "job_id"):
        assert len({c["attempts"][0][key] for c in cycles}) == 2
    assert len(s.gateway.posts) == 2
    event, = s.ledger("continue")
    assert event["actor"] == "capability:test-operator" and event["continue_seq"] == 1
    assert event["after_cycle_index"] == 1 and event["after_outcome"] == "PASS"


def test_fail_after_retries_pauses_counts_one_cycle_and_never_adds_one(tmp_path):
    # Cycle 1: FAIL, Retry FAIL (exhausted). Cycles 2, 3: PASS.
    s = Session(tmp_path, {1: ["failed", "failed", "success"]}, repeat=3, retry_limit=1)
    unit = s.awaiting()
    assert unit["cycle"]["wait_reason"] == "FAIL_REVIEW"
    last = unit["cycle"]["last"]
    assert last["outcome"] == "FAIL" and last["attempts"] == 2
    assert last["receipt"]["job_state"] and last["receipt"]["safe_off"] is True
    s.cont()
    s.awaiting(seq=2)
    s.cont()
    batch = s.done()
    cycle = batch["units"][0]["cycle"]
    assert (cycle["planned"], cycle["settled"], cycle["pass"], cycle["fail"]) == (3, 3, 2, 1)
    assert cycle["retry_attempts"] == 1 and cycle["remaining"] == 0
    assert len(s.gateway.posts) == 4  # 2 attempts + 2 Cycles, nothing extra
    assert batch["outcome"] == "FAIL" and batch["units"][0]["reason"] == "COMPLETED_WITH_FAILURES"
    assert batch["units"][0]["cycle"]["disposition"] == "COMPLETED_WITH_FAILURES"


def test_retry_then_pass_is_one_pass_cycle(tmp_path):
    s = Session(tmp_path, {1: ["failed", "success"]}, repeat=1, retry_limit=1)
    batch = s.done()
    cycle = batch["units"][0]["cycle"]
    assert batch["outcome"] == "PASS"
    assert (cycle["settled"], cycle["pass"], cycle["fail"], cycle["retry_attempts"]) == (1, 1, 0, 1)


def test_final_cycle_fail_settles_without_another_pause(tmp_path):
    s = Session(tmp_path, {1: ["success", "failed"]}, repeat=2)
    s.awaiting()
    s.cont()
    batch = s.done()
    cycle = batch["units"][0]["cycle"]
    assert cycle["continue_seq"] == 1 and cycle["remaining"] == 0
    assert (cycle["pass"], cycle["fail"]) == (1, 1)
    assert batch["outcome"] == "FAIL" and cycle["disposition"] == "COMPLETED_WITH_FAILURES"


# ------------------------------------------------------------ same-IC Debug

def test_debug_pass_runs_the_next_cycle_without_an_operator(tmp_path):
    s = Session(tmp_path, repeat=3, replace_ic_before_next_cycle=False)
    batch = s.done()
    cycle = batch["units"][0]["cycle"]
    assert batch["outcome"] == "PASS" and cycle["pass"] == 3 and cycle["continue_seq"] == 0
    assert len(s.gateway.posts) == 3 and s.ledger("continue") == []
    # Same-IC Cycles are Cycles; the Batch still counts ONE Site / IC.
    assert batch["counts"]["pass"] == 1 and batch["cycles"]["pass"] == 3


def test_debug_fail_still_pauses_for_the_operator(tmp_path):
    s = Session(tmp_path, {1: ["success", "failed", "success"]}, repeat=3,
                replace_ic_before_next_cycle=False)
    unit = s.awaiting()
    assert unit["cycle"]["wait_reason"] == "FAIL_REVIEW" and unit["cycle"]["index"] == 2
    s.cont()
    batch = s.done()
    cycle = batch["units"][0]["cycle"]
    assert (cycle["settled"], cycle["pass"], cycle["fail"]) == (3, 2, 1)


# --------------------------------------------------------------- isolation

def test_one_site_paused_on_fail_never_holds_back_a_healthy_site(tmp_path):
    s = Session(tmp_path, {1: ["failed"], 2: ["success"]}, sites=(1, 2), repeat=3,
                replace_ic_before_next_cycle=False)
    s.awaiting(1)
    s.until(lambda b: b["units"][1]["cycle"]["settled"] == 3, "Site 2 completes")
    assert s.unit(1)["cycle"]["state"] == AWAITING_CONTINUE  # still paused alone
    assert s.unit(2)["outcome"] == "PASS"
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    batch = s.done()
    one, two = batch["units"]
    assert one["outcome"] == "FAIL" and one["cycle"]["disposition"] == "STOPPED"
    assert one["cycle"]["remaining"] == 2 and two["cycle"]["remaining"] == 0
    assert batch["cycles"]["settled"] == 4 and len(s.gateway.posts) == 4


# ------------------------------------------------------- Stop / idempotency

def test_stop_while_paused_ends_that_session_and_refuses_continue(tmp_path):
    s = Session(tmp_path, repeat=5)
    unit = s.awaiting()
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    batch = s.done()
    assert batch["execution_status"] == "STOPPED" and batch["outcome"] == "PARTIAL"
    assert batch["units"][0]["cycle"]["remaining"] == 4
    with pytest.raises(ProgrammingError) as caught:
        s.cont(seq=unit["cycle"]["continue_seq"])
    assert caught.value.code == "programming_continue_stale"
    assert len(s.gateway.posts) == 1


def test_stop_racing_an_accepted_continue_dispatches_nothing(tmp_path):
    s = Session(tmp_path, repeat=3)
    s.awaiting()
    # Both land before the lane looks again: Stop wins at the dispatch gate.
    with s.batches._lock:
        s.cont()
        s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    batch = s.done()
    assert len(s.gateway.posts) == 1 and batch["execution_status"] == "STOPPED"
    assert batch["units"][0]["cycle"]["settled"] == 1


def test_continue_after_stop_is_refused(tmp_path):
    s = Session(tmp_path, repeat=3)
    s.awaiting()
    with s.batches._lock:
        s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
        with pytest.raises(ProgrammingError) as caught:
            s.cont()
    assert caught.value.code == "programming_batch_stopping"
    s.done()
    assert len(s.gateway.posts) == 1


def test_duplicate_stale_and_reloaded_continue_never_dispatch_twice(tmp_path):
    s = Session(tmp_path, repeat=3)
    first = s.awaiting()["cycle"]["continue_seq"]
    for bad in (0, first + 1):
        with pytest.raises(ProgrammingError) as caught:
            s.cont(seq=bad)
        assert caught.value.code in ("invalid_request", "programming_continue_stale")
    assert s.cont(seq=first)["duplicate"] is False
    # The double click and a reloaded tab repeat the SAME seq.
    assert s.cont(seq=first)["duplicate"] is True
    s.awaiting(seq=first + 1)
    # The old tab's click must not answer the NEW pause.
    assert s.cont(seq=first)["duplicate"] is True
    assert s.unit()["cycle"]["state"] == AWAITING_CONTINUE
    assert len(s.gateway.posts) == 2
    for _ in range(3):
        s.view()  # a reloaded Browser only reads
    assert len(s.gateway.posts) == 2
    s.cont(seq=first + 1)
    s.done()
    assert len(s.gateway.posts) == 3 and len(s.ledger("continue")) == 2


def test_continue_of_a_running_or_unknown_site_is_refused(tmp_path):
    s = Session(tmp_path, repeat=2)
    s.awaiting()
    with pytest.raises(ProgrammingError) as caught:
        s.batches.continue_site(s.batch_id, {"ppu_alias": "z2", "site_id": 7,
                                             "continue_seq": 1})
    assert caught.value.code == "programming_batch_site_not_found"
    for body in ({"ppu_alias": "z2", "site_id": 1}, {"ppu_alias": "z2", "site_id": 1,
                 "continue_seq": 1, "actor": ""}, {"ppu_alias": "z2", "site_id": 1,
                 "continue_seq": 1, "extra": 1}):
        with pytest.raises(ProgrammingError) as caught:
            s.batches.continue_site(s.batch_id, body)
        assert caught.value.code == "invalid_request"
    s.cont()
    s.done()


# ------------------------------------------------------ UNKNOWN / SAFE_OFF

def test_unknown_next_cycle_is_never_resent_or_settled(tmp_path):
    s = Session(tmp_path, {1: ["success", "lost"]}, repeat=3)
    s.awaiting()
    s.cont()
    batch = s.done()
    unit = batch["units"][0]
    assert unit["outcome"] == "OUTCOME_UNKNOWN" and batch["outcome"] == "OUTCOME_UNKNOWN"
    assert unit["cycle"]["settled"] == 1 and unit["cycle"]["remaining"] == 2
    assert unit["cycle"]["disposition"] == "OUTCOME_UNKNOWN"
    assert len(s.gateway.posts) == 2  # the lost POST was sent once, never again


def test_fail_without_verified_safe_off_counts_but_never_releases(tmp_path):
    s = Session(tmp_path, {1: ["unsafe"]}, repeat=3, replace_ic_before_next_cycle=False)
    batch = s.done()
    unit = batch["units"][0]
    assert unit["cycle"]["fail"] == 1 and unit["cycle"]["continue_seq"] == 0
    assert unit["cycle"]["disposition"] == "SAFETY_BLOCKED"
    assert unit["reason"].startswith("CYCLE_NOT_RELEASED_SAFE_OFF_NOT_VERIFIED")
    assert unit["outcome"] == "FAIL" and len(s.gateway.posts) == 1
    with pytest.raises(ProgrammingError):
        s.cont(seq=1)


# ---------------------------------------------------- journal / restart

def test_continue_journal_failure_is_refused_and_nothing_runs(tmp_path):
    s = Session(tmp_path, repeat=3)
    seq = s.awaiting()["cycle"]["continue_seq"]
    def broken(*_a, **_k):
        raise OSError("disk full")
    original = s.batches._write_journal_locked
    s.batches._write_journal_locked = broken
    with pytest.raises(ProgrammingError) as caught:
        s.cont(seq=seq)
    assert caught.value.status == 503
    assert s.batches._control_failure is not None
    s.batches._write_journal_locked = original
    batch = s.done()
    assert batch["failure_domain"] == "SHARED_CONTROL_FAILURE"
    assert batch["units"][0]["cycle"]["continued_seq"] == 0
    assert len(s.gateway.posts) == 1


def reload(s):
    return ProgrammingBatchCoordinator(s.workflow, journal_path=s.tmp_path / "batches.json",
                                       sleep=lambda _s: None, spawn=lambda _t: None)


def test_manager_restart_while_paused_ends_the_session_without_resend(tmp_path):
    s = Session(tmp_path, repeat=4)
    s.awaiting()
    restarted = reload(s)
    batch = restarted.status_batch(s.batch_id)["batch"]
    unit = batch["units"][0]
    assert batch["state"] == "finished" and unit["outcome"] == "PARTIAL"
    assert unit["reason"] == "MANAGER_RESTARTED_SESSION_ENDED"
    assert (unit["cycle"]["settled"], unit["cycle"]["remaining"]) == (1, 3)
    assert len(restarted.cycle_records(s.batch_id)["records"]) == 1
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    s.done()
    assert len(s.gateway.posts) == 1


def test_restart_between_segment_and_journal_counts_the_cycle_once(tmp_path):
    s = Session(tmp_path, repeat=2)
    s.awaiting()
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    s.done()
    # Rewind the main record to "Cycle 1 in flight": the crash came after the
    # segment append and before the main journal write.
    path = tmp_path / "batches.json"
    data = json.loads(path.read_text())
    record = next(b for b in data["batches"] if b["batch_id"] == s.batch_id)
    record.update(outcome=None, state="running", execution_status="RUNNING",
                  stop_requested=False, finished_at=None)
    unit = record["units"][0]
    unit.update(outcome=None, status="RUNNING")
    unit["cycle"].update(settled=0, **{"pass": 0}, last=None, state="ACTIVE",
                         continue_seq=0, disposition=None)
    path.write_text(json.dumps(data))
    restarted = reload(s)
    unit = restarted.status_batch(s.batch_id)["batch"]["units"][0]
    assert (unit["cycle"]["settled"], unit["cycle"]["pass"]) == (1, 1)
    assert unit["outcome"] == "PARTIAL"
    assert len([r for r in restarted.cycle_records(s.batch_id)["records"]
                if r["type"] == "cycle"]) == 1


def test_long_session_keeps_every_cycle_with_bounded_memory_and_journal(tmp_path):
    cycles = 120  # > 64 retained runs: proves memory follows journal retention
    s = Session(tmp_path, repeat=cycles, replace_ic_before_next_cycle=False)
    batch = s.done(wait=120)
    assert batch["outcome"] == "PASS" and batch["cycles"]["pass"] == cycles
    records = s.ledger("cycle")
    assert [r["cycle_index"] for r in records] == list(range(1, cycles + 1))
    assert len(set(job_ids(records))) == cycles
    # The rewritten main record holds counters + the current Cycle only.
    assert (tmp_path / "batches.json").stat().st_size < 64 * 1024
    assert len(s.workflow._runs) <= 64 + 1
    page = s.batches.cycle_records(s.batch_id, cycles - 10, 50)
    assert page["total"] == cycles and len(page["records"]) == 10
    restarted = reload(s)
    assert restarted.status_batch(s.batch_id)["batch"]["cycles"]["settled"] == cycles
    assert restarted.cycle_records(s.batch_id)["total"] == cycles


def test_blocked_next_cycle_is_neither_failed_nor_skipped(tmp_path):
    s = Session(tmp_path, repeat=2)
    s.awaiting()
    original = s.workflow.target_block
    refusals = []
    def busy_once(alias, site, **kw):
        if not refusals:
            refusals.append(site)
            return "TARGET_NOT_READY", "SITE_BUSY"
        return original(alias, site, **kw)
    s.workflow.target_block = busy_once
    s.cont()
    unit = s.awaiting(seq=2)
    assert unit["cycle"]["wait_reason"] == "NEXT_CYCLE_EXECUTION_SITE_BUSY"
    assert (unit["cycle"]["index"], unit["cycle"]["settled"]) == (2, 1)
    assert len(s.gateway.posts) == 1  # nothing was submitted, nothing counted
    s.cont(seq=2)
    batch = s.done()
    assert batch["units"][0]["cycle"]["settled"] == 2 and len(s.gateway.posts) == 2
