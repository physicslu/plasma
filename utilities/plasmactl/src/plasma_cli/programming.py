"""Programming through the existing Manager Batch API. No second engine.

The Manager owns the Batch: Target admission, per-Site lanes, retry, stop
policy, SAFE_OFF evidence and the durable journal. This module only

1. obtains a Manager-issued ``start_id`` and submits ONE Batch carrying it;
2. records a local submission journal *before* every POST, so a lost answer
   is reconciled read-only (``GET /api/programming/starts/{id}``) instead of
   being resent;
3. observes the Batch and reports the Manager's persisted outcome;
4. Manual Repeat: submits ``repeat`` / ``replace_ic_before_next_cycle`` and,
   when a Site pauses between Cycles, returns ``EXIT_AWAITING_CONTINUE``
   instead of waiting; ``continue_sites`` sends the operator's Continue for
   explicitly named Sites only (the Manager runs every next Cycle itself).

It never resubmits, never retries a Site, never stops other Sites because one
Site failed, and never turns ``OUTCOME_UNKNOWN`` into a new attempt.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import sys
import time
import getpass
from collections.abc import Callable
from pathlib import Path

from .api import FleetError, ManagerRefused, ManagerUnknown, manager_batch, manager_call, require_id
from .targets import Target

JOURNAL_SCHEMA = "plasma.utility.program-journal.v1"
RECEIPT_SCHEMA = "plasma.utility.program.v1"
STOP_TOKEN = "STOP_QUEUING"
VOID_TOKEN = "VOID_UNSTARTED_START"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
OPERATIONS = ("erase", "program", "verify")
#: Manual Repeat: Cycles per selected Site (Manager contract, WP-02).
MAX_REPEAT = 10000
AWAITING_CONTINUE = "AWAITING_CONTINUE"

# One exit-code table for every plasmactl command.
EXIT_PASS = 0          # Manager-reported PASS, or a read/accept that succeeded
EXIT_NOT_PASS = 1      # terminal FAIL / PARTIAL / BLOCKED, or NOT_VERIFIED observation
EXIT_USAGE = 2         # invalid input or contract violation; nothing was submitted
EXIT_UNKNOWN = 3       # OUTCOME_UNKNOWN: reconcile read-only, never resend
EXIT_NOT_ACCEPTED = 4  # Manager refused, or the start provably was never admitted
EXIT_IN_PROGRESS = 5   # Batch still running (wait timeout, or reconcile pending)
EXIT_AWAITING_CONTINUE = 6  # a Repeat Site waits for `program continue` (IC replaced)

_OUTCOME_EXIT = {"PASS": EXIT_PASS, "FAIL": EXIT_NOT_PASS, "PARTIAL": EXIT_NOT_PASS,
                 "BLOCKED": EXIT_NOT_PASS, "OUTCOME_UNKNOWN": EXIT_UNKNOWN}


def _read_source(path: Path) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise FleetError(f"programming source is not readable: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SOURCE_BYTES:
        raise FleetError("programming source must be a regular non-empty file within the size limit")
    return path.read_bytes()


def parse_operations(text: str) -> list[str]:
    ops = [item.strip() for item in text.split(",")]
    if not ops or any(op not in OPERATIONS for op in ops) or len(set(ops)) != len(ops) \
            or ops != sorted(ops, key=OPERATIONS.index):
        raise FleetError("operations must be an erase,program,verify subset in that order")
    return ops


def build_request(*, icpn: str, operations: list[str], targets: tuple[Target, ...],
                  image: Path | None = None, bundle: Path | None = None,
                  address: int | None = None, length: int | None = None,
                  retry_limit: int = 0, stop_after_failed_sites: int | None = None,
                  repeat: int = 1, replace_ic: bool = True
                  ) -> tuple[dict, dict]:
    """The Batch body (without start_id) and its journal-safe description.

    Only syntax is checked here; the Manager remains the sole validator of
    Route, Profile, Image and Target authority.
    """
    if not isinstance(icpn, str) or not icpn.strip() or len(icpn) > 96:
        raise FleetError("icpn is required")
    if not targets:
        raise FleetError("at least one --target PPU:SITE[,SITE...] is required")
    if type(repeat) is not int or not 1 <= repeat <= MAX_REPEAT:
        raise FleetError(f"--repeat must be an integer from 1 to {MAX_REPEAT} (Cycles per Site)")
    body: dict = {"icpn": icpn, "operations": list(operations),
                  "targets": [{"ppu_alias": t.ppu_alias, "site_ids": list(t.site_ids)}
                              for t in targets],
                  "repeat": 1, "retry_limit": retry_limit,
                  "stop_policy": ({"kind": "never"} if stop_after_failed_sites is None else
                                  {"kind": "failed_sites", "threshold": stop_after_failed_sites})}
    if repeat > 1:
        # repeat=1 keeps the exact pre-Repeat request: one Cycle never pauses.
        body.update(repeat=repeat, replace_ic_before_next_cycle=bool(replace_ic))
    sources = [s for s in (image, bundle) if s is not None]
    takes_image = "program" in operations or "verify" in operations
    source: dict
    if takes_image:
        if len(sources) != 1 or address is not None or length is not None:
            raise FleetError("program/verify require exactly one of --image or --bundle")
        raw = _read_source(sources[0])
        key = "image_base64" if image is not None else "bundle_base64"
        body[key] = base64.b64encode(raw).decode("ascii")
        if image is not None:
            body["image_filename"] = image.name
        source = {"kind": "image" if image is not None else "bundle",
                  "name": sources[0].name, "size": len(raw),
                  "sha256": hashlib.sha256(raw).hexdigest()}
    else:
        if sources or address is None or length is None or address < 0 or length <= 0:
            raise FleetError("erase-only requires --address and --length and no image")
        body.update(address=address, length=length)
        source = {"kind": "erase-range", "address": address, "length": length}
    return body, source


class Journal:
    """Local durable record of what this CLI sent. Created exclusively."""

    def __init__(self, path: Path, data: dict):
        self.path, self.data = path, data

    @classmethod
    def create(cls, path: Path, data: dict) -> "Journal":
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise FleetError("journal already exists: this submission was already made; "
                             "use 'plasmactl program reconcile --journal' (never resend)") from None
        except OSError as exc:
            raise FleetError(f"journal cannot be created: {exc.strerror}") from None
        os.close(fd)
        journal = cls(path, data)
        journal.save()
        return journal

    @classmethod
    def load(cls, path: Path) -> "Journal":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise FleetError("journal is unreadable") from exc
        if not isinstance(data, dict) or data.get("schema") != JOURNAL_SCHEMA:
            raise FleetError("journal schema mismatch")
        return cls(path, data)

    def save(self, **changes) -> None:
        self.data.update(changes)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(self.data, stream, sort_keys=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)


def _same_targets(batch: dict, body: dict) -> bool:
    """The Manager's Batch is this request's Batch: identity and Target Set."""
    batch_id = batch.get("batch_id")
    return (isinstance(batch_id, str) and len(batch_id) == 32
            and all(c in "0123456789abcdef" for c in batch_id)
            and batch.get("targets") == body["targets"])


def _reconcile(url: str, start_id: str, timeout: float) -> dict:
    rec = manager_call(url, "GET", "/api/programming/starts/" + start_id,
                       timeout=timeout).get("reconciliation")
    if not isinstance(rec, dict) or rec.get("start_id") != start_id:
        raise FleetError("Manager reconciliation identity mismatch")
    return rec


def submit(url: str, body: dict, source: dict, journal_path: Path, *,
           timeout: float = 10.0) -> tuple[dict, int]:
    """Issue one start ID and submit exactly one Batch. Never resend."""
    journal = Journal.create(journal_path, {
        "schema": JOURNAL_SCHEMA, "manager_url": url, "icpn": body["icpn"],
        "operations": body["operations"], "targets": body["targets"], "source": source,
        "policy": {k: body[k] for k in ("repeat", "replace_ic_before_next_cycle",
                                        "retry_limit", "stop_policy") if k in body},
        "start_post_count": 1, "start_id": None, "batch_post_count": 0,
        "submission": "NOT_SUBMITTED", "batch_id": None, "reason": None})
    try:
        issued = manager_call(url, "POST", "/api/programming/starts", {"kind": "batch"},
                              timeout=timeout)
        start_id = require_id((issued.get("start") or {}).get("start_id"), "start_id")
    except (ManagerRefused, ManagerUnknown, FleetError) as exc:
        # No Batch was posted: an unheld start ID only expires.
        journal.save(submission="NOT_SUBMITTED", reason=f"START_NOT_ISSUED: {exc}")
        return _receipt(journal, None), EXIT_NOT_ACCEPTED
    journal.save(start_id=start_id, batch_post_count=1, submission="UNKNOWN")
    try:
        batch = manager_call(url, "POST", "/api/programming/batches",
                             {**body, "start_id": start_id}, timeout=timeout)["batch"]
    except ManagerRefused as exc:
        journal.save(submission="REFUSED", reason=f"{exc.code}: {exc.message}")
        return _receipt(journal, None), EXIT_NOT_ACCEPTED
    except (ManagerUnknown, KeyError):
        return _after_unknown_post(url, journal, body, timeout)
    if not isinstance(batch, dict) or batch.get("start_id") != start_id \
            or not _same_targets(batch, body):
        journal.save(reason="BATCH_IDENTITY_MISMATCH")
        return _receipt(journal, None), EXIT_UNKNOWN
    journal.save(submission="ACCEPTED", batch_id=batch["batch_id"])
    return _receipt(journal, batch), EXIT_PASS


def _after_unknown_post(url: str, journal: Journal, body: dict,
                        timeout: float) -> tuple[dict, int]:
    """A lost Batch answer: read-only reconcile; void only an unadmitted start."""
    start_id = journal.data["start_id"]
    try:
        rec = _reconcile(url, start_id, timeout)
        if rec.get("state") == "ACCEPTANCE_PENDING":
            # The Manager serializes void and admission: either the start can
            # never be admitted, or the void is refused because it was.
            journal.save(void_post_count=1)
            try:
                manager_call(url, "POST", f"/api/programming/starts/{start_id}/void",
                             {"void": VOID_TOKEN}, timeout=timeout)
            except FleetError:
                pass
            rec = _reconcile(url, start_id, timeout)
    except FleetError as exc:
        journal.save(reason=f"RECONCILE_UNAVAILABLE: {exc}")
        return _receipt(journal, None), EXIT_UNKNOWN
    state = rec.get("state")
    if state == "NOT_ACCEPTED":
        journal.save(submission="NOT_ACCEPTED", reason=rec.get("reason"))
        return _receipt(journal, None), EXIT_NOT_ACCEPTED
    batch = rec.get("batch")
    if state in ("ACCEPTED_RUNNING", "TERMINAL_CONFIRMED") and isinstance(batch, dict) \
            and _same_targets(batch, body):
        journal.save(submission="ACCEPTED", batch_id=batch["batch_id"])
        return _receipt(journal, batch), EXIT_PASS
    journal.save(reason=rec.get("reason") or "SUBMISSION_UNKNOWN_NO_RESEND")
    return _receipt(journal, None), EXIT_UNKNOWN


def _receipt(journal: Journal, batch: dict | None) -> dict:
    data = journal.data
    return {"schema": RECEIPT_SCHEMA, "journal": str(journal.path),
            "start_id": data["start_id"], "batch_id": data["batch_id"],
            "submission": data["submission"], "reason": data["reason"],
            "batch_post_count": data["batch_post_count"], "auto_retry": "DISABLED",
            "source": data["source"],
            "batch": summarize_batch(batch) if batch is not None else None}


def _repeat_of(batch: dict) -> int:
    policy = batch.get("policy") if isinstance(batch.get("policy"), dict) else {}
    repeat = policy.get("repeat", 1)
    return repeat if type(repeat) is int else 1


def awaiting_units(batch: dict) -> list[dict]:
    """Sites of a running Repeat session that wait for the operator's Continue."""
    if batch.get("outcome") is not None or batch.get("state") == "finished":
        return []
    return [u for u in batch.get("units") or [] if isinstance(u, dict)
            and isinstance(u.get("cycle"), dict) and u["cycle"].get("state") == AWAITING_CONTINUE]


