#!/usr/bin/env python3
"""PLASMA HIL-A1.5: offline pinned A1 artifact verification and ARMv7 QEMU smoke.

This tool never opens real MMIO/UIO, FPGA or DUT; 'execute' is allowed only
inside a verified ARMv7 Linux Python process. No network, SSH or device I/O.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import struct
import sys

EXPECTED_BINARY_SHA256 = "435e8a1e14b644396a5a14b52211bb50535176448442c08b4b55aed1a0463956"
A1_GITHUB_HEAD = "4f79aea1744333bb08720aa9cbda555140523066"
A1_RUN_ID = 39192248348
A1_ARTIFACT_ID = 12160282344
A1_NAME = "plasma-armv7-hil-a1-pr-39192248348"
BIN = "libplasma_mmio_barrier.so"
FILES = frozenset((BIN, "receipt.json", "SHA256SUMS", "elf-header.txt",
                   "elf-attributes.txt", "elf-symbols.txt", "barrier-disassembly.txt"))
SNAPSHOT = "20261005T000000Z"
IMAGE = ("debian:bookworm-20261005@sha256:"
         "bc49dc1918ee1a47a93e65b5e4676e8680fb754b133197b92ca52bfe6731d5f0")
FUNCTION = "plasma_mmio_dmb_sy"


class Rejected(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise Rejected(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_artifact(path: Path) -> dict:
    """Verify exact 7-file artifact, all six SHA256SUMS and ARMv7 ELF ABI."""
    require(path.is_dir() and not path.is_symlink(), "Artifact is not a real directory")
    names = {p.name for p in path.iterdir()}
    require(names == FILES, f"Artifact exact file inventory mismatch: {sorted(names ^ FILES)}")
    for name in FILES:
        item = path / name
        require(not item.is_symlink() and item.is_file(), f"Non-regular/symlink artifact: {name}")
        require(stat.S_ISREG(item.stat().st_mode), f"Invalid artifact type: {name}")
        require(item.stat().st_size > 0 and item.stat().st_size <= 65536,
                f"Artifact file size is out of bounds: {name}")

    sums = (path / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    seen = set()
    for line in sums:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        require(match is not None, "Malformed SHA256 manifest line")
        digest, name = match.groups()
        require(name in FILES - {"SHA256SUMS"} and name not in seen,
                "Unapproved/duplicate artifact manifest path")
        seen.add(name)
        require(sha256(path / name) == digest, f"SHA256 manifest mismatch: {name}")
    require(seen == FILES - {"SHA256SUMS"}, "SHA256 manifest does not cover every file")
    require(sha256(path / BIN) == EXPECTED_BINARY_SHA256, "A1 ELF pinned digest mismatch")

    raw = (path / BIN).read_bytes()
    require(raw[:6] == b"\x7fELF\x01\x01", "ELF must be little-endian ELF32")
    require(struct.unpack_from("<H", raw, 16)[0] == 3, "ELF type must be shared object")
    require(struct.unpack_from("<H", raw, 18)[0] == 40, "ELF machine must be ARM")
    require((struct.unpack_from("<I", raw, 36)[0] >> 24) == 5,
            "ELF must be ARM EABI5")
    receipt = json.loads((path / "receipt.json").read_text(encoding="utf-8"))
    require(type(receipt) is dict and receipt.get("schema") == "plasma-hil-a1-armv7-barrier-build-v1",
            "Invalid A1 receipt schema")
    for field, value in (
        ("result", "PASS"), ("binary", BIN), ("binary_sha256", EXPECTED_BINARY_SHA256),
        ("compiler_triplet", "arm-linux-gnueabihf"),
        ("toolchain_image", IMAGE), ("toolchain_snapshot", SNAPSHOT),
        ("z2_native_execution", "NOT_RUN"), ("physical_mmio_or_uio", "NOT_RUN"),
        ("fpga_or_dut", "NOT_RUN"), ("m1", "NO_GO"),
    ):
        require(receipt.get(field) == value, f"A1 receipt mismatch: {field}")
    require(re.fullmatch(r"[a-f0-9]{40}", receipt.get("github_sha", "")) is not None,
            "A1 checkout identity must be a Git commit SHA")
    require(receipt.get("inspection_sha256") == {
        name: sha256(path / name)
        for name in sorted(FILES & {"elf-header.txt", "elf-attributes.txt",
                                    "elf-symbols.txt", "barrier-disassembly.txt"})
    }, "A1 inspection digest mismatch")
    require("dmb sy" in (path / "barrier-disassembly.txt").read_text().lower(),
            "No DMB SY instruction in pinned disassembly")
    return {
        "schema": "plasma-hil-a15-artifact-check-v1",
        "status": "PASS",
        "source_run_id": A1_RUN_ID,
        "source_artifact_id": A1_ARTIFACT_ID,
        "source_head_sha": A1_GITHUB_HEAD,
        "elf_sha256": EXPECTED_BINARY_SHA256,
        "manifest_file_count": len(seen),
        "m1": "NO_GO",
    }


def execute(path: Path, report: Path, repetitions: int) -> dict:
    """CPU-only run. Real Z2 acceptance is explicitly NOT established."""
    require(repetitions == 1000, "Only the reviewed 1000-call fixed probe is permitted")
    require(platform.machine().lower() in {"armv7l", "armv7"},
            "Execution requires genuine/emulated ARMv7 Linux userspace")
    require(sys.byteorder == "little" and ctypes.sizeof(ctypes.c_void_p) == 4,
            "Execution requires 32-bit little-endian Python ABI")
    evidence = check_artifact(path)
    binary = (path / BIN).resolve(strict=True)
    before = sha256(binary)
    # RTLD_LOCAL keeps this symbol out of the global process symbol namespace.
    library = ctypes.CDLL(str(binary), mode=ctypes.RTLD_LOCAL)
    barrier = getattr(library, FUNCTION)
    barrier.argtypes = []
    barrier.restype = None
    for _ in range(repetitions):
        barrier()
    require(sha256(binary) == before, "A1 shared library changed during CPU exercise")
    require(report.parent.is_dir() and not report.is_symlink() and
            not report.exists(), "Evidence output must be a fresh ordinary file")
    result = {
        **evidence,
        "schema": "plasma-hil-a15-armv7-qemu-runtime-v1",
        "status": "PASS",
        "cpu": platform.machine(),
        "python": platform.python_version(),
        "process_pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
        "function": FUNCTION,
        "calls": repetitions,
        "emu_execution": "PASS",
        "real_z2_a2": "NOT_RUN",
        "mmio_uio": "NOT_RUN",
        "fpga_dut": "NOT_RUN",
        "m1": "NO_GO",
    }
    report.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("verify", "execute"))
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--repetitions", type=int, default=1000)
    args = parser.parse_args()
    try:
        if args.operation == "verify":
            require(args.report is None, "verify has no output side effects")
            data = check_artifact(args.artifact_dir)
            print("PLASMA_HIL_A15_PINNED_ARTIFACT_PASS", json.dumps(data, sort_keys=True))
        else:
            require(args.report is not None, "execute requires a report path")
            data = execute(args.artifact_dir, args.report, args.repetitions)
            print("PLASMA_HIL_A15_QEMU_PASS", json.dumps(data, sort_keys=True))
        return 0
    except (Rejected, OSError, ValueError, json.JSONDecodeError, AttributeError) as exc:
        print(f"PLASMA_HIL_A15_FAIL: {exc}; Z2 NOT_RUN", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
