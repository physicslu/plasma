"""Host-only: Site safety evidence v1 (SAFE_OFF_NOT_VERIFIED root cause, 2026-11-23).

A C-3 ``run`` refusal carries the Site Worker's structured safety statement
(``plasma.ppu.site-safety.v1``). The PPU Runtime (Reservation release) and the
Manager (Run / Cycle classification) judge it with the SAME rules:

* PRE_HARDWARE_DENIED (trusted)       -> Run BLOCKED, SAFE_OFF NOT_TOUCHED,
  no Cycle result; the Batch pauses the Site for the operator's Continue.
* FAILED_SAFE_OFF_VERIFIED (trusted)  -> Run FAIL, SAFE_OFF VERIFIED.
* anything else (code text only, any identity / stage / Binding mismatch,
  outcome unknown)                    -> unchanged conservative handling.

Fake PPU only; never touches Z2, FPGA or a DUT.
"""
from __future__ import annotations

import copy
import time

import pytest

from plasma_manager import programming as manager_side
from plasma_manager.programming_batch import AWAITING_CONTINUE
from plasma_server import site_manager as ppu_side

from .test_bundle_programming_workflow import (
    ALIAS, CONFIRM_TOKEN, ops_body, ops_workflow,
)
from .test_programming_batch_repeat import Session, job_ids

DENIED = "SITE_DENIED_BEFORE_HARDWARE"
JOB = "job-20261123-004025-5406d009"


# ------------------------------------------------- shared contract table

def _context(kind="PRE_HARDWARE_DENIED"):
    denied = kind == "PRE_HARDWARE_DENIED"
    code = "ADMISSION_DENIED:PROC_SCAN_INCOMPLETE" if denied else "OPERATION_TIMEOUT"
    return {
        "site_worker_stage": "run",
        "site_worker_code": ("TRANSPORT_DENIED:" if denied else "OPERATION_FAILED_SAFE:") + code,
        "outcome_unknown": False, "job_id": JOB, "site_id": 2, "operation": "programming",
        "site_worker_safety": {
            "schema": "plasma.ppu.site-safety.v1", "class": kind, "job_id": JOB,
            "session_id": "5" * 32, "site": 2, "operation": "programming", "stage": "run",
            "code": code, "hardware_touched": not denied, "safe_off": None if denied else True},
    }


def _mutated(kind, path, value):
    context = _context(kind)
    target = context["site_worker_safety"] if path.startswith("safety.") else context
    key = path.split(".", 1)[1] if "." in path else path
    if value is _DROP:
        target.pop(key)
    else:
        target[key] = value
    return context


_DROP = object()

CONTRACT = [
    # (case, context, expected class)
    ("pre-hardware denied", _context(), "PRE_HARDWARE_DENIED"),
    ("failed, SAFE_OFF verified", _context("FAILED_SAFE_OFF_VERIFIED"), "FAILED_SAFE_OFF_VERIFIED"),
    ("code text only", _mutated("PRE_HARDWARE_DENIED", "site_worker_safety", _DROP), None),
    ("outcome unknown", _mutated("PRE_HARDWARE_DENIED", "outcome_unknown", True), None),
    ("outcome_unknown missing", _mutated("PRE_HARDWARE_DENIED", "outcome_unknown", _DROP), None),
    ("open stage", _mutated("PRE_HARDWARE_DENIED", "site_worker_stage", "open"), None),
    ("statement stage", _mutated("PRE_HARDWARE_DENIED", "safety.stage", "open"), None),
    ("other Job (statement)", _mutated("PRE_HARDWARE_DENIED", "safety.job_id", "job-other"), None),
    ("other Job (context)", _mutated("PRE_HARDWARE_DENIED", "job_id", "job-other"), None),
    ("other Site (statement)", _mutated("PRE_HARDWARE_DENIED", "safety.site", 1), None),
    ("other Site (context)", _mutated("PRE_HARDWARE_DENIED", "site_id", 1), None),
    ("bool Site", _mutated("PRE_HARDWARE_DENIED", "safety.site", True), None),
    ("other operation", _mutated("PRE_HARDWARE_DENIED", "safety.operation", "read"), None),
    ("context operation missing", _mutated("PRE_HARDWARE_DENIED", "operation", _DROP), None),
    ("wrong schema", _mutated("PRE_HARDWARE_DENIED", "safety.schema", "plasma.ppu.site-safety.v0"), None),
    ("unknown class", _mutated("PRE_HARDWARE_DENIED", "safety.class", "SAFE"), None),
    ("class vs code prefix", _mutated("PRE_HARDWARE_DENIED", "safety.class",
                                      "FAILED_SAFE_OFF_VERIFIED"), None),
    ("code differs", _mutated("PRE_HARDWARE_DENIED", "safety.code", "OTHER"), None),
    ("empty code", _mutated("PRE_HARDWARE_DENIED", "safety.code", ""), None),
    ("sealed code", _mutated("PRE_HARDWARE_DENIED", "site_worker_code",
                             "OUTCOME_UNKNOWN_SITE_SEALED:ADMISSION_DENIED:PROC_SCAN_INCOMPLETE"), None),
    ("denied but touched", _mutated("PRE_HARDWARE_DENIED", "safety.hardware_touched", True), None),
    ("denied with safe_off claim", _mutated("PRE_HARDWARE_DENIED", "safety.safe_off", True), None),
    ("failed, not touched", _mutated("FAILED_SAFE_OFF_VERIFIED", "safety.hardware_touched", False), None),
    ("failed, SAFE_OFF unproven", _mutated("FAILED_SAFE_OFF_VERIFIED", "safety.safe_off", None), None),
    ("failed, SAFE_OFF truthy", _mutated("FAILED_SAFE_OFF_VERIFIED", "safety.safe_off", 1), None),
    ("statement not an object", _mutated("PRE_HARDWARE_DENIED", "site_worker_safety", "safe"), None),
]