def _cycle_view(cycle: dict) -> dict:
    keys = ("planned", "index", "state", "disposition", "settled", "pass", "fail",
            "retry_attempts", "remaining", "continue_seq", "continued_seq", "wait_reason")
    view = {key: cycle.get(key) for key in keys}
    last = cycle.get("last") if isinstance(cycle.get("last"), dict) else None
    if last is not None:
        receipt = last.get("receipt") if isinstance(last.get("receipt"), dict) else {}
        view["last"] = {"cycle_index": last.get("cycle_index"), "outcome": last.get("outcome"),
                        "reason": last.get("reason"), "attempts": last.get("attempts"),
                        "job_id": receipt.get("job_id"), "job_state": receipt.get("job_state"),
                        "flash_result": receipt.get("flash_result"),
                        "safe_off": receipt.get("safe_off")}
    return view


def next_steps(batch: dict) -> list[str]:
    """One explicit Continue per waiting Site: never 'continue everything'."""
    steps = [f"plasmactl program continue --batch-id {batch.get('batch_id')} "
             f"--site {u.get('ppu_alias')}:{u.get('site_id')}"
             for u in awaiting_units(batch)]
    if steps:
        steps.append(f"plasmactl program status --batch-id {batch.get('batch_id')} --wait")
    return steps


