#!/usr/bin/env python3
"""Trusted Path 2 generic Vivado HOST build. No target load, device or deployment.

A reviewed owner Issue #981 Path 2 Work Order is mandatory. It may pin trusted
main or the exact head of an explicitly authorized open owner PR. The pinned
project supplies its own ``host-build.json`` contract, ``build_bitstream.tcl``
and ``verify_hwh.py``; this driver does not implement per-project workflows.
"""
from __future__ import annotations

import errno
import hashlib
import sys
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def authenticate_host_inputs(workspace: Path, pinned_sha: str) -> dict:
    """Reject edits/symlinks before executing candidate Tcl/Python on the host.

    Called only by the trusted dispatcher after live owner/PR admission and
    after Codex has exited. Changed inputs need a newly reviewed pinned SHA.
    Git's index/status alone is insufficient (assume-unchanged/skip-worktree).
    """
    require(BOARD_SHA40.fullmatch(pinned_sha) is not None, "BUILD_SOURCE_SHA_MISMATCH")
    root = workspace.resolve(strict=True)
    def git(*args):
        return subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30).stdout
    require(git("rev-parse", "HEAD").strip().decode() == pinned_sha,
            "BUILD_SOURCE_SHA_MISMATCH")
    paths = git("ls-tree", "-r", "--name-only", "-z", pinned_sha, "--", "pl").split(b"\0")
    hashes = {}
    for item in filter(None, paths):
        name = item.decode()
        path = root / name
        require(path.is_file() and not path.is_symlink() and
                path.resolve() == path and path.resolve().is_relative_to(root),
                "BUILD_SOURCE_DENIED")
        expected = git("show", pinned_sha + ":" + name)
        require(path.read_bytes() == expected, "BUILD_UNREVIEWED_INPUT_DENIED")
        hashes[name] = hashlib.sha256(expected).hexdigest()
    require(bool(hashes), "BUILD_SOURCE_DENIED")
    # Helper is executable; it must match trusted engine's co-versioned copy.
    helper = "pl/projects/z2-swd-gpio/prepare-board-repository.sh"
    trusted = Path(__file__).resolve().parents[1] / helper
    require((root / helper).read_bytes() == trusted.read_bytes(),
            "BUILD_UNREVIEWED_HELPER_DENIED")
    return {"pinned_sha": pinned_sha, "files_sha256": hashes}

BOARD_SHA40 = re.compile(r"[a-f0-9]{40}\Z")
PROJECT_NAME = re.compile(r"pl/projects/[a-z0-9-]{3,70}\Z")
SETTINGS64 = Path("/storage/tools/xilinx/2026.1/Vivado/settings64.sh")


