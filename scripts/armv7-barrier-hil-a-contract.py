#!/usr/bin/env python3
"""Host-only static safety gate for manual HIL-A1 SWPC Workflow."""
from __future__ import annotations

import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/plasma-armv7-barrier-hil-a.yml"
HOST_CI = ROOT / ".github/workflows/plasma-armv7-barrier-hil-a-contract.yml"


class ContractError(RuntimeError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ContractError(reason)


def validate(main: str, host_ci: str) -> None:
    _require(re.search(r"(?m)^on:\n  workflow_dispatch:\s*$", main) is not None,
             "A1 requires manual workflow_dispatch")
    events = main.split("on:\n", 1)[-1].split("\nconcurrency:", 1)[0]
    _require(re.findall(r"(?m)^  ([a-z_]+):", events) == ["workflow_dispatch"],
             "A1 cannot use PR, push, issue, or scheduled triggers")
    jobs = re.findall(r"(?m)^  ([\w-]+):\s*$", main.split("\njobs:\n", 1)[-1])
    _require(jobs == ["authorize", "swpc-cross-compile"],
             "A1 permits only hosted authorization and SWPC cross-build; no A2 job")
    _require(main.count("runs-on: ubuntu-24.04") == 1,
             "Require one hosted authorize job")
    _require(main.count("runs-on: [self-hosted, linux, x64, plasma-integration]") == 1,
             "Require exactly one SWPC A1 job")
    _require(main.count("github.actor == 'physicslu'") == 2,
             "Both jobs require approved owner actor")
    _require(main.count("github.ref == 'refs/heads/main'") == 2,
             "Both jobs require approved main")
    _require(main.count("github.event_name == 'workflow_dispatch'") == 2,
             "Both jobs require dispatch event")
    _require("needs: authorize" in main and
             "needs.authorize.result == 'success'" in main,
             "SWPC job must depend on hosted authorization")
    _require(main.count('test "$GITHUB_ACTOR" = physicslu') == 2,
             "Both shell jobs must check actor")
    markers = [
        'test "$RUNNER_NAME" = SWPC-plasma-ci',
        'test "$(hostname)" = SWPC',
        'test "$(id -un)" = plasma-ci',
        'test "$(id -u)" -ne 0',
        'test -z "$SSH_AUTH_SOCK"',
        'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
        "ref: " + "$" + "{{ github.sha }}",
        "persist-credentials: false",
        "clean: true",
        "contents: read",
        "concurrency:",
        "cancel-in-progress: false",
        "armv7-barrier-hil-a1.py build",
        '--expected-sha "$GITHUB_SHA"',
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        "Z2 native execution: NOT_RUN",
    ]
    for marker in markers:
        _require(marker in main, f"Missing SWPC guard: {marker}")
    commands = main.split("\n    steps:", 1)[-1]
    _require(re.search(
        r"(?m)^\s+(?:ssh|scp|sftp|rsync|sudo|docker|vivado|curl|wget|"
        r"gh|eval|bash -c|python -c)\b", commands,
    ) is None, "A1 contains forbidden hardware, remote or privilege command")

    _require(re.search(r"(?m)^on:\n  pull_request:\s*$", host_ci) is not None,
             "Contract CI must run on PRs")
    host_events = host_ci.split("on:\n", 1)[-1].split("\npermissions:", 1)[0]
    _require(re.findall(r"(?m)^  ([a-z_]+):", host_events) == ["pull_request"],
             "PR contract must not use manual or self-hosted dispatch")
    _require("runs-on: ubuntu-24.04" in host_ci and
             "self-hosted" not in host_ci and "plasma-integration" not in host_ci,
             "PR checks must not use a self-hosted runner")
    for marker in (
        "contents: read", "persist-credentials: false",
        "python3 scripts/armv7-barrier-hil-a-contract.py check",
        "python3 scripts/tests/test-armv7-barrier-hil-a.py",
        "bash -n",
    ):
        _require(marker in host_ci, f"Missing host check: {marker}")


if __name__ == "__main__":
    if sys.argv[1:] != ["check"]:
        raise SystemExit("Usage: python3 scripts/armv7-barrier-hil-a-contract.py check")
    try:
        validate(WORKFLOW.read_text(encoding="utf-8"),
                 HOST_CI.read_text(encoding="utf-8"))
    except ContractError as exc:
        raise SystemExit(f"HIL-A1 contract FAIL: {exc}")
    print("HIL-A1 dispatch contract: PASS; SWPC/Z2: NOT_RUN")