@pytest.mark.parametrize("case,context,expected", CONTRACT, ids=[c[0] for c in CONTRACT])
def test_manager_and_ppu_judge_every_statement_identically(case, context, expected):
    kwargs = dict(job_id=JOB, site_id=2, operation="programming")
    assert manager_side.site_safety_class(copy.deepcopy(context), **kwargs) == expected
    assert ppu_side.site_safety_class(copy.deepcopy(context), **kwargs) == expected


def test_both_sides_share_the_schema_and_class_names():
    for name in ("SITE_SAFETY_SCHEMA", "PRE_HARDWARE_DENIED", "FAILED_SAFE_OFF_VERIFIED",
                 "_SITE_SAFETY_PREFIX"):
        assert getattr(manager_side, name) == getattr(ppu_side, name), name


# ------------------------------------------------- Manager Run classification

def _run(tmp_path, refusal, **gateway_kw):
    workflow, _c, gateway = ops_workflow(tmp_path, job_final="error",
                                         worker_refusal=refusal, **gateway_kw)
    planned = workflow.plan(ALIAS, ops_body(["erase", "program", "verify"]))["plan"]
    started = workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    return workflow.run_status(ALIAS, started["run"]["run_id"])["run"], gateway


def test_trusted_pre_hardware_denial_is_blocked_not_fail(tmp_path):
    run, gateway = _run(tmp_path, "denied")
    receipt = run["receipt"]
    assert (run["outcome"], run["reason"]) == ("BLOCKED", DENIED), run
    assert receipt["safe_off"] is None and receipt["safe_off_state"] == "NOT_TOUCHED"
    assert receipt["safe_off_source"] == "site_worker_safety"
    assert receipt["site_safety"] == {
        "class": "PRE_HARDWARE_DENIED",
        "code": "ADMISSION_DENIED:PROC_SCAN_INCOMPLETE:PROC_VISIBILITY_DENIED:5704:MAPS:"
                "ProcessLookupError"}
    assert len(gateway.posts) == 1  # never resubmitted


def test_trusted_failed_safe_is_fail_with_safe_off_verified(tmp_path):
    run, _ = _run(tmp_path, "failed_safe")
    receipt = run["receipt"]
    assert (run["outcome"], run["reason"]) == ("FAIL", "JOB_NOT_SUCCESS"), run
    assert receipt["safe_off"] is True and receipt["safe_off_state"] == "VERIFIED"
    assert receipt["safe_off_source"] == "site_worker_safety"
    from plasma_manager.programming_batch import retry_eligibility, terminal_evidence
    assert terminal_evidence(run) == (True, "TERMINAL_SAFE_OFF_VERIFIED")
    assert retry_eligibility(run) == (True, "DEFINITE_FAIL_SAFE_OFF_VERIFIED")