class BuildDenied(ValueError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise BuildDenied(code)


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


def prepare_host_build_dir(workspace: Path, *, prefix: str = "vivado-") -> Path:
    """Reuse Git-ignored candidate/pl/build; never mutate persistent SWPC root."""
    root = workspace.resolve(strict=True)
    output = root / "pl/build"
    require(output.is_dir() and not output.is_symlink() and
            output.resolve().is_relative_to(root), "BUILD_OUTPUT_ROOT_MISSING")
    try:
        result = Path(tempfile.mkdtemp(prefix=prefix, dir=output))
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


def run(task: dict, *, workspace: Path, approval: dict,
        evidence_dir: Path | None = None, executor=subprocess.run,
        execution_path: str = "path2-cli") -> dict:
    """Only the dynamic Path 2 Work Order host build is admitted."""
    require(execution_path == "path2-cli" and
            approval.get("task_id") == "path2-work-order",
            "BUILD_LEGACY_PATH_RETIRED")
    return run_generic(task, workspace=workspace, approval=approval,
                       evidence_dir=evidence_dir, executor=executor)


GENERIC_REPORTS = ("timing_summary.rpt", "drc.rpt", "methodology.rpt",
                   "utilization.rpt")


def generic_project_contract(task: dict, *, workspace: Path,
                             approval: dict) -> dict:
    """A pinned project supplies its own output names and artifact verifier."""
    require(type(task) is dict and set(task) == {
        "execution_path", "capability", "project", "toolchain", "board_repo_sha"
    } and task["execution_path"] == "path2-cli" and
            task["capability"] == "vivado-host-build" and
            type(task["project"]) is str and
            PROJECT_NAME.fullmatch(task["project"]) is not None and
            task["toolchain"] == "2026.1" and
            type(task["board_repo_sha"]) is str and
            BOARD_SHA40.fullmatch(task["board_repo_sha"]) is not None,
            "BUILD_GENERIC_TASK_DENIED")
    require(type(approval) is dict and
            approval.get("task_id") == "path2-work-order" and
            approval.get("execution_path") == "path2-cli" and
            approval.get("execution_capability") == "vivado-host-build" and
            type(approval.get("pinned_sha")) is str and
            BOARD_SHA40.fullmatch(approval["pinned_sha"]) is not None and
            type(approval.get("work_order_sha256")) is str and
            re.fullmatch(r"[a-f0-9]{64}", approval["work_order_sha256"]) is not None,
            "BUILD_GENERIC_APPROVAL_DENIED")
    root = workspace.resolve(strict=True)
    project = root / task["project"]
    require(project.is_dir() and not project.is_symlink() and
            project.resolve(strict=True) == project,
            "BUILD_GENERIC_PROJECT_DENIED")
    contract_file = project / "host-build.json"
    raw = _read_safe_file(contract_file)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "BUILD_GENERIC_CONTRACT_DUPLICATE")
            result[key] = value
        return result
    try:
        contract = json.loads(raw, object_pairs_hook=unique)
    except BuildDenied:
        raise
    except (ValueError, TypeError) as exc:
        raise BuildDenied("BUILD_GENERIC_CONTRACT_INVALID") from exc
    require(type(contract) is dict and set(contract) == {
        "schema", "vivado_project", "build_env", "success_marker", "reports",
        "prepare_artifact"
    } and contract["schema"] == "plasma.vivado-host-project.v1" and
            type(contract["vivado_project"]) is str and
            re.fullmatch(r"[a-z][a-z0-9_]{2,63}", contract["vivado_project"]) and
            type(contract["build_env"]) is str and
            re.fullmatch(r"PLASMA_[A-Z0-9_]{2,64}_BUILD", contract["build_env"]) and
            type(contract["success_marker"]) is str and
            re.fullmatch(r"[A-Z0-9_]{12,100}", contract["success_marker"]) and
            type(contract["reports"]) is list and
            all(type(name) is str and
                re.fullmatch(r"[a-z_]+\.rpt", name) for name in contract["reports"]) and
            set(GENERIC_REPORTS) <= set(contract["reports"]) and
            len(contract["reports"]) == len(set(contract["reports"])) and
            type(contract["prepare_artifact"]) is bool,
            "BUILD_GENERIC_CONTRACT_DENIED")
    required = ["create_project.tcl", "create_block_design.tcl",
                "build_bitstream.tcl", "verify_hwh.py"]
    if contract["prepare_artifact"]:
        required.append("artifact.py")
    for name in required:
        _read_safe_file(project / name)
    code = ""
    for name in ("create_project.tcl", "create_block_design.tcl",
                 "build_bitstream.tcl"):
        tcl = _read_safe_file(project / name)
        candidate = "\n".join(line for line in tcl.splitlines()
                              if not line.lstrip().startswith("#"))
        require(not re.search(r"\b(?:open_hw|connect_hw_server|program_hw_devices|"
                              r"write_cfgmem|exec|openocd|ssh|scp|sudo)\b|"
                              r"/dev/(?:mem|uio)|fpga_manager", candidate, re.I),
                "BUILD_GENERIC_TCL_DENIED")
        if name == "build_bitstream.tcl":
            code = candidate
    require(all(token in code for token in ("launch_runs synth_1",
                                            "launch_runs impl_1",
                                            "report_timing_summary",
                                            "get_drc_violations")),
            "BUILD_GENERIC_IMPLEMENTATION_GATES_MISSING")
    return {**contract, "project_dir": project,
            "source_sha": approval["pinned_sha"]}