def summarize_batch(batch: dict) -> dict:
    """Projection of the Manager's own Batch record; never a second verdict."""
    units = batch.get("units") if isinstance(batch.get("units"), list) else []
    summary = {
        "batch_id": batch.get("batch_id"), "start_id": batch.get("start_id"),
        "state": batch.get("state"), "execution_status": batch.get("execution_status"),
        "outcome": batch.get("outcome"), "reason": batch.get("reason"),
        "failure_domain": batch.get("failure_domain"),
        "stop_requested": batch.get("stop_requested"),
        "journal_persisted": batch.get("journal_persisted"),
        "counts": batch.get("counts"),
        "created_at": batch.get("created_at"), "finished_at": batch.get("finished_at"),
        "sites": [{
            "ppu_alias": u.get("ppu_alias"), "site_id": u.get("site_id"),
            "status": u.get("status"), "outcome": u.get("outcome"), "reason": u.get("reason"),
            "failure_domain": u.get("failure_domain"),
            "attempts": [{k: a.get(k) for k in ("attempt", "run_id", "job_id", "outcome",
                                                 "reason", "safe_off")}
                         for a in u.get("attempts") or [] if isinstance(a, dict)],
            "progress": u.get("progress"),
        } for u in units if isinstance(u, dict)],
    }
    if _repeat_of(batch) > 1:
        # Manual Repeat only, so a one-Cycle Batch reads exactly as before.
        policy = batch.get("policy") if isinstance(batch.get("policy"), dict) else {}
        summary["repeat"] = {"repeat": _repeat_of(batch),
                             "replace_ic_before_next_cycle":
                                 policy.get("replace_ic_before_next_cycle"),
                             "cycles": batch.get("cycles")}
        for site, unit in zip(summary["sites"], (u for u in units if isinstance(u, dict))):
            if isinstance(unit.get("cycle"), dict):
                site["cycle"] = _cycle_view(unit["cycle"])
        waiting = awaiting_units(batch)
        summary["awaiting_continue"] = [
            {"ppu_alias": u.get("ppu_alias"), "site_id": u.get("site_id"),
             "continue_seq": u["cycle"].get("continue_seq"),
             "wait_reason": u["cycle"].get("wait_reason")} for u in waiting]
        summary["next"] = next_steps(batch)
    return summary


