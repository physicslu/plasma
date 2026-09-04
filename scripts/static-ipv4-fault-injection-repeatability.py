#!/usr/bin/env python3
"""Run Static IPv4 fault acceptance twice in the same workspace.

This is the CI repeatability/privilege-parity gate. It deliberately performs no
workspace cleanup itself: the production-like lab runner must make its own stale
root-owned disposable workspace removable, then succeed again in the identical
work directory. Before run 1, a locked-down root producer seeds deterministic
private filesystem residue. After each run, a separate non-root verifier confirms
that the canonical PPU activation journal remains root:root 0600 and is readable
only via a locked-down read-only container.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
DEFAULT_WORK_REL = Path(".work/static-ipv4-fault-injection")
DEFAULT_REPORT_REL = Path(".work/reports/static-ipv4-fault-injection-repeatability.json")
VERIFIER_RESULT_MARKER = "PLASMA_PRIVATE_PPU_EVIDENCE_VERIFIER_RESULT="
RESULT_MARKER = "PLASMA_STATIC_IPV4_REPEATABILITY_RESULT="


class RepeatabilityError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve(repo: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo / path).resolve()


def _run_streaming(command: Sequence[str], *, cwd: Path) -> int:
    process = subprocess.Popen(list(command), cwd=cwd)
    return process.wait()


def _seed_dirty_state(work: Path) -> None:
    """Create direct root-owned residue without granting the producer capabilities.

    The host owns the disposable work root. It temporarily adds only write/execute
    for "other" so a uid-0, cap-drop-all container can create one known child
    directly under that root. The original work-root mode is restored before the
    formal fault lab starts. The resulting child is root:root 0700, so the host
    user cannot traverse or delete it until the lab's production-like cleanup
    path repairs the disposable tree.
    """
    work.mkdir(parents=True, exist_ok=True)
    original_mode = stat.S_IMODE(work.stat().st_mode)
    dirty_name = f".dirty-state-root-owned-{os.getpid()}-{time.time_ns()}"
    dirty_path = work / dirty_name
    seed = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "leaf = Path('/work') / sys.argv[1]\n"
        "leaf.mkdir(mode=0o700, exist_ok=False)\n"
        "fd = os.open(str(leaf / 'private-marker'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n"
        "try:\n"
        "    os.write(fd, b'plasma-dirty-state\\n')\n"
        "finally:\n"
        "    os.close(fd)\n"
    )
    try:
        work.chmod(original_mode | 0o003)
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/arm/v7",
                "--network",
                "none",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--user",
                "0:0",
                "--volume",
                f"{work}:/work",
                ARM_IMAGE,
                "python3",
                "-c",
                seed,
                dirty_name,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        work.chmod(original_mode)

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RepeatabilityError(f"dirty-state injection failed: {detail}")

    try:
        info = dirty_path.lstat()
    except FileNotFoundError as exc:
        raise RepeatabilityError(f"dirty-state root-owned residue missing: {dirty_path}") from exc
    mode = stat.S_IMODE(info.st_mode)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or mode != 0o700:
        raise RepeatabilityError(
            "dirty-state residue ownership/mode mismatch: "
            f"uid={info.st_uid} gid={info.st_gid} mode={mode:04o}; expected root:root 0700"
        )
    restored_mode = stat.S_IMODE(work.stat().st_mode)
    if restored_mode != original_mode:
        raise RepeatabilityError(
            f"dirty-state injection did not restore work-root mode: {restored_mode:04o} != {original_mode:04o}"
        )
    print(f"[REPEATABILITY] injected direct root:root 0700 dirty state at {dirty_path}", flush=True)


def _run_verifier(repo: Path, ppu_work: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/private-ppu-evidence-verifier.py"),
            "--ppu-work",
            str(ppu_work),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr, flush=True)
    if result.returncode != 0:
        raise RepeatabilityError(f"independent evidence verifier failed with rc={result.returncode}")
    marker_line = next(
        (line for line in result.stdout.splitlines() if line.startswith(VERIFIER_RESULT_MARKER)),
        None,
    )
    if marker_line is None:
        raise RepeatabilityError("independent evidence verifier result marker missing")
    payload = json.loads(marker_line[len(VERIFIER_RESULT_MARKER) :])
    if payload.get("overall_result") != "PASS":
        raise RepeatabilityError(f"independent evidence verifier did not pass: {payload!r}")
    return payload


def _run_report_path(summary_report: Path, attempt: int) -> Path:
    suffix = summary_report.suffix or ".json"
    stem = summary_report.name[: -len(summary_report.suffix)] if summary_report.suffix else summary_report.name
    return summary_report.with_name(f"{stem}-run{attempt}{suffix}")


def _main(args: argparse.Namespace) -> int:
    if platform.system() != "Linux":
        raise RepeatabilityError("Static IPv4 repeatability gate requires Linux")
    if os.geteuid() == 0:
        raise RepeatabilityError("repeatability gate must run as a non-root host verifier")
    if shutil.which("docker") is None or shutil.which("ip") is None:
        raise RepeatabilityError("docker and iproute2 are required")

    repo = _repo_root()
    work = _resolve(repo, args.work_dir)
    summary_report = _resolve(repo, args.report)
    runtime = _resolve(repo, args.runtime_dir) if args.runtime_dir is not None else None
    summary_report.parent.mkdir(parents=True, exist_ok=True)

    _seed_dirty_state(work)

    runs: list[dict[str, Any]] = []
    for attempt in range(1, 3):
        run_report = _run_report_path(summary_report, attempt)
        command = [
            sys.executable,
            str(repo / "scripts/static-ipv4-fault-injection-lab.py"),
        ]
        if runtime is not None:
            command.extend(["--runtime-dir", str(runtime)])
        command.extend(["--work-dir", str(work), "--report", str(run_report)])

        print(f"[REPEATABILITY] run {attempt}/2 using work-dir {work}", flush=True)
        started = time.monotonic()
        returncode = _run_streaming(command, cwd=repo)
        elapsed = time.monotonic() - started
        if returncode != 0:
            raise RepeatabilityError(f"fault lab run {attempt}/2 failed with rc={returncode}")
        if not run_report.is_file():
            raise RepeatabilityError(f"fault lab run {attempt}/2 did not produce report: {run_report}")

        payload = json.loads(run_report.read_text(encoding="utf-8"))
        if payload.get("overall_result") != "PASS":
            raise RepeatabilityError(f"fault lab run {attempt}/2 did not pass: {payload!r}")

        ppu_work = work / "manager-crash-after-commit" / "ppu-a"
        verifier = _run_verifier(repo, ppu_work)
        runs.append(
            {
                "attempt": attempt,
                "elapsed_s": round(elapsed, 3),
                "fault_report": str(run_report),
                "git_sha": payload.get("git_sha"),
                "host_uplink": payload.get("host_uplink"),
                "evidence_level": payload.get("evidence_level"),
                "private_journal": {
                    "owner": verifier.get("owner"),
                    "mode": verifier.get("mode"),
                    "sha256": verifier.get("sha256"),
                    "verifier_euid": verifier.get("verifier_euid"),
                },
            }
        )
        print(f"[REPEATABILITY] run {attempt}/2 PASS ({elapsed:.1f}s)", flush=True)

    git_shas = {run.get("git_sha") for run in runs}
    if len(git_shas) != 1:
        raise RepeatabilityError(f"repeatability runs used different git revisions: {sorted(git_shas)!r}")

    result = {
        "overall_result": "PASS",
        "same_work_dir": str(work),
        "run_count": 2,
        "dirty_state_injected_before_run1": True,
        "dirty_state_contract": "direct root:root 0700 directory + root:root 0600 marker",
        "manual_cleanup": False,
        "sudo": False,
        "host_verifier_non_root": True,
        "producer_evidence_contract": "root:root 0600",
        "verifier_independent": True,
        "runs": runs,
        "not_claimed": [
            "PYNQ-Z2 hardware",
            "final PYNQ-Z2 Linux network-manager backend",
            "DHCP endpoint migration",
            "boot-time network persistence",
            "physical cable/switch behavior",
            "PS-to-PL",
            "FPGA Site I/O",
            "real IC programming",
        ],
    }
    summary_report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("[REPEATABILITY] DIRTY-STATE STARTUP        : PASS")
    print("[REPEATABILITY] SAME WORK-DIR TWICE        : PASS")
    print("[REPEATABILITY] NON-ROOT VERIFIER          : PASS")
    print("[REPEATABILITY] ROOT:ROOT 0600 EVIDENCE    : PASS")
    print("[REPEATABILITY] INDEPENDENT READ-ONLY HASH : PASS")
    print("[REPEATABILITY] Z2 NETWORK BACKEND CLAIM   : NONE")
    print("[REPEATABILITY] OVERALL RESULT             : PASS")
    print(RESULT_MARKER + json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Static IPv4 acceptance twice in the same work directory")
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_REL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_REL)
    args = parser.parse_args(argv)
    try:
        return _main(args)
    except (RepeatabilityError, OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        print(f"static-ipv4-fault-injection-repeatability: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
