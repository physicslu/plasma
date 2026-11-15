#!/usr/bin/env python3
"""Read-only SWPC Control Station deployment preflight.

The check is deliberately conservative: unreadable transaction evidence or an
unobservable PPU blocks a Manager restart. It does not acquire a Manager
admission lock; a PASS is a snapshot, not atomic quiescence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Blocked(Exception):
    pass


def read_journal(path: Path, schemas: set[str], field: str) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Blocked(f"{path.name}: unreadable journal") from exc
    if (not isinstance(data, dict) or data.get("schema") not in schemas
            or not isinstance(data.get(field), list)
            or any(not isinstance(item, dict) for item in data[field])):
        raise Blocked(f"{path.name}: invalid schema or records")
    return data[field]


def batch_identity(batch: dict) -> dict:
    """Match Manager's persisted *transaction* identity, not v1/v2 JSON layout.

    v1 rows store ppu_alias/site_id/attempts flat; v2 nests those under
    targets/units and adds bookkeeping, timestamps and status fields.
    A matching migrated row must not be mistaken for a conflict; a changed
    Start, Job, outcome or SAFE_OFF must always be rejected.
    """
    units = batch.get("units")
    if not isinstance(units, list) or not units:
        raise Blocked("Batch: missing or invalid Site units")
    targets = batch.get("targets")
    if targets is None:
        targets = [{"ppu_alias": batch.get("ppu_alias"),
                    "site_ids": [batch.get("site_id")]}]
    if (not isinstance(targets, list) or not targets
            or any(not isinstance(t, dict) for t in targets)):
        raise Blocked("Batch: missing or invalid Target Set")
    projected = []
    for unit in units:
        if not isinstance(unit, dict):
            raise Blocked("Batch: invalid Site unit")
        attempts = unit.get("attempts") or []
        if not isinstance(attempts, list) or any(not isinstance(a, dict) for a in attempts):
            raise Blocked("Batch: invalid Site attempts")
        projected.append({
            "ppu_alias": unit.get("ppu_alias"),
            "site_id": unit.get("site_id"),
            "outcome": unit.get("outcome"),
            "attempts": [{
                key: attempt.get(key) for key in
                ("attempt", "plan_id", "run_id", "job_id",
                 "job_binding_sha256", "outcome", "safe_off")
            } for attempt in attempts],
        })
    return {"start_id": batch.get("start_id"), "targets": targets,
            "outcome": batch.get("outcome"), "units": projected}


def check_transactions(state_dir: Path) -> dict:
    legacy = "plasma.manager.programming-batch-journal.v1"
    current = "plasma.manager.programming-batch-journal.v2"
    files = (("programming-batches.json", {legacy, current}),
             ("programming-batches.json.v2", {current}))
    batches: list[dict] = []
    seen: dict[str, dict] = {}
    # A recorded Batch necessarily has a Manager-issued Start. An absent
    # Run/Start ledger while a Batch ledger remains is not an empty system.
    if (not (state_dir / "bundle-programming-runs.json").exists()
            and any((state_dir / name).exists() for name, _ in files)):
        raise Blocked("Run/Start journal missing with Batch history")
    claimed_starts: dict[str, str] = {}
    for name, schemas in files:
        records = read_journal(state_dir / name, schemas, "batches")
        for raw in records:
            batch = dict(raw)
            # v1 has one Site and flat attempts. Never require a v2-only
            # units[] field from immutable legacy evidence.
            if "units" not in batch:
                if "site_id" not in batch or "ppu_alias" not in batch:
                    raise Blocked(f"{name}: invalid legacy Site identity")
                batch["units"] = [{
                    "ppu_alias": batch["ppu_alias"], "site_id": batch["site_id"],
                    "outcome": None if batch.get("outcome") == "STOPPED"
                               else batch.get("outcome"),
                    "attempts": batch.get("attempts", []),
                }]
                if batch.get("outcome") == "STOPPED":
                    raise Blocked(f"{name}: stopped legacy Batch requires reconciliation")
            batch_id = batch.get("batch_id")
            if not isinstance(batch_id, str) or not batch_id:
                raise Blocked(f"{name}: invalid batch identity")
            if batch_id in seen and batch_identity(seen[batch_id]) != batch_identity(batch):
                raise Blocked("conflicting Batch transaction identity between journals")
            seen[batch_id] = batch
            batches.append(batch)
            start_id = batch.get("start_id")
            if start_id is not None:
                if not isinstance(start_id, str) or not start_id:
                    raise Blocked(f"Batch {batch_id}: invalid Start identity")
                if claimed_starts.setdefault(start_id, batch_id) != batch_id:
                    raise Blocked(f"Start {start_id}: claimed by multiple Batches")
            if (batch.get("outcome") is None
                    or batch.get("outcome") == "OUTCOME_UNKNOWN"
                    or batch.get("execution_status") == "RUNNING"
                    or batch.get("state") == "running"):
                raise Blocked(f"Batch {batch_id}: unresolved/running")
            if batch.get("outcome") not in ("PASS", "FAIL", "PARTIAL", "BLOCKED"):
                raise Blocked(f"Batch {batch_id}: nonterminal or invalid outcome")
            if (batch.get("state") != "finished"
                    or batch.get("execution_status") not in
                       (None, "COMPLETED", "STOPPED")):
                raise Blocked(f"Batch {batch_id}: nonterminal or invalid execution status")
            units = batch.get("units")
            if not isinstance(units, list) or not units:
                raise Blocked(f"Batch {batch_id}: invalid units")
            for unit in units:
                if not isinstance(unit, dict):
                    raise Blocked(f"Batch {batch_id}: invalid unit")
                if unit.get("outcome") not in ("PASS", "FAIL", "BLOCKED"):
                    raise Blocked(f"Batch {batch_id}: unresolved/invalid Site outcome")
                attempts = unit.get("attempts", [])
                if not isinstance(attempts, list):
                    raise Blocked(f"Batch {batch_id}: invalid attempts")
                if any(not isinstance(attempt, dict)
                       or attempt.get("outcome") not in ("PASS", "FAIL", "BLOCKED")
                       for attempt in attempts):
                    raise Blocked(f"Batch {batch_id}: unresolved/invalid attempt")
            # The Manager's aggregation rule is a transaction invariant:
            # a claimed PASS cannot hide a FAILED or BLOCKED Site.
            outcomes = [unit["outcome"] for unit in units]
            if "FAIL" in outcomes:
                aggregate = "FAIL"
            elif all(outcome == "BLOCKED" for outcome in outcomes):
                aggregate = "BLOCKED"
            elif "BLOCKED" in outcomes:
                aggregate = "PARTIAL"
            else:
                aggregate = "PASS"
            if batch["outcome"] != aggregate:
                raise Blocked(f"Batch {batch_id}: aggregate/Site outcomes disagree")
    data = state_dir / "bundle-programming-runs.json"
    runs = read_journal(data, {"plasma.manager.bundle-programming-journal.v1"}, "runs")
    # Acknowledgement is explicit on the run; a consumed Start is not itself
    # proof that a Job is still running, so do not invent a deployment blocker.
    for run in runs:
        ident = run.get("run_id")
        if run.get("outcome") not in ("PASS", "FAIL", "BLOCKED", "OUTCOME_UNKNOWN"):
            raise Blocked(f"Run {ident}: outcome not terminal or invalid")
        if run.get("state") not in (None, "finished"):
            raise Blocked(f"Run {ident}: state not terminal")
        if run.get("outcome") == "OUTCOME_UNKNOWN" and run.get("acknowledged") is not True:
            raise Blocked(f"Run {ident}: outcome unknown/unacknowledged")
    starts = (read_journal(data, {"plasma.manager.bundle-programming-journal.v1"},
                           "starts") if data.exists() else [])
    return {"batches": len(seen), "runs": len(runs), "starts": starts, "batch_records": seen,
            "run_records": runs}


def check_start_reconciliation(journal: dict, manager_url: str) -> int:
    """Fail closed if Start admission cannot be accounted for without any writes.

    CONSUMED must identify an existing completed Batch or Run. ISSUED is
    allowed only when Manager's read-only reconciliation proves NOT_ACCEPTED;
    an older never-admitted Start must not block deployments indefinitely.
    """
    starts = journal["starts"]
    batches = journal["batch_records"]
    runs = journal["run_records"]
    known = set()
    for start in starts:
        start_id = start.get("start_id")
        kind = start.get("kind")
        state = start.get("state")
        if (not isinstance(start_id, str) or len(start_id) != 32
                or any(c not in "0123456789abcdef" for c in start_id)
                or start_id in known or kind not in ("run", "batch")
                or state not in ("ISSUED", "CONSUMED", "VOIDED")):
            raise Blocked("Start journal: duplicate/invalid identity or state")
        known.add(start_id)
        matched_batches = [b for b in batches.values() if b.get("start_id") == start_id]
        matched_runs = [r for r in runs if isinstance(r.get("plan"), dict)
                        and r["plan"].get("plan_id") == start_id]
        if len(matched_batches) + len(matched_runs) > 1:
            raise Blocked(f"Start {start_id}: conflicting transaction records")
        if state == "CONSUMED":
            if kind == "batch":
                ident = start.get("batch_id")
                if (not isinstance(ident, str) or ident not in batches
                        or batches[ident].get("start_id") != start_id
                        or len(matched_batches) != 1 or matched_runs):
                    raise Blocked(f"Start {start_id}: admitted Batch record missing/mismatched")
            else:
                ident = start.get("run_id")
                if (not isinstance(ident, str) or len(matched_runs) != 1
                        or matched_runs[0].get("run_id") != ident or matched_batches):
                    raise Blocked(f"Start {start_id}: admitted Run record missing/mismatched")
        elif state == "VOIDED":
            if matched_batches or matched_runs:
                raise Blocked(f"Start {start_id}: voided Start has admitted transaction")
        else:
            if matched_batches or matched_runs:
                raise Blocked(f"Start {start_id}: issued Start has admitted transaction")
            response = http_json(manager_url.rstrip("/") + "/api/programming/starts/" + start_id)
            reconciliation = response.get("reconciliation")
            if (response.get("ok") is not True or not isinstance(reconciliation, dict)
                    or reconciliation.get("start_id") != start_id
                    or reconciliation.get("kind") != kind
                    or reconciliation.get("read_only") is not True
                    or reconciliation.get("state") != "NOT_ACCEPTED"):
                raise Blocked(f"Start {start_id}: admission not proved inactive")
    return len(starts)


def http_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=4) as response:
            if response.status != 200:
                raise Blocked("HTTP endpoint did not return 200")
            payload = json.loads(response.read(1024 * 1024))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise Blocked(f"endpoint unavailable or invalid ({type(exc).__name__})") from exc
    if not isinstance(payload, dict):
        raise Blocked("endpoint response is not an object")
    return payload


def check_runtime(manager_url: str, ppu_endpoint: str) -> dict:
    manager = http_json(manager_url.rstrip("/") + "/api/health/live")
    if manager.get("ok") is not True or manager.get("manager") != "alive":
        raise Blocked("Manager health reported failure")
    status = http_json(ppu_endpoint.rstrip("/") + "/api/status")
    ppu = status.get("ppu")
    execution = ppu.get("execution") if isinstance(ppu, dict) else None
    if not isinstance(execution, dict):
        raise Blocked("PPU execution status not observable")
    if (execution.get("busy") is not False
            or type(execution.get("active_job_count")) is not int
            or execution["active_job_count"] != 0
            or execution.get("owner_kind") is not None
            or execution.get("owner_id") is not None):
        raise Blocked("PPU has active/unknown execution owner")
    return {"manager_health": "PASS", "ppu_execution": "IDLE"}


def check(state_dir: Path, manager_url: str, ppu_endpoint: str) -> dict:
    if not state_dir.is_dir():
        raise Blocked("Control Station state directory missing")
    journal = check_transactions(state_dir)
    checked_starts = check_start_reconciliation(journal, manager_url)
    runtime = check_runtime(manager_url, ppu_endpoint)
    return {"result": "PASS",
            "journal": {"batches": journal["batches"], "runs": journal["runs"],
                        "starts": checked_starts}, **runtime,
            "admission_quiesce": "NOT_IMPLEMENTED",
            "meaning": "read-only snapshot; recheck before activation"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--manager-url", required=True)
    parser.add_argument("--ppu-endpoint", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.state_dir, args.manager_url, args.ppu_endpoint),
                         sort_keys=True))
        return 0
    except Blocked as exc:
        print(json.dumps({"result": "BLOCKED", "reason": str(exc)},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
