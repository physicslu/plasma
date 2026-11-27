"""Host-only: Manual Repeat v1 (WP-02) on the canonical Manager Batch.

Real ``BundleProgrammingWorkflow`` + ``ProgrammingBatchCoordinator`` with the
fake multi-Site PPU Gateway of ``test_programming_batch_targets``. No PPU,
FPGA or DUT: a PASS here proves Cycle accounting, pause/Continue, Stop and
recovery decisions only - never real programming.
"""
from __future__ import annotations

import json
import os
import resource
import threading
import time
from pathlib import Path

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
    fails without verified SAFE_OFF. ``denied`` / ``failed_safe`` are C-3
    ``run`` refusals with the Worker's structured safety statement;
    ``code_only`` is a denial code without one.
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
                refusal = {"denied": "denied", "failed_safe": "failed_safe",
                           "code_only": {"mode": "denied", "safety": None}}.get(final)
                self.job_kwargs.update(
                    job_final=("failed" if final == "unsafe" else
                               "error" if refusal else final),
                    safe_off=final != "unsafe", worker_refusal=refusal)
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


def test_two_sites_waiting_only_the_continued_site_gets_a_new_job(tmp_path):
    s = Session(tmp_path, sites=(1, 2), repeat=3)
    s.awaiting(1)
    two = s.awaiting(2)
    posts = len(s.gateway.posts)
    s.cont(site=1)  # only Site 1's IC was replaced
    s.awaiting(1, seq=2)
    time.sleep(0.1)
    sites = [p["job_binding"]["site_id"] for p in s.gateway.posts[posts:]]
    assert sites == [1]
    unit = s.unit(2)
    assert unit["cycle"]["state"] == AWAITING_CONTINUE
    assert unit["cycle"]["continue_seq"] == two["cycle"]["continue_seq"]
    assert unit["cycle"]["continued_seq"] == 0 and unit["cycle"]["settled"] == 1
    assert [e["site_id"] for e in s.ledger("continue")] == [1]
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    batch = s.done()
    assert batch["units"][1]["cycle"]["settled"] == 1
    assert sum(p["job_binding"]["site_id"] == 2 for p in s.gateway.posts) == 1


def _release_pending(s, times):
    original = s.workflow.target_block
    seen = []
    def pending(alias, site, **kw):
        # Only the NEXT Cycle meets a Site the PPU has not released yet.
        settled = s.batches._batches[s.batch_id]["units"][0]["cycle"]["settled"]
        if settled and len(seen) < times:
            seen.append(site)
            return "TARGET_NOT_READY", "SITE_NOT_READY_OR_BUSY"
        return original(alias, site, **kw)
    s.workflow.target_block = pending
    return seen


def test_debug_pass_waits_bounded_for_site_release_then_proceeds(tmp_path):
    s = Session(tmp_path, repeat=2, replace_ic_before_next_cycle=False)
    s.batches.release_wait_s = 5.0
    seen = _release_pending(s, 2)
    batch = s.done()
    cycle = batch["units"][0]["cycle"]
    assert len(seen) == 2 and cycle["pass"] == 2 and cycle["continue_seq"] == 0
    assert len(s.gateway.posts) == 2


def test_site_never_released_pauses_after_the_bound_without_submitting(tmp_path):
    s = Session(tmp_path, repeat=2, replace_ic_before_next_cycle=False)
    s.batches.release_wait_s = 0.3
    seen = _release_pending(s, 10**6)
    unit = s.awaiting()
    assert unit["cycle"]["wait_reason"] == "NEXT_CYCLE_EXECUTION_SITE_NOT_READY_OR_BUSY"
    assert len(seen) >= 1 and len(s.gateway.posts) == 1
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    s.done()
    assert len(s.gateway.posts) == 1


def test_stop_during_release_wait_submits_nothing(tmp_path):
    s = Session(tmp_path, repeat=2, replace_ic_before_next_cycle=False)
    s.batches.release_wait_s = 30.0
    seen = _release_pending(s, 10**6)
    s.until(lambda _b: seen, "release wait")
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    batch = s.done(wait=5)
    assert batch["execution_status"] == "STOPPED" and len(s.gateway.posts) == 1


