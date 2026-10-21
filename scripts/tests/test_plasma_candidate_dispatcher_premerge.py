#!/usr/bin/env python3
"""GitHub-hosted PRE-MERGE candidate Dispatcher CLI integration; SWPC is simulated.

Runs the actual candidate command-line interface as subprocesses with a stub
Codex binary and fixture events. Never contacts SWPC, hardware or Issue #981.
Tests command admission / exit semantics, NOT OS-level privilege isolation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DISPATCHER = ROOT / "scripts/plasma_development_dispatch.py"
REGISTRY = ROOT / "specs/engineering-dispatch/development-tasks-v1.json"
TRUSTED = "a" * 40
CANDIDATE = "b" * 40
TASK = "auto4-premerge-path3"

# Stub only. No Codex installation, network, sudo, USB, FPGA or devices.
CODEX_STUB = r'''#!/usr/bin/env python3
import os
from pathlib import Path

root = Path.cwd()
evidence = root / ".plasma-path3-evidence"
evidence.mkdir(exist_ok=True)
(evidence / "engineering-report.md").write_text(
    "HOSTED_SIMULATION_ONLY: stub Codex; NOT a SWPC E2E test.\\n"
    "12 rows independently checked by the outer integration harness.\\n"
)
dest = root / "scripts/experiments/plasma_auto4_branch_codex_generated.py"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(
    "print('n,triangular')\\n"
    "for n in range(1, 13):\\n"
    "    print(f'{n},{n*(n+1)//2}')\\n"
)
out = dest.with_suffix(".csv")
out.write_text("n,triangular\\n" + "".join(
    f"{n},{n*(n+1)//2}\\n" for n in range(1, 13)
))
dest.with_suffix(".test.log").write_text(
    "HOSTED_STUB_ONLY: 12 generated rows, outer harness verifies.\\n"
)
print("HOSTED_CODEX_STUB_ONLY")
raise SystemExit(int(os.environ.get("SIMULATED_CODEX_EXIT", "0")))
'''

def check(test: bool, reason: str) -> None:
    if not test:
        raise AssertionError(reason)

def invoke(arguments: list[str], env: dict[str, str]) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(DISPATCHER), *arguments],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=20,
    )
    check(proc.stderr == b"", "unexpected CLI stderr: " + proc.stderr.decode(errors="replace"))
    try:
        receipt = json.loads(proc.stdout)
    except (ValueError, UnicodeError) as exc:
        raise AssertionError(f"invalid CLI JSON: {proc.stdout!r}") from exc
    return proc.returncode, receipt

def smoke() -> None:
    check(os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
          "ONLY_GITHUB_HOSTED_ALLOWED")
    check(os.environ.get("GITHUB_EVENT_NAME") == "pull_request",
          "ONLY_PULL_REQUEST_ALLOWED")
    check(os.environ.get("GITHUB_REPOSITORY") == "physicslu/plasma",
          "REPOSITORY_DENIED")
    expected = os.environ.get("PLASMA_CANDIDATE_SHA", "")
    actual = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    check(len(expected) == 40 and actual == expected, "CANDIDATE_HEAD_MISMATCH")
    task = json.loads(REGISTRY.read_text())["tasks"][TASK]
    check(task["execution_path"] == "path3-codex"
          and "Do not use hardware" in task["objective"], "CPU_ONLY_TASK_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="plasma-premerge-hosted-") as td:
        temp = Path(td)
        event = {
            "action": "created",
            "issue": {"number": 981},
            "comment": {"id": 1001, "user": {"login": "physicslu"},
                        "body": f"/plasma-dispatch run {TASK} --pr 1083 --sha {CANDIDATE} 981"},
            "sender": {"login": "physicslu"},
            "repository": {"full_name": "physicslu/plasma"},
        }
        event_file = temp / "event.json"
        event_file.write_text(json.dumps(event))
        pr_file = temp / "pr.json"
        pr_file.write_text(json.dumps({
            "number": 1083, "state": "open", "merged_at": None,
            "user": {"login": "physicslu"},
            "head": {"ref": "candidate", "sha": CANDIDATE,
                     "repo": {"full_name": "physicslu/plasma"}},
            "base": {"ref": "main", "repo": {"full_name": "physicslu/plasma"}},
        }))
        fake_bin = temp / "bin"
        fake_bin.mkdir()
        codex = fake_bin / "codex"
        codex.write_text(CODEX_STUB)
        codex.chmod(0o700)
        clean_env = {
            "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(temp),
            "PYTHONNOUSERSITE": "1",
            "GITHUB_EVENT_NAME": "issue_comment",  # Fixture, not a real dispatch.
            "GITHUB_ACTOR": "physicslu",
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": TRUSTED,
            "GITHUB_RUN_ID": "HOSTED_SIMULATION_NOT_SWPC",
            "RUNNER_ENVIRONMENT": "self-hosted",  # Fixture to test worker guard.
            "RUNNER_NAME": "SWPC-plasma-codex",  # Fixture only, not a Runner claim.
        }
        auth_args = [
            "authorize", "--event", str(event_file), "--registry", str(REGISTRY),
            "--pr-info", str(pr_file),
        ]
        rc, auth = invoke(auth_args, clean_env)
        check(rc == 0 and auth.get("status") == "AUTHORIZED_DEV_TASK",
              "AUTHORIZATION_FAILED")
        check(auth["pinned_sha"] == CANDIDATE
              and auth["trusted_sha"] == TRUSTED, "SOURCE_SHA_BINDING_FAILED")
        check(auth["registry_sha256"] == hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
              "REGISTRY_SHA_BINDING_FAILED")

        def worker(workspace: Path, *, exit_code: int, digest: str | None = None,
                   pinned: str = CANDIDATE) -> tuple[int, dict]:
            workspace.mkdir()
            env = {**clean_env, "SIMULATED_CODEX_EXIT": str(exit_code)}
            args = [
                "execute-codex", "--event", str(event_file),
                "--registry", str(REGISTRY), "--workspace", str(workspace),
                "--trusted-sha", TRUSTED, "--pinned-sha", pinned,
                "--pr-number", "1083", "--registry-sha256",
                digest if digest is not None else auth["registry_sha256"],
            ]
            return invoke(args, env)

        rc, result = worker(temp / "success", exit_code=0)
        check(rc == 0 and result.get("status") == "EVIDENCE_READY_REVIEW_REQUIRED",
              "SUCCESS_RECEIPT_FAILED")
        check(result["codex_exit_code"] == 0
              and result["worker_admission"]["status"] == "WORKER_SOURCE_ADMITTED",
              "WORKER_ADMISSION_FAILED")
        check(result["registry_sha256"] == auth["registry_sha256"],
              "WORKER_REGISTRY_MISMATCH")
        csv = (temp / "success/scripts/experiments/plasma_auto4_branch_codex_generated.csv")
        rows = csv.read_text().splitlines()
        check(rows[0] == "n,triangular" and len(rows) == 13
              and all(rows[n] == f"{n},{sum(range(1, n + 1))}" for n in range(1, 13)),
              "INDEPENDENT_12_ROW_CHECK_FAILED")
        check((temp / "success/.plasma-path3-evidence/codex.log").is_file(),
              "SUCCESS_CODEX_LOG_MISSING")

        rc, failed = worker(temp / "failure", exit_code=7)
        check(rc != 0 and failed["status"] == "CODEX_EXECUTION_FAILED_REVIEW_REQUIRED"
              and failed["codex_exit_code"] == 7, "FAILURE_EXIT_MASKED")
        check((temp / "failure/.plasma-path3-evidence/codex.log").is_file(),
              "FAILURE_CODEX_LOG_MISSING")
        rc, rejected = worker(temp / "bad-registry", exit_code=0, digest="0"*64)
        check(rc != 0 and rejected.get("reason") == "AUTHORIZED_REGISTRY_MISMATCH",
              "MISMATCHED_REGISTRY_ADMITTED")
        check(not (temp / "bad-registry/.plasma-path3-evidence").exists(),
              "DENIED_JOB_EXECUTED_CODEX")
        rc, rejected = worker(temp / "bad-source", exit_code=0, pinned="c"*40)
        check(rc != 0 and rejected.get("reason") == "AUTHORIZED_SOURCE_MISMATCH",
              "MISMATCHED_SOURCE_ADMITTED")
        check(not (temp / "bad-source/.plasma-path3-evidence").exists(),
              "DENIED_SOURCE_EXECUTED_CODEX")
        invalid = dict(event)
        invalid["sender"] = {"login": "not-owner"}
        event_file.write_text(json.dumps(invalid))
        rc, rejected = invoke(auth_args, clean_env)
        check(rc != 0 and rejected.get("reason") == "EVENT_OWNER_DENIED",
              "NONOWNER_ADMITTED")
    print("CANDIDATE_DISPATCHER_PREMERGE_HOSTED_SIMULATION_PASS")
    print("REAL_SWPC_CANDIDATE_DISPATCHER_NOT_RUN")

if __name__ == "__main__":
    try:
        smoke()
    except (AssertionError, OSError, subprocess.SubprocessError) as exc:
        print("CANDIDATE_DISPATCHER_PREMERGE_HOSTED_SIMULATION_FAIL", str(exc),
              file=sys.stderr)
        raise SystemExit(1)
