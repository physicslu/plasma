"""LT02-05 bounded PYNQ-Z2 development MMIO experiment.

This module NEVER loads or restores FPGA images. A separate supervised
orchestrator must do those operations; a successful data result is not a
recovery PASS. Default CLI is inert. Invalid AXI offsets are never probed.

Live operation is permitted only for a verified five-aperture image, protected
current-boot load receipt, qualified ARMv7 interpreter, exclusive PL ownership,
and two explicit live flags. An AXI stall is not safely interruptible in Python.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

from pl.hil.swd04 import contract as old
from pl.hil.swd04.collect import fclk0_from_summary
from pl.hil.swd04.development import last_load
from pl.hil.swd04.native_qualify import check_runtime
from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOAperture
from plasma_interfaces.mmio_loop_test import (
    LoopTestDriver, LoopTestError, loopback_aperture,
)

IDENTITY = 0x40000000
LT02 = 0x40004000
AXI_BASES = {
    "identity_0": 0x40000000,
    "control_0": 0x40001000,
    "swd_0": 0x40002000,
    "transaction_0": 0x40003000,
    "lt02_0": 0x40004000,
}
LENGTHS = (1, 4, 5, 1023, 1024, 1025, 2048, 2049, 4097, 8193)


class LT02SafetyError(RuntimeError):
    """STOP rather than retry any possibly completed hardware transaction."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise LT02SafetyError(reason)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require_sha(value: object, label: str) -> str:
    require(type(value) is str and bool(re.fullmatch(r"[a-f0-9]{64}", value)),
            f"Invalid SHA-256: {label}")
    return value


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(type(value) is dict, "Expected JSON object: " + str(path))
    return value


def verify_artifacts(manifest: Path, bit: Path, hwh: Path,
                     candidate_bin: Path, recovery_bin: Path,
                     recovery_hwh: Path, expected_manifest_sha256: str) -> dict:
    """File-only guard; provenance must originate from a reviewed SWPC build."""
    require_sha(expected_manifest_sha256, "expected manifest")
    require(digest(manifest) == expected_manifest_sha256,
            "Review-pinned manifest digest changed")
    doc = read_json(manifest)
    require(doc.get("design_variant") == "lt02_axi_scratchpad_internal_dpidr_fixture",
            "Wrong FPGA design variant")
    require(doc.get("fpga_part") == "xc7z020clg400-1",
            "Candidate FPGA part mismatch")
    require(doc.get("board_part") == "tul.com.tw:pynq-z2:part0:1.0",
            "Candidate board mismatch")
    require(doc.get("external_pl_io") is False and
            doc.get("hardware_runtime_ready") is False and
            doc.get("physical_programming_qualified") is False,
            "Candidate claims forbidden external or programming capabilities")
    require(doc.get("lt02_abi_version") == 1 and
            doc.get("lt02_scratchpad_bytes") == 2048 and
            doc.get("lt02_reference_site_id") == 1,
            "LT02 Site 1 ABI/capacity mismatch")
    sha = doc.get("source_git_sha")
    require(type(sha) is str and bool(re.fullmatch(r"[a-f0-9]{40}", sha)),
            "Build source Git SHA missing/invalid")
    require(doc.get("build_id") == sha[:32], "Build ID/source mismatch")
    mapping = doc.get("axi_address_map")
    require(type(mapping) is dict and set(mapping) == set(AXI_BASES),
            "Manifest does not enumerate exactly five apertures")
    for name, base in AXI_BASES.items():
        item = mapping[name]
        require(type(item) is dict and
                item.get("base_address") == f"0x{base:08X}" and
                item.get("segment_size_bytes") == 4096,
                f"Address map mismatch: {name}")
    for path, expected, label in (
        (bit, doc.get("bitstream_sha256"), "BIT"),
        (hwh, doc.get("hwh_sha256"), "HWH"),
        (recovery_bin, old.RECOVERY_BIN_SHA256, "recovery BIN"),
        (recovery_hwh, old.RECOVERY_HWH_SHA256, "recovery HWH"),
    ):
        require(path.is_file() and path.stat().st_size > 0,
                "Missing nonempty artifact: " + label)
        require(digest(path) == require_sha(expected, label),
                "Artifact digest mismatch: " + label)
    require(candidate_bin.is_file() and candidate_bin.stat().st_size > 0,
            "Candidate converted BIN missing")
    return {"manifest_sha256": expected_manifest_sha256,
            "candidate_bin_sha256": digest(candidate_bin),
            "recovery_bin_sha256": old.RECOVERY_BIN_SHA256,
            "source_git_sha": sha,
            "build_id": sha[:32]}


