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
    if task_id in ("z2-path2-download", "z2-path2-testing"):
        expected = {"z2-path2-download": "download", "z2-path2-testing": "test"}
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
    task = task_by_id(registry, req["task_id"])
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
        require(context.get("GITHUB_RUN_ATTEMPT") == "1",
                "HOST_BUILD_RERUN_DENIED")
    return {
        "status": "AUTHORIZED_DEV_TASK",
        **req,
        "pinned_sha": req["source_sha"],
        "execution_path": task["execution_path"],
        "execution_capability": (
            "z2-cpu-only" if req["task_id"] == "hil-a2-cpu-only"
            else task.get("capability", "cpu-only")
                 if task["execution_path"] == "path2-cli"
            else "codex-workspace"
        ),
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
        return integration.disabled_hardware_stage(task, approval)
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
    require(proc.returncode == 0 and proc.stderr == b"", "COMMAND_FAILED")
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


def run_codex_task(task: dict, *, workspace: Path = ROOT,
                   executor=subprocess.run,
                   task_id: str | None = None) -> dict:
    """Run the owner-authorized Development Mode engineer with real evidence.

    Path 3 may edit candidate engineering sources, Tcl, RTL and documents,
    and invoke host-only Vivado. The fixed PR SHA remains the INPUT identity;
    the candidate Git diff and evidence are captured before review/commit.
    """
    root = workspace.resolve(strict=True)
    evidence = root / ".plasma-path3-evidence"
    require(not evidence.exists() and not evidence.is_symlink(),
            "CODEX_EVIDENCE_PATH_ALREADY_EXISTS")
    evidence.mkdir(mode=0o700)
    report = evidence / "engineering-report.md"
    codex_log = evidence / "codex.log"
    output_path = task.get("output_path")
    source = root / output_path if output_path else None
    output = (source.with_suffix(
        ".txt" if task.get("output_format") == "text" else ".csv"
    ) if source is not None else None)
    test_log = source.with_suffix(".test.log") if source is not None else None
    prompt = (
        "PLASMA Development Mode Path 3: you are the autonomous engineer. "
        "Prioritize completing the user-approved engineering goal quickly. "
        "Run tools, diagnose failures, edit RTL/Tcl/Python/build scripts/docs, "
        "repeat tests and host builds as needed. Do not stop at an offline "
        "mock when a real Vivado Host-only build is needed.\n"
        "Goal:\n" + task["objective"] + "\n"
        "You may edit files inside this candidate workspace and run "
        "commands required for development, including Vivado 2026.1 "
        "synthesis/implementation/timing/DRC and BIT/HWH generation. "
        "Host-only Vivado does not equal FPGA programming.\n"
        "Record actual commands, exit codes, observed errors, proven versus "
        "hypothesized root causes, minimal fixes, retries, final build "
        "stage results and hashes in .plasma-path3-evidence/engineering-report.md. "
        "Include a chronological problem/solution ledger. Do not fabricate "
        "PASS or claim BIT/HWH if not produced. Preserve relevant raw build "
        "logs/reports/artifacts under the workspace. The workflow captures "
        "your complete tracked-source Git diff, newly created files and "
        "this report for review; do not commit, push or change Git refs.\n"
    )
    if task_id == "f1b-path3-codex-vivado-build":
        prompt += (
            "For this F1-B task, run every Vivado build through the SAME "
            "reviewed host-only Python Build Engine as Path 2: "
            "python3 scripts/plasma_vivado_host_build.py "
            "--path3-engineering-host-only "
            "--evidence-dir .plasma-path3-evidence. "
            "Use the authorized task-specific environment supplied by the "
            "trusted dispatcher, never synthesize fake admission variables. "
            "The engine owns board preparation, license propagation, "
            "worktree build directories, stage receipts, BIT/HWH and SHA256. "
            "On failure inspect plasma-fpga-build-diagnostics.json first; "
            "retain the first observed error and never assert an unproven "
            "root cause. Do not bypass the engine with a separate Vivado "
            "invocation or fabricate successful evidence.\n"
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
        "-c", "sandbox_workspace_write.network_access=true",
        "exec", "--sandbox", "workspace-write", "-",
    ]
    # GitHub Actions job timeout is the operational limit; a fixed 480-second
    # Python timer would terminate normal Vivado implementation.
    proc = executor(
        command, input=prompt.encode("utf-8"), cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=None, check=False,
    )
    codex_log.write_bytes(b"=== Codex stdout ===\n" + proc.stdout +
                          b"\n=== Codex stderr ===\n" + proc.stderr)
    require(proc.returncode == 0, "CODEX_CLI_NONZERO")
    def digest(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    receipt = {
        "status": "EVIDENCE_READY_REVIEW_REQUIRED",
        "execution_path": "path3-codex",
        "runner": os.environ.get("RUNNER_NAME", "offline-stub"),
        "codex_exit_code": proc.returncode,
        "codex_log_path": str(codex_log.relative_to(root)),
        "codex_log_sha256": digest(codex_log),
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
    require("engineering_report_sha256" in receipt or
            all(k in receipt for k in (
                "source_sha256", "output_sha256", "test_log_sha256")),
            "CODEX_EVIDENCE_INCOMPLETE")
    return receipt

def safe_error_reason(exc: Exception) -> str:
    """Keep one trusted, constant build error code; never leak host paths."""
    if isinstance(exc, Denied):
        return str(exc)
    detail = str(exc)
    if (type(exc).__name__ == "BuildDenied" and
            re.fullmatch(r"BUILD_[A-Z0-9_]{3,80}", detail) is not None):
        return detail
    return "EXECUTION_ERROR"


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
    parser.add_argument("--execution-capability")
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
                expected_capability = (
                    "z2-cpu-only" if req["task_id"] == "hil-a2-cpu-only"
                    else task.get("capability", "cpu-only")
                         if task["execution_path"] == "path2-cli"
                    else "codex-workspace"
                )
                require(args.execution_capability in (None, expected_capability),
                        "CAPABILITY_ROUTE_MISMATCH")
                require(task["execution_path"] == (
                    "path3-codex" if args.action == "execute-codex"
                    else "path2-cli"
                ), "WRONG_EXECUTION_PATH")
                task_approval = (authorize(event, os.environ, registry, pr_info=pr)
                                 if task.get("capability") in
                                    ("z2-cpu-only", "vivado-host-build", "path2-stage-contract")
                                 else None)
                receipt = (
                    run_codex_task(task, workspace=args.workspace,
                                   task_id=req["task_id"])
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
            "reason": safe_error_reason(exc),
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