@pytest.mark.skipif(not os.environ.get("PLASMA_REPEAT_STRESS"),
                    reason="opt-in Host-only stress: PLASMA_REPEAT_STRESS=1 (about 10000 real Cycles)")
def test_stress_10000_cycles_counts_journal_restart_and_resources(tmp_path):
    cycles = MAX_REPEAT
    began = time.monotonic()
    s = Session(tmp_path, repeat=cycles, replace_ic_before_next_cycle=False)
    s.batches.sleep = lambda _s: None
    batch = s.done(wait=6 * 3600)
    elapsed = time.monotonic() - began
    cycle = batch["units"][0]["cycle"]
    assert batch["outcome"] == "PASS" and cycle["settled"] == cycles and cycle["pass"] == cycles
    assert cycle["remaining"] == 0 and len(s.gateway.posts) == cycles
    records = [r for r in s.batches._ledger_records(s.batch_id) if r["type"] == "cycle"]
    assert [r["cycle_index"] for r in records] == list(range(1, cycles + 1))
    assert len(set(job_ids(records))) == cycles
    assert len(s.workflow._runs) <= 64 + 1
    main = (tmp_path / "batches.json").stat().st_size
    runs = (tmp_path / "runs.json").stat().st_size
    segment = s.batches._ledger_path(s.batch_id).stat().st_size
    assert main < 64 * 1024
    loaded = time.monotonic()
    restarted = reload(s)
    reload_s = time.monotonic() - loaded
    view = restarted.status_batch(s.batch_id)["batch"]
    assert view["cycles"]["settled"] == cycles and restarted.cycle_records(s.batch_id)["total"] == cycles
    metrics = {"cycles": cycles, "elapsed_s": round(elapsed, 1),
               "cycles_per_s": round(cycles / elapsed, 1),
               "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               "main_journal_bytes": main, "run_journal_bytes": runs,
               "cycle_segment_bytes": segment, "workflow_runs_in_memory": len(s.workflow._runs),
               "restart_load_s": round(reload_s, 3)}
    out = os.environ.get("PLASMA_REPEAT_STRESS_METRICS")
    if out:
        Path(out).write_text(json.dumps(metrics, indent=1) + "\n")


def _platform_busy(s, times):
    """A PPU_BUSY verdict right after a Cycle. Before Site-level admission
    (#1503) the Platform gate's PPU-wide fleet read produced it for a PEER
    Site of the same Batch and the lane waited it out. Now PPU_BUSY only means
    another Execution Owner (or maintenance), so it is paused for at once."""
    seen = []
    def gate(alias):
        settled = s.batches._batches[s.batch_id]["units"][0]["cycle"]["settled"]
        if settled and len(seen) < times:
            seen.append(alias)
            return "TARGET_NOT_READY", "PPU_BUSY"
        return None
    s.batches.platform_gate = gate
    return seen


def test_ppu_busy_after_a_cycle_is_not_waited_out_and_submits_nothing(tmp_path):
    s = Session(tmp_path, repeat=2, replace_ic_before_next_cycle=False)
    s.batches.release_wait_s = 30.0
    seen = _platform_busy(s, 1)
    began = time.monotonic()
    unit = s.awaiting()
    assert time.monotonic() - began < 5.0          # no RELEASE_WAIT_S re-check loop
    assert unit["cycle"]["wait_reason"] == "NEXT_CYCLE_EXECUTION_PPU_BUSY"
    assert len(seen) == 1 and len(s.gateway.posts) == 1
    # Continue re-runs every gate (now clear) and only then submits.
    s.cont()
    batch = s.done()
    assert batch["units"][0]["cycle"]["pass"] == 2 and len(s.gateway.posts) == 2


def test_platform_ppu_busy_that_never_clears_pauses_without_submitting(tmp_path):
    s = Session(tmp_path, repeat=2, replace_ic_before_next_cycle=False)
    s.batches.release_wait_s = 0.3
    _platform_busy(s, 10**6)
    unit = s.awaiting()
    assert unit["cycle"]["wait_reason"] == "NEXT_CYCLE_EXECUTION_PPU_BUSY"
    assert len(s.gateway.posts) == 1
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    s.done()
    assert len(s.gateway.posts) == 1


