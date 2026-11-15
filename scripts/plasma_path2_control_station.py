#!/usr/bin/env python3
"""Fixed SWPC Path 2 Control Station operator CLI adapter.

The trusted Path 2 dispatcher runs only pinned Python files under its
non-root Runner. The canonical Control Station CLI is Bash owned by gordon.
This adapter offers a bounded bridge, not a generic shell or privilege
escalation: exact source, exact owner, exact CLI, exact operations.

Deploy never bypasses the Control Station's dual read-only preflight. The
explicit maintenance confirmation is a human/Work Order prerequisite, NOT
an atomic Manager admission lock or proof that concurrent admission stopped.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import socket
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "scripts/plasmactl-local-control-station"
PREFLIGHT = ROOT / "scripts/plasma_cs_deploy_preflight.py"
# Owner-managed, known Control Station checkout. Never execute a candidate
# Bash script from the UID 998 Runner workspace as UID 1000.
OWNER_ROOT = Path("/storage/projects/plasma")
OWNER_BACKEND = OWNER_ROOT / "scripts/plasmactl-local-control-station"
GIT = "/usr/bin/git"
SUDO = "/usr/bin/sudo"
BASH = "/usr/bin/bash"
ENV = "/usr/bin/env"
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
OWNER = "gordon"
OWNER_UID = 1000
COMMANDS = ("status", "verify", "deploy")


class Blocked(Exception):
    pass


def verify_source(expected_sha: str) -> None:
    if not HEX40.fullmatch(expected_sha):
        raise Blocked("SOURCE_SHA_INVALID")
    if sys.platform != "linux" or socket.gethostname().split(".", 1)[0].casefold() != "swpc":
        raise Blocked("SWPC_LINUX_REQUIRED")
    if not BACKEND.is_file() or BACKEND.is_symlink() or not BACKEND.resolve().is_relative_to(ROOT):
        raise Blocked("CANONICAL_BACKEND_UNAVAILABLE")
    if not all(Path(p).is_file() for p in (GIT, BASH, ENV, SUDO)):
        raise Blocked("FIXED_EXECUTABLE_UNAVAILABLE")
    observed = subprocess.run(
        [GIT, "-C", str(ROOT), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    if observed.returncode or observed.stdout.strip() != expected_sha:
        raise Blocked("SOURCE_SHA_MISMATCH")
    changed = subprocess.run(
        [GIT, "-C", str(ROOT), "diff", "--quiet", "HEAD", "--"],
        capture_output=True, check=False, timeout=10,
    )
    if changed.returncode != 0:
        raise Blocked("SOURCE_DIRTY_OR_UNVERIFIED")


def guard_deploy_backend() -> None:
    """Refuse candidate source without the reviewed PR #1435 preflight hooks."""
    if not PREFLIGHT.is_file() or PREFLIGHT.is_symlink():
        raise Blocked("DEPLOY_PREFLIGHT_MISSING")
    try:
        source = BACKEND.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Blocked("DEPLOY_BACKEND_UNREADABLE") from exc
    section = source.split("deploy_profile() {", 1)
    if len(section) != 2:
        raise Blocked("DEPLOY_FUNCTION_MISSING")
    deploy = section[1].split("parse_options()", 1)[0]
    if (deploy.count("run_deployment_preflight") != 2
            or "run_deployment_preflight() {" not in source
            or "plasma_cs_deploy_preflight.py" not in source
            or "prepare_release" not in deploy
            or deploy.index("run_deployment_preflight") > deploy.index("prepare_release")):
        raise Blocked("DEPLOY_PREFLIGHT_CHECKPOINTS_MISSING")


def check_owner_deploy_source(expected_sha: str) -> None:
    """Deploy only if the operator's checkout is exactly the approved source.

    The Path 2 PR checkout may be hidden under UID 998's private runner home.
    The operator-owned checkout is a separate trust boundary; it must not be
    assumed to be identical just because the runner candidate is clean.
    """
    fixed = [SUDO, "-n", "-H", "-u", OWNER, "--", GIT, "-C", str(OWNER_ROOT)]
    try:
        observed = subprocess.run(
            [*fixed, "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if observed.returncode or observed.stdout.strip() != expected_sha:
            raise Blocked("OWNER_CHECKOUT_SHA_MISMATCH")
        clean = subprocess.run(
            [*fixed, "diff", "--quiet", "HEAD", "--"],
            capture_output=True, timeout=15, check=False,
        )
        if clean.returncode:
            raise Blocked("OWNER_CHECKOUT_DIRTY_OR_UNVERIFIED")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("OWNER_CHECKOUT_UNAVAILABLE") from exc


def exact_owner_command(operation: str) -> list[str]:
    if operation not in COMMANDS:
        raise Blocked("OPERATION_DENIED")
    # Explicit, bounded sudo under an existing owner-administered delegation.
    # This script neither writes sudoers nor changes Linux identities.
    return [
        SUDO, "-n", "-H", "-u", OWNER, "--", ENV,
        f"XDG_RUNTIME_DIR=/run/user/{OWNER_UID}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{OWNER_UID}/bus",
        BASH, str(OWNER_BACKEND), operation,
    ]


def run(operation: str, expected_sha: str, owner_maintenance_confirmed: bool = False) -> int:
    verify_source(expected_sha)
    if operation not in COMMANDS:
        raise Blocked("OPERATION_DENIED")
    if operation == "deploy":
        guard_deploy_backend()
        if not owner_maintenance_confirmed:
            raise Blocked("OWNER_MAINTENANCE_EXCLUSIVITY_NOT_CONFIRMED")
        check_owner_deploy_source(expected_sha)
        # The boolean above records an Owner decision, not a lock. The
        # canonical CLI must independently pass both live preflight snapshots.
    elif owner_maintenance_confirmed:
        raise Blocked("MAINTENANCE_FLAG_ONLY_ALLOWED_FOR_DEPLOY")
    try:
        result = subprocess.run(
            exact_owner_command(operation), cwd=ROOT,
            check=False, timeout=1700,
        )
    except (PermissionError, FileNotFoundError) as exc:
        raise Blocked("OWNER_EXECUTION_UNAVAILABLE") from exc
    except subprocess.TimeoutExpired:
        # A timed-out deploy may already have restarted Manager. Do NOT retry.
        raise Blocked("OWNER_COMMAND_TIMED_OUT_OUTCOME_UNKNOWN")
    if result.returncode != 0:
        # Never auto-retry a process that may have entered the activation step.
        raise Blocked(f"OWNER_COMMAND_NONZERO_{result.returncode}_NO_RETRY")
    print(f"PATH2_CONTROL_STATION_{operation.upper()}_COMMAND_EXIT_0")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=COMMANDS)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--owner-maintenance-confirmed", action="store_true",
                        help="Owner-attested exclusive maintenance; NOT an atomic lock")
    args = parser.parse_args(argv)
    try:
        return run(args.operation, args.source_sha, args.owner_maintenance_confirmed)
    except Blocked as exc:
        print(f"PATH2_CONTROL_STATION_BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
