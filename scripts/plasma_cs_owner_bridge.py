#!/usr/bin/python3 -I
"""Immutable, owner-installed Control Station UID delegation endpoint.

Install only by the interactive trusted SWPC administrator. Never installed
by GitHub Actions / Path 2 / Path 3. In Gate 1 this endpoint supports only
read-only status and verify; deployment is fail-closed until a separately
reviewed maintenance admission fence and legacy Start transition exist.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

INSTALLED_PATH = Path("/usr/local/libexec/plasma/plasma-control-station-owner-bridge")
OWNER_ROOT = Path("/storage/projects/plasma")
BACKEND = OWNER_ROOT / "scripts/plasmactl-local-control-station"
OWNER_UID = 1000
RUNNER_UID = 998
OWNER_LOGIN = "gordon"
RUNNER_LOGIN = "plasma-codex"
BASH = "/usr/bin/bash"


class Blocked(RuntimeError):
    pass


def require_safe_installed_bridge() -> None:
    """The *executed* file, and all writable parent paths, must be root-owned."""
    executable = Path(__file__)
    if executable != INSTALLED_PATH:
        raise Blocked("NOT_TRUSTED_INSTALLED_PATH")
    for path in [INSTALLED_PATH, INSTALLED_PATH.parent, INSTALLED_PATH.parent.parent]:
        try:
            info = path.lstat()
        except OSError as exc:
            raise Blocked("TRUSTED_BRIDGE_PATH_UNAVAILABLE") from exc
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise Blocked("TRUSTED_BRIDGE_PATH_MUTABLE")
        if path == INSTALLED_PATH and not stat.S_ISREG(info.st_mode):
            raise Blocked("TRUSTED_BRIDGE_NOT_REGULAR_FILE")
        if path != INSTALLED_PATH and not stat.S_ISDIR(info.st_mode):
            raise Blocked("TRUSTED_BRIDGE_PARENT_NOT_DIRECTORY")


def require_origin() -> None:
    """The invoker must be the approved non-root Runner, not generic sudo."""
    if sys.platform != "linux" or os.getuid() != OWNER_UID or os.geteuid() != OWNER_UID:
        raise Blocked("OPERATOR_UID_MISMATCH")
    if pwd.getpwuid(OWNER_UID).pw_name != OWNER_LOGIN:
        raise Blocked("OPERATOR_ACCOUNT_MISMATCH")
    if os.environ.get("SUDO_USER") != RUNNER_LOGIN or os.environ.get("SUDO_UID") != str(RUNNER_UID):
        raise Blocked("RUNNER_IDENTITY_NOT_PROVED")
    if not Path(f"/run/user/{OWNER_UID}/bus").exists():
        raise Blocked("OPERATOR_USER_SYSTEMD_UNAVAILABLE")


def require_owner_checkout() -> None:
    """Execution source must remain under owner-controlled, fixed root."""
    try:
        info = OWNER_ROOT.lstat()
        backend = BACKEND.lstat()
    except OSError as exc:
        raise Blocked("OWNER_CHECKOUT_UNAVAILABLE") from exc
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != OWNER_UID or info.st_mode & 0o022
            or not stat.S_ISREG(backend.st_mode) or stat.S_ISLNK(backend.st_mode)
            or backend.st_uid not in (0, OWNER_UID) or backend.st_mode & 0o022):
        raise Blocked("OWNER_CHECKOUT_UNTRUSTED")
    if not BACKEND.resolve().is_relative_to(OWNER_ROOT.resolve()):
        raise Blocked("OWNER_BACKEND_OUTSIDE_CHECKOUT")


def invoke_readonly(operation: str) -> int:
    if operation not in ("status", "verify"):
        raise Blocked("ONLY_STATUS_OR_VERIFY_ALLOWED")
    require_safe_installed_bridge()
    require_origin()
    require_owner_checkout()
    clean_env = {
        "HOME": pwd.getpwuid(OWNER_UID).pw_dir,
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "XDG_RUNTIME_DIR": f"/run/user/{OWNER_UID}",
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{OWNER_UID}/bus",
        "LANG": "C.UTF-8",
    }
    try:
        result = subprocess.run([BASH, str(BACKEND), operation], cwd=OWNER_ROOT,
                                env=clean_env, check=False, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("OWNER_READONLY_COMMAND_UNVERIFIED") from exc
    if result.returncode != 0:
        raise Blocked(f"OWNER_READONLY_COMMAND_FAILED_{result.returncode}")
    print(f"OWNER_BRIDGE_{operation.upper()}_EXIT_ZERO")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        # Gate 1: deployment denied here regardless of flags or SHA. Future
        # enablement demands a separately reviewed atomic admission barrier.
        if args == ["status"]:
            return invoke_readonly("status")
        if args == ["verify"]:
            return invoke_readonly("verify")
        raise Blocked("OPERATION_NOT_ALLOWED_UNTIL_DEPLOY_FENCE_QUALIFIED")
    except Blocked as exc:
        print(f"PLASMA_OWNER_BRIDGE_BLOCKED: {exc}", file=sys.stderr)
        return 77


if __name__ == "__main__":
    raise SystemExit(main())