def verify_receipt(receipt: dict, *, boot_id: str, last_load_line: str,
                   artifact: dict) -> None:
    """Require actual last-loaded candidate, not an old SWD-03 receipt."""
    for key, value in (
        ("boot_id", boot_id),
        ("load_line", last_load_line),
        ("candidate_bin_sha256", artifact["candidate_bin_sha256"]),
        ("manifest_sha256", artifact["manifest_sha256"]),
        ("build_id", artifact["build_id"]),
        ("axi_address_map", AXI_BASES),
        ("site_id", 1),
        ("external_pl_io", False),
    ):
        require(receipt.get(key) == value, "Current load receipt mismatch: " + key)


def verify_live_environment(receipt_path: Path, candidate_bin: Path,
                            artifact: dict) -> None:
    """Read-only live checks before any LinuxMMIO opens /dev/mem."""
    require(os.geteuid() == 0, "Authorized root required on Z2")
    for path in (receipt_path, receipt_path.parent, candidate_bin,
                 candidate_bin.parent):
        info = path.stat()
        require(info.st_uid == 0 and not info.st_mode & 0o022,
                "Receipt/firmware must be root-owned and protected")
    require(Path("/dev/mem").is_char_device(), "Real /dev/mem unavailable")
    require(Path("/sys/class/fpga_manager/fpga0/state").read_text().strip()
            == "operating", "FPGA Manager not operating")
    clock = Path("/sys/kernel/debug/clk/clk_summary").read_text()
    require(fclk0_from_summary(clock) == 100000000,
            "FCLK0 not verified as 100MHz")
    require(check_fclk_enabled(clock), "FCLK0 is not enabled")
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    output = subprocess.run(["dmesg", "--color=never"], check=True,
                            capture_output=True, text=True, timeout=10).stdout
    line = last_load(output)
    require(f": writing {candidate_bin.name} to " in line,
            "Last FPGA load is not the reviewed candidate")
    verify_receipt(read_json(receipt_path), boot_id=boot_id,
                   last_load_line=line, artifact=artifact)
    check_ownership()


def check_fclk_enabled(clock_summary: str) -> bool:
    rows = [r.split() for r in clock_summary.splitlines()
            if r.split() and r.split()[0].lower() in
            {"fclk0", "fclk_clk0", "fclk0_clk"}]
    return len(rows) == 1 and len(rows[0]) >= 3 and int(rows[0][2]) > 0


def check_ownership(*, sysroot: Path = Path("/sys"),
                    procroot: Path = Path("/proc")) -> None:
    """Five-aperture ownership check, including retained /dev/mem mmap.

    Cannot rule out rogue AXI bus masters; the approved development
    orchestrator must also own FPGA configuration and all PL consumers.
    """
    start, end = IDENTITY, LT02 + 4096
    def overlaps(a: int, b: int) -> bool:
        return a < end and b > start

    related_uio, unrelated_uio = set(), set()
    for uio in (sysroot / "class/uio").glob("uio*"):
        known, conflict = False, False
        for mapping in (uio / "maps").glob("map*"):
            known = True
            lo = int((mapping / "addr").read_text(), 0)
            hi = lo + int((mapping / "size").read_text(), 0)
            if overlaps(lo, hi):
                conflict = True
                related_uio.add("/dev/" + uio.name)
                require(not (uio / "device/driver").exists(),
                        "Conflicting kernel UIO owner: " + uio.name)
        if known and not conflict:
            unrelated_uio.add("/dev/" + uio.name)
    for device in (sysroot / "bus/platform/devices").iterdir():
        if not (device / "driver").exists():
            continue
        match = re.match(r"^([a-fA-F0-9]+)\\.", device.name)
        conflict = bool(match and overlaps(int(match[1], 16),
                                           int(match[1], 16) + 1))
        resource = device / "resource"
        if resource.exists():
            for line in resource.read_text().splitlines():
                lo, hi, flags = (int(v, 16) for v in line.split())
                if flags & 0x200 and overlaps(lo, hi + 1):
                    conflict = True
        require(not conflict, "Conflicting kernel PL resource: " + device.name)

    for pid in procroot.iterdir():
        if not pid.name.isdigit():
            continue
        try:
            for fd in (pid / "fd").iterdir():
                try:
                    path = os.readlink(fd)
                except FileNotFoundError:
                    continue
                require(path not in {"/dev/mem", "/dev/xdevcfg", "/dev/fpga0"}
                        and (not path.startswith("/dev/uio")
                             or path in unrelated_uio),
                        "Conflicting PL handle: PID " + pid.name)
            for line in (pid / "maps").read_text().splitlines():
                fields = line.split()
                if len(fields) < 6:
                    continue
                device = fields[5]
                if device not in {"/dev/mem", "/dev/xdevcfg", "/dev/fpga0"} \
                        and (not device.startswith("/dev/uio")
                             or device in unrelated_uio):
                    continue
                lo, hi = (int(v, 16) for v in fields[0].split("-"))
                offset = int(fields[2], 16)
                require(device == "/dev/mem" and
                        not overlaps(offset, offset + hi - lo),
                        "Conflicting retained PL mapping: PID " + pid.name)
        except FileNotFoundError:
            continue


