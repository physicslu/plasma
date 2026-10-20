#!/usr/bin/env python3
"""Trusted Path 2 fixed Vivado HOST build. No target load, device or deployment.

A reviewed owner Issue #981 request is mandatory. It may pin trusted main
or the exact head of an explicitly authorized open owner PR. The CLI
selection is a typed fixed project, not arbitrary bash/python. Existing
F1-B build_bitstream.tcl, PYNQ-Z2 board helper and verify_hwh.py are reused;
this driver does not implement a second Vivado build workflow.
"""
from __future__ import annotations

import errno
import hashlib
import argparse
import sys
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
SETTINGS64 = Path("/storage/tools/xilinx/2026.1/Vivado/settings64.sh")


class BuildDenied(ValueError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise BuildDenied(code)


def diagnostics_type():
    """Load the co-versioned diagnostics beside the reviewed driver.

    A pinned candidate PR may introduce this library before it reaches trusted
    main; loading an unrelated trusted-main copy would violate source pairing.
    """
    source = Path(__file__).resolve().with_name(
        "plasma_fpga_build_diagnostics.py")
    require(source.is_file() and not source.is_symlink() and
            source.stat().st_size <= 65536,
            "BUILD_DIAGNOSTICS_LIBRARY_DENIED")
    spec = importlib.util.spec_from_file_location(
        "plasma_reviewed_fpga_diagnostics", source)
    require(spec is not None and spec.loader is not None,
            "BUILD_DIAGNOSTICS_LIBRARY_INVALID")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DiagnosticSession



def discover_vivado_license(*, env: dict | None = None,
                            settings: Path | None = None) -> dict[str, str]:
    """Resolve one existing Xilinx.lic from a pinned installed tool tree.

    The root is derived from the fixed, trusted Vivado installation, never
    candidate worktree, arbitrary HOME, or PR/task text. Only metadata is
    inspected: no license contents are read, modified, logged or uploaded.
    """
    env = os.environ if env is None else env
    settings = SETTINGS64 if settings is None else settings
    require(settings.name == "settings64.sh" and
            settings.parent.name == "Vivado",
            "BUILD_LICENSE_TOOL_ROOT_DENIED")
    root = settings.parents[2]
    require(root.is_dir() and not root.is_symlink(),
            "BUILD_LICENSE_TOOL_ROOT_DENIED")
    trusted_root = root.resolve(strict=True)

    def checked_file(value: str) -> str:
        require(type(value) is str and 0 < len(value) <= 1024 and
                value.startswith("/") and not any(ord(c) < 32 for c in value),
                "BUILD_LICENSE_SOURCE_DENIED")
        path = Path(value)
        require(path.name == "Xilinx.lic" and not path.is_symlink() and
                path.is_file(), "BUILD_LICENSE_SOURCE_DENIED")
        # Reject symlinks in any parent component, not just the leaf.
        require(path.resolve(strict=True).is_relative_to(trusted_root) and
                path.resolve(strict=True) == path,
                "BUILD_LICENSE_SOURCE_DENIED")
        require(os.access(path, os.R_OK), "BUILD_LICENSE_FILE_UNREADABLE")
        require(0 < path.stat().st_size <= 1024 * 1024,
                "BUILD_LICENSE_FILE_INVALID")
        return str(path)

    # Deterministic, host-verified license. Never scan installed tools.
    fixed = trusted_root / "xic" / "Xilinx.lic"
    inherited = [env.get(key) for key in (
        "XILINXD_LICENSE_FILE", "LM_LICENSE_FILE") if env.get(key)]
    if inherited:
        require(all(value == inherited[0] for value in inherited),
                "BUILD_LICENSE_SOURCE_AMBIGUOUS")
        require(inherited[0] == str(fixed),
                "BUILD_LICENSE_SOURCE_DENIED")
    require(fixed.is_file(), "BUILD_LICENSE_NOT_FOUND")
    return {"XILINXD_LICENSE_FILE": checked_file(str(fixed))}


def _read_safe_file(path: Path) -> str:
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size <= 65536, "BUILD_SOURCE_DENIED")
    return path.read_text(encoding="utf-8")


