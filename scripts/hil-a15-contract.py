#!/usr/bin/env python3
"""Static fail-closed HIL-A1.5 PR-only QEMU and frozen-artifact gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/plasma-hil-a15-armv7-qemu.yml"
HOSTED = ROOT / "scripts/hil-a15-gh-hosted-qemu.sh"
PROBE = ROOT / "scripts/hil-a15-armv7-qemu.py"


class ContractError(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ContractError(message)


def validate(workflow: str, hosted: str, probe_text: str) -> None:
    require(re.search(r"(?m)^on:\n  pull_request:\s*$", workflow) is not None,
            "PR-only trigger required")
    event_section = workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
    require(re.findall(r"(?m)^  ([a-z_]+):", event_section) == ["pull_request"],
            "PR-only event allowlist cannot be extended")
    jobs = re.findall(r"(?m)^  ([\w-]+):\s*$", workflow.split("\njobs:\n", 1)[-1])
    require(jobs == ["qemu-contract"] and workflow.count("runs-on: ubuntu-24.04") == 1,
            "Exactly one GitHub-hosted QEMU job required")
    require(workflow.count("runs-on:") == 1 and "self-hosted" not in workflow
            and "plasma-integration" not in workflow,
            "SWPC/self-hosted jobs forbidden")
    require("contents: read" in workflow and "actions: read" in workflow
            and "contents: write" not in workflow and
            "persist-credentials: false" in workflow,
            "GitHub credentials must be read-only and nonpersistent")
    for marker in (
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        "docker/setup-qemu-action@c7c53464625b32c7a7e944ae62b3e17d2b600130",
        "docker.io/tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0",
        "repository: physicslu/plasma", "run-id: 39192248348",
        "name: plasma-armv7-hil-a1-pr-39192248348",
        "github-token: " + "$" + "{{ github.token }}",
        "bash scripts/hil-a15-gh-hosted-qemu.sh",
        "python3 scripts/hil-a15-contract.py check",
        "python3 scripts/tests/test-hil-a15-qemu.py",
        "if-no-files-found: error",
        "Persistent SWPC Z2-like QEMU: NOT_RUN",
        "Real Z2 A2, MMIO/UIO, FPGA, DUT: NOT_RUN; M1 NO-GO",
    ):
        require(marker in workflow, "Workflow missing pinned gate: " + marker)
    require(re.search(
        r"(?m)^\s*(?:-\s+run:\s*)?(?:ssh|scp|sftp|rsync|sudo|"
        r"vivado|gh|curl|wget|eval)\b", workflow,
    ) is None, "Workflow cannot invoke remote or physical tools")
    for marker in (
        'test "$RUNNER_ENVIRONMENT" = github-hosted',
        'test "$GITHUB_REPOSITORY" = physicslu/plasma',
        "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c",
        "--network none", "--cap-drop=ALL", "--read-only",
        "--security-opt no-new-privileges",
        "dst=/artifact,readonly", "dst=/probe,readonly",
        "sha256sum qemu-execution.json",
        "timeout 120s docker run", "--repetitions 1000",
        "python3 scripts/hil-a15-armv7-qemu.py verify",
    ):
        require(marker in hosted, "Hosted runner isolation missing: " + marker)
    require("--privileged" not in hosted and "--cap-add=" not in hosted
            and "docker exec" not in hosted and "docker cp" not in hosted
            and "plasma-z2like-demo-qemu" not in hosted,
            "Probe cannot access an existing container or privileged Docker")
    for marker in (
        "435e8a1e14b644396a5a14b52211bb50535176448442c08b4b55aed1a0463956",
        "4f79aea1744333bb08720aa9cbda555140523066",
        "12160282344", "39192248348",
        'FUNCTION = "plasma_mmio_dmb_sy"',
        "ctypes.CDLL", "platform.machine()", "ctypes.sizeof(ctypes.c_void_p)",
        "A1 ELF pinned digest mismatch", "manifest_file_count",
        '"real_z2_a2": "NOT_RUN"', '"m1": "NO_GO"',
    ):
        require(marker in probe_text, "Probe pinned provenance missing: " + marker)


if __name__ == "__main__":
    if sys.argv[1:] != ["check"]:
        raise SystemExit("Usage: python3 scripts/hil-a15-contract.py check")
    try:
        validate(WORKFLOW.read_text(), HOSTED.read_text(), PROBE.read_text())
    except ContractError as exc:
        raise SystemExit(f"PLASMA HIL-A1.5 source contract FAIL: {exc}")
    print("PLASMA_HIL_A15_HOSTED_CONTRACT_PASS; SWPC/Z2 NOT_RUN")
