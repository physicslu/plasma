"""Manager-owned Batch coordinator over a Target Set: safe Retry and Stop.

One Batch = an ordered Target Set (``[{ppu_alias, site_ids}]``) spanning one
or more PPUs, one programming Job specification (an ordered erase / program /
verify ``operations`` list with its Programming Image or Bundle) and a policy
``{repeat: 1, retry_limit, stop_policy}``. ICPN and Image are Batch-level and
never vary per Site.

The coordinator only decides WHETHER ANOTHER ATTEMPT IS SUBMITTED. Every
attempt is an ordinary ``BundleProgrammingWorkflow`` plan + run: a new plan, a
new run and a new PPU Job (new Job ID; the Job Binding is re-derived and
re-verified by the PPU for that Job) with ``auto_retry = DISABLED``. There is
no second programming engine, no Gateway batch runtime and no Repeat
scheduler here. Execution is sequential across the whole Batch: one in-flight
run at a time.

Admission separates validity from readiness. A malformed request, or an
unknown or unauthorised Target, refuses the whole Batch and does not consume
the ``start_id``. A Target that is valid but not ready is admitted
``BLOCKED`` with its reason; the other Targets still run.

Per-Target isolation:

* One unready PPU never blocks another. ``OUTCOME_UNKNOWN`` latches its own
  PPU and skips that PPU's remaining Sites; other PPUs continue.
* Readiness read at admission does not authorise a mutation that happens
  later, so every PPU is re-checked immediately before it is operated.
* A ``BLOCKED`` Target spends no retry budget and, by default, does not count
  toward a ``failed_sites`` threshold.
* If the shared safety infrastructure fails - the journal cannot be
  committed, PPU state cannot be judged - the whole Batch fails closed.

Retry (never automatic for an unknown outcome):

* ``OUTCOME_UNKNOWN`` (lost submission, timeout, HTTP 5xx, disconnected,
  incomplete evidence, Manager restart) is never retried and stays latched in
  the workflow until an operator reconciles and acknowledges it.
* ``BLOCKED`` (nothing was submitted) ends the Batch for that Target; it is
  not a FAIL.
* Only a definite ``FAIL`` is eligible, and only when ALL of these hold:
  the run has a receipt of exactly one submitted Job in a terminal state with
  SAFE_OFF verified, and ``retry_block`` reads the PPU as released (Site idle,
  no Job, no held lease, no active or unknown run, no recovery required).
* The Stop Policy is evaluated before a retry is submitted.

Stop Policy (controls only attempts that are not submitted yet):

* ``{"kind": "never"}``;
* ``{"kind": "failed_sites", "threshold": N}``: once N Sites have a FAIL
  outcome, nothing further is submitted. ``N`` is 1 to the Batch's Site count.
* ``request_stop`` (the Console's stop button) is "stop queuing". It never
  cancels a submitted Job, releases a lease, resets a PPU or clears recovery
  state; a running attempt is observed to its end.

Execution status and outcome are separate fields. ``STOPPED`` is a status and
is never reported as an outcome; the outcome is derived from the Targets by
``OUTCOME_UNKNOWN > FAIL > PARTIAL > PASS``, and reads ``BLOCKED`` when no
Target executed at all.

State is journalled before every submission. After a Manager restart nothing
is resubmitted: an interrupted attempt that may have reached a PPU ends
``OUTCOME_UNKNOWN``; only an attempt provably never submitted ends
``BLOCKED``. A journal written by the previous schema is migrated on read,
never refused, and never rewritten in place.
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

BATCH_SCHEMA = "plasma.manager.programming-batch.v2"
JOURNAL_SCHEMA = "plasma.manager.programming-batch-journal.v2"
LEGACY_BATCH_SCHEMA = "plasma.manager.programming-batch.v1"
LEGACY_JOURNAL_SCHEMA = "plasma.manager.programming-batch-journal.v1"
MAX_RETRY_LIMIT = 5
MAX_TARGETS = 32
MAX_SITES_PER_BATCH = 64
STOP_TOKEN = "STOP_QUEUING"
MAX_BATCHES_RETAINED = 32
BATCH_TERMINAL = frozenset({"PASS", "FAIL", "PARTIAL", "OUTCOME_UNKNOWN", "BLOCKED"})
# A Target counts as executed only when a Job was submitted for it.
EXECUTED_OUTCOMES = frozenset({"PASS", "FAIL", "OUTCOME_UNKNOWN"})
PLAN_KEYS = frozenset({"icpn", "operations", "image_base64", "image_filename",
                       "bundle_base64", "address", "length"})
TARGET_KEY = "targets"
LEGACY_SITE_KEY = "site_id"
POLICY_KEYS = frozenset({"retry_limit", "stop_policy", "repeat"})
START_KEYS = frozenset({"start_id"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_targets(body: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Validated Target Set: ordered, one entry per PPU, no repeated Site.

    Validity is decided before any readiness is read, because an invalid
    Target Set refuses the whole Batch while an unready PPU does not.
    """
    targets = body.get(TARGET_KEY)
    if not isinstance(targets, list) or not 0 < len(targets) <= MAX_TARGETS:
        raise ProgrammingError(
            400, "invalid_request",
            f"targets must be a list of 1 to {MAX_TARGETS} {{ppu_alias, site_ids}} entries")
    seen: set[str] = set()
    parsed: list[dict[str, Any]] = []
    total = 0
    for entry in targets:
        if not isinstance(entry, Mapping) or set(entry) != {"ppu_alias", "site_ids"}:
            raise ProgrammingError(400, "invalid_request",
                                   "each target requires exactly ppu_alias and site_ids")
        alias = entry["ppu_alias"]
        if type(alias) is not str or not alias.strip() or len(alias) > 96:
            raise ProgrammingError(400, "invalid_request", "target ppu_alias is invalid")
        if alias in seen:
            # One entry per PPU keeps the latch, the lease and the once-per-PPU
            # Bundle reuse unambiguous.
            raise ProgrammingError(400, "invalid_request",
                                   f"ppu_alias {alias} appears in more than one target")
        seen.add(alias)
        sites = entry["site_ids"]
        if not isinstance(sites, list) or not sites:
            raise ProgrammingError(400, "invalid_request",
                                   "site_ids must be a non-empty list of Site numbers")
        for site in sites:
            if type(site) is not int or isinstance(site, bool) or not 1 <= site <= 64:
                raise ProgrammingError(400, "invalid_request", "site_id is invalid")
        if len(set(sites)) != len(sites):
            raise ProgrammingError(400, "invalid_request",
                                   f"ppu_alias {alias} repeats a Site")
        total += len(sites)
        parsed.append({"ppu_alias": alias, "site_ids": list(sites)})
    if total > MAX_SITES_PER_BATCH:
        raise ProgrammingError(400, "invalid_request",
                               f"a Batch covers at most {MAX_SITES_PER_BATCH} Sites")
    return tuple(parsed)