@pytest.mark.parametrize("refusal", [
    {"mode": "denied", "safety": None},                         # the code text only
    {"mode": "denied", "context": {"outcome_unknown": True}},
    {"mode": "denied", "safety": {"job_id": "job-other"}},
    {"mode": "denied", "safety": {"site": 3}},
    {"mode": "denied", "context": {"site_worker_stage": "open"}},
    {"mode": "denied", "safety": {"hardware_touched": True}},
    {"mode": "failed_safe", "safety": {"safe_off": None}},
])
def test_untrusted_refusals_keep_the_conservative_fail(tmp_path, refusal):
    run, _ = _run(tmp_path, refusal)
    assert (run["outcome"], run["reason"]) == ("FAIL", "SAFE_OFF_NOT_VERIFIED"), run
    assert run["receipt"]["safe_off_state"] == "NOT_VERIFIED"
    assert run["receipt"]["site_safety"] is None


@pytest.mark.parametrize("echo", [
    {"job_binding_sha256": "0" * 64}, {"resource_set_sha256": "0" * 64}, {"site_id": 3},
])
def test_binding_mismatch_never_trusts_a_denial(tmp_path, echo):
    run, _ = _run(tmp_path, "denied", echo=echo)
    assert run["outcome"] == "FAIL" and run["reason"] == "SAFE_OFF_NOT_VERIFIED", run
    assert run["receipt"]["safe_off_state"] == "NOT_VERIFIED"


def test_job_identity_and_attempts_are_checked_beyond_the_statement(tmp_path):
    from types import SimpleNamespace
    context = _context()
    error = {"job_id": JOB, "site_id": 2, "context": context}
    result = {"state": "error", "attempts": 1, "error": error, "details": {}}
    job = {"job_id": JOB, "state": "error", "site_id": 2, "operation": "programming"}
    run, plan = SimpleNamespace(site=2), SimpleNamespace(operation="programming")
    judge = manager_side._job_site_safety
    assert judge(run, plan, job, result, True) == "PRE_HARDWARE_DENIED"
    assert judge(run, plan, job, result, False) is None            # Binding not echoed
    for change in ({"attempts": 2}, {"attempts": True}, {"state": "failed"}):
        assert judge(run, plan, job, {**result, **change}, True) is None, change
    for change in ({"state": "success"}, {"site_id": 1}, {"operation": "read"},
                   {"job_id": "job-other"}):
        assert judge(run, plan, {**job, **change}, result, True) is None, change
    assert judge(run, plan, job, {**result, "error": {**error, "job_id": "x"}}, True) is None
    assert judge(run, plan, job, {**result, "error": {**error, "site_id": 1}}, True) is None


# ------------------------------------------------- Batch / Cycle semantics

def _blocked(session, site=1):
    unit = session.awaiting(site)
    assert unit["cycle"]["wait_reason"] == DENIED
    return unit


def test_same_ic_denial_pauses_for_continue_and_is_never_counted(tmp_path):
    session = Session(tmp_path, {1: ["success", "denied", "success"]},
                      repeat=3, replace_ic_before_next_cycle=False)
    unit = _blocked(session)
    cycle = unit["cycle"]
    # Not a FAIL, not settled: Cycle 2 is still the current Cycle.
    assert (cycle["index"], cycle["settled"], cycle["pass"], cycle["fail"]) == (2, 1, 1, 0)
    assert cycle["attempts"] == 2 and unit["outcome"] is None
    view = session.view()
    assert view["cycles"]["settled"] == 1 and view["cycles"]["fail"] == 0
    # No automatic resend while paused.
    posts = len(session.gateway.posts)
    time.sleep(0.05)
    assert len(session.gateway.posts) == posts == 2
    [blocked] = session.ledger("blocked_dispatch")
    assert (blocked["cycle_index"], blocked["reason"]) == (2, DENIED)
    assert blocked["receipt"]["safe_off_state"] == "NOT_TOUCHED"
    assert blocked["receipt"]["site_safety"]["class"] == "PRE_HARDWARE_DENIED"
    assert blocked["attempts"][0]["safe_off_state"] == "NOT_TOUCHED"
    session.cont()
    batch = session.done()
    assert batch["outcome"] == "PASS"
    cycles = batch["units"][0]["cycle"]
    assert (cycles["settled"], cycles["pass"], cycles["fail"], cycles["attempts"]) == (3, 3, 0, 4)
    assert batch["counts"]["attempts"] == 4 and batch["cycles"]["fail"] == 0
    history = session.ledger("cycle")
    assert [r["cycle_index"] for r in history] == [1, 2, 3]
    assert all(r["outcome"] == "PASS" for r in history)
    # Every Job is distinct: the re-run of Cycle 2 is a new plan, Run and Job.
    jobs = job_ids(history) + [a["job_id"] for a in blocked["attempts"]]
    assert len(jobs) == len(set(jobs)) == len(session.gateway.posts) == 4


