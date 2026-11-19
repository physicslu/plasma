"""Manager-owned Batch coordinator over a Target Set: safe Retry and Stop.

One Batch = an ordered Target Set (``[{ppu_alias, site_ids}]``) spanning one
or more PPUs, one programming Job specification (an ordered erase / program /
verify ``operations`` list with its Programming Image or Bundle) and a policy
``{repeat, replace_ic_before_next_cycle, retry_limit, stop_policy}``. ICPN and
Image are Batch-level and never vary per Site.

Manual Repeat (WP-02): ``repeat`` (1..10000) is the number of logical Cycles
EACH selected Site runs in this one Batch (the Manual Session). A Cycle is one
ordered E/P/V flow on one IC placement; its Retry Attempts stay inside it and
never consume another Cycle. A definite PASS or definite FAIL settles exactly
one Cycle; ``BLOCKED`` (nothing submitted) and ``OUTCOME_UNKNOWN`` never do.
After a settled Cycle the Site lane pauses for the operator's Continue (the
existing Start action, which attests the IC was replaced) - except a PASS in
same-IC Debug mode (``replace_ic_before_next_cycle=false``), which proceeds
through the same admission gates by itself. Every Cycle is a fresh plan, run
and PPU Job on the same lane; there is no second scheduler. Settled Cycles are
appended to the Batch's cycle segment of this journal so a 10000-Cycle session
keeps its evidence while the main record holds only counters and the current
Cycle.

The coordinator only decides WHETHER ANOTHER ATTEMPT IS SUBMITTED. Every
attempt is an ordinary ``BundleProgrammingWorkflow`` plan + run: a new plan, a
new run and a new PPU Job (new Job ID; the Job Binding is re-derived and
re-verified by the PPU for that Job) with ``auto_retry = DISABLED``. There is
no second programming engine, no Gateway batch runtime and no Repeat
scheduler here. Bounded Site lanes advance independently through the same
workflow, with at most one in-flight run per Site and one active Cycle per Site.

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
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generator, Mapping

from .programming import (
    SHARED_CONTROL_FAILURE, TARGET_NOT_READY, TARGET_STATE_UNAVAILABLE,
    TARGET_TRANSACTION_UNKNOWN, BundleProgrammingWorkflow, JOB_TERMINAL, ProgrammingError,
)

BATCH_SCHEMA = "plasma.manager.programming-batch.v2"
JOURNAL_SCHEMA = "plasma.manager.programming-batch-journal.v2"
LEGACY_BATCH_SCHEMA = "plasma.manager.programming-batch.v1"
LEGACY_JOURNAL_SCHEMA = "plasma.manager.programming-batch-journal.v1"
MAX_RETRY_LIMIT = 5
#: Manual Repeat: Cycles per selected Site in one Manual Session (WP-02).
MAX_REPEAT = 10000
MAX_TARGETS = 32
MAX_SITES_PER_BATCH = 64
STOP_TOKEN = "STOP_QUEUING"
MAX_BATCHES_RETAINED = 32
BATCH_TERMINAL = frozenset({"PASS", "FAIL", "PARTIAL", "OUTCOME_UNKNOWN", "BLOCKED"})
# A Target counts as executed only when a Job was submitted for it.
EXECUTED_OUTCOMES = frozenset({"PASS", "FAIL", "OUTCOME_UNKNOWN"})
SETTLED_UNIT_OUTCOMES = EXECUTED_OUTCOMES | {"PARTIAL"}
PLAN_KEYS = frozenset({"icpn", "operations", "image_base64", "image_filename",
                       "bundle_base64", "address", "length"})
TARGET_KEY = "targets"
POLICY_KEYS = frozenset({"retry_limit", "stop_policy", "repeat", "replace_ic_before_next_cycle"})
START_KEYS = frozenset({"start_id"})
CONTINUE_KEYS = frozenset({"ppu_alias", "site_id", "continue_seq"})
#: Set by the authenticating front (the Control Station BFF), never by a browser.
ACTOR_KEY = "actor"
#: A Site lane waiting for the operator's Continue (replace IC / review FAIL).
AWAITING_CONTINUE = "AWAITING_CONTINUE"


class _SharedControlFailure(RuntimeError):
    """A classified global failure, retaining its actionable reason."""


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
    """Validated ``{repeat, replace_ic_before_next_cycle, retry_limit, stop_policy}``.

    ``repeat`` is the Cycle count of EACH selected Site (1..10000), not a PASS
    quota and not a Batch total. ``sites`` is the Batch's Site count, which
    bounds a ``failed_sites`` threshold at 1..N: a threshold no Batch could
    ever reach would be a policy that silently means "never".
    """
    repeat = body.get("repeat", 1)
    if type(repeat) is not int or not 1 <= repeat <= MAX_REPEAT:
        raise ProgrammingError(400, "invalid_request",
                               f"repeat must be an integer from 1 to {MAX_REPEAT} "
                               "(Cycles per selected Site)")
    replace = body.get("replace_ic_before_next_cycle", True)
    if type(replace) is not bool:
        raise ProgrammingError(400, "invalid_request",
                               "replace_ic_before_next_cycle must be true or false")
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
    return {"repeat": repeat, "replace_ic_before_next_cycle": replace,
            "retry_limit": retry, "stop_policy": dict(stop)}


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
    # A Site that settled some, not all, of its Repeat Cycles is PARTIAL.
    executed = [outcome for outcome in outcomes if outcome in SETTLED_UNIT_OUTCOMES]
    if not executed:
        return "BLOCKED"
    if len(executed) != len(outcomes) or "PARTIAL" in outcomes:
        return "PARTIAL"
    return "PASS"


def retry_eligibility(run: Mapping[str, Any]) -> tuple[bool, str]:
    """Is this finished run a definite FAIL that a new attempt may follow?"""
    if run.get("outcome") != "FAIL":
        return False, f"OUTCOME_{run.get('outcome')}_IS_NOT_A_DEFINITE_FAIL"
    trusted, why = terminal_evidence(run)
    return (True, "DEFINITE_FAIL_SAFE_OFF_VERIFIED") if trusted else (False, why)


def terminal_evidence(run: Mapping[str, Any] | None) -> tuple[bool, str]:
    """Did this run end in a trusted terminal state with SAFE_OFF verified?

    The release condition every next submission on the Site needs, whether
    it is a Retry of the same Cycle or the next Repeat Cycle.
    """
    if not isinstance(run, Mapping):
        return False, "NO_TRUSTED_TERMINAL_JOB_STATE"
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
    return True, "TERMINAL_SAFE_OFF_VERIFIED"


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

def _source_of(body: Mapping[str, Any]) -> str:
    """The Programming Source a Batch carries, read from the request alone."""
    if "bundle_base64" in body:
        return "bundle"
    return "image" if "image_base64" in body else "range"


def _unit_status(outcome: str | None, *, stopped: bool = False) -> str:
    if outcome in SETTLED_UNIT_OUTCOMES:
        return "FINISHED"
    if outcome == "BLOCKED":
        return "BLOCKED"
    return "SKIPPED" if stopped else "NOT_RUN"


def new_cycle(planned: int) -> dict[str, Any]:
    """Per-Site Repeat accounting: counters plus the one current Cycle."""
    return {"planned": planned, "index": 1, "cycle_id": secrets.token_hex(16),
            "state": "ACTIVE", "disposition": None,
            "settled": 0, "pass": 0, "fail": 0, "retry_attempts": 0,
            "continue_seq": 0, "continued_seq": 0, "wait_reason": None,
            "last": None, "last_continue": None}


def ensure_cycle(batch: dict[str, Any]) -> None:
    """A record journalled before Manual Repeat reads as a one-Cycle session."""
    policy = batch.get("policy")
    if isinstance(policy, dict):
        policy.setdefault("replace_ic_before_next_cycle", True)
    for unit in batch.get("units") or []:
        if isinstance(unit.get("cycle"), dict):
            continue
        cycle = new_cycle(1)
        outcome = unit.get("outcome")
        attempts = unit.get("attempts") or []
        cycle["cycle_id"] = None
        if outcome in ("PASS", "FAIL"):
            cycle.update(settled=1, state="ENDED", disposition="COMPLETED" if outcome == "PASS"
                         else "COMPLETED_WITH_FAILURES",
                         retry_attempts=max(0, len(attempts) - 1),
                         **{outcome.lower(): 1})
        elif outcome is not None:
            cycle.update(state="ENDED", disposition=outcome)
        unit["cycle"] = cycle


def _receipt_summary(run: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The PPU evidence an operator sees for a settled Cycle (no free text)."""
    if not isinstance(run, Mapping):
        return None
    receipt = run.get("receipt") if isinstance(run.get("receipt"), dict) else {}
    return {
        "run_id": run.get("run_id"), "outcome": run.get("outcome"), "reason": run.get("reason"),
        "job_id": receipt.get("job_id"), "job_state": receipt.get("job_state"),
        "flash_result": receipt.get("flash_result"), "safe_off": receipt.get("safe_off"),
        "safe_off_source": receipt.get("safe_off_source"),
        "job_binding_confirmed": (receipt.get("observed_job_binding_sha256") is not None
                                  and receipt.get("observed_job_binding_sha256")
                                  == receipt.get("expected_job_binding_sha256")),
        "elapsed_ms": receipt.get("elapsed_ms"),
    }


