#!/usr/bin/env python3
"""PLASMA Issue #981: trusted, read-only SWPC Codex bootstrap inventory.

No runner registration, credential access, sudo, network calls, HIL or device I/O.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import grp
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import stat
import subprocess
import sys

EXPECTED_REPO = "physicslu/plasma"
EXPECTED_ISSUE = 981
EXPECTED_ACTOR = "physicslu"
EXPECTED_COMMAND = "/plasma-codex preflight 981"
EXPECTED_RUNNER = "SWPC-plasma-ci"
EXPECTED_USER = "plasma-ci"
EXPECTED_HOST = "SWPC"
EXPECTED_WORKER_USER = "plasma-codex"
EXPECTED_MONITOR_GROUP = "plasma-monitor"
MONITOR_DIRECTORY = Path("/run/plasma-codex")
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/plasma-codex-swpc-preflight.yml"


def allow_event(event: dict, *, actor: str, repository: str, ref: str) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    return (
        event.get("action") == "created"
        and actor == EXPECTED_ACTOR
        and repository == EXPECTED_REPO
        and ref == "refs/heads/main"
        and (event.get("repository") or {}).get("full_name") == EXPECTED_REPO
        and (event.get("sender") or {}).get("login") == EXPECTED_ACTOR
        and (comment.get("user") or {}).get("login") == EXPECTED_ACTOR
        and issue.get("number") == EXPECTED_ISSUE
        and not issue.get("pull_request")
        and comment.get("body") == EXPECTED_COMMAND
    )


def fixture() -> dict:
    return {
        "action": "created",
        "repository": {"full_name": EXPECTED_REPO},
        "sender": {"login": EXPECTED_ACTOR},
        "issue": {"number": EXPECTED_ISSUE},
        "comment": {"user": {"login": EXPECTED_ACTOR}, "body": EXPECTED_COMMAND},
    }


def self_test() -> None:
    original = fixture()
    good = dict(actor=EXPECTED_ACTOR, repository=EXPECTED_REPO, ref="refs/heads/main")
    assert allow_event(original, **good)
    for field, wrong in (("actor", "somebody"), ("repository", "other/repo"), ("ref", "refs/heads/unsafe")):
        args = {**good, field: wrong}
        assert not allow_event(original, **args), field
    negatives = (
        ("action", "edited"), ("issue.number", 980),
        ("issue.pull_request", {"url": "https://example.com/pr"}),
        ("comment.body", EXPECTED_COMMAND + "\n"),
        ("comment.body", EXPECTED_COMMAND + " ; echo unsafe"),
        ("comment.user.login", "other"),
        ("sender.login", "other"), ("repository.full_name", "other/repo"),
    )
    for dotted, value in negatives:
        event = copy.deepcopy(original)
        target = event
        parts = dotted.split(".")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
        assert not allow_event(event, **good), dotted

    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "\n  issue_comment:\n" not in workflow, "RETIRED_ISSUE_DISPATCH_REENABLED"
    mandatory = (
        "pull_request:", "github.actor == 'physicslu'",
        "github.event.issue.number == 981",
        "github.event.comment.body == '/plasma-codex preflight 981'",
        "runs-on: [self-hosted, linux, x64, plasma-integration]",
        "needs: authorize", "ref: ${{ github.sha }}",
        "persist-credentials: false",
        "python3 scripts/plasma-codex-swpc-preflight.py event",
        "python3 scripts/plasma-codex-swpc-preflight.py inspect",
        "timeout-minutes: 10", "contents: read",
    )
    assert all(token in workflow for token in mandatory), [
        token for token in mandatory if token not in workflow
    ]
    for forbidden in ("pull_request_target:", "permissions: write-all", "secrets: inherit", "sudo "):
        assert forbidden not in workflow, forbidden
    print("SWPC Codex bootstrap preflight authorization contract PASS")


def check_event(path: Path) -> None:
    event = json.loads(path.read_text(encoding="utf-8"))
    allowed = allow_event(
        event,
        actor=os.environ.get("GITHUB_ACTOR", ""),
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        ref=os.environ.get("GITHUB_REF", ""),
    )
    if not allowed:
        raise SystemExit("SWPC Codex bootstrap preflight authorization DENIED")
    print("SWPC Codex bootstrap preflight authorization PASS")


def user_exists(name: str) -> bool:
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def group_exists(name: str) -> bool:
    try:
        grp.getgrnam(name)
        return True
    except KeyError:
        return False


def tool_check(args: list[str]) -> tuple[bool, str]:
    if not shutil.which(args[0]):
        return False, "NOT_FOUND"
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=4, check=False)
        # Do not save command stdout or stderr: could disclose environment information.
        return proc.returncode == 0, "OK" if proc.returncode == 0 else "FAILED"
    except (OSError, subprocess.TimeoutExpired):
        return False, "UNAVAILABLE"


def inspect(output: Path) -> None:
    if os.environ.get("GITHUB_REPOSITORY") != EXPECTED_REPO:
        raise SystemExit("Wrong repository")
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise SystemExit("Wrong branch")
    if os.environ.get("GITHUB_EVENT_NAME") != "issue_comment":
        raise SystemExit("Wrong event")
    if os.environ.get("RUNNER_NAME") != EXPECTED_RUNNER:
        raise SystemExit("Wrong SWPC runner: do not relabel or reuse another host")
    if socket.gethostname() != EXPECTED_HOST:
        raise SystemExit("Wrong host")
    if pwd.getpwuid(os.geteuid()).pw_name != EXPECTED_USER or os.geteuid() == 0:
        raise SystemExit("Wrong OS identity")

    codex_available = shutil.which("codex") is not None
    codex_version_ok, codex_version_status = tool_check(["codex", "--version"])
    codex_help_ok, codex_help_status = tool_check(["codex", "exec", "--help"])
    tmux_ok, tmux_status = tool_check(["tmux", "-V"])
    monitor = {"exists": False, "owner_ok": False, "group_ok": False, "mode_ok": False}
    if MONITOR_DIRECTORY.is_dir() and not MONITOR_DIRECTORY.is_symlink():
        metadata = MONITOR_DIRECTORY.stat()
        monitor = {
            "exists": True,
            "owner_ok": pwd.getpwuid(metadata.st_uid).pw_name == EXPECTED_WORKER_USER,
            "group_ok": grp.getgrgid(metadata.st_gid).gr_name == EXPECTED_MONITOR_GROUP,
            "mode_ok": stat.S_IMODE(metadata.st_mode) == 0o2770,
        }
    checks = {
        "new_worker_user_exists": user_exists(EXPECTED_WORKER_USER),
        "monitor_group_exists": group_exists(EXPECTED_MONITOR_GROUP),
        "monitor_directory": monitor,
        "codex_visible_to_existing_runner": codex_available,
        "codex_version_probe": codex_version_status,
        "codex_exec_help_probe": codex_help_status,
        "tmux_probe": tmux_status,
        "system_git_available": shutil.which("git") is not None,
        "system_timeout_available": shutil.which("timeout") is not None,
    }
    ready_to_provision = (
        checks["new_worker_user_exists"]
        and checks["monitor_group_exists"]
        and all(monitor.values())
        and tmux_ok
    )
    # The dedicated runner registration, real worker credential access, and
    # operating-system isolation cannot be established from the old CI account.
    result = {
        "schema": "plasma.codex.bootstrap.preflight.v1",
        "work_order": EXPECTED_ISSUE,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "github_sha": os.environ.get("GITHUB_SHA", ""),
        "observer": {"host": EXPECTED_HOST, "runner": EXPECTED_RUNNER, "user": EXPECTED_USER},
        "checks": checks,
        "worker_registration": "NOT_CHECKED",
        "codex_worker_authentication": "NOT_CHECKED",
        "hardware_access": "NOT_TOUCHED",
        "ready_for_unattended_pilot": False,
        "provisioning_prerequisites_present": ready_to_provision,
        "status": "READ_ONLY_INVENTORY_COMPLETED",
        "limitations": [
            "No runner-administration API or SSH access is exercised.",
            "The existing plasma-ci worker is only an observer, never a Codex task runner.",
            "Codex availability under plasma-ci does not prove availability under plasma-codex.",
            "No Z2, USB Hub, LA, FPGA, MMIO, DUT or power access was attempted.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "new_worker_user_exists": checks["new_worker_user_exists"],
        "monitor_group_exists": checks["monitor_group_exists"],
        "monitor_directory_exists": monitor["exists"],
        "codex_visible_to_existing_runner": codex_available,
        "tmux_probe": tmux_status,
        "dedicated_runner_ready": "NOT_CHECKED",
        "hardware_access": result["hardware_access"],
    }, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("operation", choices=("self-test", "event", "inspect"))
    ap.add_argument("path", nargs="?")
    ns = ap.parse_args()
    if ns.operation == "self-test":
        self_test()
    elif ns.operation == "event":
        if ns.path is None:
            ap.error("event requires a path")
        check_event(Path(ns.path))
    elif ns.operation == "inspect":
        if ns.path is None:
            ap.error("inspect requires an output path")
        inspect(Path(ns.path))


if __name__ == "__main__":
    main()