def test_a_denial_in_the_first_cycle_also_waits(tmp_path):
    session = Session(tmp_path, {1: ["denied", "success"]},
                      repeat=2, replace_ic_before_next_cycle=False)
    unit = _blocked(session)
    assert (unit["cycle"]["index"], unit["cycle"]["settled"]) == (1, 0)
    session.cont()
    batch = session.done()
    assert batch["outcome"] == "PASS" and batch["units"][0]["cycle"]["settled"] == 2


def test_continue_runs_admission_again_before_any_submission(tmp_path):
    session = Session(tmp_path, {1: ["denied", "success"]},
                      repeat=1, replace_ic_before_next_cycle=False)
    _blocked(session)
    calls = []
    original = session.batches._admission_block

    def counted(*args, **kwargs):
        calls.append(len(session.gateway.posts))
        return original(*args, **kwargs)
    session.batches._admission_block = counted
    session.cont()
    batch = session.done()
    assert batch["outcome"] == "PASS"
    assert calls and calls[0] == 1  # judged before the re-run Job was posted


def test_stop_while_paused_submits_nothing_further(tmp_path):
    session = Session(tmp_path, {1: ["denied"]}, repeat=2, replace_ic_before_next_cycle=False)
    _blocked(session)
    session.batches.request_stop_batch(session.batch_id, {"stop": "STOP_QUEUING"})
    batch = session.done()
    assert len(session.gateway.posts) == 1
    assert batch["units"][0]["cycle"]["fail"] == 0
    assert batch["outcome"] != "PASS"


def test_two_sites_denial_isolated_to_its_site(tmp_path):
    session = Session(tmp_path, {1: ["success"], 2: ["success", "denied", "success"]},
                      sites=(1, 2), repeat=3, replace_ic_before_next_cycle=False)
    _blocked(session, site=2)
    # Site 1 finishes all its Cycles while Site 2 waits: no cross-Site barrier.
    session.until(lambda b: next(u for u in b["units"] if u["site_id"] == 1)["outcome"] == "PASS",
                  "Site 1 completes")
    assert session.unit(2)["cycle"]["state"] == AWAITING_CONTINUE
    session.cont(site=2)
    batch = session.done()
    assert batch["outcome"] == "PASS"
    by_site = {u["site_id"]: u["cycle"] for u in batch["units"]}
    assert (by_site[1]["settled"], by_site[1]["attempts"]) == (3, 3)
    assert (by_site[2]["settled"], by_site[2]["fail"], by_site[2]["attempts"]) == (3, 0, 4)
    assert batch["cycles"]["settled"] == 6 and batch["cycles"]["fail"] == 0
    assert batch["counts"]["attempts"] == 7


def test_failed_safe_settles_a_fail_cycle_with_safe_off_verified(tmp_path):
    session = Session(tmp_path, {1: ["failed_safe", "success"]},
                      repeat=2, replace_ic_before_next_cycle=False)
    unit = session.awaiting(1)
    assert unit["cycle"]["wait_reason"] == "FAIL_REVIEW"
    assert (unit["cycle"]["settled"], unit["cycle"]["fail"]) == (1, 1)
    [record] = session.ledger("cycle")
    assert record["outcome"] == "FAIL"
    assert record["receipt"]["safe_off_state"] == "VERIFIED"
    session.cont()
    assert session.done()["units"][0]["cycle"]["settled"] == 2


def test_a_denied_retry_keeps_the_cycle_fail_and_releases_the_site(tmp_path):
    """Attempt 1 is a definite FAIL (SAFE_OFF verified); its Retry is refused
    before hardware. The FAIL stands - never erased by a pause - and the Site
    is released (the refused Retry touched nothing)."""
    session = Session(tmp_path, {1: ["failed_safe", "denied", "success"]},
                      repeat=2, retry_limit=1, replace_ic_before_next_cycle=False)
    unit = session.awaiting(1)
    cycle = unit["cycle"]
    assert cycle["wait_reason"] == "FAIL_REVIEW"
    assert (cycle["settled"], cycle["fail"], cycle["attempts"]) == (1, 1, 2)
    assert session.ledger("blocked_dispatch") == []
    [record] = session.ledger("cycle")
    assert (record["outcome"], record["reason"]) == ("FAIL", "RETRY_" + DENIED)
    assert [a["outcome"] for a in record["attempts"]] == ["FAIL", "BLOCKED"]
    assert record["attempts"][0]["retry"]["decision"] == "RETRY"
    assert record["receipt"]["safe_off_state"] == "NOT_TOUCHED"
    assert len(session.gateway.posts) == 2
    session.cont()
    batch = session.done()
    assert (batch["units"][0]["cycle"]["fail"], batch["units"][0]["cycle"]["settled"]) == (1, 2)


