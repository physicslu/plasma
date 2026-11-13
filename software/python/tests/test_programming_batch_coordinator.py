"""Host-only: Manager-owned EMode Batch coordinator (safe Retry, Stop Policy).

Real ``BundleProgrammingWorkflow`` + ``ProgrammingBatchCoordinator``; fake
Bootstrap coordinator and fake PPU Gateway. No PPU, FPGA or DUT. A PASS here
proves the retry / stop decision contract only.
"""
from __future__ import annotations

import json

import pytest

from plasma_manager.programming import ProgrammingError
from plasma_manager.programming_batch import (
    MAX_RETRY_LIMIT, ProgrammingBatchCoordinator, parse_policy, retry_eligibility,
)

from .test_bundle_programming_workflow import (
    ALIAS, FakeCoordinator, FakeGateway, OPS_RESOURCE_SHA, image, make, ops_body,
)

FULL = ["erase", "program", "verify"]


def rig(tmp_path, *, spawn_batch=None, **gateway_kw):
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway = FakeGateway(image=image(), coordinator=coord,
                          resource_for=lambda _a: OPS_RESOURCE_SHA, **gateway_kw)
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    batches = ProgrammingBatchCoordinator(
        workflow, journal_path=tmp_path / "batches.json", sleep=lambda _s: None,
        spawn=spawn_batch or (lambda target: target()), poll_interval_s=0.0)
    return batches, workflow, gateway


def body(retry_limit=0, stop_policy=None, operations=FULL, **extra):
    request = {**ops_body(operations), "retry_limit": retry_limit, **extra}
    if stop_policy is not None:
        request["stop_policy"] = stop_policy
    return request


def final(batches, started):
    return batches.status(ALIAS, started["batch"]["batch_id"])["batch"]


# ------------------------------------------------------------------ policy

@pytest.mark.parametrize("policy, code", [
    ({"repeat": 2}, "repeat_not_supported"),
    ({"repeat": 0}, "repeat_not_supported"),
    ({"repeat": True}, "repeat_not_supported"),
    ({"retry_limit": -1}, "invalid_request"),
    ({"retry_limit": MAX_RETRY_LIMIT + 1}, "invalid_request"),
    ({"retry_limit": "1"}, "invalid_request"),
    ({"retry_limit": True}, "invalid_request"),
    ({"stop_policy": {"kind": "abort"}}, "invalid_request"),
    ({"stop_policy": {"kind": "failed_sites", "threshold": 2}}, "invalid_request"),
    ({"stop_policy": {"kind": "failed_sites"}}, "invalid_request"),
    ({"stop_policy": "never"}, "invalid_request"),
])
def test_policy_is_validated_and_repeat_is_not_implemented(tmp_path, policy, code):
    batches, _w, gateway = rig(tmp_path)
    with pytest.raises(ProgrammingError) as caught:
        batches.start(ALIAS, {**ops_body(FULL), **policy})
    assert caught.value.code == code and gateway.posts == []
    assert json.loads((tmp_path / "batches.json").read_text())["batches"] == [] \
        if (tmp_path / "batches.json").exists() else True


def test_default_policy_is_one_attempt_repeat_one_never_stop():
    assert parse_policy({}) == {"repeat": 1, "retry_limit": 0, "stop_policy": {"kind": "never"}}


def test_a_batch_takes_an_operations_list_never_a_read_or_flash_cycle(tmp_path):
    batches, _w, gateway = rig(tmp_path)
    for request in ({"icpn": "STM32F103C8T6", "site_id": 2, "operation": "read",
                     "address": 0x08000000, "length": 16},
                    {**ops_body(FULL), "operation": "flash_cycle"},
                    {k: v for k, v in ops_body(FULL).items() if k != "operations"}):
        with pytest.raises(ProgrammingError) as caught:
            batches.start(ALIAS, request)
        assert caught.value.code == "invalid_request"
    assert gateway.posts == []


# ------------------------------------------------------------------ outcomes