def preflight(task: dict, *, workspace: Path, approval: dict,
              env: dict | None = None,
              execution_path: str = "path2-cli") -> dict:
    """Pure source/authorization contract, runnable in hosted negative tests."""
    env = os.environ if env is None else env
    require(type(task) is dict and set(task) == {
        "execution_path", "capability", "project", "toolchain",
        "board_repo_sha"
    }, "BUILD_TASK_FIELDS_DENIED")
    require(execution_path in ("path2-cli", "path3-codex") and
            task["execution_path"] == execution_path and
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
            approval.get("execution_path") == execution_path and
            approval.get("task_id") in (
                ("fixed-site1-vivado-host-build", "z2-path2-build")
                if execution_path == "path2-cli"
                else ("f1b-path3-codex-vivado-build",)
            ) and
            type(approval.get("pinned_sha")) is str and
            BOARD_SHA40.fullmatch(approval["pinned_sha"]) is not None and
            type(approval.get("trusted_sha")) is str and
            BOARD_SHA40.fullmatch(approval["trusted_sha"]) is not None and
            ((approval.get("pr_number") == 0 and
              approval["pinned_sha"] == approval["trusted_sha"] and
              execution_path == "path2-cli") or
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
    if execution_path == "path3-codex":
        require(env.get("PLASMA_FPGA_PATH3_APPROVED") == "1" and
                env.get("PLASMA_FPGA_PINNED_SHA") == approval["pinned_sha"] and
                env.get("PLASMA_FPGA_PR_NUMBER") ==
                str(approval["pr_number"]),
                "BUILD_PATH3_ADMISSION_DENIED")
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
        try:
            proc = executor(
                ["/usr/bin/bash", str(script.resolve())],
                cwd=workspace.resolve(),
                env={"PATH": "/usr/bin:/bin",
                     "HOME": env.get("HOME", "/nonexistent"),
                     "GIT_TERMINAL_PROMPT": "0"},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=180, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise BuildDenied("BUILD_BOARD_PREPARE_TIMEOUT") from exc
        except OSError as exc:
            raise BuildDenied("BUILD_BOARD_PREPARE_LAUNCH_FAILED") from exc
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


def prepare_host_build_dir(workspace: Path) -> Path:
    """Reuse Git-ignored candidate/pl/build; never mutate persistent SWPC root."""
    root = workspace.resolve(strict=True)
    output = root / "pl/build"
    require(output.is_dir() and not output.is_symlink() and
            output.resolve().is_relative_to(root), "BUILD_OUTPUT_ROOT_MISSING")
    try:
        result = Path(tempfile.mkdtemp(prefix="fixed-f1-", dir=output))
        (result / "reports").mkdir()
    except OSError as exc:
        # Stage-specific constant codes retain a useful failure signal while
        # keeping private host paths and OS error messages out of the receipt.
        code = {
            errno.EACCES: "BUILD_OUTPUT_PERMISSION_DENIED",
            errno.EPERM: "BUILD_OUTPUT_PERMISSION_DENIED",
            errno.EROFS: "BUILD_OUTPUT_READ_ONLY",
            errno.ENOSPC: "BUILD_OUTPUT_NO_SPACE",
        }.get(exc.errno, "BUILD_OUTPUT_CREATE_FAILED")
        raise BuildDenied(code) from exc
    return result


def _run_pipeline(task: dict, *, workspace: Path, approval: dict,
                  evidence_dir: Path, executor, diagnostics,
                  execution_path: str) -> dict:
    diagnostics.enter("PREFLIGHT")
    plan = preflight(task, workspace=workspace, approval=approval,
                     execution_path=execution_path)
    require(os.geteuid() != 0, "BUILD_ROOT_USER_DENIED")
    require(evidence_dir is not None and evidence_dir.is_dir() and
            not evidence_dir.is_symlink(), "BUILD_EVIDENCE_DIR_REQUIRED")
    diagnostics.check("vivado_settings_readable",
                      SETTINGS64.is_file() and not SETTINGS64.is_symlink())
    require(SETTINGS64.is_file() and not SETTINGS64.is_symlink(),
            "BUILD_VIVADO_SETTINGS_UNAVAILABLE")
    try:
        # Fail before Board checkout / Vivado if discovery is unsafe or absent.
        license_env = discover_vivado_license()
    except BuildDenied:
        diagnostics.check("license_environment_present", False)
        raise
    diagnostics.check("license_environment_present", True)
    diagnostics.enter("BOARD_PREPARE")
    # Existing board preparation uses its own pinned cache or first-fetch.
    board = resolve_board_repository(task, workspace=workspace,
                                     executor=executor)
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
    diagnostics.enter("OUTPUT_PREPARE")
    # Use the same candidate/worktree-local ignored pl/build already created
    # by the pinned board helper; the historical SWPC root is not writable by
    # plasma-codex (observed on Run 39277523452).
    build = prepare_host_build_dir(workspace)
    diagnostics.check("build_root_writable", True)
    diagnostics.enter("VIVADO_IMPLEMENTATION")
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
    # Use the already checked, allowlisted license; never export its location
    # into diagnostic JSON, receipt, Workflow output or command arguments.
    build_env.update(license_env)
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
        diagnostics.artifact("vivado_stdout", build / "vivado-stdout.log")
        diagnostics.artifact("vivado_stderr", build / "vivado-stderr.log")
        require(proc.returncode == 0 and
                b"FIXED_F1_BITSTREAM_BUILD_PASS_HOST_ONLY_NOT_Z2" in proc.stdout,
                "BUILD_VIVADO_IMPLEMENTATION_FAILED")
        diagnostics.enter("ARTIFACT_VERIFY")
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
        for name, path in (("bit", bit), ("hwh", hwh),
                           ("timing_summary", build / "reports/timing_summary.rpt"),
                           ("drc", build / "reports/drc.rpt"),
                           ("methodology", build / "reports/methodology.rpt"),
                           ("check_timing", build / "reports/check_timing.rpt")):
            diagnostics.artifact(name, path)
        diagnostics.enter("EVIDENCE_WRITE")
        receipt.update({
            "status": "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED",
            "execution_path": execution_path,
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
        receipt_file = evidence_dir / "plasma-path2-vivado-host-receipt.json"
        receipt_file.write_text(text)
        diagnostics.artifact("host_receipt", receipt_file)
        diagnostics.complete()
        return receipt
    except Exception:
        # Retain uniquely scoped diagnostics on failure; never roll into a
        # success receipt or attempt a retry of uncertain tool work.
        raise


def run(task: dict, *, workspace: Path, approval: dict,
        evidence_dir: Path | None = None, executor=subprocess.run,
        execution_path: str = "path2-cli") -> dict:
    """Both authorized paths use this same host build and diagnostic engine."""
    require(evidence_dir is not None and evidence_dir.is_dir() and
            not evidence_dir.is_symlink(), "BUILD_EVIDENCE_DIR_REQUIRED")
    diagnostic = diagnostics_type()(
        execution_path=execution_path, source_sha=approval.get("pinned_sha", ""),
        evidence_dir=evidence_dir,
    )
    pipeline_failed = False
    try:
        return _run_pipeline(task, workspace=workspace, approval=approval,
                             evidence_dir=evidence_dir, executor=executor,
                             diagnostics=diagnostic, execution_path=execution_path)
    except Exception as exc:
        pipeline_failed = True
        diagnostic.fail(exc)
        raise
    finally:
        try:
            diagnostic.persist()
        except (OSError, ValueError):
            # Never report build success without a persisted diagnostic.
            # On build failure, preserve the earlier first exception.
            if not pipeline_failed:
                raise


def main(argv: list[str] | None = None) -> int:
    """Dedicated Path 3 host-only entry; NO generic command or Tcl injection."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--path3-engineering-host-only", action="store_true",
                        required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    approved = os.environ.get("PLASMA_FPGA_PATH3_APPROVED") == "1"
    pinned = os.environ.get("PLASMA_FPGA_PINNED_SHA", "")
    trusted = os.environ.get("GITHUB_SHA", "")
    pr = os.environ.get("PLASMA_FPGA_PR_NUMBER", "")
    if not (approved and BOARD_SHA40.fullmatch(pinned) and
            BOARD_SHA40.fullmatch(trusted) and pr.isdecimal() and
            int(pr) > 0 and pinned != trusted):
        print('{"status":"NOT_RUN_OR_FAIL","reason":"BUILD_PATH3_ADMISSION_DENIED"}')
        return 2
    registry = root / "specs/engineering-dispatch/development-tasks-v1.json"
    tasks = json.loads(_read_safe_file(registry))["tasks"]
    fixed = tasks["fixed-site1-vivado-host-build"]
    task = dict(fixed, execution_path="path3-codex")
    approval = {
        "execution_path": "path3-codex",
        "execution_capability": "vivado-host-build",
        "task_id": "f1b-path3-codex-vivado-build",
        "pinned_sha": pinned, "trusted_sha": trusted, "pr_number": int(pr),
    }
    try:
        receipt = run(task, workspace=root, approval=approval,
                      evidence_dir=args.evidence_dir,
                      execution_path="path3-codex")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (BuildDenied, OSError, ValueError, subprocess.SubprocessError) as exc:
        # The diagnostic file is the detailed source of truth, not stderr.
        reason = str(exc)
        if not re.fullmatch(r"BUILD_[A-Z0-9_]{3,80}", reason):
            reason = "BUILD_UNCLASSIFIED_EXCEPTION"
        print(json.dumps({"status": "NOT_RUN_OR_FAIL", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
