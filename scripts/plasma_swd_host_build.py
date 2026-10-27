#!/usr/bin/env python3
"""Owner-authorized Path 2 operator-cli: independent dual Site FPGA HOST build.

ONLY Vivado on SWPC. No SSH, Z2, FPGA Manager, OpenOCD, MMIO, LA or DUT.
Exit 69 means pre-execution missing resource; real failed build exits 2.
Do not print license contents or sensitive host metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO / "pl/projects/z2-swd-independent"
TCL = PROJECT / "build_bitstream.tcl"
XDC = REPO / "pl/constraints/pynq-z2/z2-swd-independent.xdc"
VERIFIER = PROJECT / "verify_hwh.py"
SETTINGS = Path("/storage/tools/xilinx/2026.1/Vivado/settings64.sh")
BOARD_HELPER = REPO / "pl/projects/z2-swd-gpio/prepare-board-repository.sh"
BOARD_SHA = "e02d6a3866b5465218f777168cdc51344ac94e07"
# Allow enough room for board checkout & artifact verifier within the trusted
# Path 2 max timeout_seconds=1800. No auto-rerun on unknown failure.
VIVADO_TIMEOUT = 1520
RUNNER_TIMEOUT_EXPECTED = 1800


class BuildRejected(RuntimeError):
    def __init__(self, code: str, exit_code: int = 2):
        super().__init__(code)
        self.exit_code = exit_code


def require(ok: bool, code: str, exit_code: int = 2) -> None:
    if not ok:
        raise BuildRejected(code, exit_code)


def read_git(*args: str, cwd: Path = REPO, timeout: int = 12) -> str:
    proc = subprocess.run(["git", "--no-replace-objects", "-C", str(cwd), *args],
                          capture_output=True, timeout=timeout, check=False)
    require(proc.returncode == 0, "SWD_GIT_SOURCE_CHECK_FAILED")
    return proc.stdout.decode("utf-8").strip()


def validate_source(sha: str) -> None:
    require(isinstance(sha, str) and
            re.fullmatch("[a-f0-9]{40}", sha) is not None,
            "SWD_SOURCE_SHA_INVALID")
    require(read_git("rev-parse", "HEAD") == sha,
            "SWD_SOURCE_PIN_MISMATCH")
    require(not read_git("status", "--porcelain", "--untracked-files=no"),
            "SWD_TRACKED_SOURCE_MODIFIED")
    for path in (TCL, XDC, VERIFIER, PROJECT / "create_project.tcl",
                 PROJECT / "create_block_design.tcl"):
        require(path.is_file() and not path.is_symlink() and
                path.resolve().is_relative_to(REPO.resolve()),
                "SWD_SOURCE_FILE_MISSING_OR_SYMLINK")
    sources = (PROJECT / "create_project.tcl").read_text(encoding="utf-8")
    require("plasma_swd_transaction_engine.sv" in sources and
            "plasma_swd_site_axi_lite.sv" in sources and
            "plasma_mpe_" not in sources and
            "fixed_unified" not in sources,
            "SWD_SOURCE_NOT_INDEPENDENT_SITE")


def select_license() -> Path:
    # Same trusted installed Xilinx root as previously qualified tools,
    # but do not depend on or import the historical F1-B Build Engine.
    path = SETTINGS.parents[2] / "xic" / "Xilinx.lic"
    require(path.is_file() and not path.is_symlink() and
            path.resolve() == path and 0 < path.stat().st_size < 1024*1024 and
            os.access(path, os.R_OK),
            "SWD_VIVADO_LICENSE_NOT_AVAILABLE", 69)
    for name in ("XILINXD_LICENSE_FILE", "LM_LICENSE_FILE"):
        inherited = os.environ.get(name)
        require(not inherited or inherited == str(path),
                "SWD_VIVADO_LICENSE_SOURCE_AMBIGUOUS")
    return path


def prepare_board() -> Path:
    require(BOARD_HELPER.is_file() and not BOARD_HELPER.is_symlink() and
            f'source_commit="{BOARD_SHA}"' in
            BOARD_HELPER.read_text(encoding="utf-8"),
            "SWD_BOARD_HELPER_PIN_MISMATCH")
    try:
        proc = subprocess.run(["bash", str(BOARD_HELPER)], cwd=REPO,
                              capture_output=True, check=False, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise BuildRejected("SWD_PINNED_BOARD_PREP_NOT_AVAILABLE", 69) from exc
    require(proc.returncode == 0,
            "SWD_PINNED_BOARD_PREP_FAILED", 69)
    lines = proc.stdout.decode("utf-8").strip().splitlines()
    require(len(lines) == 1, "SWD_BOARD_PATH_UNEXPECTED")
    board = Path(lines[0]).resolve(strict=True)
    require(board.is_relative_to((REPO / "pl/build").resolve()),
            "SWD_BOARD_PATH_OUTSIDE_WORKTREE")
    require(read_git("rev-parse", "HEAD", cwd=board) == BOARD_SHA,
            "SWD_BOARD_COMMIT_MISMATCH")
    require(not read_git("status", "--porcelain", "--untracked-files=no",
                         cwd=board), "SWD_BOARD_FILES_MODIFIED")
    for name in ("board.xml", "preset.xml", "part0_pins.xml"):
        p = board / "pynq-z2/A.0" / name
        require(p.is_file() and not p.is_symlink(),
                "SWD_BOARD_FILE_ABSENT")
    return board


def load_verifier():
    spec = importlib.util.spec_from_file_location("swd_independent_hwh", VERIFIER)
    require(spec is not None and spec.loader is not None,
            "SWD_HWH_VERIFIER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_build(*, source_sha: str, preflight_only: bool = False) -> dict:
    validate_source(source_sha)
    require(os.geteuid() != 0, "SWD_ROOT_BUILD_FORBIDDEN", 77)
    require(SETTINGS.is_file() and not SETTINGS.is_symlink(),
            "SWD_VIVADO_2026_1_NOT_INSTALLED", 69)
    license_file = select_license()
    # Check-only is inert: no board clone, Vivado, output or hardware access.
    if preflight_only:
        return {"status": "PREFLIGHT_ONLY_NOT_BUILD", "source_sha": source_sha,
                "toolchain_present": True, "license_file_available": True,
                "z2_hil": "NOT_RUN"}
    board = prepare_board()
    dest = REPO / "pl/build" / f"swd-independent-{source_sha[:12]}"
    require(not dest.exists() and not dest.is_symlink(),
            "SWD_BUILD_DIRECTORY_NOT_EMPTY")
    dest.mkdir(parents=True, mode=0o700)
    log_file = dest / "vivado-build.log"
    env = {
        "HOME": os.environ.get("HOME", "/nonexistent"),
        "PATH": "/usr/bin:/bin",
        "XILINXD_LICENSE_FILE": str(license_file),
        "PLASMA_SWD_BUILD": str(dest),
        "PLASMA_BOARD_REPO": str(board),
        "PLASMA_SWD_JOBS": "4",
    }
    # Bash must source installed Vivado settings before resolving vivado.
    cmd = ["bash", "-c",
           'set -e; source "$1"; exec vivado -mode batch -notrace -nolog '
           '-nojournal -source "$2"',
           "plasma-swd-vivado", str(SETTINGS), str(TCL)]
    with log_file.open("wb") as log:
        try:
            proc = subprocess.run(cmd, cwd=REPO, env=env,
                                  stdout=log, stderr=subprocess.STDOUT,
                                  check=False, timeout=VIVADO_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            raise BuildRejected("SWD_VIVADO_BUILD_TIMED_OUT_STARTED") from exc
        except OSError as exc:
            raise BuildRejected("SWD_VIVADO_PROCESS_LAUNCH_FAILED") from exc
    require(proc.returncode == 0, "SWD_VIVADO_BUILD_FAILED")
    # Only an actual successful Vivado invocation can supply this log marker.
    log_text = log_file.read_text(encoding="utf-8", errors="replace")
    require("SWD_HOST_IMPL_REPORTS_TIMING_DRC_PASS" in log_text,
            "SWD_VIVADO_SIGNOFF_MARKER_ABSENT")
    hwh = dest / "artifacts/system.hwh"
    bit = dest / "artifacts/system_wrapper.bit"
    evidence = load_verifier().verify_artifacts(
        hwh=hwh, bit=bit, reports=dest / "reports", xdc=XDC,
        source_sha=source_sha, build_stdout=log_text)
    evidence["board_files_git_sha"] = BOARD_SHA
    evidence["toolchain"] = "Vivado 2026.1"
    evidence["vivado_exit_code"] = proc.returncode
    evidence["vivado_log_sha256"] = hashlib.sha256(
        log_file.read_bytes()).hexdigest()
    receipt = dest / "artifacts/host-build-receipt.json"
    require(not receipt.exists(), "SWD_BUILD_RECEIPT_EXISTS")
    receipt.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n",
                       encoding="utf-8")
    return {"status": "SWPC_HOST_BUILD_ARTIFACTS_VERIFY_REVIEW_REQUIRED",
            "source_sha": source_sha,
            "board_files_git_sha": BOARD_SHA,
            "bit_sha256": evidence["bit_sha256"],
            "hwh_sha256": evidence["hwh_sha256"],
            "vivado_log_sha256": evidence["vivado_log_sha256"],
            "z2_hil": "NOT_RUN", "dut_programming": "NOT_RUN",
            "external_swd_io_timing": evidence["external_swd_io_timing"],
            "evidence_relpath": str(receipt.relative_to(REPO))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_build(source_sha=args.source_sha,
                           preflight_only=args.preflight_only)
        print(json.dumps(result, sort_keys=True))
        return 0
    except BuildRejected as exc:
        print(json.dumps({"status": "NOT_RUN" if exc.exit_code in (69,77)
                          else "FAIL", "error": str(exc),
                          "host_build_pass": False, "z2_hil": "NOT_RUN"},
                         sort_keys=True))
        return exc.exit_code
    except Exception:
        # Never leak paths/licenses/stacks into the GitHub comment evidence.
        print('{"status":"FAIL","error":"SWD_UNEXPECTED_BUILD_FAILURE",'
              '"host_build_pass":false,"z2_hil":"NOT_RUN"}')
        return 2


if __name__ == "__main__":
    sys.exit(main())