def test_pass_on_the_first_attempt_is_one_job_and_counts_once(tmp_path):
    batches, _w, gateway = rig(tmp_path)
    batch = final(batches, batches.start(ALIAS, body(retry_limit=3)))
    assert batch["outcome"] == "PASS" and batch["state"] == "finished"
    assert len(batch["attempts"]) == 1 and len(gateway.posts) == 1
    assert batch["counts"] == {"pass": 1, "fail": 0, "blocked": 0, "unknown": 0,
                               "sites": 1, "attempts": 1}
    assert batch["policy"] == {"repeat": 1, "retry_limit": 3, "stop_policy": {"kind": "never"}}
    assert batch["auto_retry"] == "DISABLED" and batch["operations"] == FULL
    assert batch["current_run"]["outcome"] == "PASS"
    assert gateway.posts[0]["operations"] == FULL


def test_definite_fail_is_retried_with_a_new_plan_run_and_job_then_passes(tmp_path):
    batches, workflow, gateway = rig(tmp_path, job_final=["failed", "success"])
    batch = final(batches, batches.start(ALIAS, body(retry_limit=2)))
    assert batch["outcome"] == "PASS"
    first, second = batch["attempts"]
    assert (first["outcome"], second["outcome"]) == ("FAIL", "PASS")
    assert first["retry"] == {"eligible": True, "reason": "DEFINITE_FAIL_SAFE_OFF_VERIFIED",
                              "decision": "RETRY"}
    assert second["retry"] is None
    # Independent identities per attempt; each Job submitted exactly once.
    assert len({first["plan_id"], second["plan_id"]}) == 2
    assert len({first["run_id"], second["run_id"]}) == 2
    assert len({first["job_id"], second["job_id"]}) == 2
    assert len(gateway.posts) == 2
    for run_id in (first["run_id"], second["run_id"]):
        run = workflow.run_status(ALIAS, run_id)["run"]
        assert run["job_submission_count"] == 1 and run["auto_retry"] == "DISABLED"
    # The Batch is ONE IC: one PASS, no FAIL, never double counted.
    assert batch["counts"] == {"pass": 1, "fail": 0, "blocked": 0, "unknown": 0,
                               "sites": 1, "attempts": 2}


def test_retry_limit_bounds_the_attempts_and_the_batch_fails_once(tmp_path):
    batches, _w, gateway = rig(tmp_path, job_final="failed")
    batch = final(batches, batches.start(ALIAS, body(retry_limit=2)))
    assert batch["outcome"] == "FAIL" and batch["reason"] == "RETRY_LIMIT_EXHAUSTED"
    assert len(batch["attempts"]) == 3 == len(gateway.posts)
    assert [a["retry"]["decision"] for a in batch["attempts"]] == ["RETRY", "RETRY", "NO_RETRY"]
    assert batch["counts"] == {"pass": 0, "fail": 1, "blocked": 0, "unknown": 0,
                               "sites": 1, "attempts": 3}


def test_retry_limit_zero_never_retries_and_keeps_the_run_reason(tmp_path):
    batches, _w, gateway = rig(tmp_path, job_final="failed")
    batch = final(batches, batches.start(ALIAS, body(retry_limit=0)))
    assert batch["outcome"] == "FAIL" and batch["reason"] == "JOB_NOT_SUCCESS"
    assert len(gateway.posts) == 1