def test_only_the_sites_own_release_is_waited_for():
    from plasma_manager.programming_batch import RELEASE_PENDING_REASONS, RELEASE_WAIT_S
    # One E/P/V Job ~12.5 s on Z2 (2026-11-19); the bound is unchanged.
    assert RELEASE_WAIT_S >= 30 and RELEASE_PENDING_REASONS == {"SITE_NOT_READY_OR_BUSY"}


# ------------------------------------------------- Batch Statistics v1 (T01-T21)
# Host-only: one statistics contract for EMode and PMode, read from the
# Manager's own counters and its append-only Cycle History. No PPU/FPGA/DUT.

def drive_continues(s, sites, cycles):
    """Replace-IC: answer every pause of every Site until the Batch ends."""
    deadline = time.monotonic() + WAIT * 4
    while time.monotonic() < deadline:
        batch = s.view()
        if batch["outcome"] is not None:
            return s.done()
        for unit in batch["units"]:
            if unit["cycle"]["state"] == AWAITING_CONTINUE:
                s.cont(unit["site_id"], unit["cycle"]["continue_seq"])
        time.sleep(0.005)
    raise AssertionError(f"replace-IC session did not finish: {s.view()}")


def history(batches, batch_id, limit=7):
    """Every History record, read the way a Console does: by cursor pages."""
    cursor, seen = 0, []
    while True:
        page = batches.cycle_records(batch_id, cursor, limit)
        seen += page["records"]
        assert page["next_offset"] >= cursor
        if page["next_offset"] == cursor:
            return seen, page["total"]
        cursor = page["next_offset"]


def assert_all_pass_statistics(batch, sites, repeat):
    cycles, counts = batch["cycles"], batch["counts"]
    total = sites * repeat
    assert (cycles["planned"], cycles["settled"], cycles["pass"], cycles["fail"],
            cycles["remaining"]) == (total, total, total, 0, 0)
    # Job attempts are cumulative over every Cycle; no Retry happened.
    assert cycles["attempts"] == counts["attempts"] == total
    assert cycles["retry_attempts"] == 0
    assert cycles["sites_completed"] == sites
    # Site final outcomes stay one per Site, never a Cycle count.
    assert counts["sites"] == sites and counts["pass"] == sites
    for unit in batch["units"]:
        assert unit["cycle"]["attempts"] == repeat and unit["cycle"]["retry_attempts"] == 0
        assert len(unit["attempts"]) == 1  # the live list is the current Cycle only


def assert_history_complete(s, sites, repeat):
    records, total = history(s.batches, s.batch_id)
    seqs = [r["seq"] for r in records]
    assert seqs == list(range(total))  # ordered, gap-free, no duplicate
    cycles = [r for r in records if r["type"] == "cycle"]
    assert len(cycles) == sites * repeat
    for site in sites_of(sites):
        mine = [r for r in cycles if r["site_id"] == site]
        assert [r["cycle_index"] for r in mine] == list(range(1, repeat + 1))
    for record in cycles:
        receipt = record["receipt"]
        assert receipt["run_id"] and receipt["job_id"] and receipt["safe_off"] is True
        assert receipt["job_binding_confirmed"] is True
        for key in ("readback_sha256", "job_binding_sha256", "resource_set_sha256"):
            assert key in receipt
        attempt = record["attempts"][-1]
        assert attempt["run_id"] == receipt["run_id"] and attempt["job_id"] == receipt["job_id"]
    assert len(set(job_ids(cycles))) == sites * repeat
    return records


def sites_of(count):
    return tuple(range(1, count + 1))


def test_t01_replace_ic_two_sites_repeat_10(tmp_path):
    s = Session(tmp_path, sites=(1, 2), repeat=10)
    batch = drive_continues(s, (1, 2), 10)
    assert batch["outcome"] == "PASS" and batch["policy"]["replace_ic_before_next_cycle"]
    assert_all_pass_statistics(batch, 2, 10)
    assert_history_complete(s, 2, 10)
    assert len(s.ledger("continue")) == 18 and len(s.gateway.posts) == 20


