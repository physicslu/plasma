#!/usr/bin/env python3
"""Path 2: READ-ONLY bounded Z2 Gateway journal diagnostic.

Runs one fixed 'sudo journalctl' command over the existing pinned SWPC->Z2
SSH channel. Does not open REST POST, run OpenOCD, load FPGA or touch the DUT.
Raw journal, credentials and SSH transcript are never printed or archived.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = "plasma-web-rest-gateway"
SIGNALS = frozenset({"request_error", "security_authentication_failed"})
PATH = "/api/jobs"


class DiagnosticDenied(Exception):
    pass


def utc_window(start: str, end: str) -> tuple[str, str]:
    def parse(s: str) -> datetime:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise DiagnosticDenied("BAD_UTC_TIME") from exc
        if dt.tzinfo is None or dt.utcoffset() != timedelta():
            raise DiagnosticDenied("EXPLICIT_UTC_REQUIRED")
        return dt.astimezone(timezone.utc)
    a, b = parse(start), parse(end)
    if not timedelta(seconds=0) < b - a <= timedelta(minutes=5):
        raise DiagnosticDenied("WINDOW_TOO_WIDE_OR_INVALID")
    return a.strftime("%Y-%m-%d %H:%M:%S UTC"), b.strftime("%Y-%m-%d %H:%M:%S UTC")


def classify_gateway_log(text: str) -> dict:
    """Return a strict projection of JSON diagnostic lines; no raw logs."""
    matches: list[dict] = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (not isinstance(row, dict) or row.get("component") != COMPONENT
                or row.get("event") not in SIGNALS
                or row.get("method") != "POST"
                or row.get("path") != PATH):
            continue
        message = str(row.get("message", "")).lower()
        if "bearer authentication" in message or row["event"] == "security_authentication_failed":
            reason = "AUTHENTICATION_REQUIRED"
        elif "idempotency-key" in message:
            reason = "IDEMPOTENCY_KEY_REQUIRED"
        elif "runtime-ready" in message or "interface_not_configured" in message:
            reason = "BACKEND_NOT_READY"
        elif "ppu_busy" in message or "busy" in message:
            reason = "PPU_BUSY"
        elif "target" in message or "icpn" in message:
            reason = "TARGET_OR_PROFILE_REJECTED"
        else:
            reason = "UNCLASSIFIED_GATEWAY_REQUEST_ERROR"
        item = {
            "event": row["event"], "error_type": str(row.get("error_type", ""))[:80],
            "reason_category": reason,
        }
        matches.append(item)
    return {
        "result": "READ_ONLY_GATEWAY_JOURNAL_OBSERVATION",
        "unit": "plasma-web.service", "method": "POST", "path": PATH,
        "matches": matches[:15], "matching_event_count": len(matches),
        "no_mutations": True,
        "http_response_code_proven": False,
        "physical_flash_outcome_proven": False,
        "retry_authorized": False,
    }


def run(host: str, start: str, end: str, *, helper=None, home: Path | None = None) -> dict:
    a, b = utc_window(start, end)
    if helper is None:
        source = ROOT / "scripts/plasma_wordport_program.py"
        spec = importlib.util.spec_from_file_location("path2_existing_pinned_ssh", source)
        if spec is None or spec.loader is None:
            raise DiagnosticDenied("PINNED_SSH_HELPER_NOT_AVAILABLE")
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
    try:
        credentials, hosts = helper.z2_login_credentials(home or Path.home())
    except Exception as exc:
        raise DiagnosticDenied("ENROLLED_Z2_CREDENTIAL_UNAVAILABLE") from exc
    if credentials.get("ssh_host") != host:
        raise DiagnosticDenied("ENROLLED_HOST_MISMATCH")
    command = [
        "journalctl", "--no-pager", "--utc", "--output=cat",
        "-u", "plasma-web.service", "--since", a, "--until", b,
    ]
    try:
        rc, output = helper.password_ssh_z2(command, credentials, hosts, timeout=45)
    except Exception as exc:
        raise DiagnosticDenied("Z2_JOURNAL_READ_UNAVAILABLE") from exc
    if rc != 0:
        raise DiagnosticDenied("Z2_JOURNAL_READ_DENIED")
    receipt = classify_gateway_log(output)
    receipt.update({"window_start": start, "window_end": end, "ssh_host_matched_enrollment": True})
    return receipt


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", required=True)
    p.add_argument("--from-utc", required=True)
    p.add_argument("--to-utc", required=True)
    args = p.parse_args(argv)
    try:
        receipt = run(args.host, args.from_utc, args.to_utc)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except DiagnosticDenied as exc:
        print(json.dumps({"result": "NOT_RUN", "reason": str(exc), "no_mutations": True}),
              file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