@pytest.mark.parametrize("gateway_kw, outcome, why", [
    # Unknown outcomes: lost submission, HTTP 5xx, lost status.
    ({"post_raises": True}, "OUTCOME_UNKNOWN", None),
    ({"post_status": 503}, "OUTCOME_UNKNOWN", None),
    # A FAIL without verified SAFE_OFF is not a retryable FAIL.
    ({"job_final": "failed", "safe_off": False}, "FAIL", "RETRY_NOT_ELIGIBLE_SAFE_OFF_NOT_VERIFIED"),
    # A rejected submission has no terminal Job evidence.
    ({"post_status": 422}, "FAIL", "RETRY_NOT_ELIGIBLE_NO_TRUSTED_TERMINAL_JOB_STATE"),
    # The PPU did not echo the Binding it ran.
    ({"job_final": "failed", "echo": False}, "FAIL", "RETRY_NOT_ELIGIBLE_JOB_IDENTITY_NOT_CONFIRMED"),
])
def test_only_a_definite_safe_fail_is_ever_retried(tmp_path, gateway_kw, outcome, why):
    batches, workflow, gateway = rig(tmp_path, **gateway_kw)
    batch = final(batches, batches.start(ALIAS, body(retry_limit=3)))
    assert batch["outcome"] == outcome
    assert len(batch["attempts"]) == 1 and len(gateway.posts) == 1  # never resubmitted
    if outcome == "OUTCOME_UNKNOWN":
        assert batch["attempts"][0]["retry"] is None
        # Still latched: neither a new Batch nor a single run can start.
        with pytest.raises(ProgrammingError) as caught:
            batches.start(ALIAS, body(retry_limit=1))
        assert caught.value.code == "programming_outcome_unknown_unresolved"
        assert len(batches._batches) == 1  # the refused request created no Batch
        assert len(gateway.posts) == 1
    else:
        assert batch["reason"] == why
        assert batch["attempts"][0]["retry"]["decision"] == "NO_RETRY"
        assert batch["attempts"][0]["retry"]["eligible"] is False


def test_retry_is_refused_when_the_ppu_is_not_released(tmp_path):
    batches, _w, gateway = rig(tmp_path, job_final="failed")
    original = gateway.relay
    state = {"lease_busy": False}

    def relay(method, path, **kw):
        # After the first Job, the PPU still reports a held execution lease.
        if method == "GET" and path.startswith("/api/status?job="):
            state["lease_busy"] = True
        gateway.busy = state["lease_busy"] and path.startswith("/api/status?site=")
        return original(method, path, **kw)

    gateway.relay = relay
    batch = final(batches, batches.start(ALIAS, body(retry_limit=3)))
    assert batch["outcome"] == "FAIL"
    assert batch["reason"] == "RETRY_NOT_ELIGIBLE_PPU_NOT_RELEASED_SITE_NOT_READY_OR_BUSY"
    assert len(gateway.posts) == 1


def test_recovery_required_blocks_a_retry(tmp_path):
    batches, workflow, gateway = rig(tmp_path, job_final="failed")
    original = workflow.coordinator.assets
    calls = {"n": 0}

    def assets(alias):
        calls["n"] += 1
        state = original(alias)
        # The Active Set needs recovery once the first attempt is over.
        return {**state, "state": "RECOVERY_REQUIRED"} if gateway.posts and gateway.polls >= 2 \
            else state

    workflow.coordinator.assets = assets
    batch = final(batches, batches.start(ALIAS, body(retry_limit=2)))
    assert batch["outcome"] == "FAIL"
    assert batch["reason"] == "RETRY_NOT_ELIGIBLE_PPU_NOT_RELEASED_PPU_RECOVERY_REQUIRED"
    assert len(gateway.posts) == 1


# ---------------------------------------------------------------- stop policy

def test_stop_policy_failed_sites_stops_queuing_after_the_first_fail(tmp_path):
    batches, _w, gateway = rig(tmp_path, job_final="failed")
    batch = final(batches, batches.start(
        ALIAS, body(retry_limit=3, stop_policy={"kind": "failed_sites", "threshold": 1})))
    assert batch["outcome"] == "FAIL"
    assert batch["reason"] == "STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED"
    assert len(batch["attempts"]) == 1 and len(gateway.posts) == 1
    assert batch["attempts"][0]["retry"] == {
        "eligible": True, "reason": "DEFINITE_FAIL_SAFE_OFF_VERIFIED", "decision": "NO_RETRY"}