def batch_exit(batch: dict) -> int:
    if awaiting_units(batch):
        return EXIT_AWAITING_CONTINUE
    if batch.get("state") != "finished" or batch.get("outcome") is None:
        return EXIT_IN_PROGRESS
    if batch.get("outcome") == "PASS":
        return EXIT_PASS if batch_is_pass(batch) else EXIT_NOT_PASS
    return _OUTCOME_EXIT.get(batch.get("outcome"), EXIT_UNKNOWN)


def batch_is_pass(batch: dict) -> bool:
    units = batch.get("units")
    return (batch.get("state") == "finished" and batch.get("journal_persisted") is True
            and batch.get("outcome") == "PASS" and isinstance(units, list) and bool(units)
            and all(isinstance(u, dict) and u.get("outcome") == "PASS"
                    and u.get("status") == "FINISHED" for u in units))


def _progress_line(batch: dict) -> str:
    parts = []
    for unit in batch.get("units") or []:
        progress = unit.get("progress") or {}
        stage = progress.get("stage") or progress.get("job_state") or unit.get("status")
        percent = progress.get("progress_percent")
        cycle = unit.get("cycle") if isinstance(unit.get("cycle"), dict) else None
        counters = ""
        if cycle is not None and _repeat_of(batch) > 1:
            counters = (f" c{min(cycle.get('index') or 0, cycle.get('planned') or 0)}/"
                        f"{cycle.get('planned')} P{cycle.get('pass')} F{cycle.get('fail')}"
                        f" R{cycle.get('retry_attempts')}")
            if cycle.get("state") == AWAITING_CONTINUE:
                stage, percent = f"WAITING {cycle.get('wait_reason')}", None
        parts.append(f"{unit.get('ppu_alias')}:{unit.get('site_id')}{counters} "
                     f"{unit.get('outcome') or stage}"
                     + ("" if percent is None else f" {percent:.0f}%"))
    return f"[plasmactl] batch {batch.get('batch_id')} {batch.get('execution_status')}: " \
        + ", ".join(parts)