def _site_failed(unit: Mapping[str, Any]) -> bool:
    """A Site counts toward ``failed_sites`` once, by any failed Cycle."""
    cycle = unit.get("cycle") or {}
    return unit.get("outcome") == "FAIL" or cycle.get("fail", 0) > 0


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
        "started_at": batch.get("started_at"), "finished_at": batch.get("finished_at"),
        "migrated_from": LEGACY_BATCH_SCHEMA,
    }


class ProgrammingBatchCoordinator:
    def __init__(self, workflow: BundleProgrammingWorkflow, *,
                 journal_path: Path | None = None,
                 platform_gate: Callable[[str], tuple[str, str] | None] | None = None,
                 shared_control_gate: Callable[[], tuple[str, str] | None] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 spawn: Callable[[Callable[[], None]], None] | None = None,
                 poll_interval_s: float = 0.1) -> None:
        self.workflow = workflow
        self.journal_path = journal_path
        # The Manager's Platform maintenance gate, evaluated per Target PPU at
        # admission and again immediately before each PPU is operated.
        self.platform_gate = platform_gate
        self.shared_control_gate = shared_control_gate or getattr(
            getattr(platform_gate, "__self__", None), "shared_control_gate", None)
        self.workflow.shared_control_gate = self.shared_control_gate
        self.sleep = sleep
        self.spawn = spawn or (lambda target: threading.Thread(
            target=target, name="plasma-programming-batch", daemon=True).start())
        self.poll_interval_s = poll_interval_s
        self._lock = threading.RLock()
        self._batches: dict[str, dict[str, Any]] = {}
        self._control_failure: str | None = None
        #: Where a journal of the previous schema lives, if one does. It is
        #: opened, never written: not overwritten, truncated, deleted or
        #: renamed out of the way. The v2 writer keeps its own file.
        self._legacy_path: Path | None = None
        self._v2_path: Path | None = journal_path
        #: Batches that came from the legacy journal. They stay in memory and
        #: are never copied into the v2 file, so the v1 journal remains the
        #: one and only record of its own Batches.
        self._legacy_ids: set[str] = set()
        #: Cycle segments when no journal file is configured (Host tests).
        self._memory_ledger: dict[str, list[dict[str, Any]]] = {}
        self._load_journal()

    # ------------------------------------------------------------------ journal
    def _read_journal(self, path: Path) -> tuple[str, list[Any]]:
        """One journal file, by schema. An unreadable journal fails closed."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("schema")
            schema = data.get("schema")
            if schema not in (JOURNAL_SCHEMA, LEGACY_JOURNAL_SCHEMA):
                raise ValueError("schema")
            batches = data["batches"]
            if not isinstance(batches, list):
                raise ValueError("batches")
            return schema, batches
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(
                "Programming batch journal is unreadable; refusing to start") from exc

    def _load_journal(self) -> None:
        """Load the legacy journal, then the v2 one on top of it.

        The configured path is whatever the last Manager wrote there. If that
        is a journal of the previous schema, it becomes the legacy file - read
        and never written - and the v2 writer takes a file of its own beside
        it. A Manager restarting afterwards reads both: v1 for its history,
        v2 for everything since. Neither is a second Batch engine; both load
        into the one canonical in-memory model, and where the two name the
        same Batch, v2 is the later writer and wins.
        """
        if self.journal_path is None:
            return
        legacy_records: list[Any] = []
        v2_records: list[Any] = []
        if self.journal_path.exists():
            schema, records = self._read_journal(self.journal_path)
            if schema == LEGACY_JOURNAL_SCHEMA:
                self._legacy_path = self.journal_path
                self._v2_path = self.journal_path.with_name(self.journal_path.name + ".v2")
                legacy_records = records
                if self._v2_path.exists():
                    _schema, v2_records = self._read_journal(self._v2_path)
            else:
                v2_records = records
        # Migrated on read, never refused: an interrupted attempt in a legacy
        # record is exactly what the restart rule has to judge.
        legacy = {}
        for record in legacy_records:
            batch = migrate_batch_record(record)
            legacy[batch["batch_id"]] = batch
        current = {record["batch_id"]: record for record in v2_records}
        self._refuse_conflicting_identities(legacy, current)
        for batch_id, batch in legacy.items():
            if batch_id in current:
                # Both files tell the same story; the v2 writer owns it from
                # here, and the legacy copy is not loaded twice.
                continue
            self._legacy_ids.add(batch_id)
            self._admit_loaded(batch)
        for record in v2_records:
            self._admit_loaded(record)
        with self._lock:
            self._persist_locked()

    @staticmethod
    def _transaction_identity(batch: Mapping[str, Any]) -> dict[str, Any]:
        """What two records of one Batch must agree on to be the same Batch.

        Timestamps and bookkeeping are left out; what is compared is the
        transaction: which start admitted it, what it was aimed at, what it
        concluded, and every Job identity and SAFE_OFF result underneath.
        """
        return {
            "start_id": batch.get("start_id"),
            "targets": batch.get("targets"),
            "outcome": batch.get("outcome"),
            "units": [{
                "ppu_alias": unit.get("ppu_alias"), "site_id": unit.get("site_id"),
                "outcome": unit.get("outcome"),
                "attempts": [{key: attempt.get(key) for key in
                              ("attempt", "plan_id", "run_id", "job_id",
                               "job_binding_sha256", "outcome", "safe_off")}
                             for attempt in unit.get("attempts") or []],
            } for unit in batch.get("units") or []],
        }

    def _refuse_conflicting_identities(self, legacy: Mapping[str, Any],
                                       current: Mapping[str, Any]) -> None:
        """Fail closed on a transaction identity that cannot be proven.

        Two journals may hold the same Batch - that is normal, and harmless
        while they say the same thing. When they do not, there is no safe way
        to pick a winner: preferring the later writer can bury an
        ``OUTCOME_UNKNOWN`` that an operator still has to reconcile, and
        preferring the older one can lose a Job that really ran. The same is
        true of a start ID that two different Batches claim, since one start
        admits at most one Batch. Either way the Manager refuses to start and
        says exactly which identity it could not prove; an operator reconciles
        it. Deleting the v2 journal is NOT the remedy - it holds real
        transactions.
        """
        conflicts = []
        for batch_id, record in current.items():
            older = legacy.get(batch_id)
            if older is not None and (self._transaction_identity(older)
                                      != self._transaction_identity(record)):
                conflicts.append(f"batch_id {batch_id} differs between the journals")
        claimed: dict[str, str] = {}
        for batch_id, record in list(legacy.items()) + list(current.items()):
            start_id = record.get("start_id")
            if start_id is None:
                continue
            if claimed.setdefault(start_id, batch_id) != batch_id:
                conflicts.append(
                    f"start_id {start_id} is claimed by {claimed[start_id]} and {batch_id}")
        if conflicts:
            raise RuntimeError(
                "Programming batch journals disagree about a transaction identity; "
                "refusing to start without reconciliation: " + "; ".join(sorted(conflicts)))

    def _admit_loaded(self, batch: dict[str, Any]) -> None:
        # Old journals have no authoritative timing; never infer it from updates.
        batch.setdefault("started_at", None)
        batch.setdefault("finished_at", None)
        ensure_cycle(batch)
        if batch.get("outcome") is None:
            self._close_interrupted(batch)
        self._batches[batch["batch_id"]] = batch

    def _close_interrupted(self, batch: dict[str, Any]) -> None:
        """A Batch the Manager was stopped in: decide from the run journal,
        never by submitting anything again. The judgement is per Site."""
        for unit in batch["units"]:
            if unit.get("outcome") is not None:
                continue
            cycle = unit["cycle"]
            attempts = unit.get("attempts") or []
            settled_now = (cycle["last"] is not None
                           and cycle["last"].get("cycle_id") == cycle["cycle_id"])
            if (cycle["state"] == AWAITING_CONTINUE or (cycle["settled"] and not attempts)
                    or (settled_now and cycle["disposition"] != "OUTCOME_UNKNOWN")):
                # Paused between Cycles, or the next Cycle never got an
                # attempt: nothing is in flight. The session ends here; the
                # plan bytes are not journalled, so it is never resumed.
                outcome, reason = self._conclude(unit, None, "MANAGER_RESTARTED_SESSION_ENDED")
                unit.update(status=_unit_status(outcome, stopped=True), outcome=outcome,
                            reason=reason)
                cycle["state"] = "ENDED"
                continue
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
            if outcome in ("PASS", "FAIL"):
                # The interrupted Cycle did settle: account it exactly once.
                self._settle_cycle(batch, unit, outcome, reason, run, persist=False)
                outcome = None if cycle["settled"] < cycle["planned"] else outcome
                if outcome is None:
                    reason = "MANAGER_RESTARTED_SESSION_ENDED"
            elif outcome == "BLOCKED" and cycle["settled"]:
                outcome, reason = None, "MANAGER_RESTARTED_SESSION_ENDED"
            outcome, reason = self._conclude(unit, outcome, reason)
            unit.update(status=_unit_status(outcome, stopped=outcome is None),
                        outcome=outcome, reason=reason)
            cycle["state"] = "ENDED"
        outcome = aggregate_outcome(batch["units"])
        batch.update(state="finished", outcome=outcome,
                     execution_status="STOPPED" if batch.get("stop_requested") else "COMPLETED",
                     reason=batch_reason(batch["units"], outcome,
                                         batch.get("reason") or "MANAGER_RESTARTED"),
                     finished_at=self._terminal_time(batch), updated_at=_now())

    def _persist_locked(self) -> None:
        try:
            self._write_journal_locked()
        except Exception as exc:
            self._control_failure = f"BATCH_JOURNAL_{type(exc).__name__}"
            with self.workflow._lock:
                self.workflow._control_failure = self._control_failure
            raise

    def _write_journal_locked(self) -> None:
        """Write the v2 journal, atomically, and never the legacy one.

        Batches that came from the legacy journal are left out: that file is
        still their only record, and copying them here would turn a read into
        a rewrite by another route.
        """
        if self._v2_path is None:
            return
        owned = [batch for batch in self._batches.values()
                 if batch["batch_id"] not in self._legacy_ids]
        kept = sorted((b for b in owned if b["outcome"] not in (None, "OUTCOME_UNKNOWN")),
                      key=lambda b: b["created_at"])[-MAX_BATCHES_RETAINED:]
        kept += [b for b in owned if b["outcome"] in (None, "OUTCOME_UNKNOWN")]
        kept_ids = {b["batch_id"] for b in kept}
        pruned = {b["batch_id"] for b in owned if b["batch_id"] not in kept_ids}
        if pruned - self.workflow.pruned_batch_ids:
            # Drop the admitting starts FIRST: a crash between the two writes
            # leaves a Batch without its start (harmless), never a CONSUMED
            # start without its Batch.
            with self.workflow._lock:
                self.workflow.pruned_batch_ids |= pruned
                self.workflow._persist_locked()
        for batch_id in pruned:
            # A cycle segment shares its Batch's retention, never outlives it.
            self._memory_ledger.pop(batch_id, None)
            segment = self._ledger_path(batch_id)
            if segment is not None:
                segment.unlink(missing_ok=True)
        payload = {"schema": JOURNAL_SCHEMA, "batches": kept}
        parent = self._v2_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{self._v2_path.name}.", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self._v2_path)
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise

    def _update(self, batch: dict[str, Any], **changes: Any) -> None:
        with self._lock:
            batch.update(changes)
            batch["updated_at"] = _now()
            self._persist_locked()

    # ------------------------------------------------------------ cycle segment
    def _ledger_path(self, batch_id: str) -> Path | None:
        """The append-only cycle segment of this journal for one Batch.

        It is part of the one Batch journal, not a second ledger: the main
        record holds the authoritative counters and the current Cycle; the
        segment holds each settled Cycle and operator Continue, so 10000
        Cycles never bloat the record that is rewritten on every change.
        """
        if self._v2_path is None:
            return None
        return self._v2_path.with_name(self._v2_path.name + ".cycles") / f"{batch_id}.jsonl"

    def _ledger_append_locked(self, batch_id: str, record: Mapping[str, Any]) -> None:
        """Durably append one record BEFORE the main journal reflects it."""
        try:
            path = self._ledger_path(batch_id)
            if path is None:
                self._memory_ledger.setdefault(batch_id, []).append(dict(record))
                return
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as exc:
            self._control_failure = f"BATCH_CYCLE_JOURNAL_{type(exc).__name__}"
            with self.workflow._lock:
                self.workflow._control_failure = self._control_failure
            raise

    def _ledger_records(self, batch_id: str) -> list[dict[str, Any]]:
        path = self._ledger_path(batch_id)
        if path is None:
            return [dict(r) for r in self._memory_ledger.get(batch_id, [])]
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                # A torn final line from a crash mid-append is not a record.
                continue
        return records

    def _settle_cycle(self, batch: dict[str, Any], unit: dict[str, Any], outcome: str,
                      reason: str | None, run: Mapping[str, Any] | None, *,
                      persist: bool = True) -> None:
        """One definite PASS or FAIL settles exactly one Cycle, once.

        Retry Attempts inside it are counted separately and never consume
        another Cycle. The segment record is written first; a crash between
        the two writes is recognised on restart by the Cycle ID and never
        counted twice.
        """
        with self._lock:
            cycle = unit["cycle"]
            if (cycle["cycle_id"] is not None and cycle["last"] is not None
                    and cycle["last"].get("cycle_id") == cycle["cycle_id"]):
                return  # this Cycle is already accounted
            attempts = [dict(a) for a in unit.get("attempts") or []]
            summary = _receipt_summary(run)
            record = {"type": "cycle", "batch_id": batch["batch_id"],
                      "ppu_alias": unit["ppu_alias"], "site_id": unit["site_id"],
                      "cycle_index": cycle["index"], "cycle_id": cycle["cycle_id"],
                      "outcome": outcome, "reason": reason, "attempts": attempts,
                      "receipt": summary,
                      "replace_ic_before_next_cycle":
                          batch["policy"].get("replace_ic_before_next_cycle", True),
                      "settled_at": _now()}
            already = (not persist and cycle["cycle_id"] is not None and any(
                r.get("type") == "cycle" and r.get("cycle_id") == cycle["cycle_id"]
                and r.get("site_id") == unit["site_id"]
                and r.get("ppu_alias") == unit["ppu_alias"]
                for r in self._ledger_records(batch["batch_id"])))
            if not already:
                self._ledger_append_locked(batch["batch_id"], record)
            cycle["settled"] += 1
            cycle["pass" if outcome == "PASS" else "fail"] += 1
            cycle["retry_attempts"] += max(0, len(attempts) - 1)
            cycle["last"] = {"cycle_index": cycle["index"], "cycle_id": cycle["cycle_id"],
                             "outcome": outcome, "reason": reason,
                             "attempts": len(attempts), "receipt": summary,
                             "settled_at": record["settled_at"]}
            batch["updated_at"] = _now()
            if persist:
                self._persist_locked()

    @staticmethod
    def _conclude(unit: dict[str, Any], outcome: str | None,
                  reason: str | None) -> tuple[str | None, str | None]:
        """The Site's final outcome from its settled Cycles.

        A one-Cycle Site reports exactly its Cycle, as before Repeat existed.
        A Site that settled at least one Cycle is FAIL when any Cycle failed,
        PARTIAL when Cycles remain, else PASS; an unknown always wins.
        """
        cycle = unit["cycle"]
        settled, planned = cycle["settled"], cycle["planned"]
        if outcome == "OUTCOME_UNKNOWN":
            disposition = "OUTCOME_UNKNOWN"
        elif not settled:
            disposition = "BLOCKED" if outcome == "BLOCKED" else "STOPPED"
        else:
            outcome = ("FAIL" if cycle["fail"] else "PARTIAL" if settled < planned else "PASS")
            if settled >= planned:
                disposition = "COMPLETED_WITH_FAILURES" if cycle["fail"] else "COMPLETED"
                if planned > 1:
                    reason = disposition
            elif reason is not None and reason.startswith("CYCLE_NOT_RELEASED_"):
                disposition = "SAFETY_BLOCKED"
            else:
                disposition = "STOPPED"
        # The state turns ENDED only where the Site outcome is recorded.
        cycle.update(disposition=disposition, wait_reason=None)
        return outcome, reason

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

    def _unit_progress(self, unit: Mapping[str, Any]) -> dict[str, Any] | None:
        """Read-only PPU progress of this Site's latest attempt.

        Lanes run concurrently while a Batch carries one ``current_run``, so a
        reader needs each Site's own progress. It is a projection of that
        Site's run record for display only; it never judges an outcome.
        """
        attempts = unit.get("attempts") or []
        if not attempts:
            return None
        attempt = attempts[-1]
        run = self._run_of(unit["ppu_alias"], attempt)
        if run is None or run.get("site_id") != unit["site_id"]:
            return None
        job = run.get("job") if isinstance(run.get("job"), dict) else {}
        percent = job.get("progress_percent")
        return {
            "attempt": attempt.get("attempt"), "run_id": run.get("run_id"),
            "job_id": job.get("job_id"), "job_state": job.get("state"), "stage": job.get("stage"),
            "progress_percent": percent if type(percent) in (int, float) else None,
        }

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
        units = [{**unit, "attempts": [dict(a) for a in unit.get("attempts") or []],
                  "cycle": {**unit["cycle"], "remaining":
                            unit["cycle"]["planned"] - unit["cycle"]["settled"]},
                  "progress": self._unit_progress(unit)}
                 for unit in batch["units"]]
        cycles = {key: sum(unit["cycle"][key] for unit in units)
                  for key in ("planned", "settled", "pass", "fail", "retry_attempts", "remaining")}
        cycles["awaiting_continue"] = sum(
            unit["cycle"]["state"] == AWAITING_CONTINUE for unit in units)
        attempts = [attempt for unit in units for attempt in unit["attempts"]]
        outcomes = [unit.get("outcome") for unit in units]
        view = {**batch, "units": units, "attempts": attempts,
                "current_run": self._current_run(batch),
                # One Site is one IC: counted once, by its final outcome only.
                "counts": {"pass": outcomes.count("PASS"), "fail": outcomes.count("FAIL"),
                           "blocked": outcomes.count("BLOCKED"),
                           "unknown": outcomes.count("OUTCOME_UNKNOWN"),
                           "sites": len(units), "attempts": len(attempts)},
                # Cycle accounting (Manual Repeat). Same-IC Debug PASS Cycles
                # are Cycles, never distinct physical good units.
                "cycles": cycles,
                "auto_retry": "DISABLED"}
        if len(units) == 1:
            view["ppu_alias"] = units[0]["ppu_alias"]
            view["site_id"] = units[0]["site_id"]
        return view

    def _get(self, batch_id: str) -> dict[str, Any]:
        """A Batch is read by its own ID. It is owned by the Manager, not by
        a PPU, so there is no PPU to read it through (ADR 5.8)."""
        batch = self._batches.get(batch_id)
        if batch is None:
            raise ProgrammingError(404, "programming_batch_not_found",
                                   "programming batch was not found")
        return batch

    # --------------------------------------------------------------------- API
    def start_batch(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """The canonical Manager-owned entry: a Batch over a Target Set.

        A Batch carries a Manager-issued ``start_id`` (§5.1, §5.3). It is the
        sole idempotency token, and a Batch without one cannot be reconciled
        after a lost answer, so it is required.

        The alias-scoped compatibility entry retired in PR-C (§5.8): every
        consumer was migrated to this resource first, and the Manager keeps
        exactly one door into the engine rather than two sets of semantics.
        """
        from .shared_control import SharedControlError
        try:
            return self._start(body)
        except SharedControlError as exc:
            raise ProgrammingError(503, "manager_shared_control_failure", str(exc)) from exc

    def _start(self, body: Mapping[str, Any]) -> dict[str, Any]:
        if (not isinstance(body, Mapping)
                or set(body) - PLAN_KEYS - {TARGET_KEY} - POLICY_KEYS - START_KEYS
                or "operations" not in body or TARGET_KEY not in body):
            raise ProgrammingError(
                400, "invalid_request",
                "a batch requires icpn, targets, an operations list with its Programming "
                "Image, Bundle or erase range, and optional retry_limit / stop_policy")
        if "start_id" not in body:
            raise ProgrammingError(
                400, "invalid_request",
                "a Batch requires a Manager-issued start_id; obtain one first")
        targets = parse_targets(body)
        policy = parse_policy(body, site_count(targets))
        plan_body = {key: body[key] for key in body if key in PLAN_KEYS}
        start_id = body["start_id"]
        aliases = [target["ppu_alias"] for target in targets]
        # Validity first (§5.3), and all of it before any PPU is read. A Batch
        # whose specification is illegal is refused even when every PPU in it
        # happens to be unready, so an unusable Image can never be mistaken
        # for a legitimately BLOCKED Batch.
        self.workflow.validate_specification(plan_body)
        with self._lock:
            shared = self._shared_block()
            if shared is not None:
                raise ProgrammingError(503, "manager_shared_control_failure", shared)
            if (self._control_failure is not None or self.workflow._control_failure is not None
                    or self.workflow._journal_failure is not None):
                raise ProgrammingError(503, "manager_shared_control_failure",
                                       self._control_failure or self.workflow._control_failure
                                       or self.workflow._journal_failure)
            # An unknown or unauthorised Target refuses the WHOLE Batch and
            # leaves the start_id unconsumed, so the operator may correct the
            # request and resend the same token.
            for alias in aliases:
                self.workflow._require_commissioned(alias)
            # The token is an idempotency guard, never an authority, and it is
            # not issued under a PPU: every Target's own authority was checked
            # on its own just above (§5.3, §5.8). No Target Set ordering can
            # therefore make a legal start illegal.
            self.workflow.require_batch_start(start_id)
            if any(batch["outcome"] is None
                   and {t["ppu_alias"] for t in batch["targets"]} & set(aliases)
                   for batch in self._batches.values()):
                raise ProgrammingError(409, "programming_batch_in_progress",
                                       "another programming batch is in progress on this PPU")
            # Accept and journal validity before any remote readiness I/O.
            # Bounded lanes independently resolve readiness into BLOCKED or
            # proceed through the same canonical plan/Start/Run lifecycle.
            units = [{"ppu_alias": target["ppu_alias"], "site_id": site,
                      "status": "NOT_RUN", "outcome": None, "reason": None,
                      "failure_domain": None, "attempts": [],
                      "cycle": new_cycle(policy["repeat"])}
                     for target in targets for site in target["site_ids"]]
            accepted_at = _now()
            batch = {
                "schema": BATCH_SCHEMA, "batch_id": secrets.token_hex(16),
                "start_id": start_id,
                "targets": [dict(target, site_ids=list(target["site_ids"]))
                            for target in targets],
                "operations": plan_body["operations"],
                "source": _source_of(plan_body), "icpn": plan_body.get("icpn"),
                "policy": policy, "state": "running",
                "execution_status": "RUNNING", "outcome": None, "reason": None,
                "stop_requested": False, "failure_domain": None, "units": units,
                "journal_persisted": True,
                "created_at": accepted_at, "updated_at": accepted_at,
                "started_at": accepted_at, "finished_at": None,
            }
            # Admission is journalled first: from here on the start can
            # never reconcile as "not accepted". Partial admission has still
            # consumed it, so a BLOCKED Target needs a NEW start.
            self.workflow.consume_batch_start(
                start_id, batch["batch_id"], batch["targets"])
            self._batches[batch["batch_id"]] = batch
            try:
                self._persist_locked()
            except BaseException:
                del self._batches[batch["batch_id"]]
                raise
        self.spawn(lambda: self._execute(batch, plan_body))
        return self.status_batch(batch["batch_id"])

    def _shared_block(self):
        from .shared_control import shared_control_reason
        return shared_control_reason(self.shared_control_gate)

    def _platform_block(self, alias: str) -> tuple[str, str] | None:
        """Whether this PPU may be mutated at all. PPU-scoped: one verdict
        covers every Site of that PPU, and asking it once per PPU is also
        what keeps a Batch from reading the same Platform state N times."""
        if self.platform_gate is None:
            return None
        try:
            return self.platform_gate(alias)
        except ProgrammingError as exc:
            return (SHARED_CONTROL_FAILURE if exc.code == "manager_shared_control_failure"
                    else TARGET_NOT_READY), exc.code.upper()
        except Exception as exc:  # noqa: BLE001 - an unjudgeable failure is shared
            return SHARED_CONTROL_FAILURE, f"GATE_NOT_EXECUTABLE_{type(exc).__name__}"

    def _site_block(self, alias: str, site: int) -> tuple[str, str] | None:
        """Whether THIS Site is released. Site-scoped: a verdict about one
        Site is never read as a verdict about another Site of the same PPU."""
        with self._lock:
            for batch in self._batches.values():
                for unit in batch["units"]:
                    if unit["ppu_alias"] != alias or unit.get("outcome") != "OUTCOME_UNKNOWN":
                        continue
                    attempts = unit.get("attempts") or []
                    run = self._run_of(alias, attempts[-1] if attempts else None)
                    # An absent Run answer cannot clear a durable Batch unknown.
                    if run is None or not run.get("acknowledged"):
                        return TARGET_NOT_READY, "OUTCOME_UNKNOWN_UNRESOLVED"
            # This coordinator admits at most one active Batch per PPU.
            # Carry its exact owner across readiness I/O: a healthy peer may
            # acquire the lease while this Site's HTTP response is delayed.
            owner = next((batch["batch_id"] for batch in self._batches.values()
                          if batch["outcome"] is None and any(
                              t["ppu_alias"] == alias for t in batch["targets"])), None)
        try:
            return self.workflow.target_block(alias, site, execution_owner_id=owner)
        except ProgrammingError as exc:
            return (SHARED_CONTROL_FAILURE if exc.code == "manager_shared_control_failure"
                    else TARGET_NOT_READY), exc.code.upper()
        except Exception as exc:  # noqa: BLE001 - an unjudgeable failure is shared
            return SHARED_CONTROL_FAILURE, f"GATE_NOT_EXECUTABLE_{type(exc).__name__}"

    def _admission_block(self, alias: str, site: int) -> tuple[str, str] | None:
        """Both gates for ONE Site, as the executor asks them immediately
        before operating that Site.

        The Platform gate proves the PPU is safe to mutate at all; the Target
        gate proves this Site is released. Either one blocks this Target alone
        - unless what failed is the Manager's own shared control, which stops
        the Batch instead.

        An exception escaping either gate is NOT assumed to be local. Both
        classify every PPU-scoped failure themselves, so anything left is a
        failure of the machinery that was meant to judge, and the only safe
        reading of "I could not tell" is to stop submitting.
        """
        platform = self._platform_block(alias)
        return platform if platform is not None else self._site_block(alias, site)

    def reconcile_start(self, start_id: str) -> dict[str, Any]:
        """Read-only: what became of the Start that carried ``start_id``."""
        def find_batch(wanted: str) -> dict[str, Any] | None:
            with self._lock:
                for batch in self._batches.values():
                    if batch.get("start_id") == wanted:
                        return self._view(batch)
            return None
        return self.workflow.reconcile_start(start_id, find_batch)

    def status_batch(self, batch_id: str) -> dict[str, Any]:
        with self._lock:
            return {"ok": True, "batch": self._view(self._get(batch_id))}

    def request_stop_batch(self, batch_id: str,
                           body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Stop queuing. Never cancels, resets or releases anything on the PPU."""
        if body is not None and dict(body) != {"stop": STOP_TOKEN}:
            raise ProgrammingError(400, "invalid_request",
                                   f"stop requires stop={STOP_TOKEN}")
        with self._lock:
            batch = self._get(batch_id)
            if batch["outcome"] is None and not batch["stop_requested"]:
                batch["stop_requested"] = True
                batch["updated_at"] = _now()
                self._persist_locked()
            return {"ok": True, "batch": self._view(batch)}

    def continue_site(self, batch_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """The operator's Continue for ONE paused Site lane (Manual Repeat).

        It is the existing Start action: it attests the IC was replaced (or a
        FAIL reviewed) and nothing else. It never rewrites a FAIL, UNKNOWN or
        SAFE_OFF result and never submits a Job itself - the lane does, after
        the same dispatch and admission gates as every other attempt.

        ``continue_seq`` is the pause the operator saw. Repeating an accepted
        one is answered idempotently and changes nothing; any other value is
        stale and refused, so a double click, a reloaded tab or an old tab can
        never dispatch a second Cycle.
        """
        if (not isinstance(body, Mapping) or not CONTINUE_KEYS <= set(body)
                or set(body) - CONTINUE_KEYS - {ACTOR_KEY}):
            raise ProgrammingError(400, "invalid_request",
                                   "continue requires ppu_alias, site_id and continue_seq")
        alias, site, seq = body["ppu_alias"], body["site_id"], body["continue_seq"]
        actor = body.get(ACTOR_KEY, "manager-api")
        if (type(alias) is not str or type(site) is not int or isinstance(site, bool)
                or type(seq) is not int or isinstance(seq, bool) or seq < 1
                or type(actor) is not str or not 0 < len(actor) <= 128
                or not actor.isprintable()):
            raise ProgrammingError(400, "invalid_request",
                                   "continue fields are invalid")
        with self._lock:
            batch = self._get(batch_id)
            unit = next((u for u in batch["units"]
                         if u["ppu_alias"] == alias and u["site_id"] == site), None)
            if unit is None:
                raise ProgrammingError(404, "programming_batch_site_not_found",
                                       "this Batch does not cover that PPU Site")
            cycle = unit["cycle"]
            if seq == cycle["continued_seq"]:
                # Already accepted: the same action, answered again.
                return {"ok": True, "duplicate": True, "batch": self._view(batch)}
            if (batch["outcome"] is not None or cycle["state"] != AWAITING_CONTINUE
                    or seq != cycle["continue_seq"]):
                raise ProgrammingError(409, "programming_continue_stale",
                                       "this Site is not waiting for that Continue; reload "
                                       "the Batch - nothing was started")
            if batch["stop_requested"]:
                raise ProgrammingError(409, "programming_batch_stopping",
                                       "Stop Queuing was requested; nothing was started")
            failure = (self._shared_block() or self._control_failure
                       or self.workflow._control_failure or self.workflow._journal_failure)
            if failure is not None:
                raise ProgrammingError(503, "manager_shared_control_failure", failure)
            last = cycle["last"] or {}
            event = {"type": "continue", "batch_id": batch_id, "ppu_alias": alias,
                     "site_id": site, "continue_seq": seq, "actor": actor, "at": _now(),
                     "wait_reason": cycle["wait_reason"],
                     "after_cycle_index": last.get("cycle_index"),
                     "after_cycle_id": last.get("cycle_id"),
                     "after_outcome": last.get("outcome")}
            # Intent is durable before the lane may act on it. A journal that
            # cannot take it refuses the Continue; nothing is started.
            previous = (cycle["continued_seq"], cycle["last_continue"])
            try:
                self._ledger_append_locked(batch_id, event)
                cycle.update(continued_seq=seq, last_continue=event)
                batch["updated_at"] = _now()
                self._persist_locked()
            except Exception as exc:  # noqa: BLE001 - reported as a refusal
                cycle["continued_seq"], cycle["last_continue"] = previous
                raise ProgrammingError(503, "manager_shared_control_failure",
                                       self._control_failure
                                       or f"BATCH_JOURNAL_{type(exc).__name__}") from exc
            return {"ok": True, "duplicate": False, "batch": self._view(batch)}

    def cycle_records(self, batch_id: str, offset: int = 0, limit: int = 100) -> dict[str, Any]:
        """Read-only page of a Batch's settled Cycles and Continue events."""
        if not 0 <= offset or not 1 <= limit <= 1000:
            raise ProgrammingError(400, "invalid_request",
                                   "offset must be >= 0 and limit 1..1000")
        with self._lock:
            self._get(batch_id)
            records = self._ledger_records(batch_id)
        return {"ok": True, "batch_id": batch_id, "total": len(records),
                "offset": offset, "records": records[offset:offset + limit]}

    # ---------------------------------------------------------------- execution
    def _execute(self, batch: dict[str, Any], plan_body: Mapping[str, Any]) -> None:
        try:
            self._run_units(batch, plan_body)
        except _SharedControlFailure as exc:
            self._shared_failure(batch, str(exc))
        except Exception as exc:  # noqa: BLE001 - never retried, never a guessed result
            # The machinery that judges Targets failed, not a Target. One PPU
            # being unready is isolated; being unable to tell is not (§5.7).
            self._shared_failure(batch, f"BATCH_UNEXPECTED_{type(exc).__name__}")

    def _shared_failure(self, batch: dict[str, Any], reason: str) -> None:
        """The Manager's shared safety control failed, not a Target.

        Nothing further is submitted for ANY PPU and no retry is started.
        Evidence already earned is kept as it stands: a Site whose Job may
        have reached a PPU keeps ``OUTCOME_UNKNOWN`` and is never resent, and
        a Site that was provably never submitted is left unexecuted rather
        than guessed into a failure it did not have.
        """
        with self._lock:
            self._control_failure = reason
            with self.workflow._lock:
                self.workflow._control_failure = reason
            batch["failure_domain"] = SHARED_CONTROL_FAILURE
        for unit in batch["units"]:
            if unit["outcome"] is not None:
                continue
            attempts = unit.get("attempts") or []
            last = attempts[-1] if attempts else None
            run = self._run_of(unit["ppu_alias"], last)
            if run is not None:
                try:
                    while run.get("outcome") is None:
                        self.sleep(self.poll_interval_s)
                        run = self.workflow.run_status(unit["ppu_alias"], run["run_id"])["run"]
                except Exception:
                    run = None
            with self._lock:
                cycle = unit["cycle"]
                if cycle["state"] == AWAITING_CONTINUE:
                    outcome = None  # paused between Cycles: nothing in flight
                elif run is not None:
                    self._record_attempt(last, run)
                    outcome = run["outcome"]
                    if (run.get("reason") == "manager_shared_control_failure"
                            and not run.get("job_submission_count")):
                        outcome = None
                else:
                    possible = last is not None and last.get("state") not in ("planned", "finished")
                    outcome = "OUTCOME_UNKNOWN" if possible else None
                if outcome in ("PASS", "FAIL"):
                    try:
                        self._settle_cycle(batch, unit, outcome, run.get("reason"), run,
                                           persist=False)
                    except Exception:  # noqa: BLE001 - the final write reports it
                        cycle["ledger_incomplete"] = True
                    if cycle["settled"] < cycle["planned"]:
                        outcome = None
                elif outcome == "BLOCKED" and cycle["settled"]:
                    outcome = None
                outcome, _why = self._conclude(unit, outcome, None)
                cycle["state"] = "ENDED"
                unit.update(status=_unit_status(outcome, stopped=outcome is None),
                            outcome=outcome, reason=f"SHARED_CONTROL_FAILURE_{reason}",
                            failure_domain=SHARED_CONTROL_FAILURE)
        self._finish(batch, f"SHARED_CONTROL_FAILURE_{reason}")

    @staticmethod
    def _terminal_time(batch: Mapping[str, Any]) -> str | None:
        # Recovery terminalizes NOW, not at an imagined last Job completion.
        # A wall-clock correction must never produce a negative duration.
        if batch.get("finished_at") is not None:
            return batch["finished_at"]
        try:
            start = datetime.fromisoformat(batch["started_at"])
            if start.utcoffset() is None:
                return None
        except (KeyError, TypeError, ValueError):
            return None
        return max(datetime.now(timezone.utc), start).astimezone(timezone.utc).isoformat()

    def _finish(self, batch: dict[str, Any], reason: str | None) -> None:
        outcome = aggregate_outcome(batch["units"])
        changes = {
            "state": "finished", "outcome": outcome,
            "finished_at": self._terminal_time(batch),
            "execution_status": "STOPPED" if batch["stop_requested"] else "COMPLETED",
            "reason": batch_reason(batch["units"], outcome, reason),
        }
        try:
            self._update(batch, **changes)
        except Exception:  # noqa: BLE001 - a failed journal is reported, not hidden
            self._control_failure = "BATCH_FINAL_JOURNAL_UNAVAILABLE"
            # The end of this Batch could not be recorded. Nothing further is
            # submitted either way, and the Batch says plainly that its final
            # state is not durable rather than implying it was stored.
            with self._lock:
                batch.update(changes, journal_persisted=False, updated_at=_now())

    def _skip(self, batch: dict[str, Any], unit: dict[str, Any], status: str,
              reason: str, outcome: str | None = None, domain: str | None = None) -> None:
        with self._lock:
            unit.update(status=status, outcome=outcome, reason=reason,
                        failure_domain=domain)
            batch["updated_at"] = _now()
            self._persist_locked()

    def _dispatch_block(self, batch: Mapping[str, Any], alias: str) -> str | None:
        """Called with the journal lock at every new attempt boundary."""
        shared = self._shared_block()
        if shared is not None:
            self._control_failure = shared
        if self.workflow._control_failure is not None:
            self._control_failure = self.workflow._control_failure
        if self.workflow._journal_failure is not None:
            self._control_failure = self.workflow._journal_failure
        if self._control_failure is not None:
            with self.workflow._lock:
                self.workflow._control_failure = self._control_failure
            raise _SharedControlFailure(self._control_failure)
        if batch["stop_requested"]:
            return "STOP_REQUESTED_NOTHING_SUBMITTED"
        for unit in batch["units"]:
            if unit["ppu_alias"] == alias and unit.get("outcome") == "OUTCOME_UNKNOWN":
                return f"PPU_LATCHED_{unit.get('reason') or 'OUTCOME_UNKNOWN'}"
        stop = batch["policy"]["stop_policy"]
        if (stop["kind"] == "failed_sites" and
                sum(map(_site_failed, batch["units"])) >= stop["threshold"]):
            return "STOP_POLICY_FAILED_SITES_THRESHOLD_REACHED"
        return None

    def _run_units(self, batch: dict[str, Any], plan_body: Mapping[str, Any]) -> None:
        """One bounded host worker per admitted lane, using the canonical workflow.

        Target Set limits bound host scheduling, not qualified hardware capacity.
        No remote readiness/Plan/Start call holds another lane's worker.
        """
        def step(unit, lane):
            try:
                next(lane)
                return False
            except StopIteration as done:
                outcome, reason = done.value
                with self._lock:
                    if self._control_failure is not None or self.workflow._control_failure is not None:
                        raise _SharedControlFailure(self._control_failure or self.workflow._control_failure)
                    unit.update(status=_unit_status(outcome, stopped=outcome is None),
                                outcome=outcome, reason=reason)
                    unit["cycle"]["state"] = "ENDED"
                    if outcome == "BLOCKED" and unit["failure_domain"] is None:
                        unit["failure_domain"] = TARGET_NOT_READY
                    elif outcome == "OUTCOME_UNKNOWN":
                        unit["failure_domain"] = TARGET_TRANSACTION_UNKNOWN
                    batch["updated_at"] = _now()
                    self._persist_locked()
                return True

        def latch(exc):
            reason = (str(exc) if isinstance(exc, _SharedControlFailure)
                      else f"BATCH_UNEXPECTED_{type(exc).__name__}")
            with self._lock:
                self._control_failure = self._control_failure or reason
                with self.workflow._lock:
                    self.workflow._control_failure = self._control_failure
                return self._control_failure

        def advance(unit, lane):
            try:
                return step(unit, lane)
            except Exception as exc:
                # Includes terminal journal failures, not just generator errors.
                raise _SharedControlFailure(latch(exc)) from exc

        # Share only the initial PPU-wide Platform verdict. Site readiness
        # remains independent; no remote call runs under the Journal lock.
        platforms = {}
        lanes = []
        for unit in batch["units"]:
            if unit["outcome"] is not None:
                continue
            alias = unit["ppu_alias"]
            leader = alias not in platforms
            future = platforms.setdefault(alias, Future())
            lanes.append((unit, self._run_lane(
                batch, unit, plan_body, future, leader)))
        failure = None
        if lanes:
            with ThreadPoolExecutor(max_workers=len(lanes),
                                    thread_name_prefix="plasma-batch-lane") as pool:
                try:
                    pending = {pool.submit(advance, *lane): lane for lane in lanes}
                    while pending:
                        ready, _ = wait(pending, return_when=FIRST_COMPLETED)
                        for future in ready:
                            lane = pending.pop(future)
                            try:
                                finished = future.result()
                            except _SharedControlFailure as exc:
                                failure = str(exc)
                                continue
                            if not finished and failure is None:
                                pending[pool.submit(advance, *lane)] = lane
                        if pending:
                            self.sleep(self.poll_interval_s)
                except Exception as exc:
                    # Publish scheduler failures before pool shutdown waits on
                    # slow remote calls; they cannot admit further dispatches.
                    raise _SharedControlFailure(latch(exc)) from exc
        if failure is not None:
            raise _SharedControlFailure(failure)
        self._finish(batch, None)

    def _run_lane(self, batch: dict[str, Any], unit: dict[str, Any],
                  plan_body: Mapping[str, Any], platform: Future,
                  platform_leader: bool) -> Generator[
                      None, None, tuple[str | None, str | None]]:
        """Every Cycle of ONE Site lane. Returns that Site's outcome and reason.

        Each Cycle runs the existing attempt loop (fresh plan, run and Job
        per attempt). Between Cycles the lane either waits for the operator's
        Continue or, for a same-IC Debug PASS, proceeds by itself - always
        through the same dispatch and admission gates, never around them.
        """
        alias, cycle, policy = unit["ppu_alias"], unit["cycle"], batch["policy"]
        first = True
        while True:
            outcome, reason = yield from self._run_cycle(
                batch, unit, plan_body, platform, platform_leader, first)
            first = False
            if outcome in ("PASS", "FAIL"):
                attempts = unit.get("attempts") or []
                run = self._run_of(alias, attempts[-1]) if attempts else None
                self._settle_cycle(batch, unit, outcome, reason, run)
                if cycle["settled"] >= cycle["planned"]:
                    return self._conclude(unit, None, reason)
                released, why = terminal_evidence(run)
                if not released:
                    # Counted, but the Site is never released without a
                    # trusted terminal state and verified SAFE_OFF.
                    return self._conclude(unit, None, f"CYCLE_NOT_RELEASED_{why}")
                if outcome == "PASS" and not policy["replace_ic_before_next_cycle"]:
                    stopped = None   # same-IC Debug: the next Cycle needs no operator
                else:
                    stopped = yield from self._await_continue(
                        batch, unit, "REPLACE_IC" if outcome == "PASS" else "FAIL_REVIEW")
                if stopped is not None:
                    return self._conclude(unit, None, stopped)
                self._begin_next_cycle(batch, unit)
                continue
            if outcome == "BLOCKED" and cycle["settled"]:
                # The next Cycle was not submitted. It is neither failed nor
                # skipped: it waits, with its reason, for the operator.
                self._record_blocked_dispatch(batch, unit, reason)
                stopped = yield from self._await_continue(batch, unit, f"NEXT_CYCLE_{reason}")
                if stopped is not None:
                    return self._conclude(unit, None, stopped)
                continue
            return self._conclude(unit, outcome, reason)

    def _await_continue(self, batch: dict[str, Any], unit: dict[str, Any],
                        why: str) -> Generator[None, None, str | None]:
        """Pause this lane only. None: continued; else why the session ended."""
        alias, cycle = unit["ppu_alias"], unit["cycle"]
        with self._lock:
            cycle.update(state=AWAITING_CONTINUE, wait_reason=why,
                         continue_seq=cycle["continue_seq"] + 1)
            unit["status"] = AWAITING_CONTINUE
            batch["updated_at"] = _now()
            self._persist_locked()
        while True:
            with self._lock:
                block = self._dispatch_block(batch, alias)
                if block is None and cycle["continued_seq"] == cycle["continue_seq"]:
                    cycle.update(state="ACTIVE", wait_reason=None)
                    unit["status"] = "RUNNING"
                    batch["updated_at"] = _now()
                    self._persist_locked()
                    return None
            if block is not None:
                return block
            yield

    def _begin_next_cycle(self, batch: dict[str, Any], unit: dict[str, Any]) -> None:
        with self._lock:
            cycle = unit["cycle"]
            cycle.update(index=cycle["index"] + 1, cycle_id=secrets.token_hex(16))
            # The previous Cycle's attempts live in its segment record.
            unit["attempts"] = []
            batch["updated_at"] = _now()
            self._persist_locked()

    def _record_blocked_dispatch(self, batch: dict[str, Any], unit: dict[str, Any],
                                 reason: str | None) -> None:
        with self._lock:
            attempts = unit.get("attempts") or []
            if attempts:
                self._ledger_append_locked(batch["batch_id"], {
                    "type": "blocked_dispatch", "batch_id": batch["batch_id"],
                    "ppu_alias": unit["ppu_alias"], "site_id": unit["site_id"],
                    "cycle_index": unit["cycle"]["index"], "cycle_id": unit["cycle"]["cycle_id"],
                    "reason": reason, "attempts": [dict(a) for a in attempts], "at": _now()})
            unit["attempts"] = []
            batch["updated_at"] = _now()
            self._persist_locked()

    def _run_cycle(self, batch: dict[str, Any], unit: dict[str, Any],
                   plan_body: Mapping[str, Any], platform: Future,
                   platform_leader: bool, first: bool) -> Generator[
                       None, None, tuple[str | None, str | None]]:
        """Every attempt of ONE Cycle of one Site. Returns its outcome and reason."""
        alias, site, policy = unit["ppu_alias"], unit["site_id"], batch["policy"]
        site_body = {**plan_body, "site_id": site}
        plan: Mapping[str, Any] | None = None
        # The Site verdict below was read by this lane with no yield since.
        # Re-reading it immediately would ask the PPU the same question twice
        # (Asset Set + Site readiness); the Platform gate is still re-read, and
        # every later pass (after any yield, retry or planning gap) re-reads both.
        site_verdict_fresh = first
        if first:
            if platform_leader:
                platform.set_result(self._platform_block(alias))
            verdict = platform.result()
            with self._lock:
                self._dispatch_block(batch, alias)
            if verdict is None:
                verdict = self._site_block(alias, site)
            if verdict is not None:
                domain, reason = verdict
                if domain == SHARED_CONTROL_FAILURE:
                    raise _SharedControlFailure(reason)
                with self._lock:
                    unit["failure_domain"] = domain
                return "BLOCKED", f"ADMISSION_{reason}"
        for number in range(1, policy["retry_limit"] + 2):
            # Recheck after every yield, including the planning/Start gap.
            while True:
                with self._lock:
                    block = self._dispatch_block(batch, alias)
                if block is not None:
                    return ("FAIL" if number > 1 else None), block
                if site_verdict_fresh:
                    site_verdict_fresh = False
                    verdict = self._platform_block(alias)
                else:
                    verdict = self._admission_block(alias, site)
                if verdict is None:
                    break
                domain, reason = verdict
                if domain == SHARED_CONTROL_FAILURE:
                    raise _SharedControlFailure(reason)
                # An exclusive activation must finish before peer planning.
                # It is a wait, never a fabricated blocked Site or a reload.
                if reason == "RUN_IN_PROGRESS" and any(
                        u is not unit and u["ppu_alias"] == alias
                        and u["status"] == "RUNNING" and u["outcome"] is None
                        for u in batch["units"]):
                    yield
                    continue
                with self._lock:
                    unit["failure_domain"] = domain
                return ("FAIL" if number > 1 else "BLOCKED"), f"EXECUTION_{reason}"
            if plan is None:
                try:
                    plan = self.workflow.plan(alias, site_body)["plan"]
                except ProgrammingError as exc:
                    if number == 1:
                        # Nothing was submitted for this Site: provably BLOCKED.
                        return "BLOCKED", exc.code
                    # The earlier FAIL stands; the retry could not be planned.
                    return "FAIL", f"RETRY_PLAN_REFUSED_{exc.code}"
            cycle = unit["cycle"]
            attempt = {"attempt": number, "cycle_index": cycle["index"],
                       "cycle_id": cycle["cycle_id"],
                       "job_key": {"batch_id": batch["batch_id"], "ppu_alias": alias,
                                   "site_id": site, "cycle": cycle["index"],
                                   "attempt": number},
                       "plan_id": plan["plan_id"], "run_id": None,
                       "job_binding_sha256": plan["job_binding_sha256"], "job_id": None,
                       "state": "planned", "outcome": None, "reason": None,
                       "safe_off": None, "retry": None,
                       "started_at": _now(), "finished_at": None}
            with self._lock:
                block = self._dispatch_block(batch, alias)
                if block is not None:
                    return ("FAIL" if number > 1 else None), block
                unit["attempts"].append(attempt)
                unit["status"] = "RUNNING"
                batch["updated_at"] = _now()
                # Journalled BEFORE the single start of this attempt.
                self._persist_locked()
                block = self._dispatch_block(batch, alias)
                if block is not None:
                    return ("FAIL" if number > 1 else None), block
                # Once this durable boundary is crossed, a crash must never
                # treat a missing Run answer as proof that Start was unsent.
                attempt["state"] = "starting"
                self._persist_locked()
            try:
                with self._lock:
                    block = self._dispatch_block(batch, alias)
                    if block is not None:
                        attempt.update(state="finished", outcome="BLOCKED", reason=block)
                        self._persist_locked()
                        return ("FAIL" if number > 1 else None), block
                # starting is a durable dispatch reservation. StopQueuing
                # forbids subsequent reservations, never cancels committed work.
                # Release the Journal lock before Start/spawn/remote I/O.
                started = self.workflow.start(
                    alias, {"plan_id": plan["plan_id"], "confirm": "PROGRAM"},
                    execution_owner_id=batch["batch_id"])["run"]
            except ProgrammingError as exc:
                if exc.code == "manager_shared_control_failure":
                    with self._lock:
                        attempt.update(state="finished", reason=exc.code, finished_at=_now())
                    raise _SharedControlFailure(exc.code) from exc
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
                yield
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
            elif self._stop_policy_reached(batch, unit):
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

    def _stop_policy_reached(self, batch: Mapping[str, Any], unit: Mapping[str, Any]) -> bool:
        stop = batch["policy"]["stop_policy"]
        if stop["kind"] != "failed_sites":
            return False
        failed = sum(1 for other in batch["units"] if other is not unit and _site_failed(other))
        # The Site being judged has not been recorded yet; it is the one that
        # just failed, so it counts here (once, however many Cycles failed).
        return failed + 1 >= stop["threshold"]
