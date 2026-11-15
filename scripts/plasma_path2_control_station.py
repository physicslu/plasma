#!/usr/bin/env python3
"""Source-pinned Path 2 Control Station read-only operator CLI adapter.

This runs only the fixed, independently owner-installed UID bridge, never
sudo bash/git/python or the operator's private service environment directly.
Deployment stays disabled until a separate reviewed fixed-bridge release
qualifies transaction history, maintenance exclusivity and rollback.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import socket
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
OWNER = "gordon"
BRIDGE = "/usr/local/libexec/plasma/plasma-control-station-owner-bridge"
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
READ_ONLY = ("status", "verify")
OPERATIONS = (*READ_ONLY, "deploy")


class Blocked(Exception):
    pass


def verify_source(source_sha: str) -> None:
    """Source SHA is the pinned Path 2 adapter, not the installed release."""
    if type(source_sha) is not str or not HEX40.fullmatch(source_sha):
        raise Blocked("ADAPTER_SOURCE_SHA_INVALID")
    if (sys.platform != "linux"
            or socket.gethostname().split(".", 1)[0].lower() != "swpc"):
        raise Blocked("SWPC_LINUX_REQUIRED")
    try:
        head = subprocess.run(
            [GIT, "-C", str(ROOT), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        dirty = subprocess.run(
            [GIT, "-C", str(ROOT), "status", "--porcelain=v1",
             "--untracked-files=all"],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("ADAPTER_SOURCE_UNAVAILABLE") from exc
    if (head.returncode != 0 or head.stdout.strip() != source_sha):
        raise Blocked("ADAPTER_SOURCE_SHA_MISMATCH")
    if dirty.returncode or dirty.stdout:
        raise Blocked("ADAPTER_WORKTREE_DIRTY")


def run(operation: str, source_sha: str, target_sha: str | None = None,
        owner_maintenance_confirmed: bool = False) -> int:
    if operation not in OPERATIONS:
        raise Blocked("OPERATION_DENIED")
    verify_source(source_sha)
    if operation == "deploy":
        # Gate 1: the installed UID bridge admits only status/verify.
        # Future deploy requires an independently audited admission barrier
        # and immutable evidence. No bypass via owner intent or target SHA.
        raise Blocked("DEPLOY_BRIDGE_NOT_QUALIFIED")
    if target_sha is not None or owner_maintenance_confirmed:
        raise Blocked("DEPLOY_ONLY_ARGUMENT_ON_READONLY_OPERATION")
    try:
        result = subprocess.run(
            [SUDO, "-n", "-H", "-u", OWNER, "--", BRIDGE, operation],
            cwd=ROOT, check=False, timeout=220,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("FIXED_OWNER_BRIDGE_UNAVAILABLE") from exc
    if result.returncode == 77:
        raise Blocked("FIXED_OWNER_BRIDGE_PERMISSION_DENIED")
    if result.returncode != 0:
        raise Blocked(f"FIXED_OWNER_BRIDGE_FAILED_{result.returncode}")
    print(f"PATH2_CONTROL_STATION_{operation.upper()}_EXIT_ZERO")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=OPERATIONS)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--target-sha", default=None)
    parser.add_argument("--owner-maintenance-confirmed", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run(args.operation, args.source_sha, args.target_sha,
                   args.owner_maintenance_confirmed)
    except Blocked as exc:
        print(f"PATH2_CONTROL_STATION_BLOCKED: {exc}", file=sys.stderr)
        return (77 if "BRIDGE" in str(exc) else 2)


if __name__ == "__main__":
    raise SystemExit(main())