def watch(url: str, batch_id: str, *, wait_timeout: float, interval: float = 1.0,
          timeout: float = 5.0, progress: bool = True,
          clock: Callable[[], float] = time.monotonic,
          sleep: Callable[[float], None] = time.sleep) -> dict:
    """Observe until the Manager records a final outcome, a Repeat Site waits
    for the operator, or the wait ends.

    Ending the wait never stops, cancels or resubmits anything: the Batch keeps
    running in the Manager and can be observed again with ``program status``.
    A waiting Site is answered with ``program continue``, never by this loop.
    """
    deadline = clock() + wait_timeout
    last = None
    while True:
        batch = manager_batch(url, batch_id, timeout=timeout)
        line = _progress_line(batch)
        if progress and line != last:
            print(line, file=sys.stderr, flush=True)
            last = line
        if batch.get("state") == "finished" or awaiting_units(batch) or clock() >= deadline:
            return batch
        sleep(interval)


def reconcile(url: str, start_id: str, journal: Journal | None, *,
              timeout: float = 5.0) -> tuple[dict, int]:
    """Read-only Start Outcome Reconciliation. Never submits or voids."""
    rec = _reconcile(url, start_id, timeout)
    state = rec.get("state")
    batch = rec.get("batch") if isinstance(rec.get("batch"), dict) else None
    if journal is not None and batch is not None and journal.data.get("batch_id") is None:
        journal.save(submission="ACCEPTED", batch_id=batch.get("batch_id"))
    elif journal is not None and state == "NOT_ACCEPTED" and journal.data["submission"] == "UNKNOWN":
        journal.save(submission="NOT_ACCEPTED", reason=rec.get("reason"))
    code = {"NOT_ACCEPTED": EXIT_NOT_ACCEPTED, "ACCEPTANCE_PENDING": EXIT_IN_PROGRESS,
            "ACCEPTED_RUNNING": EXIT_IN_PROGRESS}.get(state, EXIT_UNKNOWN)
    if state == "TERMINAL_CONFIRMED" and batch is not None:
        code = batch_exit(batch)
    return {"schema": "plasma.utility.program-reconcile.v1", "start_id": start_id,
            "state": state, "reason": rec.get("reason"), "read_only": True,
            "auto_retry": "DISABLED",
            "batch": summarize_batch(batch) if batch is not None else None}, code