def expected_identity(source_git_sha: str) -> dict[int, int]:
    require(type(source_git_sha) is str and
            bool(re.fullmatch(r"[a-f0-9]{40}", source_git_sha)),
            "Invalid source identity")
    words = (0x504C534D, 0x100, 1, 0,
             *(int(source_git_sha[i:i+8], 16) for i in range(0, 32, 8)))
    return {IDENTITY + index * 4: word for index, word in enumerate(words)}


def case_payload(length: int, case: int) -> bytes:
    return bytes(((i * 37 + (i >> 5) + case * 19) & 255)
                 for i in range(length))


def run_cases(mmio: LinuxMMIO, source_sha: str,
              lengths: tuple[int, ...] = LENGTHS) -> list[dict]:
    """Production driver only: verifies true readback, counters and CRC."""
    for address, word in expected_identity(source_sha).items():
        require(mmio.read32(address) == word,
                f"Candidate Identity mismatch at {address:#x}; STOP")
    observations = []
    with mmio.claim_site(site_id=1, base=LT02) as port:
        driver = LoopTestDriver(port, base=LT02, site_id=1)
        for case, length in enumerate(lengths):
            data = case_payload(length, case)
            response = driver.echo(data)
            require(response.payload == data and
                    response.tx_crc32 == response.rx_crc32 and
                    response.payload_length == len(data),
                    f"LT02 case {case} data/CRC mismatch")
            observations.append({
                "bytes": length,
                "chunks": response.chunks,
                "write_words": response.data_word_writes,
                "read_words": response.data_word_reads,
                "crc32": response.tx_crc32,
                "elapsed_ns": response.elapsed_ns,
            })
    return observations


def record(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["development"], default="development")
    for name in ("manifest", "bit", "hwh", "candidate-bin", "recovery-bin",
                 "recovery-hwh", "receipt", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--ack-unrecoverable-axi-stall-risk", action="store_true")
    args = parser.parse_args(argv)
    if not (args.execute_live and args.ack_unrecoverable_axi_stall_risk):
        print("LT02_NO_GO: inert without both live flags", file=sys.stderr)
        return 2
    try:
        require(not args.output.exists(), "Evidence output must not exist")
        check_runtime()
        artifact = verify_artifacts(
            args.manifest, args.bit, args.hwh, args.candidate_bin,
            args.recovery_bin, args.recovery_hwh,
            args.expected_manifest_sha256)
        verify_live_environment(args.receipt, args.candidate_bin, artifact)
    except (OSError, ValueError, TypeError, KeyError, LT02SafetyError,
            old.SafetyError, subprocess.SubprocessError) as exc:
        print("LT02_NO_GO: " + str(exc), file=sys.stderr)
        return 2

    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    base = {
        "scope": "LT02-05", "profile": "development",
        "source_git_sha": artifact["source_git_sha"],
        "candidate_bin_sha256": artifact["candidate_bin_sha256"],
        "manifest_sha256": artifact["manifest_sha256"],
        "load_receipt_sha256": digest(args.receipt),
        "python": platform.python_version(),
        "hardware": "Z2-ARMv7-native-LinuxMMIO",
        "fpga_recovery": "NOT_RUN",
        "physical_swd": "NOT_RUN",
        "real_ic_programming": "NOT_RUN",
    }
    record(args.output / "started.json", {
        **base, "result": "STARTED",
        "started_utc": datetime.now(timezone.utc).isoformat(),
    })
    try:
        aperture = MMIOAperture(IDENTITY, frozenset(range(0, 0x20, 4)),
                                frozenset())
        with LinuxMMIO((aperture, loopback_aperture(LT02)),
                       device="/dev/mem",
                       owner_lock="/run/lock/plasma-mmio.lock") as mmio:
            results = run_cases(mmio, artifact["source_git_sha"])
        result = {"result": "PASS", "cases": results,
                  "source": "real PS LinuxMMIO when executed on Z2"}
    except (OSError, ValueError, RuntimeError) as exc:
        result = {"result": "FAIL", "error": str(exc),
                  "stop_without_retry": True}
    record(args.output / "result.json", {
        **base, **result,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    })
    if result["result"] != "PASS":
        print("LT02_STOP: HIL failure; supervised image recovery required",
              file=sys.stderr)
        return 2
    print("LT02_REAL_MMIO_CASES_PASS_FPGA_RECOVERY_NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
