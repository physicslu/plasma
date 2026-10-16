"""MS01 supervised real PYNQ-Z2 dual-Site HIL; inert unless explicitly authorized.

This program NEVER loads, reconfigures, restores, powers, or resets the FPGA.
A separate supervisor must load the exact reviewed BIN, create a protected
current-boot receipt, and restore the original known-good base on all paths.
Host checks do not constitute real PS/PL HIL.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from pl.hil.lt02 import native as old
from pl.hil.ms01.benchmark import run_benchmark, save_reports
from pl.hil.swd04 import contract as swd04_contract
from pl.hil.swd04.collect import fclk0_from_summary
from pl.hil.swd04.development import last_load
from pl.hil.swd04.native_qualify import check_runtime
from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOAperture
from plasma_interfaces.mmio_loop_test import LoopTestDriver, loopback_aperture

REPO = Path(__file__).resolve().parents[3]
BUILD_ARTIFACT = REPO / "pl/projects/z2-ms01-axi/artifact.py"
IDENTITY = 0x40000000
SITE_BASES = {1: 0x40004000, 2: 0x40005000}
MAP = {
    "identity_0": 0x40000000,
    "control_0": 0x40001000,
    "swd_0": 0x40002000,
    "transaction_0": 0x40003000,
    "lt02_0": SITE_BASES[1],
    "lt02_1": SITE_BASES[2],
}


def require(value: bool, detail: str) -> None:
    if not value:
        raise old.LT02SafetyError(detail)


def _sha(path: Path) -> str:
    return old.digest(path)


def verify_artifacts(*, manifest: Path, bit: Path, hwh: Path,
                     candidate_bin: Path, recovery_bin: Path,
                     recovery_hwh: Path, expected_manifest_sha256: str,
                     expected_candidate_bin_sha256: str) -> dict:
    """Verify source and image; no FPGA access."""
    old.require_sha(expected_manifest_sha256, "manifest")
    old.require_sha(expected_candidate_bin_sha256, "converted BIN")
    require(_sha(manifest) == expected_manifest_sha256,
            "MS01 reviewed manifest digest mismatch")
    data = old.read_json(manifest)
    require(data.get("design_variant") ==
            "ms01_dual_lt02_internal_dpidr_fixture",
            "MS01 six-aperture design variant mismatch")
    require(data.get("fpga_part") == "xc7z020clg400-1" and
            data.get("board_part") == "tul.com.tw:pynq-z2:part0:1.0",
            "MS01 PYNQ-Z2 board mismatch")
    source_sha = data.get("source_git_sha")
    require(type(source_sha) is str and
            bool(re.fullmatch(r"[0-9a-f]{40}", source_sha)) and
            data.get("build_id") == source_sha[:32],
            "Source Build ID is not an exact SHA prefix")
    require(data.get("external_pl_io") is False and
            data.get("physical_programming_qualified") is False and
            data.get("hardware_runtime_ready") is False,
            "Candidate unexpectedly claims physical I/O or programming")
    require(data.get("lt02_site_count") == 2 and
            data.get("lt02_abi_version") == 1 and
            data.get("lt02_scratchpad_bytes") == 2048,
            "MS01 dual LT02 ABI mismatch")
    expected_sites = [{"site_id": n, "base_address": f"0x{base:08X}",
                       "scratchpad_bytes": 2048}
                      for n, base in SITE_BASES.items()]
    require(data.get("lt02_sites") == expected_sites,
            "Manifest missing exact two-Site binding")
    mapping = data.get("axi_address_map")
    require(type(mapping) is dict and set(mapping) == set(MAP),
            "MS01 requires exactly six GP0 apertures")
    for name, base in MAP.items():
        require(mapping[name] == {"base_address": f"0x{base:08X}",
                                 "segment_size_bytes": 4096},
                "Unexpected MS01 HWH map: " + name)
    for path, sha, label in (
        (bit, data.get("bitstream_sha256"), "BIT"),
        (hwh, data.get("hwh_sha256"), "HWH"),
        (candidate_bin, expected_candidate_bin_sha256, "converted BIN"),
        (recovery_bin, swd04_contract.RECOVERY_BIN_SHA256, "recovery BIN"),
        (recovery_hwh, swd04_contract.RECOVERY_HWH_SHA256, "recovery HWH"),
    ):
        require(path.is_file() and path.stat().st_size > 0,
                "Missing artifact: " + label)
        require(_sha(path) == old.require_sha(sha, label),
                "SHA mismatch: " + label)
    spec = importlib.util.spec_from_file_location("ms01_live_hwh_check",
                                                   BUILD_ARTIFACT)
    require(spec is not None and spec.loader is not None,
            "MS01 build HWH verifier unavailable")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    require(checker.verify_hwh(hwh) == mapping,
            "Actual HWH does not match the approved six apertures")
    return {
        "source_git_sha": source_sha,
        "build_id": source_sha[:32],
        "manifest_sha256": expected_manifest_sha256,
        "candidate_bin_sha256": expected_candidate_bin_sha256,
        "recovery_bin_sha256": swd04_contract.RECOVERY_BIN_SHA256,
    }


def _last_load_line(candidate_bin: Path) -> str:
    require(Path("/sys/class/fpga_manager/fpga0/state").read_text().strip()
            == "operating", "FPGA Manager is not operating")
    log = subprocess.run(["dmesg", "--color=never"], check=True,
                         capture_output=True, text=True, timeout=10).stdout
    line = last_load(log)
    require(f": writing {candidate_bin.name} to " in line,
            "Last FPGA Manager load is not the reviewed MS01 image")
    return line


def _protected(path: Path) -> None:
    info = path.stat()
    require(info.st_uid == 0 and not info.st_mode & 0o022,
            "MS01 protected root-owned path required: " + str(path))


def _candidate_receipt(candidate_bin: Path, artifact: dict) -> dict:
    return {
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "load_line": _last_load_line(candidate_bin),
        "candidate_bin_sha256": artifact["candidate_bin_sha256"],
        "manifest_sha256": artifact["manifest_sha256"],
        "source_git_sha": artifact["source_git_sha"],
        "site_bases": {str(k): v for k, v in SITE_BASES.items()},
        "external_pl_io": False,
    }


def record_load_receipt(path: Path, candidate_bin: Path,
                        artifact: dict) -> None:
    """Only after external supervised load; does not issue a reload."""
    require(os.geteuid() == 0 and not path.exists(),
            "Protected root required; no receipt overwrite")
    for f in (path.parent, candidate_bin.parent, candidate_bin):
        _protected(f)
    require(_sha(candidate_bin) == artifact["candidate_bin_sha256"],
            "Candidate BIN changed since independent verification")
    data = _candidate_receipt(candidate_bin, artifact)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def check_site2_ownership() -> None:
    """Cover site2 omitted from the retained five-aperture LT02 preflight."""
    lo, hi = SITE_BASES[2], SITE_BASES[2] + 4096

    def overlap(start: int, end: int) -> bool:
        return start < hi and end > lo

    related_uio: set[str] = set()
    for uio in Path("/sys/class/uio").glob("uio*"):
        for mapping in (uio / "maps").glob("map*"):
            start = int((mapping / "addr").read_text(), 0)
            size = int((mapping / "size").read_text(), 0)
            if overlap(start, start + size):
                related_uio.add("/dev/" + uio.name)
                require(not (uio / "device/driver").exists(),
                        "Site 2 kernel UIO driver still owns PL")
    for dev in Path("/sys/bus/platform/devices").iterdir():
        if not (dev / "driver").exists():
            continue
        match = re.match(r"^([0-9A-Fa-f]+)\.", dev.name)
        if match and overlap(int(match[1], 16), int(match[1], 16) + 1):
            raise old.LT02SafetyError("Site 2 platform owner remains active")
        resource = dev / "resource"
        if resource.exists():
            for row in resource.read_text().splitlines():
                start, last, flags = (int(part, 16) for part in row.split())
                if flags & 0x200 and overlap(start, last + 1):
                    raise old.LT02SafetyError("Site 2 kernel resource is active")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            for f in (proc / "fd").iterdir():
                if os.readlink(f) in related_uio:
                    raise old.LT02SafetyError("Site 2 UIO fd owned by PID " + proc.name)
            for row in (proc / "maps").read_text().splitlines():
                fields = row.split()
                if len(fields) >= 6 and fields[5] in related_uio:
                    raise old.LT02SafetyError("Site 2 UIO mapping owned by PID " + proc.name)
        except (FileNotFoundError, ProcessLookupError):
            continue


def verify_live_environment(receipt_path: Path, candidate_bin: Path,
                            artifact: dict) -> None:
    require(os.geteuid() == 0, "Real target root authorization required")
    check_runtime()
    for f in (receipt_path, receipt_path.parent,
              candidate_bin, candidate_bin.parent):
        _protected(f)
    require(Path("/dev/mem").is_char_device(), "Target /dev/mem absent")
    clock = Path("/sys/kernel/debug/clk/clk_summary").read_text()
    require(fclk0_from_summary(clock) == 100_000_000 and
            old.check_fclk_enabled(clock),
            "FPGA FCLK0 is not verified running at 100 MHz")
    require(old.read_json(receipt_path) == _candidate_receipt(
        candidate_bin, artifact),
        "MS01 load receipt does not match the exact current FPGA boot")
    old.check_ownership()
    check_site2_ownership()


def _record(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def run_live(artifact: dict, output: Path, *,
             iterations: int, payload_sizes: tuple[int, ...]) -> None:
    """A physical Z2 test; assumes independently admitted supervised load."""
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    common = {
        "scope": "MS01 dual-Site development HIL",
        "source_git_sha": artifact["source_git_sha"],
        "candidate_bin_sha256": artifact["candidate_bin_sha256"],
        "python": platform.python_version(),
        "hardware": "real-Z2-ARMv7",
        "fpga_recovery": "NOT_RUN",
        "physical_target_programming": "NOT_RUN",
        "direct_process_mmio": "NOT_RUN",
        "four_eight_site_hardware": "NOT_RUN",
    }
    _record(output / "started.json", {
        **common, "result": "STARTED",
        "started_utc": datetime.now(timezone.utc).isoformat(),
    })
    try:
        identity = MMIOAperture(IDENTITY,
                               frozenset(range(0, 0x20, 4)), frozenset())
        runs: list[dict] = []
        with LinuxMMIO((identity, *(loopback_aperture(b)
                                    for b in SITE_BASES.values())),
                       device="/dev/mem",
                       owner_lock="/run/lock/plasma-mmio.lock") as mmio:
            for address, word in old.expected_identity(
                    artifact["source_git_sha"]).items():
                require(mmio.read32(address) == word,
                        "FPGA source Build ID mismatch; STOP before writes")
            with ExitStack() as stack:
                drivers = {}
                for site, base in SITE_BASES.items():
                    port = stack.enter_context(
                        mmio.claim_site(site_id=site, base=base))
                    drivers[site] = LoopTestDriver(port, base=base,
                                                   site_id=site)
                for mode in ("thread", "process-ipc"):
                    for length in payload_sizes:
                        result = run_benchmark(
                            drivers, mode=mode, payload_bytes=length,
                            iterations=iterations)
                        result["source"] = "real-supervised-z2"
                        runs.append(result)
                stats = mmio.stats()
        save_reports(runs, output / "performance")
        outcome = {
            "result": "PASS",
            "modes": ["thread", "process-ipc"],
            "sites": [1, 2],
            "mmio_word_accesses": {
                "read32": stats.read32, "write32": stats.write32,
            },
            "runs": len(runs),
        }
    except (OSError, ValueError, RuntimeError) as exc:
        outcome = {
            "result": "FAIL", "reason": str(exc),
            "stop_without_retry": True,
        }
    _record(output / "result.json", {
        **common, **outcome,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    })
    if outcome["result"] != "PASS":
        raise old.LT02SafetyError(
            "MS01 real data-path STOP; external image supervisor must restore")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "bit", "hwh", "candidate-bin",
                 "recovery-bin", "recovery-hwh", "receipt", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--expected-manifest-sha256", required=True)
    p.add_argument("--expected-candidate-bin-sha256", required=True)
    p.add_argument("--iterations", type=int, default=8)
    p.add_argument("--payload-sizes", nargs="+", type=int,
                   default=[2048, 8192, 65536])
    p.add_argument("--record-loaded-image", action="store_true")
    p.add_argument("--execute-live", action="store_true")
    p.add_argument("--ack-unrecoverable-axi-stall-risk", action="store_true")
    args = p.parse_args(argv)
    if (not 1 <= args.iterations <= 10000 or
            not 1 <= len(args.payload_sizes) <= 3 or
            any(not 1 <= n <= 1048576 for n in args.payload_sizes)):
        print("MS01_NO_GO: bounded iteration/payload limits exceeded",
              file=sys.stderr)
        return 2
    if args.record_loaded_image == args.execute_live:
        print("MS01_NO_GO: choose exactly one run mode", file=sys.stderr)
        return 2
    if args.record_loaded_image and args.ack_unrecoverable_axi_stall_risk:
        print("MS01_NO_GO: recording cannot execute MMIO", file=sys.stderr)
        return 2
    if args.execute_live and not args.ack_unrecoverable_axi_stall_risk:
        print("MS01_NO_GO: missing explicit real MMIO risk flag", file=sys.stderr)
        return 2
    try:
        artifact = verify_artifacts(
            manifest=args.manifest, bit=args.bit, hwh=args.hwh,
            candidate_bin=args.candidate_bin, recovery_bin=args.recovery_bin,
            recovery_hwh=args.recovery_hwh,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_candidate_bin_sha256=args.expected_candidate_bin_sha256,
        )
        if args.record_loaded_image:
            check_runtime()
            record_load_receipt(args.receipt, args.candidate_bin, artifact)
            print("MS01_LOAD_RECEIPT_RECORDED_NO_MMIO")
        else:
            require(not args.output.exists(), "Never overwrite existing evidence")
            verify_live_environment(args.receipt, args.candidate_bin, artifact)
            run_live(artifact, args.output, iterations=args.iterations,
                     payload_sizes=tuple(args.payload_sizes))
            print("MS01_REAL_DATA_CASES_PASS_RECOVERY_NOT_RUN")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print("MS01_NO_GO_OR_STOP: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