def site_count(targets) -> int:
    return sum(len(target["site_ids"]) for target in targets)


def parse_policy(body: Mapping[str, Any], sites: int = 1) -> dict[str, Any]:
    """Validated ``{repeat, retry_limit, stop_policy}``; Repeat is fixed at 1.

    ``sites`` is the Batch's Site count, which bounds a ``failed_sites``
    threshold at 1..N: a threshold no Batch could ever reach would be a policy
    that silently means "never".
    """
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
          and stop["kind"] == "failed_sites"
          and type(stop["threshold"]) is int
          and 1 <= stop["threshold"] <= sites):
        pass
    else:
        raise ProgrammingError(
            400, "invalid_request",
            'stop_policy must be {"kind": "never"} or {"kind": "failed_sites", '
            f'"threshold": 1..{sites}}}')
    return {"repeat": 1, "retry_limit": retry, "stop_policy": dict(stop)}


def aggregate_outcome(units) -> str:
    """The Batch outcome derived from its Targets.

    ``OUTCOME_UNKNOWN > FAIL > PARTIAL > PASS``. Safety outranks everything
    below it, so no number of passing Targets dilutes one unknown. ``PASS``
    requires every scheduled unit to have executed and passed; a Batch that
    did not finish its Target Set reads ``PARTIAL``, and one where nothing
    executed at all reads ``BLOCKED``.
    """
    outcomes = [unit.get("outcome") for unit in units]
    if "OUTCOME_UNKNOWN" in outcomes:
        return "OUTCOME_UNKNOWN"
    if "FAIL" in outcomes:
        return "FAIL"
    executed = [outcome for outcome in outcomes if outcome in EXECUTED_OUTCOMES]
    if not executed:
        return "BLOCKED"
    if len(executed) != len(outcomes):
        return "PARTIAL"
    return "PASS"


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


