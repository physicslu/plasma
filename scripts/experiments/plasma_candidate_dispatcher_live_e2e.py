#!/usr/bin/env python3
"""One bounded real-Codex E2E of the PR Candidate Dispatcher, nested under
the existing owner-authorized trusted main Path 3 Codex workspace sandbox.

No GitHub dispatches or hardware calls. Actual inner Codex exit and generated
source/output are independently verified; no stub executor is used.
If the outer Codex sandbox cannot launch a nested real Codex CLI, fail closed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
DISPATCHER = REPO / "scripts/plasma_development_dispatch.py"
REGISTRY = REPO / "specs/engineering-dispatch/development-tasks-v1.json"
TASK_ID = "auto4-premerge-path3"
RESULT_FILE = REPO / ".plasma-path3-evidence/candidate-dispatcher-live-e2e.json"

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def command(args: list[str], *, env: dict[str, str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    # Kill the entire child process group if the nested Codex CLI stalls.
    proc = subprocess.Popen(
        args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise RuntimeError("NESTED_CODEX_TIMEOUT_FAIL_CLOSED") from None
    require(len(out) <= 262144 and len(err) <= 262144,
            "NESTED_DISPATCHER_OUTPUT_TOO_LARGE")
    return subprocess.CompletedProcess(args, proc.returncode, out, err)

def run() -> None:
    require(os.geteuid() != 0, "ROOT_DENIED")
    require(os.environ.get("GITHUB_EVENT_NAME") == "issue_comment" and
            os.environ.get("GITHUB_ACTOR") == "physicslu" and
            os.environ.get("GITHUB_REPOSITORY") == "physicslu/plasma" and
            os.environ.get("GITHUB_REF") == "refs/heads/main" and
            os.environ.get("RUNNER_NAME") == "SWPC-plasma-codex" and
            os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted",
            "TRUSTED_PARENT_CONTEXT_MISSING")
    require(RESULT_FILE.parent.is_dir() and RESULT_FILE.parent.resolve().is_relative_to(REPO),
            "OUTER_CODEX_EVIDENCE_DIR_MISSING")
    require(not RESULT_FILE.exists(), "DUPLICATE_LIVE_E2E_DENIED")
    require(DISPATCHER.is_file() and REGISTRY.is_file() and
            not DISPATCHER.is_symlink() and not REGISTRY.is_symlink(),
            "CANDIDATE_FILES_INVALID")
    actual = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        text=True, timeout=5).strip()
    trusted = os.environ["GITHUB_SHA"]
    require(len(trusted) == 40 and len(actual) == 40 and trusted != actual,
            "SOURCE_IDENTITY_DENIED")
    registry = json.loads(REGISTRY.read_text())
    task = registry["tasks"][TASK_ID]
    require(task["execution_path"] == "path3-codex" and
            "Do not use hardware" in task["objective"], "SOFTWARE_ONLY_TASK_REQUIRED")
    with tempfile.TemporaryDirectory(prefix=".plasma-candidate-live-", dir=REPO) as d:
        root = Path(d)
        workspace = root / "workspace"
        workspace.mkdir()
        event = {
            "action": "created",
            "issue": {"number": 981},
            "sender": {"login": "physicslu"},
            "comment": {
                "id": 101, "user": {"login": "physicslu"},
                "body": f"/plasma-dispatch run {TASK_ID} --pr 1083 --sha {actual} 981",
            },
            "repository": {"full_name": "physicslu/plasma"},
        }
        event_file = root / "event.json"
        event_file.write_text(json.dumps(event), encoding="utf-8")
        args = [
            sys.executable, str(DISPATCHER), "execute-codex",
            "--event", str(event_file), "--registry", str(REGISTRY),
            "--workspace", str(workspace), "--trusted-sha", trusted,
            "--pinned-sha", actual, "--pr-number", "1083",
            "--registry-sha256", sha(REGISTRY),
        ]
        # The candidate receives no additional privileges or credentials:
        # this subprocess inherits only the already-authorized outer Codex
        # sandbox context, and nested Codex itself requests workspace-write.
        result = command(args, env=os.environ.copy(), cwd=REPO, timeout=180)
        try:
            receipt = json.loads(result.stdout)
        except ValueError:
            raise RuntimeError("NESTED_DISPATCHER_RECEIPT_INVALID") from None
        # Never print raw agent logs or credentials to Actions output.
        facts = {
            "schema": "plasma.candidate_dispatcher.live_e2e.v1",
            "candidate_sha": actual,
            "trusted_sha": trusted,
            "task_id": TASK_ID,
            "runner": os.environ["RUNNER_NAME"],
            "dispatcher_exit": result.returncode,
            "codex_exit_code": receipt.get("codex_exit_code"),
            "status": receipt.get("status"),
            "worker_admission": receipt.get("worker_admission", {}).get("status"),
            "codex_log_sha256": receipt.get("codex_log_sha256"),
            "engineering_report_sha256": receipt.get("engineering_report_sha256"),
        }
        expected = task["output_path"]
        code = workspace / expected
        csv = code.with_suffix(".csv")
        test_log = code.with_suffix(".test.log")
        complete = (
            result.returncode == 0 and
            receipt.get("status") == "EVIDENCE_READY_REVIEW_REQUIRED" and
            receipt.get("codex_exit_code") == 0 and
            receipt.get("worker_admission", {}).get("status") == "WORKER_SOURCE_ADMITTED" and
            receipt.get("pinned_sha") == actual and
            receipt.get("registry_sha256") == sha(REGISTRY) and
            code.is_file() and csv.is_file() and test_log.is_file() and
            receipt.get("source_sha256") == sha(code) and
            receipt.get("output_sha256") == sha(csv) and
            receipt.get("test_log_sha256") == sha(test_log)
        )
        if complete:
            rows = csv.read_text(encoding="utf-8").splitlines()
            complete = (len(rows) == 13 and rows[0] == "n,triangular" and
                        all(rows[i] == f"{i},{i*(i+1)//2}" for i in range(1,13)))
        facts["acceptance"] = "PASS" if complete else "FAIL"
        # The trusted-main uploader omits hidden directories. Retain actual
        # failure and success evidence under its existing generated-file globs
        # BEFORE TemporaryDirectory cleanup, even on nonzero nested exit.
        prefix = REPO / "scripts/experiments/plasma_candidate_dispatcher_live_generated"
        inner_log = workspace / ".plasma-path3-evidence/codex.log"
        if inner_log.is_file() and not inner_log.is_symlink():
            require(inner_log.stat().st_size <= 1048576, "CODEX_LOG_TOO_LARGE")
            shutil.copyfile(inner_log, Path(str(prefix) + ".codex.log"))
        # Record the unmodified dispatcher receipt and exact stderr.
        # Never print these raw diagnostics to the GitHub Actions console.
        trace = (
            b"=== inner dispatcher receipt stdout ===\\n" + result.stdout +
            b"\\n=== inner dispatcher stderr ===\\n" + result.stderr + b"\\n"
        )
        Path(str(prefix) + ".test.log").write_bytes(trace)
        if code.is_file() and not code.is_symlink():
            shutil.copyfile(code, prefix.with_suffix(".py"))
        if csv.is_file() and not csv.is_symlink():
            shutil.copyfile(csv, prefix.with_suffix(".csv"))
        RESULT_FILE.write_text(json.dumps(facts, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        require(complete, "CANDIDATE_LIVE_CODEX_E2E_FAILED")
        print("CANDIDATE_DISPATCHER_REAL_CODEX_E2E_PASS")
        print(f"candidate_sha={actual} dispatcher_exit=0 codex_exit=0 rows=12")

if __name__ == "__main__":
    try:
        run()
    except (OSError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"CANDIDATE_DISPATCHER_REAL_CODEX_E2E_NOT_PASS: {exc}", file=sys.stderr)
        raise SystemExit(1)