def stop_queuing(url: str, batch_id: str, *, timeout: float = 5.0) -> tuple[dict, int]:
    """Existing STOP_QUEUING: no further attempts; never cancels a running Job."""
    require_id(batch_id, "Batch ID")
    try:
        batch = manager_call(url, "POST", f"/api/programming/batches/{batch_id}/stop",
                             {"stop": STOP_TOKEN}, timeout=timeout)["batch"]
    except (ManagerUnknown, KeyError):
        return {"schema": "plasma.utility.program-stop.v1", "batch_id": batch_id,
                "stop": "OUTCOME_UNKNOWN"}, EXIT_UNKNOWN
    return {"schema": "plasma.utility.program-stop.v1", "batch_id": batch_id,
            "stop": "STOP_QUEUING_RECORDED", "batch": summarize_batch(batch)}, EXIT_PASS


def local_actor() -> str:
    """Audit label for a Continue sent from this host.

    The CLI reaches the Manager directly on its own host and holds no verified
    operator credential, so this is the local OS user, recorded as such: an
    unverified local identity, never an authenticated operator.
    """
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - no login name: fall back to the uid
        user = f"uid{os.getuid()}"
    label = "plasmactl-local:" + "".join(ch for ch in user if ch.isprintable())
    return label[:128]


def continue_sites(url: str, batch_id: str, sites: list[tuple[str, int]], *,
                   seq: int | None = None, timeout: float = 5.0) -> tuple[dict, int]:
    """The operator's Continue for explicitly named waiting Sites.

    Each named Site gets at most ONE Continue POST, echoing the pause it
    answers. A Site that is not waiting is refused here without a POST; the
    Manager remains the authority on stale or repeated pauses. A lost answer
    is reported OUTCOME_UNKNOWN and never resent: observe with ``status``.
    Only a one-Site Batch may omit ``--site``: it is unambiguous.
    """
    batch = manager_batch(url, require_id(batch_id, "Batch ID"), timeout=timeout)
    units = {(u.get("ppu_alias"), u.get("site_id")): u
             for u in batch.get("units") or [] if isinstance(u, dict)}
    if not sites:
        if len(units) != 1:
            raise FleetError("--site PPU:SITE is required: name each Site whose IC was replaced")
        sites = list(units)
    if len(set(sites)) != len(sites):
        raise FleetError("a Site is named more than once")
    if seq is not None and len(sites) != 1:
        raise FleetError("--seq answers one Site's pause: name exactly one --site")
    for key in sites:
        if key not in units:
            raise FleetError(f"Site {key[0]}:{key[1]} is not part of this Batch")
    actor = local_actor()
    results, codes = [], []
    for alias, site in sites:
        cycle = units[(alias, site)].get("cycle")
        cycle = cycle if isinstance(cycle, dict) else {}
        pause = seq if seq is not None else cycle.get("continue_seq")
        entry = {"ppu_alias": alias, "site_id": site, "continue_seq": pause,
                 "wait_reason": cycle.get("wait_reason"), "post_count": 0}
        if seq is None and cycle.get("state") != AWAITING_CONTINUE:
            entry["result"] = "NOT_AWAITING_CONTINUE"
            results.append(entry); codes.append(EXIT_NOT_ACCEPTED)
            continue
        entry["post_count"] = 1
        try:
            answer = manager_call(url, "POST", f"/api/programming/batches/{batch_id}/continue",
                                  {"ppu_alias": alias, "site_id": site, "continue_seq": pause,
                                   "actor": actor}, timeout=timeout)
        except ManagerRefused as exc:
            entry["result"] = f"REFUSED: {exc.code}"
            codes.append(EXIT_NOT_ACCEPTED)
        except (ManagerUnknown, FleetError) as exc:
            entry["result"] = f"OUTCOME_UNKNOWN: {exc} (never resent; observe with program status)"
            codes.append(EXIT_UNKNOWN)
        else:
            entry["result"] = "ALREADY_ACCEPTED" if answer.get("duplicate") else "ACCEPTED"
            if isinstance(answer.get("batch"), dict):
                batch = answer["batch"]
            codes.append(EXIT_PASS)
        results.append(entry)
    code = (EXIT_UNKNOWN if EXIT_UNKNOWN in codes
            else EXIT_NOT_ACCEPTED if EXIT_NOT_ACCEPTED in codes else EXIT_PASS)
    return {"schema": "plasma.utility.program-continue.v1", "batch_id": batch_id,
            "actor": actor, "actor_verified": False, "sites": results,
            "batch": summarize_batch(batch)}, code