def test_t02_same_ic_debug_two_sites_repeat_10(tmp_path):
    s = Session(tmp_path, sites=(1, 2), repeat=10, replace_ic_before_next_cycle=False)
    batch = s.done()
    assert batch["outcome"] == "PASS" and not batch["policy"]["replace_ic_before_next_cycle"]
    assert_all_pass_statistics(batch, 2, 10)
    assert_history_complete(s, 2, 10)
    assert s.ledger("continue") == [] and len(s.gateway.posts) == 20


def test_t03_repeat_1_statistics_are_one_cycle_one_attempt(tmp_path):
    s = Session(tmp_path)
    batch = s.done()
    assert_all_pass_statistics(batch, 1, 1)
    page = s.batches.cycle_records(s.batch_id)
    assert page["total"] == 1 and page["next_offset"] == 1 and page["records"][0]["seq"] == 0


def test_t04_repeat_100_accumulates_every_cycle(tmp_path):
    s = Session(tmp_path, sites=(1, 2), repeat=100, replace_ic_before_next_cycle=False)
    batch = s.done(wait=120)
    assert_all_pass_statistics(batch, 2, 100)
    assert_history_complete(s, 2, 100)


def test_t05_retry_makes_attempts_exceed_cycles(tmp_path):
    # Cycle 1: FAIL then Retry PASS. Cycles 2, 3: PASS. Same-IC Debug.
    s = Session(tmp_path, {1: ["failed", "success"]}, repeat=3, retry_limit=1,
                replace_ic_before_next_cycle=False)
    batch = s.done()
    cycles = batch["cycles"]
    assert (cycles["settled"], cycles["pass"], cycles["fail"]) == (3, 3, 0)
    assert cycles["attempts"] == batch["counts"]["attempts"] == 4
    assert cycles["retry_attempts"] == 1 and len(s.gateway.posts) == 4
    first = s.ledger("cycle")[0]
    assert [a["attempt"] for a in first["attempts"]] == [1, 2]
    assert first["attempts"][0]["retry"]["decision"] == "RETRY"


def test_t06_t07_stop_after_first_cycle_keeps_pass_cycles_as_partial(tmp_path):
    s = Session(tmp_path, sites=(1, 2), repeat=10)
    s.awaiting(1)
    s.awaiting(2)
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    batch = s.done()
    cycles, counts = batch["cycles"], batch["counts"]
    assert batch["outcome"] == "PARTIAL" and batch["execution_status"] == "STOPPED"
    assert cycles["sites_completed"] == 0 and len(batch["units"]) == 2
    assert (cycles["pass"], cycles["settled"], cycles["planned"], cycles["remaining"]) == (2, 2, 20, 18)
    # Site final PASS 0 is not Cycle PASS 0: both are reported, separately.
    assert counts["pass"] == 0 and counts["partial"] == 2
    assert cycles["attempts"] == 2 and cycles["retry_attempts"] == 0
    assert len(s.ledger("cycle")) == 2 and len(s.gateway.posts) == 2


def test_t08_fail_cycles_are_counted_once_each(tmp_path):
    s = Session(tmp_path, {1: ["success", "failed", "success", "failed"]}, repeat=4)
    batch = drive_continues(s, (1,), 4)
    cycles = batch["cycles"]
    assert (cycles["settled"], cycles["pass"], cycles["fail"]) == (4, 2, 2)
    assert cycles["attempts"] == 4 and cycles["retry_attempts"] == 0
    assert batch["outcome"] == "FAIL" and batch["counts"]["fail"] == 1
    assert [r["outcome"] for r in s.ledger("cycle")] == ["PASS", "FAIL", "PASS", "FAIL"]


def test_t09_outcome_unknown_is_never_counted_as_pass(tmp_path):
    s = Session(tmp_path, {1: ["success", "lost"]}, repeat=3,
                replace_ic_before_next_cycle=False)
    batch = s.done()
    cycles, counts = batch["cycles"], batch["counts"]
    assert batch["outcome"] == "OUTCOME_UNKNOWN"
    assert (cycles["settled"], cycles["pass"], cycles["fail"]) == (1, 1, 0)
    assert counts["pass"] == 0 and counts["unknown"] == 1
    # The unknown attempt is an attempt, held live (never settled, never resent).
    assert cycles["attempts"] == 2 and len(s.gateway.posts) == 2
    assert [r["cycle_index"] for r in s.ledger("cycle")] == [1]
    assert batch["units"][0]["attempts"][-1]["cycle_index"] == 2


