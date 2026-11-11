"""Manager-owned EMode Batch coordinator: safe Retry and Stop Policy.

One Batch = one PPU, one Site, one programming Job specification (an ordered
erase / program / verify ``operations`` list with its Programming Image or
Bundle) and a policy ``{repeat: 1, retry_limit, stop_policy}``. The
coordinator only decides WHETHER ANOTHER ATTEMPT IS SUBMITTED. Every attempt
is an ordinary ``BundleProgrammingWorkflow`` plan + run: a new plan, a new run
and a new PPU Job (new Job ID; the Job Binding is re-derived and re-verified
by the PPU for that Job) with ``auto_retry = DISABLED``. There is no second
programming engine, no Gateway batch runtime and no Repeat scheduler here.

Retry (never automatic for an unknown outcome):

* ``OUTCOME_UNKNOWN`` (lost submission, timeout, HTTP 5xx, disconnected,
  incomplete evidence, Manager restart) is never retried and stays latched in
  the workflow until an operator reconciles and acknowledges it.
* ``BLOCKED`` (nothing was submitted) ends the Batch; it is not a FAIL.
* Only a definite ``FAIL`` is eligible, and only when ALL of these hold:
  the run has a receipt of exactly one submitted Job in a terminal state with
  SAFE_OFF verified, and ``retry_block`` reads the PPU as released (Site idle,
  no Job, no held lease, no active or unknown run, no recovery required).
* The Stop Policy is evaluated before a retry is submitted.

Stop Policy (controls only attempts that are not submitted yet):

* ``{"kind": "never"}``;
* ``{"kind": "failed_sites", "threshold": N}``: once N Sites have a FAIL
  attempt, nothing further is submitted (a Batch has one Site, so N is 1).
* ``request_stop`` (the Console's stop button) is "stop queuing". It never
  cancels a submitted Job, releases a lease, resets a PPU or clears recovery
  state; a running attempt is observed to its end.

State is journalled before every submission. After a Manager restart nothing
is resubmitted: an interrupted Batch ends ``OUTCOME_UNKNOWN`` if its last
attempt may have reached the PPU, else ``BLOCKED``.
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .programming import BundleProgrammingWorkflow, JOB_TERMINAL, ProgrammingError

BATCH_SCHEMA = "plasma.manager.programming-batch.v1"
JOURNAL_SCHEMA = "plasma.manager.programming-batch-journal.v1"
MAX_RETRY_LIMIT = 5
STOP_TOKEN = "STOP_QUEUING"
MAX_BATCHES_RETAINED = 32
BATCH_TERMINAL = frozenset({"PASS", "FAIL", "OUTCOME_UNKNOWN", "BLOCKED", "STOPPED"})
PLAN_KEYS = frozenset({"icpn", "site_id", "operations", "image_base64", "image_filename",
                       "bundle_base64", "address", "length"})
POLICY_KEYS = frozenset({"retry_limit", "stop_policy", "repeat"})
START_KEYS = frozenset({"start_id"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_policy(body: Mapping[str, Any]) -> dict[str, Any]:
    """Validated ``{repeat, retry_limit, stop_policy}``; Repeat is fixed at 1."""
    if body.get("repeat", 1) != 1 or type(body.get("repeat", 1)) is not int:
        raise ProgrammingError(400, "repeat_not_supported",
                               "Repeat is not implemented; repeat must be 1")
    retry = body.get("retry_limit", 0)
    if type(retry) is not int or not 0 <= retry <= MAX_RETRY_LIMIT:
        raise ProgrammingError(400, "invalid_request",
                               f"retry_limit must be an integer from 0 to {MAX_RETRY_LIMIT}")
    stop = body.get("stop_policy", {"kind": "never"})
    if stop == {"kind": "never"}:
        pass
    elif (isinstance(stop, dict) and set(stop) == {"kind", "threshold"}
          and stop["kind"] == "failed_sites" and stop["threshold"] == 1
          and type(stop["threshold"]) is int):
        pass  # one Site per Batch: the only meaningful threshold is 1
    else:
        raise ProgrammingError(
            400, "invalid_request",
            'stop_policy must be {"kind": "never"} or {"kind": "failed_sites", "threshold": 1}')
    return {"repeat": 1, "retry_limit": retry, "stop_policy": dict(stop)}


def retry_eligibility(run: Mapping[str, Any]) -> tuple[bool, str]:
    """Is this finished run a definite FAIL that a new attempt may follow?"""
    if run.get("outcome") != "FAIL":
        return False, f"OUTCOME_{run.get('outcome')}_IS_NOT_A_DEFINITE_FAIL"
    receipt = run.get("receipt")
    if not isinstance(receipt, dict):
        return False, "NO_TRUSTED_TERMINAL_JOB_STATE"
    if run.get("job_submission_count") != 1 or run.get("auto_retry") != "DISABLED":
        return False, "JOB_SUBMISSION_NOT_EXACTLY_ONE"
    if type(receipt.get("job_id")) is not str or receipt.get("job_state") not in JOB_TERMINAL:
        return False, "NO_TRUSTED_TERMINAL_JOB_STATE"
    if receipt.get("safe_off") is not True:
        return False, "SAFE_OFF_NOT_VERIFIED"
    if (receipt.get("observed_job_binding_sha256") != receipt.get("expected_job_binding_sha256")
            or receipt.get("observed_resource_set_sha256")
            != receipt.get("expected_resource_set_sha256")):
        # The PPU did not prove it ran the Job that was planned.
        return False, "JOB_IDENTITY_NOT_CONFIRMED"
    return True, "DEFINITE_FAIL_SAFE_OFF_VERIFIED"


class ProgrammingBatchCoordinator:
    def __init__(self, workflow: BundleProgrammingWorkflow, *,
                 journal_path: Path | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 spawn: Callable[[Callable[[], None]], None] | None = None,
                 poll_interval_s: float = 0.5) -> None:
        self.workflow = workflow
        self.journal_path = journal_path
        self.sleep = sleep
        self.spawn = spawn or (lambda target: threading.Thread(
            target=target, name="plasma-programming-batch", daemon=True).start())
        self.poll_interval_s = poll_interval_s
        self._lock = threading.RLock()
        self._batches: dict[str, dict[str, Any]] = {}
        self._load_journal()

    # ------------------------------------------------------------------ journal
    def _load_journal(self) -> None:
        if self.journal_path is None or not self.journal_path.exists():
            return
        try:
            data = json.loads(self.journal_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != JOURNAL_SCHEMA:
                raise ValueError("schema")
            for batch in data["batches"]:
                if batch.get("outcome") is None:
                    self._close_interrupted(batch)
                self._batches[batch["batch_id"]] = batch
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(
                "Programming batch journal is unreadable; refusing to start") from exc
        with self._lock:
            self._persist_locked()

    def _close_interrupted(self, batch: dict[str, Any]) -> None:
        """A Batch the Manager was stopped in: decide from the run journal,
        never by submitting anything again."""
        attempts = batch.get("attempts") or []
        last = attempts[-1] if attempts else None
        run = self._run_of(batch["ppu_alias"], last) if last else None
        if last is None or (last.get("run_id") is None and run is None
                            and last.get("state") == "planned"):
            outcome, reason = "BLOCKED", "MANAGER_RESTARTED_BEFORE_SUBMISSION"
        elif run is not None and run.get("outcome") in ("PASS", "FAIL", "BLOCKED"):
            # The attempt itself finished; only the Batch bookkeeping was cut.
            self._record_attempt(last, run)
            outcome = run["outcome"] if run["outcome"] != "FAIL" else "FAIL"
            reason = ("MANAGER_RESTARTED_NO_FURTHER_ATTEMPT" if outcome == "FAIL"
                      else run.get("reason"))
        else:
            if run is not None:
                self._record_attempt(last, run)
            outcome, reason = "OUTCOME_UNKNOWN", "MANAGER_RESTARTED_DURING_ATTEMPT"
        batch.update(state="finished", outcome=outcome, reason=reason, updated_at=_now())

    def _persist_locked(self) -> None:
        if self.journal_path is None:
            return
        kept = sorted(self._batches.values(), key=lambda b: b["created_at"])[-MAX_BATCHES_RETAINED:]
        payload = {"schema": JOURNAL_SCHEMA, "batches": kept}
        parent = self.journal_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{self.journal_path.name}.", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self.journal_path)
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise

    def _update(self, batch: dict[str, Any], **changes: Any) -> None:
        with self._lock:
            batch.update(changes)
            batch["updated_at"] = _now()
            self._persist_locked()

    # ------------------------------------------------------------------ helpers
    def _run_of(self, alias: str, attempt: Mapping[str, Any] | None) -> dict[str, Any] | None:
        """The workflow run of an attempt, by run ID or by its consumed plan."""
        if attempt is None:
            return None
        with self.workflow._lock:
            runs = [run.as_dict() for run in self.workflow._runs.values() if run.alias == alias]
        for run in runs:
            if attempt.get("run_id") is not None and run["run_id"] == attempt["run_id"]:
                return run
        for run in runs:
            if (attempt.get("run_id") is None
                    and (run.get("plan") or {}).get("plan_id") == attempt.get("plan_id")):
                return run
        return None

    @staticmethod
    def _record_attempt(attempt: dict[str, Any], run: Mapping[str, Any]) -> None:
        receipt = run.get("receipt") if isinstance(run.get("receipt"), dict) else {}
        job = run.get("job") if isinstance(run.get("job"), dict) else {}
        attempt.update(
            run_id=run.get("run_id"), state="finished" if run.get("outcome") else "running",
            outcome=run.get("outcome"), reason=run.get("reason"),
            job_id=receipt.get("job_id") or job.get("job_id"),
            safe_off=receipt.get("safe_off"), finished_at=run.get("updated_at"))

    def _view(self, batch: Mapping[str, Any]) -> dict[str, Any]:
        attempts = batch["attempts"]
        current = self._run_of(batch["ppu_alias"], attempts[-1]) if attempts else None
        outcome = batch["outcome"]
        return {**batch, "attempts": [dict(a) for a in attempts], "current_run": current,
                # One Batch is one IC: counted once, by its final outcome only.
                "counts": {"pass": 1 if outcome == "PASS" else 0,
                           "fail": 1 if outcome == "FAIL" else 0,
                           "attempts": len(attempts)},
                "auto_retry": "DISABLED"}

    def _get(self, alias: str, batch_id: str) -> dict[str, Any]:
        batch = self._batches.get(batch_id)
        if batch is None or batch["ppu_alias"] != alias:
            raise ProgrammingError(404, "programming_batch_not_found",
                                   "programming batch was not found")
        return batch

    # --------------------------------------------------------------------- API
    def start(self, alias: str, body: Mapping[str, Any]) -> dict[str, Any]:
        if (not isinstance(body, Mapping) or set(body) - PLAN_KEYS - POLICY_KEYS - START_KEYS
                or "operations" not in body):
            raise ProgrammingError(
                400, "invalid_request",
                "a batch requires icpn, site_id, an operations list with its Programming "
                "Image, Bundle or erase range, and optional retry_limit / stop_policy")
        policy = parse_policy(body)
        plan_body = {key: body[key] for key in body if key in PLAN_KEYS}
        # Optional Manager-issued start ID (Start Outcome Reconciliation). A
        # start that carries one is admitted at most once and is refused when
        # the ID is unknown, used, voided or expired.
        start_id = body.get("start_id")
        with self._lock:
            if "start_id" in body:
                self.workflow.require_batch_start(alias, start_id)
            if any(b["ppu_alias"] == alias and b["outcome"] is None
                   for b in self._batches.values()):
                raise ProgrammingError(409, "programming_batch_in_progress",
                                       "another programming batch is in progress on this PPU")
            # An unresolved OUTCOME_UNKNOWN or a run in progress refuses the
            # whole Batch up front: nothing is planned, queued or journalled.
            with self.workflow._lock:
                latched = self.workflow._unknown_latched(alias)
                busy = self.workflow._active_run(alias)
            if latched is not None:
                raise ProgrammingError(
                    409, "programming_outcome_unknown_unresolved",
                    f"run {latched.run_id} ended OUTCOME_UNKNOWN; reconcile and acknowledge first")
            if busy is not None:
                raise ProgrammingError(409, "programming_run_in_progress",
                                       "another programming run is in progress on this PPU")
            # The first plan is made synchronously: a refused request creates
            # no Batch, and its identities are fixed before anything is queued.
            planned = self.workflow.plan(alias, plan_body)["plan"]
            batch = {
                "schema": BATCH_SCHEMA, "batch_id": secrets.token_hex(16), "ppu_alias": alias,
                "start_id": start_id,
                "site_id": planned["site_id"], "operations": planned["operations"],
                "source": planned["source"], "icpn": planned["route"]["icpn"],
                "policy": policy, "state": "running", "outcome": None, "reason": None,
                "stop_requested": False, "attempts": [],
                "created_at": _now(), "updated_at": _now(),
            }
            if start_id is not None:
                # Admission is journalled first: from here on the start can
                # never reconcile as "not accepted".
                self.workflow.consume_batch_start(
                    alias, start_id, batch["batch_id"], planned["site_id"])
            self._batches[batch["batch_id"]] = batch
            try:
                self._persist_locked()
            except BaseException:
                del self._batches[batch["batch_id"]]
                raise
        self.spawn(lambda: self._execute(batch, plan_body, planned))
        return {"ok": True, "batch": self._view(batch)}

    def reconcile_start(self, alias: str, start_id: str) -> dict[str, Any]:
        """Read-only: what became of the Start that carried ``start_id``."""
        def find_batch(wanted: str) -> dict[str, Any] | None:
            with self._lock:
                for batch in self._batches.values():
                    if batch.get("start_id") == wanted:
                        return self._view(batch)
            return None
        return self.workflow.reconcile_start(alias, start_id, find_batch)

    def status(self, alias: str, batch_id: str) -> dict[str, Any]:
        with self._lock:
            return {"ok": True, "batch": self._view(self._get(alias, batch_id))}

    def request_stop(self, alias: str, batch_id: str,
                     body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Stop queuing. Never cancels, resets or releases anything on the PPU."""
        if body is not None and dict(body) != {"stop": STOP_TOKEN}:
            raise ProgrammingError(400, "invalid_request",
                                   f"stop requires stop={STOP_TOKEN}")
        with self._lock:
            batch = self._get(alias, batch_id)
            if batch["outcome"] is None and not batch["stop_requested"]:
                batch["stop_requested"] = True
                batch["updated_at"] = _now()
                self._persist_locked()
            return {"ok": True, "batch": self._view(batch)}

    # ---------------------------------------------------------------- execution
    def _execute(self, batch: dict[str, Any], plan_body: Mapping[str, Any],
                 first_plan: Mapping[str, Any]) -> None:
        try:
            self._run_attempts(batch, plan_body, first_plan)
        except Exception as exc:  # noqa: BLE001 - never retried, never a guessed result
            self._update(batch, state="finished", outcome="OUTCOME_UNKNOWN",
                         reason=f"BATCH_UNEXPECTED_{type(exc).__name__}")

    def _finish(self, batch: dict[str, Any], outcome: str, reason: str | None) -> None:
        self._update(batch, state="finished", outcome=outcome, reason=reason)

    def _run_attempts(self, batch: dict[str, Any], plan_body: Mapping[str, Any],
                      first_plan: Mapping[str, Any]) -> None:
        alias, policy = batch["ppu_alias"], batch["policy"]
        plan: Mapping[str, Any] | None = first_plan
        for number in range(1, policy["retry_limit"] + 2):
            if batch["stop_requested"]:
                self._finish(batch, "STOPPED" if number == 1 else "FAIL",
                             "STOP_REQUESTED_NOTHING_SUBMITTED" if number == 1
                             else "STOP_REQUESTED_NO_FURTHER_ATTEMPT")
                return
            if plan is None:
                try:
                    plan = self.workflow.plan(alias, plan_body)["plan"]
                except ProgrammingError as exc:
                    # The earlier FAIL stands; the retry could not even be planned.
                    self._finish(batch, "FAIL", f"RETRY_PLAN_REFUSED_{exc.code}")
                    return
            attempt = {"attempt": number, "plan_id": plan["plan_id"], "run_id": None,
                       "job_binding_sha256": plan["job_binding_sha256"], "job_id": None,
                       "state": "planned", "outcome": None, "reason": None,
                       "safe_off": None, "retry": None,
                       "started_at": _now(), "finished_at": None}
            with self._lock:
                batch["attempts"].append(attempt)
                batch["updated_at"] = _now()
                # Journalled BEFORE the single start of this attempt.
                self._persist_locked()
            try:
                started = self.workflow.start(
                    alias, {"plan_id": plan["plan_id"], "confirm": "PROGRAM"})["run"]
            except ProgrammingError as exc:
                with self._lock:
                    attempt.update(state="finished", outcome="BLOCKED", reason=exc.code,
                                   finished_at=_now())
                self._finish(batch, "BLOCKED" if number == 1 else "FAIL",
                             exc.code if number == 1 else f"RETRY_START_REFUSED_{exc.code}")
                return
            with self._lock:
                attempt.update(run_id=started["run_id"], state="running")
                batch["updated_at"] = _now()
                self._persist_locked()
            run = started
            while run.get("outcome") is None:
                self.sleep(self.poll_interval_s)
                run = self.workflow.run_status(alias, started["run_id"])["run"]
            with self._lock:
                self._record_attempt(attempt, run)
                self._persist_locked()
            outcome = run["outcome"]
            if outcome != "FAIL":
                # PASS ends the Batch; OUTCOME_UNKNOWN and BLOCKED are never retried.
                self._finish(batch, outcome, run.get("reason"))
                return
            eligible, why = retry_eligibility(run)
            decision = {"eligible": eligible, "reason": why, "decision": "NO_RETRY"}
            final_reason = run.get("reason")
            if number > policy["retry_limit"]:
                # No attempt is left: the FAIL stands with its own reason.
                final = "RETRY_LIMIT_EXHAUSTED" if policy["retry_limit"] else None
            elif not eligible:
                final = f"RETRY_NOT_ELIGIBLE_{why}"
            elif policy["stop_policy"]["kind"] == "failed_sites":
                final = "STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED"
            elif batch["stop_requested"]:
                final = "STOP_REQUESTED_NO_FURTHER_ATTEMPT"
            else:
                blocked = self.workflow.retry_block(alias, batch["site_id"])
                if blocked is not None:
                    decision.update(eligible=False, reason=f"PPU_NOT_RELEASED_{blocked}")
                    final = f"RETRY_NOT_ELIGIBLE_PPU_NOT_RELEASED_{blocked}"
                else:
                    decision["decision"] = "RETRY"
                    final = None
            with self._lock:
                attempt["retry"] = decision
                self._persist_locked()
            if decision["decision"] != "RETRY":
                self._finish(batch, "FAIL", final or final_reason)
                return
            plan = None  # a retry always gets a new plan, run and Job