def batch_reason(units, outcome: str, fallback: str | None = None) -> str | None:
    """The reason of the Target that decided the Batch outcome.

    A single-Target Batch therefore reports that Target's reason unchanged,
    and a mixed Batch reports the reason of the Target whose outcome won the
    priority rather than inventing a summary of its own.
    """
    for unit in units:
        if unit.get("outcome") == outcome and unit.get("reason"):
            return unit["reason"]
    for unit in units:
        if unit.get("reason"):
            return unit["reason"]
    return fallback


#: Refusals that describe the REQUEST, not a Target. No other PPU could
#: satisfy them, so they refuse the whole Batch (§5.3 validity).
REQUEST_INVALID_CODES = frozenset({
    "invalid_request", "operations_invalid", "image_too_large", "bundle_too_large",
})

#: A readiness reason refuses the whole Batch only when it blocked EVERY
#: Target, and then it is reported with the code that reason has always had.
NOTHING_READY_ERRORS = {
    "OUTCOME_UNKNOWN_UNRESOLVED": (409, "programming_outcome_unknown_unresolved",
                                   "a run on this PPU ended OUTCOME_UNKNOWN; reconcile "
                                   "and acknowledge first"),
    "RUN_IN_PROGRESS": (409, "programming_run_in_progress",
                        "another programming run is in progress on this PPU"),
    "PPU_RECOVERY_REQUIRED": (409, "ppu_recovery_required",
                              "PPU Active Asset Set requires explicit recovery"),
    "PPU_NOT_ENABLED": (409, "ppu_not_enabled",
                        "PPU must complete Validate & Enable before programming"),
}


def nothing_ready_error(reason: str) -> ProgrammingError:
    status, code, message = NOTHING_READY_ERRORS.get(
        reason, (409, "ppu_not_ready", f"no Target PPU is ready to be operated: {reason}"))
    return ProgrammingError(status, code, message)


def _unit_status(outcome: str | None, *, stopped: bool = False) -> str:
    if outcome in EXECUTED_OUTCOMES:
        return "FINISHED"
    if outcome == "BLOCKED":
        return "BLOCKED"
    return "SKIPPED" if stopped else "NOT_RUN"


def migrate_batch_record(batch: Mapping[str, Any]) -> dict[str, Any]:
    """A journalled Batch of the previous schema, read as a single-Target one.

    Read-only: the caller's record is not modified and the stored journal is
    never rewritten in place. The shape changes; nothing is reinterpreted. An
    interrupted attempt stays interrupted, for the restart rule to judge under
    exactly the rule it would have met before the upgrade.
    """
    alias, site = batch["ppu_alias"], batch["site_id"]
    attempts = [dict(attempt) for attempt in (batch.get("attempts") or [])]
    for attempt in attempts:
        attempt.setdefault("job_key", {"batch_id": batch["batch_id"], "ppu_alias": alias,
                                       "site_id": site, "attempt": attempt.get("attempt")})
    outcome = batch.get("outcome")
    # A v1 Batch reported STOPPED in the outcome field. Execution status and
    # outcome are separate now, so the stop moves to the status it always was.
    stopped = outcome == "STOPPED"
    unit_outcome = None if stopped else outcome
    unit = {
        "ppu_alias": alias, "site_id": site,
        "status": _unit_status(unit_outcome, stopped=stopped),
        "outcome": unit_outcome, "reason": batch.get("reason"),
        "attempts": attempts,
    }
    return {
        "schema": BATCH_SCHEMA, "batch_id": batch["batch_id"],
        "start_id": batch.get("start_id"),
        "targets": [{"ppu_alias": alias, "site_ids": [site]}],
        "operations": batch.get("operations"), "source": batch.get("source"),
        "icpn": batch.get("icpn"), "policy": batch.get("policy"),
        "state": batch.get("state"),
        "execution_status": ("STOPPED" if stopped or batch.get("stop_requested")
                             else "COMPLETED" if batch.get("state") == "finished"
                             else "RUNNING"),
        "outcome": aggregate_outcome([unit]) if outcome is not None else None,
        "reason": batch.get("reason"),
        "stop_requested": bool(batch.get("stop_requested")),
        "units": [unit],
        "created_at": batch.get("created_at"), "updated_at": batch.get("updated_at"),
        "migrated_from": LEGACY_BATCH_SCHEMA,
    }