def test_t10_t11_t12_history_cursor_survives_missed_polls_reload_and_repeats(tmp_path):
    s = Session(tmp_path, sites=(1, 2), repeat=6)
    s.awaiting(1)
    s.awaiting(2)
    # A Console that saw only the first poll, then missed every later one.
    first = s.batches.cycle_records(s.batch_id, 0, 1000)
    cursor = first["next_offset"]
    assert cursor == 2 and [r["seq"] for r in first["records"]] == [0, 1]
    batch = drive_continues(s, (1, 2), 6)
    assert batch["outcome"] == "PASS"
    late = s.batches.cycle_records(s.batch_id, cursor, 1000)
    records = first["records"] + late["records"]
    assert [r["seq"] for r in records] == list(range(late["total"]))
    assert len([r for r in records if r["type"] == "cycle"]) == 12
    # The same cursor read twice returns the same records, never new ones.
    again = s.batches.cycle_records(s.batch_id, cursor, 1000)
    assert again["records"] == late["records"]
    # A reloaded Browser starts from 0 and gets exactly the same history.
    reloaded, total = history(s.batches, s.batch_id, limit=5)
    assert reloaded == records and total == late["total"]
    # A cursor past the end is empty and stays put.
    end = s.batches.cycle_records(s.batch_id, total, 10)
    assert end["records"] == [] and end["next_offset"] == total


def test_t13_restart_keeps_cumulative_attempts_and_history(tmp_path):
    s = Session(tmp_path, {1: ["failed", "success"]}, sites=(1, 2), repeat=5, retry_limit=1,
                replace_ic_before_next_cycle=False)
    batch = s.done()
    before, history_before = batch["cycles"], history(s.batches, s.batch_id)
    assert before["attempts"] == 11 and before["retry_attempts"] == 1
    restarted = reload(s)
    after = restarted.status_batch(s.batch_id)["batch"]["cycles"]
    assert after == before
    assert history(restarted, s.batch_id) == history_before
    # A journal written before Batch Statistics v1 has no archive counter:
    # it is rebuilt once, at load, from the Batch's own Cycle History.
    path = tmp_path / "batches.json"
    data = json.loads(path.read_text())
    for unit in next(b for b in data["batches"] if b["batch_id"] == s.batch_id)["units"]:
        del unit["cycle"]["attempts_archived"]
    path.write_text(json.dumps(data))
    migrated = reload(s).status_batch(s.batch_id)["batch"]
    assert migrated["cycles"] == before
    assert [u["cycle"]["attempts"] for u in migrated["units"]] == [6, 5]


def test_restart_mid_session_counts_archived_and_live_attempts_once(tmp_path):
    s = Session(tmp_path, sites=(1,), repeat=4)
    s.awaiting()
    s.cont()
    s.awaiting(seq=2)
    restarted = reload(s)
    batch = restarted.status_batch(s.batch_id)["batch"]
    # Cycle 1 archived, Cycle 2 settled and still held: 2 attempts, not 3.
    assert batch["cycles"]["attempts"] == 2 and batch["cycles"]["settled"] == 2
    assert batch["outcome"] == "PARTIAL" and batch["cycles"]["remaining"] == 2
    s.batches.request_stop_batch(s.batch_id, {"stop": "STOP_QUEUING"})
    s.done()


def test_t14_parallel_sites_never_overwrite_each_others_statistics(tmp_path):
    s = Session(tmp_path, {1: ["success", "failed", "success"]}, sites=(1, 2), repeat=3,
                replace_ic_before_next_cycle=False)
    s.awaiting(1)            # Site 1 paused on its FAIL; Site 2 keeps running
    s.until(lambda b: next(u for u in b["units"] if u["site_id"] == 2)["outcome"] == "PASS",
            "Site 2 finished")
    s.cont(1)
    batch = s.done()
    units = {u["site_id"]: u["cycle"] for u in batch["units"]}
    assert (units[1]["pass"], units[1]["fail"], units[1]["attempts"]) == (2, 1, 3)
    assert (units[2]["pass"], units[2]["fail"], units[2]["attempts"]) == (3, 0, 3)
    records = s.ledger("cycle")
    for site in (1, 2):
        assert [r["cycle_index"] for r in records if r["site_id"] == site] == [1, 2, 3]


