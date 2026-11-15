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


def check_transactions(state_dir: Path) -> dict:
    legacy = "plasma.manager.programming-batch-journal.v1"
    current = "plasma.manager.programming-batch-journal.v2"
    files = (("programming-batches.json", {legacy, current}),
             ("programming-batches.json.v2", {current}))
    batches: list[dict] = []
    seen: dict[str, dict] = {}
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
            if batch_id in seen and seen[batch_id] != batch:
                raise Blocked("conflicting Batch records between journals")
            seen[batch_id] = batch
            batches.append(batch)
            if (batch.get("outcome") is None
                    or batch.get("outcome") == "OUTCOME_UNKNOWN"
                    or batch.get("execution_status") == "RUNNING"
                    or batch.get("state") == "running"):
                raise Blocked(f"Batch {batch_id}: unresolved/running")
            units = batch.get("units")
            if not isinstance(units, list):
                raise Blocked(f"Batch {batch_id}: invalid units")
            for unit in units:
                if not isinstance(unit, dict):
                    raise Blocked(f"Batch {batch_id}: invalid unit")
                if unit.get("outcome") is None or unit.get("outcome") == "OUTCOME_UNKNOWN":
                    raise Blocked(f"Batch {batch_id}: unresolved Site outcome")
                attempts = unit.get("attempts", [])
                if not isinstance(attempts, list):
                    raise Blocked(f"Batch {batch_id}: invalid attempts")
                if any(not isinstance(attempt, dict) or attempt.get("outcome") is None
                       or attempt.get("outcome") == "OUTCOME_UNKNOWN"
                       for attempt in attempts):
                    raise Blocked(f"Batch {batch_id}: unresolved attempt")
    data = state_dir / "bundle-programming-runs.json"
    runs = read_journal(data, {"plasma.manager.bundle-programming-journal.v1"}, "runs")
    # Acknowledgement is explicit on the run; a consumed Start is not itself
    # proof that a Job is still running, so do not invent a deployment blocker.
    for run in runs:
        ident = run.get("run_id")
        if run.get("outcome") is None:
            raise Blocked(f"Run {ident}: outcome not terminal")
        if run.get("outcome") == "OUTCOME_UNKNOWN" and run.get("acknowledged") is not True:
            raise Blocked(f"Run {ident}: outcome unknown/unacknowledged")
    if data.exists():
        read_journal(data, {"plasma.manager.bundle-programming-journal.v1"}, "starts")
    return {"batches": len(seen), "runs": len(runs)}


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
    if manager.get("ok") is False:
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
    runtime = check_runtime(manager_url, ppu_endpoint)
    return {"result": "PASS", "journal": journal, **runtime,
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
