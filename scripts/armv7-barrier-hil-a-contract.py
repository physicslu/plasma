#!/usr/bin/env python3
"""HIL-A1 hosted-only dispatch, immutable toolchain and PR negative contracts."""
from __future__ import annotations

import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/plasma-armv7-barrier-hil-a.yml"
HOST_CI = ROOT / ".github/workflows/plasma-armv7-barrier-hil-a-contract.yml"
HOST_SCRIPT = ROOT / "scripts/armv7-barrier-hil-a1-hosted.sh"
IMAGE = ("debian:bookworm-20261005@sha256:"
         "bc49dc1918ee1a47a93e65b5e4676e8680fb754b133197b92ca52bfe6731d5f0")
SNAPSHOT = "20261005T000000Z"


class ContractError(RuntimeError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ContractError(reason)


def _events(content: str, stop: str) -> list[str]:
    _require("on:\n" in content and stop in content, "Missing workflow event boundary")
    return re.findall(
        r"(?m)^  ([a-z_]+):",
        content.split("on:\n", 1)[-1].split(stop, 1)[0],
    )


def validate(main: str, host_ci: str, hosted_script: str | None = None) -> None:
    script = hosted_script if hosted_script is not None else HOST_SCRIPT.read_text()
    _require(_events(main, "\nconcurrency:") == ["workflow_dispatch"],
             "Manual A1 must permit only workflow_dispatch")
    _require(_events(host_ci, "\npermissions:") == ["pull_request"],
             "PR contract must permit only pull_request")
    _require("runs-on: [self-hosted" not in main and "self-hosted" not in main
             and "plasma-integration" not in main and "SWPC-plasma-ci" not in main,
             "Manual A1 must have no self-hosted/SWPC runner")
    _require("self-hosted" not in host_ci and "plasma-integration" not in host_ci,
             "PR contract must have no self-hosted runner")
    jobs = re.findall(r"(?m)^  ([\w-]+):\s*$", main.split("\njobs:\n", 1)[-1])
    _require(jobs == ["hosted-cross-compile"],
             "Manual A1 must have exactly one GitHub-hosted cross-build job")
    jobs_pr = re.findall(r"(?m)^  ([\w-]+):\s*$", host_ci.split("\njobs:\n", 1)[-1])
    _require(jobs_pr == ["contract"],
             "PR CI must have only one hosted contract+build job")
    for title, text, expected in (
        ("manual", main, 1), ("PR", host_ci, 1),
    ):
        _require(text.count("runs-on: ubuntu-24.04") == expected,
                 f"{title} must use only ubuntu-24.04")
        _require("contents: read" in text and "contents: write" not in text
                 and "persist-credentials: false" in text,
                 f"{title} credentials must be read-only/nonpersistent")
        _require("actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in text,
                 f"{title} needs pinned checkout")
        _require("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text,
                 f"{title} must upload validated ELF and SHA256")
        _require("bash scripts/armv7-barrier-hil-a1-hosted.sh" in text,
                 f"{title} must use identical immutable toolchain wrapper")
        _require("if-no-files-found: error" in text,
                 f"{title} must fail on missing artifact")
        _require(text.count("runs-on:") == 1,
                 f"{title} runner cannot be extended silently")
        _require(re.search(
            r"(?m)^\s*(?:-\s+run:\s*)?(?:ssh|scp|sftp|rsync|sudo|vivado|"
            r"curl|wget|gh|eval|bash -c|python -c)\b", text,
        ) is None, f"{title} includes forbidden remote/hardware command")
    for marker in (
        "github.event_name == 'workflow_dispatch'",
        "github.repository == 'physicslu/plasma'",
        "github.ref == 'refs/heads/main'",
        "github.actor == 'physicslu'",
        'test "$GITHUB_ACTOR" = physicslu',
        'test "$GITHUB_REF" = refs/heads/main',
        'test "$RUNNER_ENVIRONMENT" = github-hosted',
        "ref: " + "$" + "{{ github.sha }}",
        "cancel-in-progress: false",
        "Z2 native execution: NOT_RUN",
    ):
        _require(marker in main, f"Manual workflow guard missing: {marker}")
    for marker in (
        "python3 scripts/armv7-barrier-hil-a-contract.py check",
        "python3 scripts/tests/test-armv7-barrier-hil-a.py",
        "bash -n scripts/armv7-barrier-hil-a1-hosted.sh",
        "SWPC, Z2 HIL, real MMIO/UIO, FPGA and DUT: NOT_RUN",
    ):
        _require(marker in host_ci, f"PR CI guard missing: {marker}")

    _require(f"readonly IMAGE='{IMAGE}'" in script,
             "Toolchain OCI image digest must be pinned exactly")
    _require(f"readonly SNAPSHOT='{SNAPSHOT}'" in script,
             "APT repository snapshot must be date-pinned")
    for marker in (
        'test "$RUNNER_ENVIRONMENT" = github-hosted',
        'test "$GITHUB_REPOSITORY" = physicslu/plasma',
        'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
        '--platform linux/amd64',
        '--cap-drop=ALL',
        '--security-opt no-new-privileges',
        'dst=/plasma,readonly',
        'https://snapshot.debian.org/archive/debian/',
        'gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf',
        'python3 /plasma/scripts/armv7-barrier-hil-a1.py build',
        '--expected-sha "$GITHUB_SHA"',
        'sha256sum',
    ):
        _require(marker in script, f"Immutable hosted wrapper missing: {marker}")
    _require(re.search(
        r"(?m)^\s*(?:ssh|scp|sftp|rsync|sudo|vivado|curl|wget|gh|eval)\b",
        script,
    ) is None, "Hosted wrapper must not contact hardware or elevate the host")


if __name__ == "__main__":
    if sys.argv[1:] != ["check"]:
        raise SystemExit("Usage: python3 scripts/armv7-barrier-hil-a-contract.py check")
    try:
        validate(WORKFLOW.read_text(), HOST_CI.read_text(), HOST_SCRIPT.read_text())
    except ContractError as exc:
        raise SystemExit(f"HIL-A1 contract FAIL: {exc}")
    print("HIL-A1 hosted immutable toolchain/PR contract: PASS; SWPC/Z2: NOT_RUN")