def test_t15_two_ppus_keep_separate_statistics_and_history(tmp_path):
    pending = []
    batches, workflow, gateways, _ = rig(tmp_path, aliases=("z2", "z3"), sites=(1, 2),
                                         spawn_batch=pending.append)
    batches.sleep = lambda _s: time.sleep(0.002)
    started = batches.start_batch(with_start(
        workflow, [{"ppu_alias": "z2", "site_ids": [1, 2]}, {"ppu_alias": "z3", "site_ids": [1]}],
        repeat=3, replace_ic_before_next_cycle=False))
    batch_id = started["batch"]["batch_id"]
    pending.pop()()
    batch = batches.status_batch(batch_id)["batch"]
    assert batch["outcome"] == "PASS"
    assert batch["cycles"]["settled"] == 9 and batch["cycles"]["attempts"] == 9
    by_unit = {(u["ppu_alias"], u["site_id"]): u["cycle"]["attempts"] for u in batch["units"]}
    assert by_unit == {("z2", 1): 3, ("z2", 2): 3, ("z3", 1): 3}
    records, _ = history(batches, batch_id)
    keys = [(r["ppu_alias"], r["site_id"], r["cycle_index"]) for r in records]
    assert sorted(keys) == sorted((a, s, c) for a, s in by_unit for c in (1, 2, 3))
    assert len(gateways["z2"].posts) == 6 and len(gateways["z3"].posts) == 3


def test_t21_status_and_history_reads_stay_bounded(tmp_path, monkeypatch):
    cycles = 300
    s = Session(tmp_path, sites=(1, 2), repeat=cycles, replace_ic_before_next_cycle=False)
    batch = s.done(wait=300)
    assert_all_pass_statistics(batch, 2, cycles)
    restarted = reload(s)

    def full_read(*_a, **_k):
        raise AssertionError("a poll must not re-read the whole Cycle History")
    monkeypatch.setattr(restarted, "_ledger_records", full_read)
    began = time.monotonic()
    for _ in range(50):
        view = restarted.status_batch(s.batch_id)["batch"]
    status_s = time.monotonic() - began
    assert view["cycles"]["attempts"] == 2 * cycles
    # The index is built once; every later page is a bounded seek + read.
    first = restarted.cycle_records(s.batch_id, 0, 100)
    reads = []
    real_open = Path.open

    def counting_open(self, *a, **k):
        reads.append(self)
        return real_open(self, *a, **k)
    monkeypatch.setattr(Path, "open", counting_open)
    began = time.monotonic()
    tail = restarted.cycle_records(s.batch_id, 2 * cycles - 10, 1000)
    page_s = time.monotonic() - began
    assert len(reads) == 1 and len(tail["records"]) == 10
    assert tail["records"][-1]["seq"] == 2 * cycles - 1 and tail["next_offset"] == 2 * cycles
    assert len(first["records"]) == 100 and first["next_offset"] == 100
    assert status_s < 5 and page_s < 1


def test_torn_history_line_keeps_a_stable_cursor(tmp_path):
    s = Session(tmp_path, repeat=3, replace_ic_before_next_cycle=False)
    s.done()
    segment = s.batches._ledger_path(s.batch_id)
    with segment.open("ab") as stream:
        stream.write(b'{"type": "cycle", "torn')   # crash mid-append
    restarted = reload(s)
    restarted._ledger_append_locked(s.batch_id, {"type": "probe", "batch_id": s.batch_id})
    live = restarted.cycle_records(s.batch_id, 0, 100)
    assert [r["seq"] for r in live["records"]] == [0, 1, 2, 4] and live["total"] == 5
    assert live["records"][-1]["type"] == "probe"
    again = reload(s).cycle_records(s.batch_id, 0, 100)
    assert again["records"] == live["records"] and again["total"] == 5