def test_stop_request_only_stops_queuing_and_never_touches_the_running_job(tmp_path):
    batches, workflow, gateway = rig(tmp_path, job_final="failed")
    stopped = {}
    original = gateway.relay

    def relay(method, path, **kw):
        # The operator presses stop while the first Job is running.
        if method == "GET" and path.startswith("/api/status?job=") and not stopped:
            batch_id = next(iter(batches._batches))
            stopped["view"] = batches.request_stop(ALIAS, batch_id, {"stop": "STOP_QUEUING"})
        return original(method, path, **kw)

    gateway.relay = relay
    batch = final(batches, batches.start(ALIAS, body(retry_limit=3)))
    assert stopped["view"]["batch"]["stop_requested"] is True
    assert stopped["view"]["batch"]["outcome"] is None  # the running attempt is not cut
    # The running Job was observed to its real end; nothing was cancelled.
    assert batch["attempts"][0]["outcome"] == "FAIL"
    assert batch["outcome"] == "FAIL" and batch["reason"] == "STOP_REQUESTED_NO_FURTHER_ATTEMPT"
    assert len(gateway.posts) == 1
    methods = [post for post in gateway.posts]
    assert all("cancel" not in json.dumps(post) for post in methods)
    assert workflow._active_run(ALIAS) is None


def test_stop_before_any_submission_submits_nothing(tmp_path):
    pending = []
    batches, _w, gateway = rig(tmp_path, spawn_batch=pending.append)
    started = batches.start(ALIAS, body(retry_limit=1))
    assert started["batch"]["outcome"] is None and started["batch"]["attempts"] == []
    with pytest.raises(ProgrammingError) as caught:
        batches.request_stop(ALIAS, started["batch"]["batch_id"], {"stop": "now"})
    assert caught.value.code == "invalid_request"
    batches.request_stop(ALIAS, started["batch"]["batch_id"], {"stop": "STOP_QUEUING"})
    pending.pop()()
    batch = final(batches, started)
    # Execution status and outcome are separate now: STOPPED is the status,
    # and the outcome is what the Targets say - nothing executed, so BLOCKED.
    assert batch["execution_status"] == "STOPPED"
    assert batch["outcome"] == "BLOCKED" and batch["reason"] == "STOP_REQUESTED_NOTHING_SUBMITTED"
    assert gateway.posts == [] and batch["counts"] == {
        "pass": 0, "fail": 0, "blocked": 0, "unknown": 0, "sites": 1, "attempts": 0}


def test_stop_never_ends_or_acknowledges_an_unknown_run(tmp_path):
    batches, workflow, gateway = rig(tmp_path, post_raises=True)
    started = batches.start(ALIAS, body(retry_limit=2))
    batch = batches.request_stop(ALIAS, started["batch"]["batch_id"], {"stop": "STOP_QUEUING"})["batch"]
    assert batch["outcome"] == "OUTCOME_UNKNOWN" and batch["stop_requested"] is False
    assert workflow._unknown_latched(ALIAS) is not None


# -------------------------------------------------------- admission and restart

def test_one_batch_per_ppu_and_refused_plan_creates_no_batch(tmp_path):
    pending = []
    batches, _w, gateway = rig(tmp_path, spawn_batch=pending.append)
    batches.start(ALIAS, body())
    with pytest.raises(ProgrammingError) as caught:
        batches.start(ALIAS, body())
    assert caught.value.code == "programming_batch_in_progress"
    other, _w2, gateway2 = rig(tmp_path / "other")
    with pytest.raises(ProgrammingError) as caught:
        other.start(ALIAS, body(operations=["erase", "verify"]))
    assert caught.value.code == "operations_invalid"
    assert other._batches == {} and gateway2.posts == [] and gateway.posts == []


