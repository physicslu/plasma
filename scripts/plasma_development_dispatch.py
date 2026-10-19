#!/usr/bin/env python3
"""Owner-triggered PLASMA Development Mode dispatcher, shared Workflow/Runner.

Trusted dispatcher code stays on main; a reviewed development PR SHA may
supply a candidate task registry/workspace. No shell-based dispatch.
The product/qualification Runtime dispatcher remains independently disabled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = "physicslu/plasma"
OWNER = "physicslu"
ISSUE = 981
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "specs/engineering-dispatch/development-tasks-v1.json"
VERSION = "plasma.engineering.development_tasks.v1"
COMMAND_PREFIX = "/plasma-dispatch run "
EXPECTED_RUNNER = "SWPC-plasma-codex"
TASK_ID = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")

BRANCH_COMMAND = re.compile(
    r"/plasma-dispatch run (?P<task>[a-z][a-z0-9-]{2,63}) "
    r"--pr (?P<pr>[1-9][0-9]{0,7}) --sha (?P<sha>[a-f0-9]{40}) 981\Z"
)
LEGACY_COMMAND = re.compile(
    r"/plasma-dispatch run (?P<task>[a-z][a-z0-9-]{2,63}) 981\Z"
)


class Denied(ValueError):
    pass


def require(test: bool, code: str) -> None:
    if not test:
        raise Denied(code)


def parse_json(path: Path) -> object:
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_size <= 65536, "JSON_FILE_DENIED")
    def unique(pairs: list[tuple[str, object]]) -> dict:
        value = {}
        for key, item in pairs:
            require(key not in value, "JSON_DUPLICATE_FIELD")
            value[key] = item
        return value
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def task_by_id(registry: object, task_id: str) -> dict:
    require(type(registry) is dict and set(registry) == {
        "schema_version", "mode", "tasks",
    }, "REGISTRY_FIELDS_DENIED")
    require(registry["schema_version"] == VERSION
            and registry["mode"] == "development", "REGISTRY_MODE_DENIED")
    tasks = registry["tasks"]
    require(type(tasks) is dict and 1 <= len(tasks) <= 64,
            "REGISTRY_TASKS_DENIED")
    require(type(task_id) is str and TASK_ID.fullmatch(task_id) is not None
            and task_id in tasks, "TASK_ID_DENIED")
    task = tasks[task_id]
    require(type(task) is dict and "execution_path" in task,
            "TASK_FIELDS_DENIED")
    execution_path = task["execution_path"]
    require(execution_path in ("path2-cli", "path3-codex"),
            "PATH_NOT_SUPPORTED")
    if execution_path == "path2-cli":
        require(set(task) in ({
            "execution_path", "script", "argv", "expected_stdout_sha256",
        }, {
            "execution_path", "script", "argv", "expected_stdout_sha256",
            "verification",
        }), "TASK_FIELDS_DENIED")
        require(task.get("verification", "sha256-only") in (
            "sha256-only", "nine-nine-table-v1",
        ), "TASK_VERIFICATION_DENIED")
        path = task["script"]
        require(type(path) is str and re.fullmatch(
            r"scripts/experiments/[a-zA-Z0-9_-]+\.py", path
        ) is not None, "SCRIPT_PATH_DENIED")
        argv = task["argv"]
        require(type(argv) is list and len(argv) <= 8 and all(
            type(x) is str and re.fullmatch(r"[A-Za-z0-9._=/:-]{1,80}", x)
            and not x.startswith("-") and ".." not in x for x in argv
        ), "TASK_ARGS_DENIED")
    else:
        require(set(task) == {
            "execution_path", "output_path", "objective",
            "expected_stdout_sha256",
        }, "TASK_FIELDS_DENIED")
        output_path = task["output_path"]
        require(type(output_path) is str and re.fullmatch(
            r"scripts/experiments/plasma_[a-z0-9_]+_generated\.py",
            output_path,
        ) is not None, "CODEX_OUTPUT_PATH_DENIED")
        objective = task["objective"]
        require(type(objective) is str and 40 <= len(objective) <= 800
                and all(32 <= ord(c) <= 126 for c in objective),
                "CODEX_OBJECTIVE_DENIED")
    require(type(task["expected_stdout_sha256"]) is str
            and SHA256.fullmatch(task["expected_stdout_sha256"]) is not None,
            "OUTPUT_DIGEST_INVALID")
    return task

def request(event: object, context: dict) -> dict:
    """Verify owner, issue and exact command before any candidate checkout."""
    require(type(event) is dict and event.get("action") == "created",
            "EVENT_ACTION_DENIED")
    require(context.get("GITHUB_EVENT_NAME") == "issue_comment"
            and context.get("GITHUB_ACTOR") == OWNER
            and context.get("GITHUB_REPOSITORY") == REPO
            and context.get("GITHUB_REF") == "refs/heads/main",
            "EVENT_CONTEXT_DENIED")
    sha = context.get("GITHUB_SHA")
    require(type(sha) is str and SHA40.fullmatch(sha) is not None,
            "REVIEWED_SHA_INVALID")
    issue, comment, sender, repository = (
        event.get("issue"), event.get("comment"),
        event.get("sender"), event.get("repository"),
    )
    require(all(type(x) is dict for x in (
        issue, comment, sender, repository,
    )), "EVENT_SHAPE_DENIED")
    require(type(issue.get("number")) is int and issue["number"] == ISSUE
            and "pull_request" not in issue, "EVENT_ISSUE_DENIED")
    require(sender.get("login") == OWNER
            and type(comment.get("user")) is dict
            and comment["user"].get("login") == OWNER
            and repository.get("full_name") == REPO,
            "EVENT_OWNER_DENIED")
    require(type(comment.get("id")) is int and comment["id"] > 0,
            "EVENT_COMMENT_ID_DENIED")
    body = comment.get("body")
    require(type(body) is str and 0 < len(body) <= 200,
            "COMMAND_DENIED")
    branch_match = BRANCH_COMMAND.fullmatch(body)
    legacy_match = LEGACY_COMMAND.fullmatch(body)
    require(branch_match is not None or legacy_match is not None,
            "EXACT_COMMAND_DENIED")
    match = branch_match or legacy_match
    return {
        "task_id": match.group("task"),
        "pr_number": int(branch_match.group("pr")) if branch_match else 0,
        "source_sha": branch_match.group("sha") if branch_match else sha,
        "trusted_sha": sha,
        "comment_id": comment["id"],
        "issue_number": ISSUE,
    }


def verify_pr(pr: object, req: dict) -> None:
    """Authorize exact, open, same-repository, owner-created PR HEAD."""
    require(type(pr) is dict and req["pr_number"] > 0,
            "PR_METADATA_DENIED")
    require(type(pr.get("number")) is int and
            pr["number"] == req["pr_number"], "PR_NUMBER_MISMATCH")
    require(pr.get("state") == "open" and
            pr.get("merged_at") is None, "PR_NOT_OPEN")
    head, base, author = pr.get("head"), pr.get("base"), pr.get("user")
    require(all(type(x) is dict for x in (head, base, author)),
            "PR_SHAPE_DENIED")
    require(type(head.get("repo")) is dict and
            head["repo"].get("full_name") == REPO and
            type(base.get("repo")) is dict and
            base["repo"].get("full_name") == REPO and
            base.get("ref") == "main", "PR_REPOSITORY_OR_BASE_DENIED")
    require(author.get("login") == OWNER and
            type(head.get("ref")) is str and
            head["ref"].startswith("agent/"), "PR_OWNER_OR_BRANCH_DENIED")
    require(head.get("sha") == req["source_sha"],
            "PR_HEAD_SHA_MISMATCH")


def authorize(event: object, context: dict, registry: object,
              pr_info: object = None) -> dict:
    req = request(event, context)
    if req["pr_number"]:
        verify_pr(pr_info, req)
    else:
        require(pr_info is None, "UNEXPECTED_PR_METADATA")
    task = task_by_id(registry, req["task_id"])
    return {
        "status": "AUTHORIZED_DEV_TASK",
        **req,
        "pinned_sha": req["source_sha"],
        "execution_path": task["execution_path"],
    }


def run_task(task: dict, *, workspace: Path = ROOT,
             executor=subprocess.run, evidence_dir: Path | None = None) -> dict:
    script = workspace / task["script"]
    require(script.is_file() and not script.is_symlink(), "SCRIPT_NOT_FOUND")
    proc = executor(
        [sys.executable, str(script), *task["argv"]],
        cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=40, check=False,
    )
    require(len(proc.stdout) <= 65536 and len(proc.stderr) <= 65536,
            "OUTPUT_EXCEEDS_LIMIT")
    if evidence_dir is not None:
        require(evidence_dir.is_dir(), "EVIDENCE_DIR_DENIED")
        (evidence_dir / "plasma-path2-stdout.txt").write_bytes(proc.stdout)
        (evidence_dir / "plasma-path2-stderr.txt").write_bytes(proc.stderr)
    digest = hashlib.sha256(proc.stdout).hexdigest()
    lines = proc.stdout.decode("ascii").splitlines()
    require(proc.returncode == 0 and proc.stderr == b"", "COMMAND_FAILED")
    require(digest == task["expected_stdout_sha256"], "OUTPUT_SHA256_MISMATCH")
    if task.get("verification", "sha256-only") == "nine-nine-table-v1":
        require(len(lines) == 82
                and lines[0] == "multiplicand,multiplier,product",
                "TABLE_FORMAT_DENIED")
        for a in range(1, 10):
            for b in range(1, 10):
                require(lines[1 + (a - 1) * 9 + (b - 1)] == f"{a},{b},{a*b}",
                        "MULTIPLICATION_MISMATCH")
    return {
        "status": "PASS",
        "execution_path": "path2-cli",
        "runner": os.environ.get("RUNNER_NAME", "offline-stub"),
        "exit_code": proc.returncode,
        "rows": max(0, len(lines) - 1),
        "stdout_bytes": len(proc.stdout),
        "stdout_sha256": digest,
        "first_row": lines[1] if len(lines) > 1 else "",
        "last_row": lines[-1] if lines else "",
    }


def run_codex_task(task: dict, *, workspace: Path = ROOT,
                   executor=subprocess.run) -> dict:
    """Delegate creation AND testing to Codex; collect evidence for ChatGPT.

    Dispatcher does not evaluate Python AST, re-run generated software, or
    declare the work correct. Only actual reviewer evidence can prove PASS.
    """
    source = workspace / task["output_path"]
    output = source.with_suffix(".csv")
    test_log = source.with_suffix(".test.log")
    codex_log = source.with_suffix(".codex.log")
    require(source.parent.is_dir() and not any(
        p.exists() for p in (source, output, test_log, codex_log)
    ), "CODEX_EVIDENCE_PATH_ALREADY_EXISTS")
    prompt = (
        "PLASMA single-owner Development Mode Path 3. You are the engineer. "
        "Independently implement, run, test, debug and finish the task.\n"
        "Goal: " + task["objective"] + "\n"
        "Write your Python implementation to " + task["output_path"] + ".\n"
        "Execute that code yourself using Python on this Runner. Capture "
        "the program's ACTUAL complete output as CSV in " +
        str(output.relative_to(workspace)) + ".\n"
        "Independently check that the 9 x 9 results are mathematically "
        "correct and complete (81 products); if not, fix the code and "
        "rerun it yourself. Write a short honest test report, with the "
        "actual command(s), observed test outcome, test counts and exit "
        "status, to " + str(test_log.relative_to(workspace)) + ".\n"
        "Any Python implementation is acceptable. Header labels or AST "
        "shape need NOT match the Path 2 implementation. Do not falsely "
        "claim a test passed or fabricate outputs. Keep all generated "
        "source and evidence files, including on failure.\n"
        "Only create the specified implementation, CSV and test report. "
        "Do not modify existing files, Git state or repositories. "
        "No Z2, FPGA, USB, LA, DUT, MMIO, SSH, sudo, physical device, "
        "network or deployment actions. Stop if these are required.\n"
    )
    command = [
        "codex", "--ask-for-approval", "never",
        "-c", "sandbox_workspace_write.network_access=false",
        "exec", "--sandbox", "workspace-write", "-",
    ]
    proc = executor(
        command, input=prompt.encode("utf-8"), cwd=workspace,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=480, check=False,
    )
    require(len(proc.stdout) <= 262144 and len(proc.stderr) <= 262144,
            "CODEX_LOG_TOO_LARGE")
    codex_log.write_bytes(b"=== Codex stdout ===\n" + proc.stdout +
                          b"\n=== Codex stderr ===\n" + proc.stderr)
    require(proc.returncode == 0, "CODEX_CLI_NONZERO")
    require(all(p.is_file() and not p.is_symlink() for p in (
        source, output, test_log
    )), "CODEX_EVIDENCE_INCOMPLETE")
    require(all(p.stat().st_size <= 65536 for p in (
        source, output, test_log
    )), "CODEX_EVIDENCE_TOO_LARGE")
    def digest(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    return {
        "status": "EVIDENCE_READY_REVIEW_REQUIRED",
        "execution_path": "path3-codex",
        "runner": os.environ.get("RUNNER_NAME", "offline-stub"),
        "codex_exit_code": proc.returncode,
        "source_path": task["output_path"],
        "source_sha256": digest(source),
        "output_path": str(output.relative_to(workspace)),
        "output_sha256": digest(output),
        "test_log_path": str(test_log.relative_to(workspace)),
        "test_log_sha256": digest(test_log),
        "codex_log_path": str(codex_log.relative_to(workspace)),
        "codex_log_sha256": digest(codex_log),
        "reference_stdout_sha256": task["expected_stdout_sha256"],
        "acceptance": "CHATGPT_REVIEW_OF_REAL_OUTPUT_AND_TEST_LOG",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=(
        "request", "authorize", "execute", "execute-codex",
    ))
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=MANIFEST)
    parser.add_argument("--pr-info", type=Path)
    parser.add_argument("--pinned-sha")
    parser.add_argument("--trusted-sha")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--registry-sha256")
    parser.add_argument("--workspace", type=Path, default=ROOT)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    try:
        event = parse_json(args.event)
        req = request(event, os.environ)
        if args.action == "request":
            plan = {"status": "VALID_OWNER_REQUEST", **req}
        else:
            registry = parse_json(args.registry)
            pr = parse_json(args.pr_info) if args.pr_info else None
            if args.action in ("execute", "execute-codex"):
                require(os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted"
                        and os.environ.get("RUNNER_NAME") == EXPECTED_RUNNER
                        and os.geteuid() != 0, "SWPC_RUNNER_DENIED")
                require(args.trusted_sha == req["trusted_sha"] and
                        args.pinned_sha == req["source_sha"] and
                        args.pr_number == req["pr_number"],
                        "AUTHORIZED_SOURCE_MISMATCH")
                require(type(args.registry_sha256) is str and
                        SHA256.fullmatch(args.registry_sha256) is not None
                        and hashlib.sha256(
                            args.registry.read_bytes()
                        ).hexdigest() == args.registry_sha256,
                        "AUTHORIZED_REGISTRY_MISMATCH")
                require(args.workspace.is_dir() and
                        args.workspace.resolve() != ROOT.resolve(),
                        "WORKSPACE_DENIED")
                task = task_by_id(registry, req["task_id"])
                require(task["execution_path"] == (
                    "path3-codex" if args.action == "execute-codex"
                    else "path2-cli"
                ), "WRONG_EXECUTION_PATH")
                receipt = (
                    run_codex_task(task, workspace=args.workspace)
                    if args.action == "execute-codex"
                    else run_task(task, workspace=args.workspace,
                                  evidence_dir=args.evidence_dir)
                )
                plan = {
                    **receipt, **req,
                    "task_id": req["task_id"],
                    "pinned_sha": req["source_sha"],
                    "registry_sha256": args.registry_sha256,
                    "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
                }
            else:
                plan = authorize(event, os.environ, registry, pr)
                plan["registry_sha256"] = hashlib.sha256(
                    args.registry.read_bytes()
                ).hexdigest()
        print(json.dumps(plan, sort_keys=True))
        return 0
    except (Denied, OSError, UnicodeError, json.JSONDecodeError,
            subprocess.SubprocessError, ValueError) as exc:
        print(json.dumps({
            "status": "NOT_RUN_OR_FAIL",
            "reason": str(exc) if isinstance(exc, Denied) else "EXECUTION_ERROR",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
