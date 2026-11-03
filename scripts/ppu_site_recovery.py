#!/usr/bin/env python3
"""Stage C Seal Operator Recovery (root CLI on the PPU; NOT an IPC operation).

A Site seal (``<state>/seals/site<N>.sealed``) is never cleared by a Worker
restart, a session end or any Package request. This explicit, operator-run
procedure is the ONLY way back, and only when every precondition is proven:

  1. the seal marker exists and is well-formed;
  2. the Site Worker service is NOT running (no in-memory owner of the seal);
  3. the Runtime reports no active execution lease (or the Runtime is down);
  4. no OpenOCD process and no Site admission record (single owner absent);
  5. the Hardware Adapter re-verifies SAFE_OFF for that Site.

FPGA Image lifecycle is owned by the PPU Loader, never by Site recovery.

Every attempt writes a root-private evidence record. On success the marker is
MOVED into the evidence directory (never deleted); on any failure the Site
stays sealed. ``diagnose`` runs checks 1-5 only and changes nothing.

usage: ppu_site_recovery.py diagnose <site> | recover <site> --operator <name>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

EVIDENCE_SCHEMA = "plasma.ppu.site-seal-recovery.v1"


def _marker(seal_dir: Path, site: int) -> tuple[Path, dict | None]:
    path = seal_dir / f"site{site}.sealed"
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return path, None
    except (OSError, ValueError):
        return path, {"unparseable": True}
    return path, data if isinstance(data, dict) else {"unparseable": True}


def checks(site: int, *, adapter, seal_dir: Path, worker_active: Callable[[], bool | None],
           runtime_lease: Callable[[], str]) -> dict[str, Any]:
    """Read-only precondition matrix. Values: PASS / FAIL / UNKNOWN."""
    path, marker = _marker(seal_dir, site)
    out: dict[str, Any] = {"site": site, "marker_path": str(path), "marker": marker}
    out["seal_present"] = ("PASS" if marker and not marker.get("unparseable") and marker.get("site") == site
                           else "FAIL")
    out["site_supported"] = "PASS" if site in adapter.supported_sites else "FAIL"
    active = worker_active()
    out["worker_stopped"] = "PASS" if active is False else "FAIL" if active else "UNKNOWN"
    lease = runtime_lease()
    out["no_active_job"] = "PASS" if lease in ("idle", "runtime_down") else (
        "FAIL" if lease == "busy" else "UNKNOWN")
    out["runtime_lease"] = lease
    try:
        leftover = adapter.startup_sealed_sites()
        out["no_external_owner"] = "FAIL" if site in leftover else "PASS"
    except Exception as exc:
        out["no_external_owner"] = "UNKNOWN"
        out["owner_error"] = type(exc).__name__
    keys = ("seal_present", "site_supported", "worker_stopped", "no_active_job",
            "no_external_owner")
    out["preconditions"] = "PASS" if all(out[k] == "PASS" for k in keys) else "BLOCKED"
    return out


def _write_evidence(evidence_dir: Path, site: int, outcome: str, payload: Mapping[str, Any]) -> Path:
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = evidence_dir / f"{stamp}-site{site}-{outcome}.json"
    n = 0
    while os.path.lexists(path):
        n += 1
        path = evidence_dir / f"{stamp}-site{site}-{outcome}-{n}.json"
    raw = json.dumps({"schema": EVIDENCE_SCHEMA, "outcome": outcome, **payload},
                     sort_keys=True, indent=1).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def recover(site: int, *, operator: str, adapter, seal_dir: Path, evidence_dir: Path,
            worker_active: Callable[[], bool | None], runtime_lease: Callable[[], str],
            timeout_s: float = 60.0) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", operator or ""):
        raise SystemExit("OPERATOR_NAME_REQUIRED")
    pre = checks(site, adapter=adapter, seal_dir=seal_dir, worker_active=worker_active,
                 runtime_lease=runtime_lease)
    record: dict[str, Any] = {"operator": operator, "time": time.time(), "checks": pre}
    if pre["preconditions"] != "PASS":
        record["result"] = "DENIED_STILL_SEALED"
        record["evidence"] = str(_write_evidence(evidence_dir, site, "denied", record))
        return record
    try:
        verify = dict(adapter.verify_safe_off(site, deadline=time.monotonic() + timeout_s))
    except Exception as exc:  # TransportDenied / TransportUnknown / anything: stay sealed
        record.update(result="DENIED_STILL_SEALED", safe_off="FAIL",
                      error=getattr(exc, "code", type(exc).__name__))
        record["evidence"] = str(_write_evidence(evidence_dir, site, "denied", record))
        return record
    # Re-check after the hardware step: nothing may have changed meanwhile.
    post = checks(site, adapter=adapter, seal_dir=seal_dir, worker_active=worker_active,
                  runtime_lease=runtime_lease)
    record.update(safe_off=verify, post_checks=post)
    if post["preconditions"] != "PASS":
        record["result"] = "DENIED_STILL_SEALED"
        record["evidence"] = str(_write_evidence(evidence_dir, site, "denied", record))
        return record
    marker_path = Path(pre["marker_path"])
    marker_sha = hashlib.sha256(marker_path.read_bytes()).hexdigest()
    archived = evidence_dir / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-site{site}.sealed"
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.rename(marker_path, archived)      # moved, never deleted
    record.update(result="RECOVERED", marker_sha256=marker_sha, archived_marker=str(archived))
    record["evidence"] = str(_write_evidence(evidence_dir, site, "recovered", record))
    return record


def main(argv: list[str]) -> int:  # pragma: no cover - thin production wiring
    import subprocess
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ppu_site_worker as worker
    from ppu_site_adapter_abi5 import Abi5OpenocdAdapter
    import ppu_site_worker_service as svc

    if os.geteuid() != 0:
        print("SITE_RECOVERY_REQUIRES_ROOT", file=sys.stderr)
        return 77
    if len(argv) < 2 or argv[0] not in ("diagnose", "recover") or argv[1] not in ("1", "2"):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 64
    site = int(argv[1])
    adapter = Abi5OpenocdAdapter(openocd_root=svc.OPENOCD_ROOT, python=svc.PYTHON)

    def worker_active() -> bool | None:
        r = subprocess.run(["systemctl", "is-active", "plasma-site-worker.service"],
                           capture_output=True, text=True)
        state = r.stdout.strip()
        return False if state in ("inactive", "failed") else True if state == "active" else None

    def runtime_lease() -> str:
        r = subprocess.run(["systemctl", "is-active", "plasma-server.service"], capture_output=True, text=True)
        if r.stdout.strip() in ("inactive", "failed"):
            return "runtime_down"
        snap = worker.runtime_lease_snapshot(svc.RUNTIME_CONTROL)
        return "unknown" if snap is None else "busy" if snap.get("busy") else "idle"

    common = dict(adapter=adapter, seal_dir=svc.STATE / "seals", worker_active=worker_active,
                  runtime_lease=runtime_lease)
    if argv[0] == "diagnose":
        out = checks(site, **common)
    else:
        if len(argv) != 4 or argv[2] != "--operator":
            print("recover requires --operator <name>", file=sys.stderr)
            return 64
        out = recover(site, operator=argv[3], evidence_dir=svc.STATE / "recovery", **common)
    print(json.dumps(out, sort_keys=True, indent=1))
    return 0 if out.get("preconditions") == "PASS" or out.get("result") == "RECOVERED" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
