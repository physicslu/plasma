#!/usr/bin/env python3
"""Owner-triggered PLASMA Development Mode dispatcher, shared Workflow/Runner.

A reviewed task registry on pinned main defines the exact fixed command. This
adapter uses no privilege elevation, device APIs, network calls or shell.
The product/qualification Runtime dispatcher remains independently disabled.
"""
from __future__ import annotations

import argparse
import ast
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
        require(set(task) == {
            "execution_path", "script", "argv", "expected_stdout_sha256",
        }, "TASK_FIELDS_DENIED")
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

def authorize(event: object, context: dict, registry: object) -> dict:
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
    require(issue.get("number") == ISSUE and "pull_request" not in issue,
            "EVENT_ISSUE_DENIED")
    require(sender.get("login") == OWNER
            and type(comment.get("user")) is dict
            and comment["user"].get("login") == OWNER
            and repository.get("full_name") == REPO,
            "EVENT_OWNER_DENIED")
    require(type(comment.get("id")) is int and comment["id"] > 0,
            "EVENT_COMMENT_ID_DENIED")
    body = comment.get("body")
    require(type(body) is str and body.startswith(COMMAND_PREFIX)
            and body.endswith(" " + str(ISSUE)), "COMMAND_DENIED")
    task_id = body[len(COMMAND_PREFIX):-len(" " + str(ISSUE))]
    task = task_by_id(registry, task_id)
    require(body == f"{COMMAND_PREFIX}{task_id} {ISSUE}",
            "EXACT_COMMAND_DENIED")
    return {
        "status": "AUTHORIZED_DEV_TASK",
        "task_id": task_id,
        "execution_path": task["execution_path"],
        "pinned_sha": sha,
        "comment_id": comment["id"],
        "issue_number": ISSUE,
    }


def run_task(task: dict, *, executor=subprocess.run) -> dict:
    script = ROOT / task["script"]
    require(script.is_file() and not script.is_symlink(), "SCRIPT_NOT_FOUND")
    proc = executor(
        [sys.executable, str(script), *task["argv"]],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=40, check=False,
    )
    require(len(proc.stdout) <= 65536 and len(proc.stderr) <= 65536,
            "OUTPUT_EXCEEDS_LIMIT")
    digest = hashlib.sha256(proc.stdout).hexdigest()
    lines = proc.stdout.decode("ascii").splitlines()
    require(proc.returncode == 0 and proc.stderr == b"", "COMMAND_FAILED")
    require(digest == task["expected_stdout_sha256"], "OUTPUT_SHA256_MISMATCH")
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
        "rows": 81,
        "stdout_bytes": len(proc.stdout),
        "stdout_sha256": digest,
        "first_row": lines[1],
        "last_row": lines[-1],
    }


def validate_generated_source(source: str) -> None:
    """Admit only pure Python print + two range loops before execution.

    This is not a general Python sandbox: it is a narrow, fixed smoke-test
    grammar so a generated script cannot invoke hardware APIs or shell.
    """
    require(len(source.encode("utf-8")) <= 2048,
            "CODEX_SOURCE_TOO_LARGE")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise Denied("CODEX_SOURCE_SYNTAX_DENIED") from exc
    allowed = (
        ast.Module, ast.Expr, ast.Call, ast.Name, ast.Load, ast.Store,
        ast.For, ast.Constant, ast.JoinedStr, ast.FormattedValue,
        ast.BinOp, ast.Mult,
    )
    for node in ast.walk(tree):
        require(type(node) in allowed, "CODEX_SOURCE_NODE_DENIED")
        if isinstance(node, ast.Name):
            require(node.id in {"a", "b", "print", "range"},
                    "CODEX_SOURCE_NAME_DENIED")
        if isinstance(node, ast.Call):
            require(type(node.func) is ast.Name and
                    node.func.id in ("print", "range") and
                    not node.keywords, "CODEX_SOURCE_CALL_DENIED")
        if isinstance(node, ast.For):
            require(not node.orelse and type(node.target) is ast.Name,
                    "CODEX_SOURCE_LOOP_DENIED")
    require(len(tree.body) == 2 and
            type(tree.body[0]) is ast.Expr and
            type(tree.body[1]) is ast.For,
            "CODEX_SOURCE_SHAPE_DENIED")
    header = tree.body[0].value
    require(type(header) is ast.Call and len(header.args) == 1 and
            type(header.args[0]) is ast.Constant and
            header.args[0].value == "multiplicand,multiplier,product",
            "CODEX_SOURCE_HEADER_DENIED")
    outer = tree.body[1]
    require(outer.target.id == "a" and len(outer.body) == 1 and
            type(outer.body[0]) is ast.For,
            "CODEX_SOURCE_OUTER_LOOP_DENIED")
    inner = outer.body[0]
    require(inner.target.id == "b" and len(inner.body) == 1 and
            type(inner.body[0]) is ast.Expr,
            "CODEX_SOURCE_INNER_LOOP_DENIED")
    for loop in (outer, inner):
        it = loop.iter
        require(type(it) is ast.Call and type(it.func) is ast.Name and
                it.func.id == "range" and len(it.args) == 2 and
                all(type(arg) is ast.Constant for arg in it.args) and
                [arg.value for arg in it.args] == [1, 10],
                "CODEX_SOURCE_RANGE_DENIED")
    row = inner.body[0].value
    require(type(row) is ast.Call and type(row.func) is ast.Name and
            row.func.id == "print" and len(row.args) == 1 and
            type(row.args[0]) is ast.JoinedStr,
            "CODEX_SOURCE_PRINT_DENIED")


def run_codex_task(task: dict, *, workspace: Path = ROOT,
                   executor=subprocess.run) -> dict:
    """Invoke real Codex CLI to create one new source file, then run it."""
    path = workspace / task["output_path"]
    require(not path.exists() and path.parent.is_dir(),
            "CODEX_OUTPUT_ALREADY_EXISTS")
    prompt = (
        "PLASMA Development Mode single-owner Path 3 approved 9x9 smoke test.\n"
        "Generate exactly ONE new Python 3 file at "
        + task["output_path"] + " inside the current repository.\n"
        "Objective: " + task["objective"] + "\n"
        "Use precisely a print statement for the CSV header, then two "
        "nested for loops with a in range(1,10), b in range(1,10), "
        "and an f-string print of a,b,a*b on every row. "
        "No imports, functions, assignments, comprehensions, attributes, "
        "external commands, extra text, or other file writes. "
        "No Z2, FPGA, USB, LA, DUT, MMIO, SSH, sudo, network or Git operations. "
        "Do not modify any existing file; return only the generated file.\n"
    )
    command = [
        "codex", "--ask-for-approval", "never",
        "-c", "sandbox_workspace_write.network_access=false",
        "exec", "--sandbox", "workspace-write", "-",
    ]
    model = executor(
        command, input=prompt.encode("utf-8"), cwd=workspace,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=480, check=False,
    )
    require(model.returncode == 0, "CODEX_CLI_NONZERO")
    require(path.is_file() and not path.is_symlink(),
            "CODEX_SOURCE_NOT_CREATED")
    source = path.read_text(encoding="utf-8")
    validate_generated_source(source)
    result = subprocess.run(
        [sys.executable, str(path)], cwd=workspace,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20, check=False,
    )
    require(result.returncode == 0 and result.stderr == b"",
            "GENERATED_PROGRAM_FAILED")
    require(len(result.stdout) <= 65536, "OUTPUT_EXCEEDS_LIMIT")
    digest = hashlib.sha256(result.stdout).hexdigest()
    lines = result.stdout.decode("ascii").splitlines()
    require(digest == task["expected_stdout_sha256"],
            "OUTPUT_SHA256_MISMATCH")
    require(len(lines) == 82 and
            lines[0] == "multiplicand,multiplier,product",
            "TABLE_FORMAT_DENIED")
    for a in range(1, 10):
        for b in range(1, 10):
            require(lines[1 + (a - 1) * 9 + (b - 1)] == f"{a},{b},{a*b}",
                    "MULTIPLICATION_MISMATCH")
    return {
        "status": "PASS",
        "execution_path": "path3-codex",
        "runner": os.environ.get("RUNNER_NAME", "offline-stub"),
        "codex_exit_code": model.returncode,
        "exit_code": result.returncode,
        "rows": 81,
        "stdout_bytes": len(result.stdout),
        "stdout_sha256": digest,
        "source_path": task["output_path"],
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "first_row": lines[1],
        "last_row": lines[-1],
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("authorize", "execute", "execute-codex"))
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=MANIFEST)
    parser.add_argument("--pinned-sha")
    args = parser.parse_args()
    try:
        registry = parse_json(args.registry)
        event = parse_json(args.event)
        plan = authorize(event, os.environ, registry)
        if args.action in ("execute", "execute-codex"):
            require(os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted"
                    and os.environ.get("RUNNER_NAME") == EXPECTED_RUNNER
                    and os.geteuid() != 0, "SWPC_RUNNER_DENIED")
            require(args.pinned_sha == plan["pinned_sha"],
                    "PINNED_SHA_MISMATCH")
            task = task_by_id(registry, plan["task_id"])
            require(task["execution_path"] == (
                "path3-codex" if args.action == "execute-codex" else "path2-cli"
            ), "WRONG_EXECUTION_PATH")
            receipt = (run_codex_task(task) if args.action == "execute-codex"
                       else run_task(task))
            receipt.update({
                "task_id": plan["task_id"],
                "pinned_sha": plan["pinned_sha"],
                "comment_id": plan["comment_id"],
                "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
            })
            plan = receipt
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