def test_manager_restart_never_resubmits_and_closes_the_batch_conservatively(tmp_path):
    # 1) Stopped before any submission: nothing reached the PPU.
    pending = []
    batches, workflow, gateway = rig(tmp_path, spawn_batch=pending.append)
    started = batches.start(ALIAS, body(retry_limit=2))
    again = ProgrammingBatchCoordinator(workflow, journal_path=tmp_path / "batches.json")
    batch = again.status(ALIAS, started["batch"]["batch_id"])["batch"]
    assert (batch["outcome"], batch["reason"]) == ("BLOCKED", "MANAGER_RESTARTED_BEFORE_SUBMISSION")
    assert gateway.posts == []

    # 2) Stopped while an attempt was in flight: the outcome is unknown.
    root = tmp_path / "inflight"
    held = []
    batches, workflow, gateway = rig(root)
    workflow.spawn = held.append  # the run never executes (Manager dies)
    batches.spawn = lambda target: held.append(target)
    started = batches.start(ALIAS, body(retry_limit=2))
    batch_job = held.pop()

    class Died(BaseException):
        pass

    def die(_seconds):
        raise Died()

    batches.sleep = die
    with pytest.raises(Died):
        batch_job()
    # A new Manager process loads both journals.
    from .test_bundle_programming_workflow import make as remake
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway2 = FakeGateway(image=image(), coordinator=coord,
                           resource_for=lambda _a: OPS_RESOURCE_SHA)
    workflow2, _c, _g = remake(root, coordinator=coord, gateway=gateway2)
    reloaded = ProgrammingBatchCoordinator(workflow2, journal_path=root / "batches.json")
    batch = reloaded.status(ALIAS, started["batch"]["batch_id"])["batch"]
    assert (batch["outcome"], batch["reason"]) == (
        "OUTCOME_UNKNOWN", "MANAGER_RESTARTED_DURING_ATTEMPT")
    assert len(batch["attempts"]) == 1 and batch["attempts"][0]["outcome"] == "OUTCOME_UNKNOWN"
    assert gateway.posts == [] and gateway2.posts == []  # nothing was (re)submitted
    with pytest.raises(ProgrammingError) as caught:
        reloaded.start(ALIAS, body())
    assert caught.value.code == "programming_outcome_unknown_unresolved"


def test_unreadable_batch_journal_refuses_to_start(tmp_path):
    (tmp_path / "batches.json").write_text("{not json")
    _b, workflow, _g = rig(tmp_path / "w")
    with pytest.raises(RuntimeError, match="journal is unreadable"):
        ProgrammingBatchCoordinator(workflow, journal_path=tmp_path / "batches.json")


@pytest.mark.parametrize("run, eligible, reason", [
    ({"outcome": "PASS"}, False, "OUTCOME_PASS_IS_NOT_A_DEFINITE_FAIL"),
    ({"outcome": "OUTCOME_UNKNOWN"}, False, "OUTCOME_OUTCOME_UNKNOWN_IS_NOT_A_DEFINITE_FAIL"),
    ({"outcome": "BLOCKED"}, False, "OUTCOME_BLOCKED_IS_NOT_A_DEFINITE_FAIL"),
    ({"outcome": "FAIL", "receipt": None}, False, "NO_TRUSTED_TERMINAL_JOB_STATE"),
    ({"outcome": "FAIL", "job_submission_count": 2, "auto_retry": "DISABLED",
      "receipt": {"job_id": "j", "job_state": "failed", "safe_off": True}}, False,
     "JOB_SUBMISSION_NOT_EXACTLY_ONE"),
    ({"outcome": "FAIL", "job_submission_count": 1, "auto_retry": "DISABLED",
      "receipt": {"job_id": "j", "job_state": "running", "safe_off": True}}, False,
     "NO_TRUSTED_TERMINAL_JOB_STATE"),
    ({"outcome": "FAIL", "job_submission_count": 1, "auto_retry": "DISABLED",
      "receipt": {"job_id": "j", "job_state": "failed", "safe_off": None}}, False,
     "SAFE_OFF_NOT_VERIFIED"),
    ({"outcome": "FAIL", "job_submission_count": 1, "auto_retry": "DISABLED",
      "receipt": {"job_id": "j", "job_state": "failed", "safe_off": True,
                  "expected_job_binding_sha256": "a", "observed_job_binding_sha256": "a",
                  "expected_resource_set_sha256": "r", "observed_resource_set_sha256": "r"}},
     True, "DEFINITE_FAIL_SAFE_OFF_VERIFIED"),
])
def test_retry_eligibility_table(run, eligible, reason):
    assert retry_eligibility(run) == (eligible, reason)
