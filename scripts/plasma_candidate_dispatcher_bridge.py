#!/usr/bin/env python3
"""Trusted main-only Candidate Dispatcher -> real Codex development relay.

The candidate Dispatcher executes only in bwrap (synthetic /dev, no network,
no host homes/credentials). A trusted one-shot relay invokes authenticated
Codex outside the candidate sandbox using the already approved SWPC account.
No new daemon, workflow, runner or hardware interface is introduced.

This is a tightly scoped pre-merge engineering experiment for PR #1083.
The entry is NOT active until this trusted code is independently reviewed
and merged to main. Do not use this file from a candidate checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

import plasma_development_dispatch as trusted

TASK_ID = "candidate-dispatcher-e2e-1083"
PR_NUMBER = 1083
REPO = "physicslu/plasma"
EXPECTED_RUNNER = "SWPC-plasma-codex"
CODEX_CMD = (
    "codex", "--ask-for-approval", "never", "-c",
    "sandbox_workspace_write.network_access=true",
    "exec", "--sandbox", "workspace-write", "-",
)
MAX_PROMPT = 16384
MAX_LOG = 2 * 1024 * 1024
STAMP = "plasma.candidate_dispatcher.trusted_relay.v1"

# Deliberately no network/credential/host-device access from the candidate.
# The shim is a local request/response transport, NOT a Codex authenticator.
CODEX_SHIM = r'''#!/usr/bin/python3
import hashlib, os, pathlib, sys
if tuple(sys.argv[1:]) != (
        "--ask-for-approval","never","-c",
        "sandbox_workspace_write.network_access=true",
        "exec","--sandbox","workspace-write","-"):
    raise SystemExit(61)
buf=sys.stdin.buffer.read(16385)
if not (1 <= len(buf) <= 16384):
    raise SystemExit(62)
root=pathlib.Path("/scratch")
phase=os.environ.get("BRIDGE_PHASE")
if phase=="prepare":
    (root/"prompt.bin").write_bytes(buf)
    raise SystemExit(73)  # expected: no real agent in this isolated phase
if phase=="replay":
    if hashlib.sha256(buf).hexdigest() != (root/"prompt.sha256").read_text():
        raise SystemExit(74)
    report=root/"engineering-report.md"
    if report.is_file():
        dest=root/"workspace/.plasma-path3-evidence/engineering-report.md"
        dest.write_bytes(report.read_bytes())
    sys.stdout.buffer.write((root/"codex-stdout.bin").read_bytes())
    sys.stderr.buffer.write((root/"codex-stderr.bin").read_bytes())
    raise SystemExit(int((root/"codex-exit.txt").read_text()))
raise SystemExit(75)
'''


class BridgeDenied(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise BridgeDenied(reason)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def valid_task(task: dict, pr_number: int) -> None:
    """One exact CPU-only PR task, not a generic candidate-code launcher."""
    require(pr_number == PR_NUMBER, "CANDIDATE_PR_DENIED")
    require(task.get("execution_path") == "path3-codex" and
            task.get("capability", "cpu-only") == "cpu-only" and
            type(task.get("objective")) is str and
            "Do not use hardware" in task["objective"] and
            task.get("output_path") ==
                "scripts/experiments/plasma_auto4_branch_codex_generated.py",
            "CANDIDATE_TASK_DENIED")


def admission(event: dict, env: dict[str, str], args, registry: dict,
              actual_candidate_sha: str) -> dict:
    """Run inside trusted main; caller does not supply an authorization claim."""
    require(env.get("GITHUB_EVENT_NAME") == "issue_comment" and
            env.get("GITHUB_REPOSITORY") == REPO and
            env.get("GITHUB_ACTOR") == "physicslu" and
            env.get("GITHUB_REF") == "refs/heads/main" and
            env.get("RUNNER_ENVIRONMENT") == "self-hosted" and
            env.get("RUNNER_NAME") == EXPECTED_RUNNER and
            os.geteuid() != 0, "TRUSTED_WORKER_DENIED")
    req = trusted.request(event, env)
    require(req["task_id"] == TASK_ID and
            req["pr_number"] == PR_NUMBER and
            req["source_sha"] == args.pinned_sha and
            req["trusted_sha"] == args.trusted_sha and
            actual_candidate_sha == args.pinned_sha and
            args.pinned_sha != args.trusted_sha, "CANDIDATE_SOURCE_DENIED")
    require(env.get("GITHUB_SHA") == args.trusted_sha,
            "TRUSTED_MAIN_SHA_DENIED")
    require(digest(args.registry.read_bytes()) == args.registry_sha256,
            "CANDIDATE_REGISTRY_DENIED")
    task = trusted.task_by_id(registry, TASK_ID)
    valid_task(task, args.pr_number)
    require(args.workspace.is_dir() and not args.workspace.is_symlink(),
            "CANDIDATE_WORKSPACE_DENIED")
    return {"request": req, "task": task, "registry_sha256": args.registry_sha256}


def run_process(cmd: list[str], *, cwd: Path, env: dict[str, str],
                input_bytes: bytes | None = None, timeout: int = 45):
    """Bounded child + process-group cleanup, no shell or detached jobs."""
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    try:
        stdout, stderr = proc.communicate(input=input_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise BridgeDenied("CANDIDATE_EXECUTION_TIMEOUT") from None
    require(len(stdout) <= MAX_LOG and len(stderr) <= MAX_LOG,
            "CANDIDATE_OUTPUT_TOO_LARGE")
    return proc.returncode, stdout, stderr


def sandbox_command(candidate: Path, scratch: Path, *,
                    trusted_sha: str, pinned_sha: str,
                    registry_sha256: str, phase: str) -> list[str]:
    """Read-only candidate source, writable task scratch, no host /dev or auth."""
    bwrap = shutil.which("bwrap")
    require(bwrap is not None and Path(bwrap).is_file(),
            "CANDIDATE_SANDBOX_NOT_AVAILABLE")
    require(phase in ("prepare", "replay"), "CANDIDATE_PHASE_DENIED")
    binds = []
    for root in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(root).exists():
            binds += ["--ro-bind", root, root]
    return [
        bwrap, "--die-with-parent", "--new-session", "--unshare-all",
        "--clearenv", *binds,
        "--ro-bind", str(candidate), "/work",
        "--bind", str(scratch), "/scratch",
        "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
        "--setenv", "HOME", "/tmp",
        "--setenv", "PYTHONNOUSERSITE", "1",
        "--setenv", "PATH", "/scratch/bin:/usr/bin:/bin",
        "--setenv", "BRIDGE_PHASE", phase,
        "--setenv", "GITHUB_EVENT_NAME", "issue_comment",
        "--setenv", "GITHUB_ACTOR", "physicslu",
        "--setenv", "GITHUB_REPOSITORY", REPO,
        "--setenv", "GITHUB_REF", "refs/heads/main",
        "--setenv", "GITHUB_SHA", trusted_sha,
        "--setenv", "RUNNER_ENVIRONMENT", "self-hosted",
        "--setenv", "RUNNER_NAME", EXPECTED_RUNNER,
        "--chdir", "/work", "--",
        "/usr/bin/python3", "-I", "-S",
        "/work/scripts/plasma_development_dispatch.py", "execute-codex",
        "--event", "/scratch/event.json",
        "--registry", "/work/specs/engineering-dispatch/development-tasks-v1.json",
        "--workspace", "/scratch/workspace",
        "--trusted-sha", trusted_sha,
        "--pinned-sha", pinned_sha,
        "--pr-number", str(PR_NUMBER),
        "--registry-sha256", registry_sha256,
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--trusted-sha", required=True)
    parser.add_argument("--pinned-sha", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--registry-sha256", required=True)
    args = parser.parse_args()
    try:
        # Fail before starting bwrap, Codex, or writing workspaces.
        require(args.event.is_file() and args.registry.is_file(),
                "CANDIDATE_INPUTS_MISSING")
        event = trusted.parse_json(args.event)
        registry = trusted.parse_json(args.registry)
        current = subprocess.check_output(
            ["git", "-C", str(args.workspace), "rev-parse", "HEAD"],
            text=True, timeout=5).strip()
        approved = admission(event, os.environ, args, registry, current)
        task = approved["task"]
        candidate = args.workspace.resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix="plasma-candidate-relay-") as td:
            scratch = Path(td)
            (scratch / "bin").mkdir(mode=0o700)
            (scratch / "workspace").mkdir(mode=0o700)
            (scratch / "event.json").write_text(json.dumps(event))
            shim = scratch / "bin/codex"
            shim.write_text(CODEX_SHIM)
            shim.chmod(0o700)
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                   "HOME": os.environ.get("HOME", ""),
                   "PYTHONNOUSERSITE": "1"}
            phase1 = sandbox_command(candidate, scratch,
                trusted_sha=args.trusted_sha, pinned_sha=current,
                registry_sha256=args.registry_sha256, phase="prepare")
            rc1, out1, err1 = run_process(phase1, cwd=candidate, env=env)
            require(rc1 == 2 and (scratch / "prompt.bin").is_file(),
                    "CANDIDATE_PREPARE_DENIED")
            first = json.loads(out1)
            require(first.get("status") ==
                    "CODEX_EXECUTION_FAILED_REVIEW_REQUIRED" and
                    first.get("worker_admission", {}).get("status") ==
                    "WORKER_SOURCE_ADMITTED", "CANDIDATE_PREPARE_RECEIPT_DENIED")
            prompt = (scratch / "prompt.bin").read_bytes()
            require(1 <= len(prompt) <= MAX_PROMPT and
                    task["objective"].encode() in prompt,
                    "CANDIDATE_PROMPT_OUT_OF_SCOPE")
            (scratch / "prompt.sha256").write_text(digest(prompt))
            # A real Codex invocation occurs ONCE in trusted SWPC context.
            # Candidate cannot see this process's HOME, auth or host devices.
            shutil.rmtree(scratch / "workspace/.plasma-path3-evidence")
            # Codex normally expects a Git worktree. This is an isolated,
            # scratch-only repository, not the candidate's source tree.
            subprocess.run(["git", "init", "-q", str(scratch / "workspace")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True, timeout=8)
            rc, stdout, stderr = run_process(
                list(CODEX_CMD), cwd=scratch / "workspace", env=os.environ.copy(),
                input_bytes=prompt, timeout=240)
            (scratch / "codex-stdout.bin").write_bytes(stdout)
            (scratch / "codex-stderr.bin").write_bytes(stderr)
            (scratch / "codex-exit.txt").write_text(str(rc))
            report = scratch / "workspace/.plasma-path3-evidence/engineering-report.md"
            if report.is_file() and not report.is_symlink():
                require(report.stat().st_size <= MAX_LOG, "CANDIDATE_REPORT_OVERSIZE")
                shutil.copyfile(report, scratch / "engineering-report.md")
            if (scratch / "workspace/.plasma-path3-evidence").exists():
                shutil.rmtree(scratch / "workspace/.plasma-path3-evidence")
            phase2 = sandbox_command(candidate, scratch,
                trusted_sha=args.trusted_sha, pinned_sha=current,
                registry_sha256=args.registry_sha256, phase="replay")
            rc2, out2, err2 = run_process(phase2, cwd=candidate, env=env)
            receipt = json.loads(out2)
            # Copy real agent evidence for the already existing trusted
            # Workflow uploader, including failure logs. Candidate source
            # is not executed outside the sandbox at any point.
            output_rel = Path(task["output_path"])
            target = candidate / output_rel
            source = scratch / "workspace" / output_rel
            generated_log = target.with_suffix(".codex.log")
            require(not generated_log.exists() and not generated_log.is_symlink(),
                    "CANDIDATE_EVIDENCE_COLLISION")
            generated_log.parent.mkdir(parents=True, exist_ok=True)
            generated_log.write_bytes(
                b"=== Real Codex stdout ===\\n" + stdout +
                b"\\n=== Real Codex stderr ===\\n" + stderr)
            if rc == 0 and rc2 == 0:
                csv = source.with_suffix(".csv")
                test_log = source.with_suffix(".test.log")
                for file in (source, csv, test_log):
                    require(file.is_file() and not file.is_symlink()
                            and file.stat().st_size < MAX_LOG,
                            "CANDIDATE_REAL_EVIDENCE_MISSING")
                rows = csv.read_text(encoding="utf-8").splitlines()
                require(len(rows) == 13 and rows[0] == "n,triangular" and
                        all(rows[i] == f"{i},{i*(i+1)//2}"
                            for i in range(1, 13)), "CANDIDATE_OUTPUT_INVALID")
                require(receipt.get("source_sha256") == digest(source.read_bytes())
                        and receipt.get("output_sha256") == digest(csv.read_bytes())
                        and receipt.get("test_log_sha256") == digest(test_log.read_bytes()),
                        "CANDIDATE_EVIDENCE_DIGEST_MISMATCH")
                for file in (source, csv, test_log):
                    dest = target.with_suffix(file.suffix)
                    require(not dest.exists() and not dest.is_symlink(),
                            "CANDIDATE_SOURCE_COLLISION")
                    shutil.copyfile(file, dest)
            require(rc2 == (0 if rc == 0 else 2) and
                    receipt.get("codex_exit_code") == rc and
                    receipt.get("pinned_sha") == current and
                    receipt.get("worker_admission", {}).get("status") ==
                    "WORKER_SOURCE_ADMITTED" and
                    receipt.get("codex_log_sha256"),
                    "CANDIDATE_REPLAY_RECEIPT_DENIED")
            result = {
                "schema": STAMP,
                "status": receipt.get("status"),
                "execution_path": "path3-codex",
                "candidate_sha": current,
                "trusted_sha": args.trusted_sha,
                "registry_sha256": args.registry_sha256,
                "task_id": TASK_ID,
                "codex_exit_code": rc,
                "codex_log_sha256": receipt["codex_log_sha256"],
                "dispatcher_exit_code": rc2,
                "agent_real_execution": True,
                "candidate_sandbox": "bwrap-no-network-no-host-home-no-devices",
                "agent_process": "trusted-main-outside-candidate-sandbox",
                "acceptance": "REVIEW_REQUIRED",
            }
            # Don't claim PASS merely from Codex exit 0 or JSON.
            print(json.dumps(result, sort_keys=True))
            return 0 if rc2 == 0 and rc == 0 else 2
    except (BridgeDenied, trusted.Denied, ValueError, KeyError, OSError,
            subprocess.SubprocessError, json.JSONDecodeError) as exc:
        # No host paths, stdout of Codex, or auth material in error receipt.
        code = str(exc) if isinstance(exc, (BridgeDenied, trusted.Denied)) else "TRUSTED_RELAY_ERROR"
        print(json.dumps({"status": "NOT_RUN_OR_FAIL", "reason": code},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