def test_terminal_evidence_trusts_only_the_managers_own_denial_verdict():
    from plasma_manager.programming_batch import terminal_evidence
    receipt = {"job_id": JOB, "job_state": "error", "safe_off": None,
               "safe_off_state": "NOT_TOUCHED",
               "site_safety": {"class": "PRE_HARDWARE_DENIED", "code": "ADMISSION_DENIED"},
               "observed_job_binding_sha256": "a" * 64, "expected_job_binding_sha256": "a" * 64,
               "observed_resource_set_sha256": "b" * 64, "expected_resource_set_sha256": "b" * 64}
    run = {"outcome": "BLOCKED", "reason": DENIED, "job_submission_count": 1,
           "auto_retry": "DISABLED", "receipt": receipt}
    assert terminal_evidence(run) == (True, "TERMINAL_HARDWARE_NOT_TOUCHED")
    for change in ({"outcome": "FAIL"}, {"reason": "SAFE_OFF_NOT_VERIFIED"}):
        assert terminal_evidence({**run, **change}) == (False, "SAFE_OFF_NOT_VERIFIED"), change
    for change in ({"safe_off_state": "NOT_VERIFIED"}, {"site_safety": None},
                   {"site_safety": {"class": "FAILED_SAFE_OFF_VERIFIED", "code": "X"}}):
        assert terminal_evidence({**run, "receipt": {**receipt, **change}})[0] is False, change
    assert terminal_evidence({**run, "receipt": {**receipt, "observed_job_binding_sha256": "c" * 64}}) \
        == (False, "JOB_IDENTITY_NOT_CONFIRMED")


def test_a_code_only_denial_still_ends_the_site_unreleased(tmp_path):
    session = Session(tmp_path, {1: ["success", "code_only"]},
                      repeat=3, replace_ic_before_next_cycle=False)
    batch = session.done()
    unit = batch["units"][0]
    assert unit["reason"] == "CYCLE_NOT_RELEASED_SAFE_OFF_NOT_VERIFIED"
    assert len(session.gateway.posts) == 2
    assert session.ledger("cycle")[-1]["receipt"]["safe_off_state"] == "NOT_VERIFIED"


# ------------------------------------------------- C-3 client forwarding

def test_c3_refusal_forwards_the_statement_only_when_the_outcome_is_known():
    from plasma_interfaces.site_worker_c3 import SiteWorkerRefused, _refusal
    statement = _context()["site_worker_safety"]
    known = _refusal("run", SiteWorkerRefused("TRANSPORT_DENIED:ADMISSION_DENIED", statement),
                     job_id=JOB, site_id=2, operation="programming")
    assert known.context["site_worker_safety"] == statement
    assert known.context["outcome_unknown"] is False
    sealed = _refusal("run", SiteWorkerRefused("OUTCOME_UNKNOWN_SITE_SEALED:X", statement),
                      job_id=JOB, site_id=2, operation="programming")
    assert "site_worker_safety" not in sealed.context and sealed.context["outcome_unknown"]
    bare = _refusal("run", SiteWorkerRefused("TRANSPORT_DENIED:ADMISSION_DENIED"),
                    job_id=JOB, site_id=2, operation="programming")
    assert "site_worker_safety" not in bare.context
    # A non-object statement is dropped, never forwarded as evidence.
    assert SiteWorkerRefused("X", "safe").safety is None


def test_c3_client_reads_the_statement_from_the_worker_reply(tmp_path):
    import json
    import socket
    import threading
    from plasma_interfaces.site_worker_c3 import SiteWorkerControlClient, SiteWorkerRefused
    path = tmp_path / "w.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    statement = _context()["site_worker_safety"]

    def answer():
        conn, _ = server.accept()
        with conn:
            conn.recv(65536)
            conn.sendall((json.dumps({"ok": False, "error": "TRANSPORT_DENIED:ADMISSION_DENIED",
                                      "safety": statement}) + "\n").encode())
    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    with pytest.raises(SiteWorkerRefused) as refused:
        SiteWorkerControlClient(path, timeout_s=5).call("run", session_id="s", site=2,
                                                        operation="programming")
    thread.join(5)
    server.close()
    assert refused.value.code == "TRANSPORT_DENIED:ADMISSION_DENIED"
    assert refused.value.safety == statement
