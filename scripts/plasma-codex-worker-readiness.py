#!/usr/bin/env python3
"""Read-only readiness checker for the dedicated SWPC Codex worker.

Does NOT authenticate, access GitHub, open serial devices or inspect secrets.
"""
from __future__ import annotations

import argparse
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

WORKER = "plasma-codex"
MONITOR_GROUP = "plasma-monitor"
OPERATOR = "gordon"
HOME = Path("/home/plasma-codex")
MONITOR = Path("/run/plasma-codex")
RUNNER = HOME / "actions-runner"
BLOCKED_GROUPS = frozenset(("sudo", "docker", "adm", "dialout", "gpio", "i2c", "video", "plasma-hil"))


def groups_safe(names: set[str]) -> bool:
    return len(names & BLOCKED_GROUPS) == 0


def mode_matches(path: Path, owner: str, group: str | None, expected_mode: int) -> bool:
    if not path.is_dir() or path.is_symlink():
        return False
    metadata = path.stat()
    try:
        user = pwd.getpwuid(metadata.st_uid).pw_name
        group_name = grp.getgrgid(metadata.st_gid).gr_name
    except KeyError:
        return False
    return (
        user == owner
        and (group is None or group_name == group)
        and stat.S_IMODE(metadata.st_mode) == expected_mode
    )


def names_for_user(name: str) -> set[str]:
    user = pwd.getpwnam(name)
    return {grp.getgrgid(group).gr_name for group in os.getgrouplist(name, user.pw_gid)}


def safe_cli_probe() -> dict:
    results: dict[str, str] = {}
    for label, cmd in (
        ("codex_version", ["codex", "--version"]),
        ("codex_exec_help", ["codex", "exec", "--help"]),
        ("tmux", ["tmux", "-V"]),
        ("timeout", ["timeout", "--version"]),
    ):
        if shutil.which(cmd[0]) is None:
            results[label] = "NOT_FOUND"
            continue
        try:
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            results[label] = "OK" if process.returncode == 0 else "FAILED"
        except (OSError, subprocess.TimeoutExpired):
            results[label] = "UNAVAILABLE"
    return results


def readiness() -> dict:
    try:
        worker_groups = names_for_user(WORKER)
        operator_groups = names_for_user(OPERATOR)
        worker = pwd.getpwnam(WORKER)
        identity = worker.pw_uid != 0 and worker.pw_dir == str(HOME) and worker.pw_shell == "/bin/bash"
    except KeyError:
        worker_groups, operator_groups = set(), set()
        identity = False

    facts = {
        "host_swpc": socket.gethostname() == "SWPC",
        "running_as_worker": pwd.getpwuid(os.geteuid()).pw_name == WORKER,
        "worker_identity_safe": identity,
        "worker_privileged_groups_absent": groups_safe(worker_groups),
        "worker_monitor_group": MONITOR_GROUP in worker_groups,
        "operator_monitor_group": MONITOR_GROUP in operator_groups,
        "worker_home_protected": mode_matches(HOME, WORKER, None, 0o700),
        "runner_directory_protected": mode_matches(RUNNER, WORKER, None, 0o700),
        "monitor_directory_protected": mode_matches(MONITOR, WORKER, MONITOR_GROUP, 0o2770),
        "runner_config_marker_present": (RUNNER / ".runner").is_file(),
    }
    tool_status = safe_cli_probe()
    # Neither the existence of a runner config marker nor CLI help proves
    # registration, authentication, isolation or that the runner is online.
    return {
        "schema": "plasma.codex.worker-readiness.v1",
        "facts": facts,
        "tool_status": tool_status,
        "prerequisites_ready": all(v for k, v in facts.items() if k != "runner_config_marker_present")
        and all(value == "OK" for value in tool_status.values()),
        "github_runner_online": "NOT_CHECKED",
        "codex_authentication": "NOT_CHECKED",
        "os_sandbox_enforcement": "NOT_CHECKED",
        "hardware_access": "NOT_TOUCHED",
        "codex_session_started": False,
    }


def self_test() -> None:
    assert groups_safe({"plasma-codex", MONITOR_GROUP})
    assert not groups_safe({"plasma-codex", "sudo"})
    assert not groups_safe({"plasma-codex", "docker"})
    assert not groups_safe({"plasma-codex", "plasma-hil"})
    assert BLOCKED_GROUPS.isdisjoint({"plasma-codex", MONITOR_GROUP})
    print("SWPC Codex worker readiness helper self-test PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    result = readiness()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for k, value in result["facts"].items():
            print(f"{k}={'PASS' if value else 'MISSING'}")
        for k, value in result["tool_status"].items():
            print(f"{k}={value}")
        print("prerequisites_ready=" + ("PASS" if result["prerequisites_ready"] else "BLOCKED"))
        print("runner_online=NOT_CHECKED codex_auth=NOT_CHECKED hardware=NOT_TOUCHED")
    # Return failure for incomplete environment to avoid accidental pilot.
    if not result["prerequisites_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