class ProgrammingBatchCoordinator:
    def __init__(self, workflow: BundleProgrammingWorkflow, *,
                 journal_path: Path | None = None,
                 platform_gate: Callable[[str], str | None] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 spawn: Callable[[Callable[[], None]], None] | None = None,
                 poll_interval_s: float = 0.5) -> None:
        self.workflow = workflow
        self.journal_path = journal_path
        # The Manager's Platform maintenance gate, evaluated per Target PPU at
        # admission and again immediately before each PPU is operated.
        self.platform_gate = platform_gate
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
            if not isinstance(data, dict):
                raise ValueError("schema")
            schema = data.get("schema")
            if schema not in (JOURNAL_SCHEMA, LEGACY_JOURNAL_SCHEMA):
                raise ValueError("schema")
            for record in data["batches"]:
                # A journal of the previous schema is migrated, never refused:
                # an interrupted attempt in it is exactly the record the
                # restart rule has to judge.
                batch = (migrate_batch_record(record)
                         if schema == LEGACY_JOURNAL_SCHEMA else record)
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
        never by submitting anything again. The judgement is per Site."""
        for unit in batch["units"]:
            if unit.get("outcome") is not None:
                continue
            attempts = unit.get("attempts") or []
            last = attempts[-1] if attempts else None
            run = self._run_of(unit["ppu_alias"], last) if last else None
            if last is None or (last.get("run_id") is None and run is None
                                and last.get("state") == "planned"):
                # Provably never submitted - no attempt was journalled, or one
                # was journalled and never started. That proof is the only
                # BLOCKED a restart may conclude.
                outcome, reason = "BLOCKED", "MANAGER_RESTARTED_BEFORE_SUBMISSION"
            elif run is not None and run.get("outcome") in ("PASS", "FAIL", "BLOCKED"):
                # The attempt itself finished; only the bookkeeping was cut.
                self._record_attempt(last, run)
                outcome = run["outcome"]
                reason = ("MANAGER_RESTARTED_NO_FURTHER_ATTEMPT" if outcome == "FAIL"
                          else run.get("reason"))
            else:
                # Not provably unsent, so never BLOCKED.
                if run is not None:
                    self._record_attempt(last, run)
                outcome, reason = "OUTCOME_UNKNOWN", "MANAGER_RESTARTED_DURING_ATTEMPT"
            unit.update(status=_unit_status(outcome), outcome=outcome, reason=reason)
        outcome = aggregate_outcome(batch["units"])
        batch.update(state="finished", outcome=outcome,
                     execution_status="STOPPED" if batch.get("stop_requested") else "COMPLETED",
                     reason=batch_reason(batch["units"], outcome,
                                         batch.get("reason") or "MANAGER_RESTARTED"),
                     updated_at=_now())

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

    def _current_run(self, batch: Mapping[str, Any]) -> dict[str, Any] | None:
        for unit in reversed(batch["units"]):
            attempts = unit.get("attempts") or []
            if attempts:
                return self._run_of(unit["ppu_alias"], attempts[-1])
        return None

    def _view(self, batch: Mapping[str, Any]) -> dict[str, Any]:
        """The Batch as a reader sees it.

        A single-Site Batch also carries the fields the alias-scoped entry has
        always returned (``ppu_alias``, ``site_id``, a flat ``attempts``).
        Those are a projection of the same record, not a second shape of the
        truth: they are derived here and never stored or judged separately.
        """
        units = [{**unit, "attempts": [dict(a) for a in unit.get("attempts") or []]}
                 for unit in batch["units"]]
        attempts = [attempt for unit in units for attempt in unit["attempts"]]
        outcomes = [unit.get("outcome") for unit in units]
        view = {**batch, "units": units, "attempts": attempts,
                "current_run": self._current_run(batch),
                # One Site is one IC: counted once, by its final outcome only.
                "counts": {"pass": outcomes.count("PASS"), "fail": outcomes.count("FAIL"),
                           "blocked": outcomes.count("BLOCKED"),
                           "unknown": outcomes.count("OUTCOME_UNKNOWN"),
                           "sites": len(units), "attempts": len(attempts)},
                "auto_retry": "DISABLED"}
        if len(units) == 1:
            view["ppu_alias"] = units[0]["ppu_alias"]
            view["site_id"] = units[0]["site_id"]
        return view

    @staticmethod
    def _single_alias(batch: Mapping[str, Any]) -> str | None:
        """The alias of a single-Target, single-Site Batch, else None."""
        targets = batch["targets"]
        if len(targets) == 1 and len(targets[0]["site_ids"]) == 1:
            return targets[0]["ppu_alias"]
        return None

    def _get(self, batch_id: str, alias: str | None = None) -> dict[str, Any]:
        """``alias`` is the compatibility entry: it reads only a Batch that is
        a single Target on that PPU, exactly as it could before."""
        batch = self._batches.get(batch_id)
        if batch is None or (alias is not None and self._single_alias(batch) != alias):
            raise ProgrammingError(404, "programming_batch_not_found",
                                   "programming batch was not found")
        return batch

    # --------------------------------------------------------------------- API
    def start_batch(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """The canonical Manager-owned entry: a Batch over a Target Set."""
        return self._start(body)

    def start(self, alias: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """The alias-scoped compatibility entry (§5.8).

        It is a door into the same engine, not a second path: the body is
        normalised into a single-Target Batch and judged by exactly the same
        admission, isolation and outcome rules.
        """
        if not isinstance(body, Mapping) or TARGET_KEY in body or LEGACY_SITE_KEY not in body:
            raise ProgrammingError(
                400, "invalid_request",
                "a batch requires icpn, site_id, an operations list with its Programming "
                "Image, Bundle or erase range, and optional retry_limit / stop_policy")
        normalised = {key: value for key, value in body.items() if key != LEGACY_SITE_KEY}
        normalised[TARGET_KEY] = [{"ppu_alias": alias, "site_ids": [body[LEGACY_SITE_KEY]]}]
        return self._start(normalised)

    def _start(self, body: Mapping[str, Any]) -> dict[str, Any]:
        if (not isinstance(body, Mapping)
                or set(body) - PLAN_KEYS - {TARGET_KEY} - POLICY_KEYS - START_KEYS
                or "operations" not in body or TARGET_KEY not in body):
            raise ProgrammingError(
                400, "invalid_request",
                "a batch requires icpn, targets, an operations list with its Programming "
                "Image, Bundle or erase range, and optional retry_limit / stop_policy")
        targets = parse_targets(body)
        policy = parse_policy(body, site_count(targets))
        plan_body = {key: body[key] for key in body if key in PLAN_KEYS}
        start_id = body.get("start_id")
        aliases = [target["ppu_alias"] for target in targets]
        with self._lock:
            # Validity first (§5.3). An unknown or unauthorised Target refuses
            # the WHOLE Batch and leaves the start_id unconsumed, so the
            # operator may correct the request and resend the same token.
            for alias in aliases:
                self.workflow._require_commissioned(alias)
            if "start_id" in body:
                self.workflow.require_batch_start(aliases[0], start_id)
            if any(batch["outcome"] is None
                   and {t["ppu_alias"] for t in batch["targets"]} & set(aliases)
                   for batch in self._batches.values()):
                raise ProgrammingError(409, "programming_batch_in_progress",
                                       "another programming batch is in progress on this PPU")
            # Readiness second: it never refuses a Batch that still has
            # somewhere to run. A Target that is not ready is admitted BLOCKED
            # with its own reason; the others still run.
            units = [{"ppu_alias": target["ppu_alias"], "site_id": site,
                      "status": "NOT_RUN", "outcome": None, "reason": None, "attempts": []}
                     for target in targets for site in target["site_ids"]]
            for alias, target in zip(aliases, targets):
                reason = self._admission_block(alias, target["site_ids"][0])
                if reason is None:
                    continue
                for unit in units:
                    if unit["ppu_alias"] == alias:
                        unit.update(status="BLOCKED", outcome="BLOCKED",
                                    reason=f"ADMISSION_{reason}")
            first = self._first_plan(plan_body, units)
            if first is None:
                # Nothing can run at all. With no other Target left to protect,
                # partial admission has nothing to do: refuse the Batch, record
                # nothing and leave the start_id unconsumed, exactly as a
                # single-Target Batch has always been refused.
                raise nothing_ready_error(
                    next((unit["reason"].removeprefix("ADMISSION_") for unit in units
                          if unit["reason"]), "NO_TARGET"))
            first_index, first_plan = first
            batch = {
                "schema": BATCH_SCHEMA, "batch_id": secrets.token_hex(16),
                "start_id": start_id,
                "targets": [dict(target, site_ids=list(target["site_ids"]))
                            for target in targets],
                "operations": plan_body["operations"],
                "source": first_plan.get("source"),
                "icpn": (first_plan.get("route") or {}).get("icpn") or plan_body.get("icpn"),
                "policy": policy, "state": "running",
                "execution_status": "RUNNING", "outcome": None, "reason": None,
                "stop_requested": False, "units": units,
                "created_at": _now(), "updated_at": _now(),
            }
            if start_id is not None:
                # Admission is journalled first: from here on the start can
                # never reconcile as "not accepted". Partial admission has
                # still consumed it, so a BLOCKED Target needs a NEW start.
                self.workflow.consume_batch_start(
                    aliases[0], start_id, batch["batch_id"], batch["targets"])
            self._batches[batch["batch_id"]] = batch
            try:
                self._persist_locked()
            except BaseException:
                del self._batches[batch["batch_id"]]
                raise
        self.spawn(lambda: self._execute(batch, plan_body, first_index, first_plan))
        return {"ok": True, "batch": self._view(batch)}

    def _first_plan(self, plan_body: Mapping[str, Any],
                    units: list[dict[str, Any]]) -> tuple[int, Mapping[str, Any]] | None:
        """Plan the first runnable Site synchronously, as a Batch always has.

        A refused request must create no Batch, and the Batch's identities are
        fixed before anything is queued. The two kinds of refusal part here: a
        refusal about the REQUEST (malformed, unusable image) refuses
        everything, while a refusal about a PPU or a Route blocks only that
        Site and the next one is tried.
        """
        for index, unit in enumerate(units):
            if unit["outcome"] is not None:
                continue
            try:
                plan = self.workflow.plan(
                    unit["ppu_alias"], {**plan_body, "site_id": unit["site_id"]})["plan"]
            except ProgrammingError as exc:
                if exc.code in REQUEST_INVALID_CODES:
                    raise
                unit.update(status="BLOCKED", outcome="BLOCKED",
                            reason=f"ADMISSION_{exc.code}")
                continue
            return index, plan
        return None

    def _admission_block(self, alias: str, site: int) -> str | None:
        """Readiness of one Target PPU. Never raises: a PPU that cannot be
        read is not ready, and that is a per-Target answer, not a Batch one.

        Both gates are asked. The Platform gate proves the PPU is safe to
        mutate at all; ``retry_block`` proves this Site is released. Either
        one blocks this Target alone.
        """
        try:
            if self.platform_gate is not None:
                blocked = self.platform_gate(alias)
                if blocked is not None:
                    return blocked
            return self.workflow.retry_block(alias, site)
        except ProgrammingError as exc:
            return exc.code
        except Exception as exc:  # noqa: BLE001 - unreadable is never "ready"
            return f"PPU_STATE_UNREADABLE_{type(exc).__name__}"

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
            return {"ok": True, "batch": self._view(self._get(batch_id, alias))}

    def status_batch(self, batch_id: str) -> dict[str, Any]:
        with self._lock:
            return {"ok": True, "batch": self._view(self._get(batch_id))}

    def request_stop(self, alias: str, batch_id: str,
                     body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._request_stop(batch_id, body, alias=alias)

    def request_stop_batch(self, batch_id: str,
                           body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._request_stop(batch_id, body)

    def _request_stop(self, batch_id: str, body: Mapping[str, Any] | None,
                      alias: str | None = None) -> dict[str, Any]:
        """Stop queuing. Never cancels, resets or releases anything on the PPU."""
        if body is not None and dict(body) != {"stop": STOP_TOKEN}:
            raise ProgrammingError(400, "invalid_request",
                                   f"stop requires stop={STOP_TOKEN}")
        with self._lock:
            batch = self._get(batch_id, alias)
            if batch["outcome"] is None and not batch["stop_requested"]:
                batch["stop_requested"] = True
                batch["updated_at"] = _now()
                self._persist_locked()
            return {"ok": True, "batch": self._view(batch)}

    # ---------------------------------------------------------------- execution
    def _execute(self, batch: dict[str, Any], plan_body: Mapping[str, Any],
                 first_index: int, first_plan: Mapping[str, Any]) -> None:
        try:
            self._run_units(batch, plan_body, first_index, first_plan)
        except Exception as exc:  # noqa: BLE001 - never retried, never a guessed result
            # The machinery that judges Targets failed, not a Target. One PPU
            # being unready is isolated; being unable to tell is not (§5.7).
            with self._lock:
                for unit in batch["units"]:
                    if unit["outcome"] is None:
                        unit.update(status="SKIPPED", outcome="OUTCOME_UNKNOWN",
                                    reason=f"BATCH_UNEXPECTED_{type(exc).__name__}")
            self._finish(batch, f"BATCH_UNEXPECTED_{type(exc).__name__}")

    def _finish(self, batch: dict[str, Any], reason: str | None) -> None:
        outcome = aggregate_outcome(batch["units"])
        self._update(batch, state="finished", outcome=outcome,
                     execution_status="STOPPED" if batch["stop_requested"] else "COMPLETED",
                     reason=batch_reason(batch["units"], outcome, reason))

    def _skip(self, batch: dict[str, Any], unit: dict[str, Any],
              status: str, reason: str, outcome: str | None = None) -> None:
        with self._lock:
            unit.update(status=status, outcome=outcome, reason=reason)
            batch["updated_at"] = _now()
            self._persist_locked()

    def _run_units(self, batch: dict[str, Any], plan_body: Mapping[str, Any],
                   first_index: int, first_plan: Mapping[str, Any]) -> None:
        """Sequential walk of the Target Set. One in-flight run at a time."""
        policy = batch["policy"]
        stop_policy = policy["stop_policy"]
        latched: dict[str, str] = {}
        failed_sites = 0
        reason: str | None = None
        for index, unit in enumerate(batch["units"]):
            alias, site = unit["ppu_alias"], unit["site_id"]
            if unit["outcome"] is not None:
                # Admitted BLOCKED. It spends no retry budget and, by default,
                # does not count toward the failed_sites threshold.
                continue
            if batch["stop_requested"]:
                self._skip(batch, unit, "SKIPPED", "STOP_REQUESTED_NOTHING_SUBMITTED")
                reason = reason or "STOP_REQUESTED"
                continue
            if alias in latched:
                # OUTCOME_UNKNOWN latches its own PPU and skips that PPU's
                # remaining Sites. Other PPUs are untouched.
                self._skip(batch, unit, "SKIPPED", f"PPU_LATCHED_{latched[alias]}")
                continue
            if (stop_policy["kind"] == "failed_sites"
                    and failed_sites >= stop_policy["threshold"]):
                self._skip(batch, unit, "SKIPPED",
                           "STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED")
                reason = reason or "STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED"
                continue
            # Readiness read at admission does not authorise a mutation that
            # happens now. Re-check immediately before operating this PPU.
            block = self._admission_block(alias, site)
            if block is not None:
                self._skip(batch, unit, "BLOCKED", f"EXECUTION_{block}", outcome="BLOCKED")
                continue
            outcome, unit_reason = self._run_attempts(
                batch, unit, plan_body, first_plan if index == first_index else None)
            with self._lock:
                unit.update(status=_unit_status(outcome), outcome=outcome, reason=unit_reason)
                batch["updated_at"] = _now()
                self._persist_locked()
            if outcome == "OUTCOME_UNKNOWN":
                latched[alias] = unit_reason or "OUTCOME_UNKNOWN"
            elif outcome == "FAIL":
                failed_sites += 1
        self._finish(batch, reason)

    def _run_attempts(self, batch: dict[str, Any], unit: dict[str, Any],
                      plan_body: Mapping[str, Any],
                      planned: Mapping[str, Any] | None = None) -> tuple[str, str | None]:
        """Every attempt for ONE Site. Returns that Site's outcome and reason."""
        alias, site, policy = unit["ppu_alias"], unit["site_id"], batch["policy"]
        site_body = {**plan_body, "site_id": site}
        plan: Mapping[str, Any] | None = planned
        for number in range(1, policy["retry_limit"] + 2):
            if batch["stop_requested"] and number > 1:
                return "FAIL", "STOP_REQUESTED_NO_FURTHER_ATTEMPT"
            if plan is None:
                try:
                    plan = self.workflow.plan(alias, site_body)["plan"]
                except ProgrammingError as exc:
                    if number == 1:
                        # Nothing was submitted for this Site: provably BLOCKED.
                        return "BLOCKED", exc.code
                    # The earlier FAIL stands; the retry could not be planned.
                    return "FAIL", f"RETRY_PLAN_REFUSED_{exc.code}"
            attempt = {"attempt": number,
                       "job_key": {"batch_id": batch["batch_id"], "ppu_alias": alias,
                                   "site_id": site, "attempt": number},
                       "plan_id": plan["plan_id"], "run_id": None,
                       "job_binding_sha256": plan["job_binding_sha256"], "job_id": None,
                       "state": "planned", "outcome": None, "reason": None,
                       "safe_off": None, "retry": None,
                       "started_at": _now(), "finished_at": None}
            with self._lock:
                unit["attempts"].append(attempt)
                unit["status"] = "RUNNING"
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
                if number == 1:
                    return "BLOCKED", exc.code
                return "FAIL", f"RETRY_START_REFUSED_{exc.code}"
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
                # PASS ends this Site; OUTCOME_UNKNOWN and BLOCKED are never retried.
                return outcome, run.get("reason")
            eligible, why = retry_eligibility(run)
            decision = {"eligible": eligible, "reason": why, "decision": "NO_RETRY"}
            final_reason = run.get("reason")
            if number > policy["retry_limit"]:
                # No attempt is left: the FAIL stands with its own reason.
                final = "RETRY_LIMIT_EXHAUSTED" if policy["retry_limit"] else None
            elif not eligible:
                final = f"RETRY_NOT_ELIGIBLE_{why}"
            elif self._stop_policy_reached(batch):
                final = "STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED"
            elif batch["stop_requested"]:
                final = "STOP_REQUESTED_NO_FURTHER_ATTEMPT"
            else:
                blocked = self.workflow.retry_block(alias, site)
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
                return "FAIL", final or final_reason
            plan = None  # a retry always gets a new plan, run and Job
        return "FAIL", final_reason

    def _stop_policy_reached(self, batch: Mapping[str, Any]) -> bool:
        stop = batch["policy"]["stop_policy"]
        if stop["kind"] != "failed_sites":
            return False
        failed = sum(1 for unit in batch["units"] if unit.get("outcome") == "FAIL")
        # The Site being judged has not been recorded yet; it is the one that
        # just failed, so it counts here.
        return failed + 1 >= stop["threshold"]
