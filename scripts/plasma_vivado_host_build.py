#!/usr/bin/env python3
"""Trusted Path 2 fixed Vivado HOST build. No target load, device or deployment.

A reviewed main-only owner Issue #981 request is mandatory. The CLI selection
is a typed project name, not arbitrary bash/python from a candidate PR.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

EXPECTED_RUNNER = "SWPC-plasma-codex"
BOARD_SHA40 = re.compile(r"[a-f0-9]{40}\Z")
PROJECT_NAME = re.compile(r"pl/projects/[a-z0-9-]{3,70}\Z")
ROOT_FOR_BUILDS = Path("/storage/projects/plasma/pl/build")
SETTINGS64 = Path("/storage/tools/xilinx/2026.1/Vivado/settings64.sh")


class BuildDenied(ValueError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise BuildDenied(code)


def _read_safe_file(path: Path) -> str:
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size <= 65536, "BUILD_SOURCE_DENIED")
    return path.read_text(encoding="utf-8")


def preflight(task: dict, *, workspace: Path, approval: dict,
              env: dict | None = None) -> dict:
    """Pure source/authorization contract, runnable in hosted negative tests."""
    env = os.environ if env is None else env
    require(type(task) is dict and set(task) == {
        "execution_path", "capability", "project", "toolchain",
        "board_repo_sha"
    }, "BUILD_TASK_FIELDS_DENIED")
    require(task["execution_path"] == "path2-cli" and
            task["capability"] == "vivado-host-build" and
            type(task["project"]) is str and
            PROJECT_NAME.fullmatch(task["project"]) is not None,
            "BUILD_CAPABILITY_OR_PROJECT_DENIED")
    require(task["toolchain"] == "2026.1" and
            type(task["board_repo_sha"]) is str and
            BOARD_SHA40.fullmatch(task["board_repo_sha"]) is not None,
            "BUILD_VERSION_OR_BOARD_DENIED")
    require(type(approval) is dict and
            approval.get("execution_capability") == "vivado-host-build" and
            approval.get("execution_path") == "path2-cli" and
            approval.get("task_id") == "fixed-site1-vivado-host-build" and
            type(approval.get("pinned_sha")) is str and
            BOARD_SHA40.fullmatch(approval["pinned_sha"]) is not None and
            type(approval.get("trusted_sha")) is str and
            BOARD_SHA40.fullmatch(approval["trusted_sha"]) is not None and
            ((approval.get("pr_number") == 0 and
              approval["pinned_sha"] == approval["trusted_sha"]) or
             (type(approval.get("pr_number")) is int and
              approval["pr_number"] > 0 and
              approval["pinned_sha"] != approval["trusted_sha"])),
            "BUILD_APPROVED_SOURCE_BINDING_DENIED")
    require(env.get("GITHUB_REPOSITORY") == "physicslu/plasma" and
            env.get("RUNNER_NAME") == EXPECTED_RUNNER and
            env.get("RUNNER_ENVIRONMENT") == "self-hosted" and
            env.get("GITHUB_EVENT_NAME") == "issue_comment" and
            env.get("GITHUB_REF") == "refs/heads/main" and
            env.get("GITHUB_RUN_ATTEMPT") == "1" and
            env.get("GITHUB_SHA") == approval["trusted_sha"],
            "BUILD_OWNER_RUNNER_CONTEXT_DENIED")
    root = workspace.resolve(strict=True)
    project = workspace / task["project"]
    require(project.is_dir() and not project.is_symlink() and
            project.resolve().is_relative_to(root),
            "BUILD_PROJECT_LOCATION_DENIED")
    files = [project / name for name in (
        "create_project.tcl", "create_block_design.tcl",
        "build_bitstream.tcl", "verify_hwh.py"
    )]
    texts = [_read_safe_file(p) for p in files]
    # These are reviewed trusted-main Tcl files; nevertheless refuse obvious
    # target programming / shell breakout commands before running any tool.
    forbidden = re.compile(
        r"\b(?:open_hw|connect_hw_server|program_hw_devices|write_cfgmem|"
        r"exec|openocd|ssh|scp|sudo)\b|/dev/(?:mem|uio)|fpga_manager",
        re.IGNORECASE
    )
    for s in texts[:3]:
        # Remove full-line comments before checking Tcl command tokens.
        code = "\n".join(line for line in s.splitlines()
                         if not line.lstrip().startswith("#"))
        require(not forbidden.search(code), "BUILD_FORBIDDEN_TCL_COMMAND")
    require("launch_runs synth_1" in texts[2] and
            "launch_runs impl_1" in texts[2] and
            "report_timing_summary" in texts[2] and
            "get_drc_violations" in texts[2],
            "BUILD_IMPLEMENTATION_GATES_MISSING")
    return {"project": str(project.resolve()),
            "script": str(files[2].resolve()),
            "verifier": str(files[3].resolve()),
            "source_sha": approval["pinned_sha"],
            "toolchain": task["toolchain"],
            "board_sha": task["board_repo_sha"]}


def _run_checked(args: list[str], *, executor, cwd: Path, timeout: int,
                 env: dict) -> bytes:
    proc = executor(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=timeout, check=False)
    require(proc.returncode == 0 and len(proc.stdout) <= 65536 and
            len(proc.stderr) <= 65536, "BUILD_PREFLIGHT_COMMAND_FAILED")
    return proc.stdout.strip()


def resolve_board_repository(task: dict, *, workspace: Path,
                             executor=subprocess.run,
                             env: dict | None = None) -> Path:
    """Invoke the existing SHA-pinned Z2 board helper, retaining overrides."""
    env = os.environ if env is None else env
    board_value = env.get("PLASMA_BOARD_REPO", "")
    if not board_value:
        script = workspace / "pl/projects/z2-swd-gpio/prepare-board-repository.sh"
        require(script.is_file() and not script.is_symlink() and
                script.resolve().is_relative_to(workspace.resolve()),
                "BUILD_BOARD_PREPARE_SCRIPT_MISSING")
        content = _read_safe_file(script)
        expected_pin = "source_commit=" + chr(34) + task["board_repo_sha"] + chr(34)
        require(expected_pin in content.splitlines() and
                "source_url=" + chr(34) +
                "https://github.com/xupsh/pynq-supported-board-file.git" + chr(34)
                in content.splitlines(), "BUILD_BOARD_PREPARE_PIN_MISMATCH")
        proc = executor(
            ["/usr/bin/bash", str(script.resolve())],
            cwd=workspace.resolve(),
            env={"PATH": "/usr/bin:/bin",
                 "HOME": env.get("HOME", "/nonexistent"),
                 "GIT_TERMINAL_PROMPT": "0"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=180, check=False,
        )
        require(proc.returncode == 0 and len(proc.stdout) <= 4096 and
                len(proc.stderr) <= 65536, "BUILD_BOARD_PREPARE_FAILED")
        try:
            board_value = proc.stdout.decode("utf-8").strip()
        except UnicodeError as exc:
            raise BuildDenied("BUILD_BOARD_PREPARE_OUTPUT_INVALID") from exc
    require(board_value.startswith("/") and ".." not in board_value,
            "BUILD_BOARD_REPO_PATH_DENIED")
    board = Path(board_value)
    require(board.is_dir() and not board.is_symlink(),
            "BUILD_BOARD_REPO_MISSING")
    return board

def run(task: dict, *, workspace: Path, approval: dict,
        evidence_dir: Path | None = None,
        executor=subprocess.run) -> dict:
    plan = preflight(task, workspace=workspace, approval=approval)
    require(os.geteuid() != 0, "BUILD_ROOT_USER_DENIED")
    require(evidence_dir is not None and evidence_dir.is_dir() and
            not evidence_dir.is_symlink(), "BUILD_EVIDENCE_DIR_REQUIRED")
    require(SETTINGS64.is_file() and not SETTINGS64.is_symlink(),
            "BUILD_VIVADO_SETTINGS_UNAVAILABLE")
    # Existing board preparation uses its own pinned cache or first-fetch.
    board = resolve_board_repository(task, workspace=workspace,
                                     executor=executor)
    require(ROOT_FOR_BUILDS.is_dir() and
            not ROOT_FOR_BUILDS.is_symlink(),
            "BUILD_OUTPUT_ROOT_MISSING")
    source_root = workspace.resolve(strict=True)
    check_env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
    actual_board_sha = _run_checked(
        ["git", "-C", str(board), "rev-parse", "HEAD"],
        executor=executor, cwd=source_root, timeout=10, env=check_env
    ).decode("ascii")
    require(actual_board_sha == plan["board_sha"], "BUILD_BOARD_SHA_MISMATCH")
    status = _run_checked(
        ["git", "-C", str(board), "status", "--porcelain", "--untracked-files=no"],
        executor=executor, cwd=source_root, timeout=10, env=check_env
    )
    require(status == b"", "BUILD_BOARD_REPO_DIRTY")
    source_sha = _run_checked(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        executor=executor, cwd=source_root, timeout=10, env=check_env
    ).decode("ascii")
    require(source_sha == plan["source_sha"], "BUILD_SOURCE_SHA_MISMATCH")
    # Unique directory, never overwrite historic PSPL, LT02 or Fixed output.
    build = Path(tempfile.mkdtemp(prefix="fixed-f1-", dir=ROOT_FOR_BUILDS))
    (build / "reports").mkdir()
    args = [
        "/usr/bin/bash", "-c",
        'set -euo pipefail; source "$1"; exec vivado -mode batch '
        '-nojournal -log "$2" -source "$3"',
        "plasma-fixed-f1", str(SETTINGS64),
        str(build / "vivado.log"), plan["script"],
    ]
    build_env = {
        "PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/nonexistent"),
        "PLASMA_F1_BUILD": str(build),
        "PLASMA_BOARD_REPO": str(board),
        "PLASMA_VIVADO_JOBS": "4",
    }
    try:
        proc = executor(args, cwd=source_root, env=build_env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=2400, check=False)
        # Logs are bounded so an unexpected tool run cannot swamp Actions.
        require(len(proc.stdout) <= 2_000_000 and
                len(proc.stderr) <= 2_000_000,
                "BUILD_LOG_EXCESSIVE")
        (build / "vivado-stdout.log").write_bytes(proc.stdout)
        (build / "vivado-stderr.log").write_bytes(proc.stderr)
        require(proc.returncode == 0 and
                b"FIXED_F1_BITSTREAM_BUILD_PASS_HOST_ONLY_NOT_Z2" in proc.stdout,
                "BUILD_VIVADO_IMPLEMENTATION_FAILED")
        proj = build / "project"
        hwh = proj / "z2_fixed_unified_site1.gen/sources_1/bd/system/hw_handoff/system.hwh"
        bit = proj / "z2_fixed_unified_site1.runs/impl_1/system_wrapper.bit"
        verifier_spec = importlib.util.spec_from_file_location(
            "plasma_f1_host_hwh_verify", plan["verifier"])
        require(verifier_spec is not None and verifier_spec.loader is not None,
                "BUILD_VERIFIER_UNAVAILABLE")
        mod = importlib.util.module_from_spec(verifier_spec)
        verifier_spec.loader.exec_module(mod)
        receipt = mod.verify_artifacts(
            hwh=hwh, bit=bit, reports=build / "reports",
            source_sha=plan["source_sha"]
        )
        receipt.update({
            "status": "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED",
            "execution_path": "path2-cli",
            "execution_capability": "vivado-host-build",
            "build_dir": str(build),
            "vivado_stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
            "vivado_stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(),
            "z2_hil": "NOT_RUN",
            "physical_load": "NOT_RUN",
            "m1": "NO_GO",
        })
        text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        require(len(text) <= 65536, "BUILD_EVIDENCE_TOO_LARGE")
        (evidence_dir / "plasma-path2-vivado-host-receipt.json").write_text(text)
        return receipt
    except Exception:
        # Retain uniquely scoped diagnostics on failure; never roll into a
        # success receipt or attempt a retry of uncertain tool work.
        raise