def verify_batch_receipt(batch: dict, targets: tuple[Target, ...]) -> tuple[dict, bool]:
    """Inspect Manager-reported Batch results; not independent hardware HIL."""
    units = batch.get("units")
    declared = batch.get("targets")
    if not isinstance(units, list) or not isinstance(declared, list) or not units:
        raise FleetError("Manager Batch is missing canonical targets or Site units")
    declared_keys = set()
    for target in declared:
        if not isinstance(target, dict):
            raise FleetError("Manager Batch Target Set is malformed")
        alias, sites = target.get("ppu_alias"), target.get("site_ids")
        if not isinstance(alias, str) or not isinstance(sites, list):
            raise FleetError("Manager Batch Target Set is malformed")
        for site in sites:
            key = alias, site
            if type(site) is not int or site < 1 or key in declared_keys:
                raise FleetError("Manager Batch has invalid or duplicate Site targets")
            declared_keys.add(key)
    indexed = {}
    for unit in units:
        if not isinstance(unit, dict):
            raise FleetError("Manager Batch contains malformed Site units")
        alias, site = unit.get("ppu_alias"), unit.get("site_id")
        if not isinstance(alias, str) or type(site) is not int or site < 1:
            raise FleetError("Manager Batch contains invalid Site identity")
        key = alias, site
        if key in indexed:
            raise FleetError("Manager Batch contains duplicate Site units")
        indexed[key] = unit
    if set(indexed) != declared_keys:
        raise FleetError("Manager Batch Target Set and Site units disagree")
    selected = (
        [(target.ppu_alias, site_id) for target in targets for site_id in target.site_ids]
        if targets else [(u["ppu_alias"], u["site_id"]) for u in units]
    )
    if any(key not in indexed for key in selected):
        raise FleetError("Requested Site is absent from this Batch")
    projected = [
        {"ppu_alias": alias, "site_id": site,
         "status": indexed[(alias, site)].get("status"),
         "outcome": indexed[(alias, site)].get("outcome"),
         "reason": indexed[(alias, site)].get("reason"),
         "attempts": indexed[(alias, site)].get("attempts")}
        for alias, site in selected
    ]
    complete = batch_is_pass(batch)
    return {
        "schema": "plasma.utility.test-receipt.v1",
        "batch_id": batch["batch_id"],
        "batch_state": batch.get("state"),
        "batch_outcome": batch.get("outcome"),
        "manager_reported_pass": complete,
        "journal_persisted": batch.get("journal_persisted"),
        "evidence_kind": "MANAGER_REPORTED_BATCH_ONLY",
        "sites": projected,
    }, complete