def run_generic(task: dict, *, workspace: Path, approval: dict,
                evidence_dir: Path | None, executor=subprocess.run) -> dict:
    """Dynamic Path 2 host build; a project contract is required for admission."""
    plan = generic_project_contract(task, workspace=workspace, approval=approval)
    require(type(approval.get("trusted_sha")) is str and
            BOARD_SHA40.fullmatch(approval["trusted_sha"]) is not None and
            type(approval.get("pr_number")) is int and
            ((approval["pr_number"] == 0 and
              approval["pinned_sha"] == approval["trusted_sha"]) or
             (approval["pr_number"] > 0 and
              approval["pinned_sha"] != approval["trusted_sha"])) and
            os.environ.get("GITHUB_SHA") == approval["trusted_sha"],
            "BUILD_GENERIC_SOURCE_BINDING_DENIED")
    require(evidence_dir is not None and evidence_dir.is_dir() and
            not evidence_dir.is_symlink() and os.geteuid() != 0,
            "BUILD_GENERIC_EVIDENCE_OR_USER_DENIED")
    authenticate_host_inputs(workspace, plan["source_sha"])
    require(SETTINGS64.is_file() and not SETTINGS64.is_symlink(),
            "BUILD_VIVADO_SETTINGS_UNAVAILABLE")
    license_env = discover_vivado_license()
    board = resolve_board_repository(task, workspace=workspace, executor=executor)
    root = workspace.resolve(strict=True)
    check_env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
    board_sha = _run_checked(["git", "-C", str(board), "rev-parse", "HEAD"],
                             executor=executor, cwd=root, timeout=10,
                             env=check_env).decode("ascii")
    require(board_sha == task["board_repo_sha"], "BUILD_BOARD_SHA_MISMATCH")
    require(_run_checked(["git", "-C", str(board), "status", "--porcelain",
                          "--untracked-files=no"], executor=executor, cwd=root,
                         timeout=10, env=check_env) == b"",
            "BUILD_BOARD_REPO_DIRTY")
    build = prepare_host_build_dir(workspace, prefix="vivado-")
    build_env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/nonexistent"),
                 plan["build_env"]: str(build), "PLASMA_BOARD_REPO": str(board),
                 "PLASMA_VIVADO_JOBS": "4", **license_env}
    if plan["prepare_artifact"]:
        prep = executor([sys.executable, str(plan["project_dir"] / "artifact.py"),
                         "prepare", "--build", str(build), "--version", "0.1.0"],
                        cwd=root, env=build_env, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, timeout=120, check=False)
        require(prep.returncode == 0 and len(prep.stdout) <= 65536 and
                len(prep.stderr) <= 65536, "BUILD_GENERIC_PREPARE_FAILED")
    args = ["/usr/bin/bash", "-c",
            'set -euo pipefail; source "$1"; exec vivado -mode batch '
            '-nojournal -log "$2" -source "$3"', "plasma-vivado-host",
            str(SETTINGS64), str(build / "vivado.log"),
            str(plan["project_dir"] / "build_bitstream.tcl")]
    proc = executor(args, cwd=root, env=build_env, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=2400, check=False)
    require(len(proc.stdout) <= 2_000_000 and len(proc.stderr) <= 2_000_000,
            "BUILD_LOG_EXCESSIVE")
    (build / "vivado-stdout.log").write_bytes(proc.stdout)
    (build / "vivado-stderr.log").write_bytes(proc.stderr)
    require(proc.returncode == 0 and
            plan["success_marker"].encode() in proc.stdout.splitlines() and
            b"CRITICAL WARNING:" not in proc.stdout + proc.stderr and
            b"ERROR:" not in proc.stdout + proc.stderr,
            "BUILD_GENERIC_IMPLEMENTATION_FAILED")
    project = build / "project"
    for child_log in project.glob("*.runs/*/runme.log"):
        require(child_log.is_file() and not child_log.is_symlink() and
                child_log.stat().st_size <= 2_000_000,
                "BUILD_GENERIC_CHILD_LOG_DENIED")
        child_text = child_log.read_bytes()
        require(b"CRITICAL WARNING:" not in child_text and
                b"ERROR:" not in child_text,
                "BUILD_GENERIC_CHILD_RUN_FAILED")
    stem = plan["vivado_project"]
    bit = project / f"{stem}.runs/impl_1/system_wrapper.bit"
    hwh = project / f"{stem}.gen/sources_1/bd/system/hw_handoff/system.hwh"
    reports = build / "reports"
    output_files = (bit, hwh, *(reports / name for name in plan["reports"]))
    require(all(path.resolve().is_relative_to(build.resolve()) for path in output_files),
            "BUILD_GENERIC_OUTPUT_ESCAPE")
    require(bit.is_file() and not bit.is_symlink() and hwh.is_file() and
            not hwh.is_symlink() and 0 < bit.stat().st_size <= 16_000_000 and
            0 < hwh.stat().st_size <= 4_000_000 and
            all((reports / name).is_file() and
                not (reports / name).is_symlink() and
                0 < (reports / name).stat().st_size <= 8_000_000
                for name in plan["reports"]),
            "BUILD_GENERIC_ARTIFACT_MISSING")
    verifier = plan["project_dir"] / "verify_hwh.py"
    spec = importlib.util.spec_from_file_location("plasma_project_host_verifier", verifier)
    require(spec is not None and spec.loader is not None,
            "BUILD_GENERIC_VERIFIER_DENIED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verified = module.verify_artifacts(hwh=hwh, bit=bit, reports=reports,
                                       source_sha=plan["source_sha"], build=build)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    actual_reports = {name: digest(reports / name) for name in plan["reports"]}
    require(type(verified) is dict and
            verified.get("source_sha") == plan["source_sha"] and
            verified.get("bit_sha256") == digest(bit) and
            verified.get("hwh_sha256") == digest(hwh) and
            verified.get("report_sha256") == actual_reports and
            type(verified.get("map")) is dict,
            "BUILD_GENERIC_VERIFIER_MISMATCH")
    receipt = {**verified, "status": "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED",
               "execution_path": "path2-cli", "execution_capability": "vivado-host-build",
               "project": task["project"], "source_sha": plan["source_sha"],
               "build_dir": str(build), "vivado_stdout_sha256": digest(build / "vivado-stdout.log"),
               "vivado_stderr_sha256": digest(build / "vivado-stderr.log"),
               "physical_load": "NOT_RUN", "z2_hil": "NOT_RUN"}
    (evidence_dir / "plasma-path2-vivado-host-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt
