#!/usr/bin/env python3
"""Owner-triggered PLASMA Development Mode dispatcher, shared Workflow/Runner.

Trusted dispatcher code stays on main; a reviewed development PR SHA may
supply a candidate task registry/workspace. No shell-based dispatch.
The product/qualification Runtime dispatcher remains independently disabled.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import plasma_engineering_activity as engineering_activity

REPO = "physicslu/plasma"
OWNER = "physicslu"
ISSUE = 981
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "specs/engineering-dispatch/development-tasks-v1.json"
VERSION = "plasma.engineering.development_tasks.v1"
COMMAND_PREFIX = "/plasma-dispatch run "
DYNAMIC_TASKS = {"path2-cli": "path2-work-order", "path3-codex": "path3-work-order"}
WORK_ORDER_PREFIX = "/plasma-dispatch work-order 981\n"
WORK_ORDER_SCHEMA = "plasma.development.work_order.v1"
# Explicit operator-public metadata; never derived from objective/acceptance.
# Single-line restricted vocabulary prevents control sequences, URLs, quotes,
# shell syntax and raw JSON from crossing the GitHub output/monitor boundary.
MONITOR_SUMMARY = re.compile(
    r"[A-Za-z0-9\u4e00-\u9fff]"
    r"[A-Za-z0-9\u4e00-\u9fff ._()/+-]{6,78}"
    r"[A-Za-z0-9\u4e00-\u9fff)]\Z"
)
MONITOR_SENSITIVE = re.compile(
    r"\b(?:password|passwd|secret|credential|token|bearer|"
    r"private.key|api.key|authorization)\b|[a-fA-F0-9]{32,}",
    re.IGNORECASE,
)
# Fixed trusted-main Path 2 observation; NOT an arbitrary-script capability.
NATIVE_PREFLIGHT = "codex-native-install-v1"
EXPECTED_RUNNER = "SWPC-plasma-codex"
TASK_ID = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")

BRANCH_COMMAND = re.compile(
    r"/plasma-dispatch run (?P<task>[a-z][a-z0-9-]{2,63}) "
    r"--pr (?P<pr>[1-9][0-9]{0,7}) --sha (?P<sha>[a-f0-9]{40})"
    r"(?P<flags>(?: --auto-download)?(?: --auto-testing)?) 981\Z"
)
LEGACY_COMMAND = re.compile(
    r"/plasma-dispatch run (?P<task>[a-z][a-z0-9-]{2,63})"
    r"(?P<flags>(?: --auto-download)?(?: --auto-testing)?) 981\Z"
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
    if task_id == "hil-a2-cpu-only":
        require(execution_path == "path2-cli" and set(task) == {
            "execution_path", "capability", "work_order",
        }, "A2_TASK_FIELDS_DENIED")
        require(task["capability"] == "z2-cpu-only" and
                task["work_order"] ==
                "specs/engineering-dispatch/work-orders/hil-a2-cpu-only-r1.json",
                "A2_TASK_BINDING_DENIED")
        return task
    if task_id in ("z2-path2-download", "z2-path2-testing",
                    "z2-path2-restore", "z2-path2-full-hil"):
        expected = {"z2-path2-download": "download",
                    "z2-path2-testing": "test",
                    "z2-path2-restore": "restore",
                    "z2-path2-full-hil": "full"}
        require(execution_path == "path2-cli" and set(task) == {
            "execution_path", "capability", "project", "stage",
        } and task["capability"] == "path2-stage-contract"
                and task["project"] == "pl/projects/z2-fixed-unified-site1"
                and task["stage"] == expected[task_id],
                "PATH2_STAGE_TASK_FIELDS_DENIED")
        return task
    if execution_path == "path2-cli" and task.get("capability") == "vivado-host-build":
        require(task_id in ("fixed-site1-vivado-host-build", "z2-path2-build"),
                "PATH2_BUILD_TASK_ID_DENIED")
        # Path 2 is an execution method, NOT synonymous with CPU-only Python.
        # Host builds use a fixed, reviewed Vivado capability and project.
        require(set(task) == {"execution_path", "capability", "project",
                              "toolchain", "board_repo_sha"},
                "HOST_BUILD_TASK_FIELDS_DENIED")
        require(type(task["project"]) is str and re.fullmatch(
            r"pl/projects/[a-z0-9-]{3,70}", task["project"]
        ) is not None, "HOST_BUILD_PROJECT_DENIED")
        require(task["toolchain"] == "2026.1" and
                type(task["board_repo_sha"]) is str and
                SHA40.fullmatch(task["board_repo_sha"]) is not None,
                "HOST_BUILD_TOOLCHAIN_DENIED")
        return task
    if execution_path == "path2-cli":
        # Legacy CPU-only CLI fixtures keep their independent sandbox.
        require(set(task) >= {
            "execution_path", "script", "argv", "expected_stdout_sha256",
        } and set(task) <= {
            "execution_path", "script", "argv", "expected_stdout_sha256",
            "verification", "capability",
        }, "TASK_FIELDS_DENIED")
        require(task.get("capability", "cpu-only") == "cpu-only",
                "DEV_CAPABILITY_DENIED")
        require(task.get("verification", "sha256-only") == "sha256-only",
                "TASK_VERIFICATION_DENIED")
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
        # Development Path 3 is a general engineering agent, not a
        # generated-Python-file-only fixture. The objective names the work;
        # the authorized candidate workspace may contain RTL, Tcl, docs, etc.
        require({"execution_path", "objective"} <= set(task)
                and set(task) <= {
                    "execution_path", "objective", "output_path",
                    "expected_stdout_sha256", "output_format",
                }, "TASK_FIELDS_DENIED")
        objective = task["objective"]
        require(type(objective) is str and 20 <= len(objective) <= 8192
                and not any(ord(c) < 32 and c not in "\n\r\t"
                            for c in objective),
                "CODEX_OBJECTIVE_DENIED")
        if "output_path" in task:
            path = task["output_path"]
            require(type(path) is str and re.fullmatch(
                r"scripts/experiments/plasma_[a-z0-9_]+_generated\.py",
                path,
            ) is not None, "CODEX_OUTPUT_PATH_DENIED")
        require(task.get("output_format", "text") in ("csv", "text"),
                "CODEX_EVIDENCE_FORMAT_DENIED")
    if execution_path == "path2-cli" or "expected_stdout_sha256" in task:
        require(type(task["expected_stdout_sha256"]) is str
                and SHA256.fullmatch(task["expected_stdout_sha256"]) is not None,
                "OUTPUT_DIGEST_INVALID")
    return task


def parse_dynamic_work_order(event: object) -> dict:
    """Owner's single Issue comment is the Work Order; no registry edit.

    The JSON must be exact and immutable within this created event. Stage
    names bound physical effects; they do not override the installed hardware
    Runtime Guard or grant OS privileges to the Codex worker.
    """
    require(type(event) is dict and type(event.get("comment")) is dict,
            "WORK_ORDER_EVENT_DENIED")
    body = event["comment"].get("body")
    require(type(body) is str and body.startswith(WORK_ORDER_PREFIX)
            and len(body.encode("utf-8")) <= 12288,
            "WORK_ORDER_FORMAT_DENIED")

    def unique(pairs):
        data = {}
        for key, val in pairs:
            require(key not in data, "WORK_ORDER_DUPLICATE_FIELD")
            data[key] = val
        return data

    try:
        order = json.loads(body[len(WORK_ORDER_PREFIX):],
                           object_pairs_hook=unique)
    except (ValueError, TypeError):
        raise Denied("WORK_ORDER_JSON_DENIED") from None
    require(type(order) is dict and
            set(order) >= {"schema", "objective", "acceptance",
                           "execution_path", "capability"}
            and set(order) <= {"schema", "objective", "acceptance", "scope",
                               "execution_path", "capability",
                               "pr_number", "source_sha", "session_resume", "native_preflight", "script", "argv",
                               "expected_stdout_sha256", "project", "stage",
                                "monitor_summary"},
            "WORK_ORDER_FIELDS_DENIED")
    require(order["schema"] == WORK_ORDER_SCHEMA,
            "WORK_ORDER_SCHEMA_DENIED")
    for key in ("objective", "acceptance"):
        val = order[key]
        require(type(val) is str and 20 <= len(val) <= 8192
                and not any(ord(ch) < 32 and ch not in "\n\r\t"
                            for ch in val), "WORK_ORDER_TEXT_DENIED")
    require(len(order["objective"]) + len(order["acceptance"]) <= 10000,
            "WORK_ORDER_TOO_LARGE")
    if "monitor_summary" in order:
        summary = order["monitor_summary"]
        require(type(summary) is str and
                MONITOR_SUMMARY.fullmatch(summary) is not None and
                MONITOR_SENSITIVE.search(summary) is None,
                "WORK_ORDER_MONITOR_SUMMARY_DENIED")
    path, capability, scope = (order["execution_path"],
                               order["capability"], order.get("scope"))
    require(type(path) is str and path in DYNAMIC_TASKS and
            type(capability) is str,
            "WORK_ORDER_PATH_DENIED")
    base = {"schema", "objective", "acceptance", "scope",
            "execution_path", "capability"}
    optional_ref = {"pr_number", "source_sha"}
    if path == "path3-codex":
        if "session_resume" in order:
            require(order["session_resume"] == "page-boundary-off-by-one"
                    and scope == "host-only"
                    and set(order) <= base | optional_ref | {"session_resume", "monitor_summary"}
                    and type(order.get("pr_number")) is int
                    and order["pr_number"] >= 0
                    and "source_sha" in order,
                    "WORK_ORDER_RESUME_SCOPE_DENIED")
        else:
            require(capability == "codex-workspace" and
                    set(order) <= (base - {"scope"}) | optional_ref | {"monitor_summary"},
                    "WORK_ORDER_PATH3_FIELDS_DENIED")
        require(capability == "codex-workspace",
                "WORK_ORDER_PATH3_FIELDS_DENIED")
    elif capability == "cpu-only" and "native_preflight" in order:
        # Existing Path 2 task_id and Runner. No candidate scripts, shell,
        # path parameters, model or hardware under this one main-only route.
        require(path == "path2-cli" and scope == "host-only" and
                order["native_preflight"] == NATIVE_PREFLIGHT and
                set(order) == base | optional_ref | {"native_preflight"} |
                 ({"monitor_summary"} if "monitor_summary" in order else set()) and
                order.get("pr_number") == 0 and
                type(order.get("pr_number")) is int and
                type(order.get("source_sha")) is str,
                "WORK_ORDER_NATIVE_PREFLIGHT_SCOPE_DENIED")
    elif capability == "cpu-only":
        require(scope == "host-only" and
                {"script", "argv", "expected_stdout_sha256"} <= set(order)
                and set(order) <= base | optional_ref |
                {"script", "argv", "expected_stdout_sha256", "monitor_summary"},
                "WORK_ORDER_PATH2_FIELDS_DENIED")
        task_by_id({"schema_version": VERSION, "mode": "development",
                    "tasks": {"work-order-fixture": {
                        "execution_path": "path2-cli",
                        "capability": "cpu-only",
                        "script": order["script"], "argv": order["argv"],
                        "expected_stdout_sha256":
                            order["expected_stdout_sha256"]}}},
                   "work-order-fixture")
    elif capability == "path2-stage-contract":
        require(scope == "guarded-hardware" and
                {"project", "stage"} <= set(order) and
                set(order) <= base | optional_ref | {"project", "stage", "monitor_summary"} and
                type(order["project"]) is str and
                re.fullmatch(r"pl/projects/[a-z0-9][a-z0-9-]{2,69}",
                             order["project"]) is not None and
                type(order["stage"]) is str and
                order["stage"] in ("download", "test", "restore"),
                "WORK_ORDER_STAGE_CAPABILITY_DENIED")
    else:
        raise Denied("WORK_ORDER_CAPABILITY_DENIED")
    number = order.get("pr_number", 0)
    require(type(number) is int and 0 <= number <= 99999999,
            "WORK_ORDER_PR_DENIED")
    if number:
        require(type(order.get("source_sha")) is str and
                SHA40.fullmatch(order["source_sha"]) is not None,
                "WORK_ORDER_SOURCE_DENIED")
    elif order.get("native_preflight") == NATIVE_PREFLIGHT:
        # Separate owner-scoped bootstrap: exact event main, Path 2 only.
        require(type(order.get("source_sha")) is str and
                SHA40.fullmatch(order["source_sha"]) is not None,
                "WORK_ORDER_NATIVE_MAIN_SHA_REQUIRED")
    elif order.get("session_resume") == "page-boundary-off-by-one":
        # Exception for this exact CPU-only post-merge diagnostic only.
        # Main pinning is checked against trusted GITHUB_SHA by request().
        require(type(order.get("source_sha")) is str and
                SHA40.fullmatch(order["source_sha"]) is not None,
                "WORK_ORDER_RESUME_MAIN_SHA_REQUIRED")
    else:
        require("source_sha" not in order,
                "WORK_ORDER_MAIN_SHA_NOT_EVENT_PINNED")
    return order


def work_order_digest(order: dict) -> str:
    data = json.dumps(order, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def task_for_request(registry: object, req: dict, event: object) -> dict:
    if req["task_id"] not in DYNAMIC_TASKS.values():
        return task_by_id(registry, req["task_id"])
    # Keep the existing registry identity check, but the generic Work Order
    # is never listed in its per-task catalogue.
    require(type(registry) is dict and
            set(registry) == {"schema_version", "mode", "tasks"} and
            registry["schema_version"] == VERSION and
            registry["mode"] == "development" and
            type(registry["tasks"]) is dict,
            "REGISTRY_FIELDS_DENIED")
    order = parse_dynamic_work_order(event)
    require(req["task_id"] == DYNAMIC_TASKS[order["execution_path"]] and
            req.get("work_order_sha256") == work_order_digest(order),
            "WORK_ORDER_DIGEST_MISMATCH")
    task = {
        "execution_path": order["execution_path"],
        "capability": order["capability"],
        "objective": order["objective"],
        "acceptance": order["acceptance"],
        "work_order_sha256": req["work_order_sha256"],
    }
    if "monitor_summary" in order:
        task["monitor_summary"] = order["monitor_summary"]
    if order["execution_path"] == "path2-cli":
        task["work_order_scope"] = order["scope"]
    if "session_resume" in order:
        task["session_resume"] = order["session_resume"]
    if "native_preflight" in order:
        task["native_preflight"] = order["native_preflight"]
    for key in ("script", "argv", "expected_stdout_sha256",
                "project", "stage"):
        if key in order:
            task[key] = order[key]
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
    require(type(body) is str and 0 < len(body) <= 12288,
            "COMMAND_DENIED")
    if body.startswith(WORK_ORDER_PREFIX):
        order = parse_dynamic_work_order(event)
        if (order.get("native_preflight") == NATIVE_PREFLIGHT and
                order["pr_number"] == 0):
            require(order["source_sha"] == sha,
                    "WORK_ORDER_NATIVE_MAIN_SHA_MISMATCH")
        if (order.get("session_resume") == "page-boundary-off-by-one" and
                order["pr_number"] == 0):
            # Never admit a different main commit, branch or omitted pin.
            require(order["source_sha"] == sha,
                    "WORK_ORDER_RESUME_MAIN_SHA_MISMATCH")
        return {
            "task_id": DYNAMIC_TASKS[order["execution_path"]],
            "auto_download_after_build_success": False,
            "auto_test_after_download_success": False,
            "pr_number": order.get("pr_number", 0),
            "source_sha": order.get("source_sha", sha),
            "trusted_sha": sha,
            "comment_id": comment["id"],
            "issue_number": ISSUE,
            "work_order_sha256": work_order_digest(order),
            **({"session_resume": order["session_resume"]}
               if "session_resume" in order else {}),
        }
    require(len(body) <= 200, "COMMAND_DENIED")
    branch_match = BRANCH_COMMAND.fullmatch(body)
    legacy_match = LEGACY_COMMAND.fullmatch(body)
    require(branch_match is not None or legacy_match is not None,
            "EXACT_COMMAND_DENIED")
    match = branch_match or legacy_match
    task_id = match.group("task")
    flags = match.group("flags") or ""
    auto_download = " --auto-download" in flags
    auto_testing = " --auto-testing" in flags
    require(not auto_download or task_id == "z2-path2-build",
            "PATH2_AUTO_DOWNLOAD_TASK_DENIED")
    require(not auto_testing or task_id in (
        "z2-path2-build", "z2-path2-download"),
        "PATH2_AUTO_TEST_TASK_DENIED")
    return {
        "task_id": task_id,
        "auto_download_after_build_success": auto_download,
        "auto_test_after_download_success": auto_testing,
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
            bool(head["ref"]) and head["ref"] != "main",
            "PR_OWNER_OR_BRANCH_DENIED")
    require(head.get("sha") == req["source_sha"],
            "PR_HEAD_SHA_MISMATCH")


def authorize(event: object, context: dict, registry: object,
              pr_info: object = None) -> dict:
    req = request(event, context)
    if req["pr_number"]:
        verify_pr(pr_info, req)
    else:
        require(pr_info is None, "UNEXPECTED_PR_METADATA")
    task = task_for_request(registry, req, event)
    a2_claim = {}
    if req["task_id"] == "hil-a2-cpu-only":
        # A hardware-capable task cannot use untrusted PR-candidate code.
        # The main-only Issue command must pin trusted == source exactly.
        require(req["pr_number"] == 0 and
                req["source_sha"] == req["trusted_sha"],
                "A2_TRUSTED_MAIN_ONLY")
        require(context.get("GITHUB_RUN_ATTEMPT") == "1",
                "A2_REPLAY_RUN_ATTEMPT_DENIED")
        work_order = parse_json(ROOT / task["work_order"])
        policy = parse_json(ROOT / "specs/engineering-dispatch/capabilities-v1.json")
        import plasma_engineering_dispatch_v1 as contracts
        try:
            contracts.validate_work_order(work_order, policy)
        except contracts.ContractDenied:
            raise Denied("A2_WORK_ORDER_CONTRACT_DENIED") from None
        require(work_order["work_order_id"] == req["task_id"] and
                work_order["issue_number"] == ISSUE and
                work_order["authorization_kind"] == "hardware-one-shot" and
                work_order["capability"] == "z2-cpu-only" and
                work_order["entrypoint"] == "z2-cpu-only",
                "A2_WORK_ORDER_SCOPE_DENIED")
        work_sha = contracts.digest(work_order)
        a2_claim = {
            "work_order_sha256": work_sha,
            "claim_ref": (f"refs/heads/plasma-engineering-claims/{ISSUE}/"
                          f"a2-{req['comment_id']}-{work_sha[:16]}-r1"),
        }
    if task.get("capability") in ("vivado-host-build", "path2-stage-contract"):
        # Owner-approved immutable PR SHA is admissible before merge.
        # verify_pr() above has already checked the live same-repo owner PR,
        # exact current HEAD and main base; do not equate merge with trust.
        require(
            (req["pr_number"] == 0 and
             req["source_sha"] == req["trusted_sha"]) or
            (req["pr_number"] > 0 and
             req["source_sha"] != req["trusted_sha"]),
            "HOST_BUILD_SOURCE_BINDING_DENIED")
    # Display-only category derived from the validated task capability/stage.
    # No freeform Work Order command, stdout or candidate data enters the pane.
    monitor_stage = ""
    if task["execution_path"] == "path2-cli":
        if task.get("capability") == "path2-stage-contract":
            monitor_stage = {
                "download": "Guarded Download",
                "test": "Guarded Test",
                "restore": "Guarded Restore",
                "full": "Guarded Full HIL",  # Existing exact registry task.
            }[task["stage"]]
        elif task.get("native_preflight") == NATIVE_PREFLIGHT:
            monitor_stage = "Native preflight"
        elif task.get("capability") == "vivado-host-build":
            monitor_stage = "Vivado host build"
        else:
            monitor_stage = "CPU-only CLI"
    return {
        "status": "AUTHORIZED_DEV_TASK",
        "monitor_stage": monitor_stage,
        "authorized_stage": (task["stage"] if
                             req["task_id"] == DYNAMIC_TASKS["path2-cli"] and
                             task.get("capability") == "path2-stage-contract"
                             else None),
        **req,
        "pinned_sha": req["source_sha"],
        "execution_path": task["execution_path"],
        "execution_capability": (
            "z2-cpu-only" if req["task_id"] == "hil-a2-cpu-only"
            else task.get("capability", "cpu-only")
                 if task["execution_path"] == "path2-cli"
            else "codex-workspace"
        ),
        # Only explicit, checksum-bound, operator-public Path 2/3 metadata.
        # No objective, acceptance, prompt, or Work Order JSON in this field.
        "monitor_summary": task.get("monitor_summary", ""),
        **a2_claim,
    }



def reviewed_host_build_driver(*, workspace: Path, approval: dict):
    """Use trusted main for main builds, an exact owner-pinned PR driver otherwise.

    The trusted dispatcher owns all authorization; this capability is limited
    to the fixed Vivado host build, never generic candidate Python execution.
    """
    if approval["pr_number"] == 0:
        import plasma_vivado_host_build as build
        return build
    root = workspace.resolve(strict=True)
    candidate = root / "scripts/plasma_vivado_host_build.py"
    require(candidate.is_file() and not candidate.is_symlink() and
            candidate.resolve(strict=True).is_relative_to(root) and
            candidate.stat().st_size <= 65536,
            "HOST_BUILD_CANDIDATE_DRIVER_DENIED")
    spec = importlib.util.spec_from_file_location(
        "plasma_reviewed_candidate_vivado_host_build", candidate)
    require(spec is not None and spec.loader is not None,
            "HOST_BUILD_CANDIDATE_DRIVER_INVALID")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    return build

def run_task(task: dict, *, workspace: Path = ROOT,
             executor=subprocess.run, evidence_dir: Path | None = None,
             approval: dict | None = None, sandbox: bool = False) -> dict:
    if task.get("capability") == "vivado-host-build":
        require(type(approval) is dict and
                approval.get("execution_capability") == "vivado-host-build" and
                approval.get("execution_path") == "path2-cli" and
                approval.get("task_id") in (
                    "fixed-site1-vivado-host-build", "z2-path2-build") and
                type(approval.get("pinned_sha")) is str and
                SHA40.fullmatch(approval["pinned_sha"]) is not None and
                type(approval.get("trusted_sha")) is str and
                SHA40.fullmatch(approval["trusted_sha"]) is not None and
                ((approval.get("pr_number") == 0 and
                  approval["pinned_sha"] == approval["trusted_sha"]) or
                 (type(approval.get("pr_number")) is int and
                  approval["pr_number"] > 0 and
                  approval["pinned_sha"] != approval["trusted_sha"])),
                "HOST_BUILD_APPROVAL_REQUIRED")
        # A request requiring an unregistered live Download provider must
        # fail before importing candidate Build code or starting Vivado.
        if (approval["task_id"] == "z2-path2-build" and
                approval.get("auto_download_after_build_success") is True):
            raise Denied("PATH2_LIVE_DOWNLOAD_PROVIDER_NOT_REGISTERED")
        build = reviewed_host_build_driver(workspace=workspace,
                                           approval=approval)
        if approval["task_id"] == "z2-path2-build":
            import plasma_path2_runtime_integration as integration
            return integration.host_build(
                task, workspace=workspace, approval=approval,
                evidence_dir=evidence_dir,
                build_driver=lambda _ctx: build.run(
                    task, workspace=workspace, approval=approval,
                    evidence_dir=evidence_dir, executor=executor))
        return build.run(task, workspace=workspace, approval=approval,
                         evidence_dir=evidence_dir, executor=executor)
    if task.get("capability") == "path2-stage-contract":
        import plasma_path2_runtime_integration as integration
        if approval is not None and approval.get("task_id") == "z2-path2-full-hil":
            return integration.full_hil_sequence(task, approval)
        return integration.registered_hardware_stage(task, approval)
    if task.get("capability") == "z2-cpu-only":
        require(type(approval) is dict and
                approval.get("task_id") == "hil-a2-cpu-only" and
                approval.get("pr_number") == 0 and
                approval.get("pinned_sha") == approval.get("trusted_sha") and
                approval.get("claim_ref") ==
                    os.environ.get("PLASMA_HIL_A2_CLAIM_REF") and
                approval.get("work_order_sha256") ==
                    os.environ.get("PLASMA_HIL_A2_WORK_ORDER_SHA256"),
                "A2_TRUSTED_CLAIM_REQUIRED")
        import plasma_hil_a2_cpu_only as a2
        work_order = parse_json(ROOT / task["work_order"])
        artifact_dir = Path(os.environ.get("PLASMA_HIL_A2_ARTIFACT_DIR", "/nonexistent"))
        return a2.run_once(work_order, artifact_dir, approval=approval)
    # Resolve before switching cwd: otherwise a relative candidate workspace
    # doubles the prefix (candidate/candidate/scripts/...).
    workspace_root = workspace.resolve()
    requested_script = workspace / task["script"]
    script = requested_script.resolve()
    require(script.is_relative_to(workspace_root) and
            requested_script.is_file() and not requested_script.is_symlink(),
            "SCRIPT_NOT_FOUND")
    command = [sys.executable, str(script), *task["argv"]]
    if sandbox:
        # Fail closed on SWPC if the OS-level CPU-only namespace sandbox
        # is missing/unavailable. Never execute untrusted candidate Python
        # with the host's original device or network privileges.
        wrapper = shutil.which("bwrap")
        require(wrapper is not None and Path(wrapper).is_file(),
                "CPU_ONLY_SANDBOX_UNAVAILABLE")
        executable = Path(sys.executable).resolve()
        require(executable.is_relative_to(Path("/usr")) or
                executable.is_relative_to(Path("/bin")),
                "CPU_ONLY_PYTHON_OUTSIDE_RO_BIND")
        binds = []
        for system_dir in ("/usr", "/bin", "/lib", "/lib64"):
            if Path(system_dir).exists():
                binds.extend(["--ro-bind", system_dir, system_dir])
        command = [
            wrapper, "--die-with-parent", "--new-session", "--unshare-all",
            "--clearenv", *binds,
            "--ro-bind", str(workspace_root), "/work",
            "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--setenv", "HOME", "/tmp",
            "--setenv", "PATH", "/usr/bin:/bin",
            "--setenv", "PYTHONNOUSERSITE", "1",
            "--chdir", "/work", "--",
            sys.executable, "-I", "-S",
            str(Path("/work") / task["script"]), *task["argv"],
        ]
    proc = executor(
        command, cwd=workspace_root, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=40, check=False,
    )
    require(len(proc.stdout) <= 65536 and len(proc.stderr) <= 65536,
            "OUTPUT_EXCEEDS_LIMIT")
    if evidence_dir is not None:
        require(evidence_dir.is_dir(), "EVIDENCE_DIR_DENIED")
        (evidence_dir / "plasma-path2-stdout.txt").write_bytes(proc.stdout)
        (evidence_dir / "plasma-path2-stderr.txt").write_bytes(proc.stderr)
    digest = hashlib.sha256(proc.stdout).hexdigest()
    lines = proc.stdout.decode("ascii").splitlines()
    require(proc.returncode == 0, "COMMAND_FAILED")
    require(digest == task["expected_stdout_sha256"], "OUTPUT_SHA256_MISMATCH")
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


def worker_admission(req: dict, args, registry: object,
                     event: object = None) -> dict:
    """One worker-side admission receipt, independent of hosted authorization.

    The GitHub-hosted job authorizes the owner and pins main/candidate SHA;
    this function independently checks the event identity, runner account,
    registry bytes, route and task capability on the SWPC boundary.
    The receipt is NOT a hardware privilege or a third human approval.
    """
    # Runner labels describe scheduling; the effective privilege is the boundary.
    require(os.geteuid() != 0, "SWPC_RUNNER_DENIED")
    require(args.trusted_sha == req["trusted_sha"]
            and args.pinned_sha == req["source_sha"]
            and args.pr_number == req["pr_number"],
            "AUTHORIZED_SOURCE_MISMATCH")
    require(type(args.registry_sha256) is str
            and SHA256.fullmatch(args.registry_sha256) is not None
            and hashlib.sha256(args.registry.read_bytes()).hexdigest()
                == args.registry_sha256,
            "AUTHORIZED_REGISTRY_MISMATCH")
    require(args.workspace.is_dir()
            and args.workspace.resolve() != ROOT.resolve(), "WORKSPACE_DENIED")
    task = task_for_request(registry, req, event)
    if req["task_id"] in DYNAMIC_TASKS.values():
        require(args.work_order_sha256 == req["work_order_sha256"],
                "WORK_ORDER_WORKER_BINDING_DENIED")
    capability = (
        "z2-cpu-only" if req["task_id"] == "hil-a2-cpu-only"
        else task.get("capability", "cpu-only")
             if task["execution_path"] == "path2-cli"
        else "codex-workspace"
    )
    require(args.execution_capability in (None, capability),
            "CAPABILITY_ROUTE_MISMATCH")
    require(task["execution_path"] == (
        "path3-codex" if args.action == "execute-codex" else "path2-cli"
    ), "WRONG_EXECUTION_PATH")
    return {
        "status": "WORKER_SOURCE_ADMITTED",
        "trusted_sha": args.trusted_sha,
        "pinned_sha": args.pinned_sha,
        "registry_sha256": args.registry_sha256,
        "execution_path": task["execution_path"],
        "execution_capability": capability,
        "task_id": req["task_id"],
    }


class LiveMonitorUnavailable(OSError):
    """Pre-execution monitor setup error; no Codex process has started."""


def codex_requested_model_settings(command: list[str]) -> dict:
    """Report only explicit CLI requests; do not guess Codex's effective model.

    The documented codex exec --json thread/turn events do not include
    effective Model/Reasoning Effort. In particular, extra JSONL keys,
    host config files and current SWPC defaults are NOT runtime evidence.
    'runtime_observed' is reserved for a future verified upstream contract.
    Do not store argv, environment or other -c values in the receipt.
    """
    candidates = {"model": [], "reasoning_effort": []}
    index = 0
    while index < len(command):
        arg = command[index]
        if arg == "--":
            break
        if arg in ("--model", "-m", "-c", "--config"):
            item = command[index + 1] if index + 1 < len(command) else ""
            index += 2
            if arg in ("--model", "-m"):
                candidates["model"].append(item)
                continue
        elif type(arg) is str and arg.startswith("--model="):
            candidates["model"].append(arg.partition("=")[2])
            index += 1
            continue
        elif type(arg) is str and arg.startswith("--config="):
            item = arg.partition("=")[2]
            index += 1
        else:
            index += 1
            continue
        if type(item) is not str or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        if name not in ("model", "model_reasoning_effort"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        candidates["model" if name == "model" else "reasoning_effort"].append(value)

    def evidence(key: str) -> dict:
        vals = candidates[key]
        valid = (bool(vals) and all(type(v) is str and
                 re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", v) for v in vals)
                 and len(set(vals)) == 1)
        if key == "reasoning_effort":
            valid = valid and vals[0] in (
                "minimal", "low", "medium", "high", "xhigh", "none")
        return {"value": vals[0] if valid else None,
                "source": "cli_requested" if valid else "NOT_AVAILABLE"}

    return {"schema_version": 1,
            "model": evidence("model"),
            "reasoning_effort": evidence("reasoning_effort")}


class CodexUsageCollector:
    """Read Codex JSONL, retaining only audited usage and event names.

    Other JSON events may contain commands, source code, prompts or secrets.
    Neither raw JSONL nor unstructured stderr is persisted or monitored.
    """

    MAX_LINE = 262144
    EVENTS = frozenset({
        "thread.started", "turn.started", "turn.completed", "turn.failed",
        "item.started", "item.updated", "item.completed", "error",
    })
    MAX_TOKENS = 2**63 - 1
    # Only fixed Codex item categories may reach the operator pane.
    # Never log freeform command, text, path, prompt or other item properties.
    MONITOR_ITEM_TYPES = frozenset({
        "command_execution", "agent_message", "reasoning", "file_change",
        "mcp_tool_call", "web_search", "collab_tool_call",
    })

    def __init__(self, *, monitor_only: bool = False,
                 workspace: Path | None = None):
        self.monitor_only = monitor_only
        self.activity = (engineering_activity.Path3Activity(workspace)
                         if monitor_only and workspace is not None else None)
        self.pending = bytearray()
        self.dropping = False
        self.session_id = None
        self.totals = {"input_tokens": 0, "cached_input_tokens": 0,
                       "output_tokens": 0}
        self.turns = 0
        self.invalid = False

    def _line(self, raw: bytes) -> bytes:
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return b"[codex unstructured output omitted]\n"
        if type(event) is not dict:
            return b"[codex unrecognized event]\n"
        kind = event.get("type")
        if kind == "thread.started":
            thread_id = event.get("thread_id")
            try:
                parsed = str(uuid.UUID(thread_id)) if type(thread_id) is str else None
            except ValueError:
                parsed = None
            if parsed is None or (self.session_id and self.session_id != parsed):
                self.invalid = True
            else:
                self.session_id = parsed
        elif kind == "turn.completed":
            usage = event.get("usage")
            keys = tuple(self.totals)
            if (type(usage) is not dict or any(
                    type(usage.get(key)) is not int or
                    not 0 <= usage[key] <= self.MAX_TOKENS for key in keys)
                    or (type(usage) is dict and
                        type(usage.get("cached_input_tokens")) is int and
                        type(usage.get("input_tokens")) is int and
                        usage["cached_input_tokens"] > usage["input_tokens"])):
                self.invalid = True
            else:
                for key in keys:
                    self.totals[key] += usage[key]
                    if self.totals[key] > self.MAX_TOKENS:
                        self.invalid = True
                self.turns += 1
        label = kind if type(kind) is str and kind in self.EVENTS else "unrecognized event"
        if self.monitor_only and kind in ("item.started", "item.updated", "item.completed"):
            if self.activity is not None:
                return self.activity.project(event)
            item = event.get("item")
            category = item.get("type") if type(item) is dict else None
            if type(category) is str and category in self.MONITOR_ITEM_TYPES:
                label = category + "." + kind.split(".", 1)[1]
        return f"[codex {label}]\n".encode("ascii")

    def feed(self, data: bytes) -> bytes:
        safe = bytearray()
        parts = data.split(b"\n")
        for index, part in enumerate(parts):
            if not self.dropping:
                if len(self.pending) + len(part) > self.MAX_LINE:
                    self.pending.clear()
                    self.dropping = True
                else:
                    self.pending.extend(part)
            if index < len(parts) - 1:
                if self.dropping:
                    safe.extend(b"[codex oversized event omitted]\n")
                else:
                    safe.extend(self._line(bytes(self.pending)))
                self.pending.clear()
                self.dropping = False
        return bytes(safe)

    def finish(self) -> bytes:
        if self.dropping:
            self.dropping = False
            self.pending.clear()
            return b"[codex oversized event omitted]\n"
        if not self.pending:
            return b""
        result = self._line(bytes(self.pending))
        self.pending.clear()
        return result

    def snapshot(self) -> dict:
        complete = self.turns > 0 and not self.invalid
        return {
            "schema_version": 1,
            "source": "codex_exec_jsonl",
            "status": "invalid" if self.invalid else
                      "reported" if complete else "unavailable",
            "session_id": self.session_id,
            "input_tokens": self.totals["input_tokens"] if complete else None,
            "cached_input_tokens": (self.totals["cached_input_tokens"]
                                    if complete else None),
            "output_tokens": self.totals["output_tokens"] if complete else None,
        }


def _run_codex_with_live_log(command: list[str], prompt: bytes, cwd: Path,
                             evidence: Path, live_log: str,
                             usage: CodexUsageCollector | None = None) -> int:
    """Stream existing type-only evidence and projected safe Monitor events.

    Only a trusted main worker supplies the fixed monitor path. Loss of the
    secondary monitor sink must never discard local engineering evidence.
    """
    try:
        live_fd = os.open(live_log, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    except OSError as exc:
        raise LiveMonitorUnavailable("MONITOR_LOG_UNAVAILABLE") from exc
    try:
        info = os.fstat(live_fd)
        if (info.st_uid != os.geteuid() or
                (info.st_mode & 0o170000) != 0o100000):
            raise LiveMonitorUnavailable("MONITOR_LOG_OWNERSHIP_DENIED")
        usage = usage if usage is not None else CodexUsageCollector()
        monitor_events = CodexUsageCollector(monitor_only=True, workspace=cwd)
        with evidence.open("wb") as trace:
            trace.write(b"=== Codex JSONL event types (sensitive fields omitted) ===\n")
            with subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL) as worker:
                assert worker.stdin is not None and worker.stdout is not None
                try:
                    worker.stdin.write(prompt)
                except BrokenPipeError:
                    pass
                finally:
                    worker.stdin.close()
                while True:
                    chunk = worker.stdout.read1(16384)
                    if not chunk:
                        break
                    safe = usage.feed(chunk)
                    monitor_safe = monitor_events.feed(chunk)
                    trace.write(safe)
                    trace.flush()
                    if live_fd >= 0 and monitor_safe:
                        try:
                            pending = memoryview(monitor_safe)
                            while pending:
                                pending = pending[os.write(live_fd, pending):]
                        except OSError:
                            os.close(live_fd)
                            live_fd = -1
                tail = usage.finish()
                monitor_tail = monitor_events.finish()
                trace.write(tail)
                if live_fd >= 0 and monitor_tail:
                    try:
                        pending = memoryview(monitor_tail)
                        while pending:
                            pending = pending[os.write(live_fd, pending):]
                    except OSError:
                        os.close(live_fd)
                        live_fd = -1
                return worker.wait()
    finally:
        if live_fd >= 0:
            os.close(live_fd)


def run_codex_task(task: dict, *, workspace: Path = ROOT,
                   executor=subprocess.run,
                   task_id: str | None = None,
                   runner_license: dict | None = None) -> dict:
    """Run the owner-authorized Development Mode engineer with real evidence.

    Path 3 may edit candidate engineering sources, Tcl, RTL and documents,
    and invoke approved Vivado builds on the SWPC host. This function does not
    grant physical device access. The fixed PR SHA remains the INPUT identity;
    the candidate Git diff and evidence are captured before review/commit.
    """
    root = workspace.resolve(strict=True)
    evidence = root / ".plasma-path3-evidence"
    require(not evidence.exists() and not evidence.is_symlink(),
            "CODEX_EVIDENCE_PATH_ALREADY_EXISTS")
    evidence.mkdir(mode=0o700)
    if runner_license is not None:
        (evidence / "runner-license-diagnostic.json").write_text(
            json.dumps(runner_license, indent=2, sort_keys=True) + "\n")
    report = evidence / "engineering-report.md"
    codex_log = evidence / "codex.log"
    output_path = task.get("output_path")
    source = root / output_path if output_path else None
    output = (source.with_suffix(
        ".txt" if task.get("output_format") == "text" else ".csv"
    ) if source is not None else None)
    test_log = source.with_suffix(".test.log") if source is not None else None
    # Codex loads the concise root AGENTS.md as the normative entrypoint.
    # Keep task details in reviewed repository Work Orders and read large
    # detailed clauses only when relevant to the approved engineering goal.
    prompt = (
        "PLASMA Path 3 Development Mode. Follow root AGENTS.md and the "
        "owner-approved Work Order at its pinned source SHA. Read only "
        "task-relevant detailed clauses linked from AGENTS.md, including "
        "nested AGENTS.md when affected. Do not preload unrelated runbooks. "
        "Within the existing Gate 1, diagnose, edit RTL/Tcl/Python, run "
        "required builds/tests and fix/retest without another user approval. "
        "Vivado 2026.1 is available only for work within approved scope. "
        "Do not retry unsafe hardware writes; respect live ownership, "
        "root-executor, electrical and rollback guards. Report inaccessible "
        "SWPC/Z2 operations as NOT_RUN, never PASS. "
        "Record actual commands, exits, results and hashes in "
        ".plasma-path3-evidence/engineering-report.md. Edit and test freely "
        "within the approved Work Order. The trusted worker publishes verified "
        "changes to the exact authorized PR after this run, so do not change "
        "Git refs or expose GitHub tokens from inside Codex.\n"
        "Goal:\n" + task["objective"] + "\n"
    )
    if task_id == DYNAMIC_TASKS["path3-codex"]:
        prompt += (
            "Owner Work Order SHA256: " + task["work_order_sha256"] + "\n"
            "Acceptance criteria:\n" + task["acceptance"] + "\n"
        )
    if task_id == "f1b-path3-codex-vivado-build":
        prompt += (
            "For this F1-B task the trusted dispatcher will execute the SAME "
            "fixed Python Build Engine as Path 2 on the licensed runner AFTER "
            "you exit, twice in fresh output directories. Inspect "
            ".plasma-path3-evidence/runner-license-diagnostic.json and record "
            "a category-only sandbox comparison. Do not escape the sandbox. "
            "Host execution accepts only byte-authenticated PL inputs at the "
            "owner-reviewed pinned SHA. Diagnose/edit/test candidate source "
            "here, but changed PL inputs require a reviewed new source pin "
            "before host execution; report that blocker honestly. No candidate "
            "driver or arbitrary command is executed outside the sandbox. "
            "Host results will be appended to your report; do not claim them "
            "in advance. On host failure inspect each run's "
            "plasma-fpga-build-diagnostics.json and preserve the first failure.\n"
        )
    prompt += (
        "In Development Mode, the existing Path 3 engineer may use accessible "
        "SWPC USB and TTY tools for hardware operations explicitly covered "
        "by the Owner's Gate 1 objective. Linux DAC/ACL still applies. "
        "Use the minimum sufficient experiment: stop after one genuine PASS; "
        "after FAIL diagnose and make a targeted retest. No Program, Readback "
        "or Verify quota applies. Within owner-approved Path 3 scope, use the "
        "enrolled Z2 SSH/sudo route for development deployment and privileged "
        "FPGA Manager/MMIO tasks when real permissions permit. Do not inherit "
        "Path 2-only Project/Stage restrictions as Path 3 business policy. "
        "Keep live voltage, device ownership, image identity, and Golden "
        "Restore protections; do not bypass an OS permission denial or "
        "change sudoers. SWPC Codex remains non-root. "
        "Never claim a physical PASS without actual evidence.\n"
    )
    if output_path:
        prompt += (
            "For this legacy task, also update " + output_path +
            " when useful and record its ACTUAL complete output as text "
            "plus a short .test.log, but do not restrict other engineering "
            "edits merely to satisfy the old generated-file convention.\n"
        )
    command = [
        "codex", "--ask-for-approval", "never",
        "-c", "sandbox_workspace_write.network_access=false",
        "exec", "--json", "--sandbox", "workspace-write", "-",
    ]
    if executor is subprocess.run:
        # Production Path 3: one rootless OS-level device-visible namespace.
        # The inner Codex sandbox cannot access the real host's other /dev.
        # Offline tests inject an inert executor and retain the legacy argv.
        import plasma_development_codex_sandbox as codex_sandbox
        command = codex_sandbox.codex_command(root)
    usage = CodexUsageCollector()
    # GitHub Actions job timeout is the operational limit; a fixed 480-second
    # Python timer would terminate normal Vivado implementation.
    # One autonomous Codex invocation owns scoped FIX -> RETEST iterations.
    # Do not launch extra SWPC jobs or grant new hardware permissions to retry.
    live_log = os.environ.get("PLASMA_ENGINEERING_MONITOR_LIVE_LOG")
    live_allowed = (
        executor is subprocess.run and
        live_log == "/run/plasma-codex/engineering-monitor/path3.log" and
        os.environ.get("RUNNER_NAME") == EXPECTED_RUNNER and
        os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted"
    )
    if live_allowed:
        try:
            returncode = _run_codex_with_live_log(
                command, prompt.encode("utf-8"), root, codex_log, live_log,
                usage=usage)
            proc = subprocess.CompletedProcess(command, returncode, b"", b"")
        except LiveMonitorUnavailable:
            # Only pre-execution setup can fall back. Never re-run a Codex
            # command after any part of its real execution has begun.
            # Monitor unavailable: preserve the original real execution path,
            # rather than blocking an authorized engineering task.
            proc = executor(
                command, input=prompt.encode("utf-8"), cwd=root,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=None, check=False,
            )
            codex_log.write_bytes(
                b"=== Codex JSONL event types (sensitive fields omitted) ===\n" +
                usage.feed(proc.stdout) + usage.finish() +
                (b"[codex stderr omitted]\n" if proc.stderr else b""))
    else:
        proc = executor(
            command, input=prompt.encode("utf-8"), cwd=root,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=None, check=False,
        )
        codex_log.write_bytes(
            b"=== Codex JSONL event types (sensitive fields omitted) ===\n" +
            usage.feed(proc.stdout) + usage.finish() +
            (b"[codex stderr omitted]\n" if proc.stderr else b""))
    def digest(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    usage_path = evidence / "codex-token-usage.json"
    usage_snapshot = usage.snapshot()
    # Bounded numeric-only context diagnostics. The size of a repo file is
    # NOT proof of actual Codex instruction loading or a model request count.
    root_agents = root / "AGENTS.md"
    agents_size = None
    if root_agents.is_file() and not root_agents.is_symlink():
        candidate_size = root_agents.stat().st_size
        if 0 <= candidate_size <= 1024 * 1024:
            agents_size = candidate_size
    context_audit = {
        "schema_version": 1,
        "repo_root_agents_bytes": agents_size,
        "dispatched_prompt_bytes": len(prompt.encode("utf-8")),
        "model_request_count": None,
        "model_request_count_status": "NOT_AVAILABLE",
        "actual_instruction_load_status": "NOT_VERIFIED",
    }
    usage_path.write_text(json.dumps(usage_snapshot, indent=2, sort_keys=True) + "\n")
    receipt = {
        "status": "EVIDENCE_READY_REVIEW_REQUIRED",
        "execution_path": "path3-codex",
        "runner": os.environ.get("RUNNER_NAME", "offline-stub"),
        "codex_exit_code": proc.returncode,
        "codex_log_path": str(codex_log.relative_to(root)),
        "codex_log_sha256": digest(codex_log),
        "codex_usage": usage_snapshot,
        "codex_context_audit": context_audit,
        "codex_model_selection": codex_requested_model_settings(command),
        "codex_usage_path": str(usage_path.relative_to(root)),
        "codex_usage_sha256": digest(usage_path),
        "acceptance": "CHATGPT_REVIEW_OF_REAL_OUTPUT_AND_TEST_LOG",
    }
    if report.is_file() and not report.is_symlink():
        receipt.update({
            "engineering_report_path": str(report.relative_to(root)),
            "engineering_report_sha256": digest(report),
        })
    # Preserve backward compatibility with older generated-file tasks;
    # these artifacts are optional rather than a universal Path 3 allowlist.
    if source is not None and source.is_file() and not source.is_symlink():
        receipt.update({"source_path": output_path, "source_sha256": digest(source)})
    if output is not None and output.is_file() and not output.is_symlink():
        receipt.update({
            "output_path": str(output.relative_to(root)),
            "output_sha256": digest(output),
        })
    if test_log is not None and test_log.is_file() and not test_log.is_symlink():
        receipt.update({
            "test_log_path": str(test_log.relative_to(root)),
            "test_log_sha256": digest(test_log),
        })
    evidence_complete = ("engineering_report_sha256" in receipt or
                         all(k in receipt for k in (
                             "source_sha256", "output_sha256", "test_log_sha256")))
    # Preserve the real Codex exit code and evidence even when execution
    # fails. A JSON receipt is NOT acceptance; main() returns nonzero for
    # failure and Actions collects source changes in an always() step.
    if proc.returncode != 0:
        receipt["status"] = "CODEX_EXECUTION_FAILED_REVIEW_REQUIRED"
        receipt["failure_reason"] = "CODEX_CLI_NONZERO"
    # Report completeness is review metadata for both Paths/scopes. Physical
    # progression still requires actual successful execution and root receipts.
    receipt["evidence_complete"] = evidence_complete
    return receipt


def run_licensed_f1b_task(task: dict, *, workspace: Path, req: dict) -> dict:
    """Trusted-main, fixed-task integration. Never a sandbox escape endpoint.

    main() calls this only after worker_admission and live_pr_metadata. No
    request file, socket, candidate command, candidate driver or workflow.
    """
    require(req["task_id"] == "f1b-path3-codex-vivado-build" and
            req["pr_number"] > 0 and req["source_sha"] != req["trusted_sha"],
            "HOST_BUILD_SOURCE_BINDING_DENIED")
    import plasma_vivado_host_build as build  # trusted dispatcher sibling
    baseline = build.license_snapshot()
    receipt = run_codex_task(task, workspace=workspace, task_id=req["task_id"],
                             runner_license=baseline)
    evidence = workspace / ".plasma-path3-evidence"
    report = evidence / "engineering-report.md"
    require(evidence.is_dir() and not evidence.is_symlink() and
            evidence.resolve() == workspace.resolve() / ".plasma-path3-evidence" and
            report.is_file() and not report.is_symlink(), "HOST_REPORT_DENIED")
    result = {"status": "NOT_RUN", "builds": [], "source_sha": req["source_sha"]}
    try:
        require(receipt["codex_exit_code"] == 0, "HOST_BUILD_CODEX_FAILED")
        require(baseline["vivado_startup"]["pass"], "HOST_BUILD_LICENSE_REJECTED")
        source = build.authenticate_host_inputs(workspace, req["source_sha"])
        with (evidence / "host-input-authentication.json").open("x") as stream:
            stream.write(json.dumps(source, indent=2, sort_keys=True) + "\n")
        fixed = parse_json(ROOT / "specs/engineering-dispatch/development-tasks-v1.json"
                           )["tasks"]["fixed-site1-vivado-host-build"]
        fixed = dict(fixed, execution_path="path3-codex")
        approval = {"execution_path": "path3-codex",
                    "execution_capability": "vivado-host-build",
                    "task_id": req["task_id"], "pr_number": req["pr_number"],
                    "trusted_sha": req["trusted_sha"], "pinned_sha": req["source_sha"]}
        for index in (1, 2):
            # Each engine invocation creates a new mkdtemp build directory.
            target = evidence / f"host-build-{index}"
            target.mkdir(mode=0o700)
            build.authenticate_host_inputs(workspace, req["source_sha"])
            actual = build.run(fixed, workspace=workspace, approval=approval,
                               evidence_dir=target, execution_path="path3-codex")
            result["builds"].append(actual)
        require(result["builds"][0]["build_dir"] != result["builds"][1]["build_dir"],
                "HOST_BUILD_OUTPUT_REUSED")
        result["status"] = "PASS"
    except (Denied, build.BuildDenied, OSError, ValueError,
            subprocess.SubprocessError) as exc:
        result["reason"] = safe_error_reason(exc)
        result["status"] = "FAIL" if result["builds"] else "NOT_RUN_OR_FAIL"
        receipt["status"] = "HOST_BUILD_FAILED_REVIEW_REQUIRED"
    with (evidence / "licensed-host-builds.json").open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    # Host output is appended after the sandbox engineer finishes; never infer
    # Build PASS from Codex's exit or from a successful GitHub job.
    require(report.is_file() and not report.is_symlink(), "HOST_REPORT_DENIED")
    with report.open("a") as stream:
        stream.write("\nTrusted runner F1-B execution: " + result["status"] +
                     ". See licensed-host-builds.json and host-build-{1,2}/.\n")
    receipt["engineering_report_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
    receipt["licensed_host_build_status"] = result["status"]
    return receipt

def safe_error_reason(exc: Exception) -> str:
    """Keep one trusted, constant build error code; never leak host paths."""
    if isinstance(exc, Denied):
        return str(exc)
    detail = str(exc)
    if (type(exc).__name__ == "CodexSandboxDenied" and
            re.fullmatch(r"CODEX_SANDBOX_[A-Z0-9_]{3,80}", detail) is not None):
        # Auditable fixed category, not the host path or exception traceback.
        return detail
    if type(exc).__name__ in ("RuntimeDenied", "QualificationDenied"):
        if re.fullmatch(r"PATH2_[A-Z0-9_]{3,80}|BUILD_[A-Z0-9_]{3,80}", detail):
            return detail
    if (type(exc).__name__ == "BuildDenied" and
            re.fullmatch(r"BUILD_[A-Z0-9_]{3,80}", detail) is not None):
        return detail
    return "EXECUTION_ERROR"


def live_pr_metadata(req: dict) -> dict | None:
    """Worker independently queries GitHub; never trust a cached admission snapshot."""
    if not req["pr_number"]:
        return None
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/pulls/{req['pr_number']}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=15)
        require(len(result.stdout) <= 262144, "LIVE_PR_RESPONSE_TOO_LARGE")
        pr = json.loads(result.stdout)
        verify_pr(pr, req)
        return pr
    except (OSError, ValueError, subprocess.SubprocessError):
        raise Denied("LIVE_PR_VERIFICATION_FAILED") from None


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
    parser.add_argument("--work-order-sha256")
    parser.add_argument("--execution-capability")
    parser.add_argument("--resume-phase", choices=("new", "resume"))
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
                # Single worker admission path for Path 2/3; retains the
                # independent SWPC checks of trusted main SHA, candidate SHA
                # and registry SHA256 before any task executes.
                admission = worker_admission(req, args, registry, event)
                pr = live_pr_metadata(req)
                if args.action == "execute-codex":
                    # Keep the step-scoped live PR token out of Codex and Vivado.
                    os.environ.pop("GH_TOKEN", None)
                task = task_for_request(registry, req, event)
                task_approval = (authorize(event, os.environ, registry, pr_info=pr)
                                 if task.get("capability") in
                                    ("z2-cpu-only", "vivado-host-build", "path2-stage-contract")
                                 else None)
                # One fixed main-only Path 2 observation. Executed by
                # trusted main, not candidate code and NEVER by Codex.
                if task.get("native_preflight") == NATIVE_PREFLIGHT:
                    require(args.action == "execute" and
                            req["task_id"] == DYNAMIC_TASKS["path2-cli"] and
                            req["pr_number"] == 0 and
                            req["source_sha"] == req["trusted_sha"] ==
                                os.environ.get("GITHUB_SHA") and
                            os.environ.get("GITHUB_JOB") == "development-execute" and
                            os.environ.get("GITHUB_RUN_ATTEMPT") == "1" and
                            os.environ.get("RUNNER_NAME") == EXPECTED_RUNNER and
                            os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted" and
                            task["capability"] == "cpu-only" and
                            task["work_order_scope"] == "host-only" and
                            args.resume_phase is None,
                            "NATIVE_PREFLIGHT_WORKER_DENIED")
                    import plasma_codex_native_preflight as native
                    try:
                        receipt = native.inspect()
                    except native.PreflightDenied as exc:
                        if str(exc) != "NATIVE_PATH_PERMISSIONS_DENIED":
                            raise Denied(str(exc)) from None
                        # Only static, separately validated category fields.
                        # Never include any observed host path or uid/gid.
                        require(exc.stage in native.SAFE_PERMISSION_STAGES and
                                exc.cause in native.SAFE_PERMISSION_CAUSES and
                                type(exc.component_index) is int and
                                1 <= exc.component_index <= 24,
                                "NATIVE_DIAGNOSTIC_FIELDS_DENIED")
                        receipt = {
                            "schema": "plasma.codex.native_preflight.v1",
                            "status": "NOT_RUN_OR_FAIL",
                            "reason": "NATIVE_PATH_PERMISSIONS_DENIED",
                            "denial_stage": exc.stage,
                            "denial_cause": exc.cause,
                            "denial_component_index": exc.component_index,
                            "model_session": "NOT_RUN",
                            "hardware_access": "NOT_RUN",
                            "provenance": "NOT_INDEPENDENTLY_VERIFIED",
                            "sha256_pin_authorized": False,
                        }
                # This exact CPU-only fixture is the ONLY cross-Job route.
                # Unflagged Path 3 retains its existing single-exec behavior.
                elif task.get("session_resume") or args.resume_phase:
                    require(args.action == "execute-codex" and
                            task.get("session_resume") == "page-boundary-off-by-one"
                            and args.resume_phase in ("new", "resume"),
                            "RESUME_EXPLICIT_PHASE_DENIED")
                    import plasma_path3_cross_job_resume as crossjob
                    try:
                        receipt = crossjob.execute(
                            args.resume_phase,
                            {**req, "execution_path": task["execution_path"]},
                            args.workspace)
                    except crossjob.ResumeDenied as exc:
                        raise Denied(str(exc)) from None
                else:
                    receipt = (
                        (run_licensed_f1b_task(task, workspace=args.workspace, req=req)
                         if req["task_id"] == "f1b-path3-codex-vivado-build"
                         else run_codex_task(task, workspace=args.workspace,
                                             task_id=req["task_id"]))
                        if args.action == "execute-codex"
                        else run_task(task, workspace=args.workspace,
                                      evidence_dir=args.evidence_dir,
                                      approval=task_approval,
                                      sandbox=task.get("capability", "cpu-only") == "cpu-only")
                    )
                plan = {
                    **receipt, **req,
                    "task_id": req["task_id"],
                    "pinned_sha": req["source_sha"],
                    "registry_sha256": args.registry_sha256,
                    "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
                    "worker_admission": admission,
                }
                task_failed = (
                    (args.action == "execute-codex"
                     and receipt.get("status") != (
                         "NEW_EXPECTED_TEST_FAIL" if args.resume_phase == "new"
                         else "RESUME_FIX_PASS" if args.resume_phase == "resume"
                         else "EVIDENCE_READY_REVIEW_REQUIRED"))
                    or (task.get("native_preflight") == NATIVE_PREFLIGHT
                        and receipt.get("status") != "OBSERVED")
                )
            else:
                plan = authorize(event, os.environ, registry, pr)
                plan["registry_sha256"] = hashlib.sha256(
                    args.registry.read_bytes()
                ).hexdigest()
        print(json.dumps(plan, sort_keys=True))
        return 2 if args.action in ("execute", "execute-codex") and task_failed else 0
    except (Denied, OSError, UnicodeError, json.JSONDecodeError,
            subprocess.SubprocessError, ValueError) as exc:
        print(json.dumps({
            "status": "NOT_RUN_OR_FAIL",
            "reason": safe_error_reason(exc),
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
