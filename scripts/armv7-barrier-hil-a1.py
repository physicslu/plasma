#!/usr/bin/env python3
"""HIL-A1 SWPC cross-build/ELF inspection. Never opens hardware or networks.

Only intended for the separately authorized, main-only workflow_dispatch.
Host CI tests validate_elf() with synthetic binutils output; they do not cross
compile ARMv7 or execute the resulting library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "software/python/native/armv7_mmio_barrier.c"
PREFIX = "arm-linux-gnueabihf"
SYMBOL = "plasma_mmio_dmb_sy"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class HILA1Error(RuntimeError):
    pass


def validate_elf(header: str, attributes: str, symbols: str, disassembly: str) -> None:
    """Refuse an ABI mismatch or a library without the exact exported DMB SY."""
    checks = (
        ("ELF32", re.search(r"(?m)^\s*Class:\s+ELF32\s*$", header)),
        ("little-endian ELF", re.search(r"(?m)^\s*Data:\s+2's complement, little endian\s*$", header)),
        ("ARM machine", re.search(r"(?m)^\s*Machine:\s+ARM\s*$", header)),
        ("shared object", re.search(r"(?m)^\s*Type:\s+DYN\s+\(", header)),
        ("EABI version 5", re.search(r"(?m)^\s*Flags:.*\bVersion5 EABI\b", header)),
        ("ARMv7 CPU tag", re.search(r"(?m)^\s*Tag_CPU_arch:\s+v7\s*$", attributes)),
        ("hard-float ABI", re.search(r"(?m)^\s*Tag_ABI_VFP_args:\s+VFP registers\s*$", attributes)),
        ("defined globally exported DMB function", re.search(
            rf"(?m)^\s*\d+:\s+[0-9a-fA-F]+\s+\d+\s+FUNC\s+GLOBAL\s+DEFAULT\s+\d+\s+{SYMBOL}\s*$",
            symbols,
        )),
    )
    for what, matched in checks:
        if matched is None:
            raise HILA1Error(f"ARMv7 ELF validation failed: {what}")

    # Only accept the DMB SY inside the named, explicitly disassembled function.
    opening = re.search(rf"(?m)^[0-9a-fA-F]+ <{SYMBOL}>:\s*$", disassembly)
    if opening is None:
        raise HILA1Error("ARMv7 disassembly missing exact DMB symbol")
    body = disassembly[opening.end():]
    next_label = re.search(r"(?m)^[0-9a-fA-F]+ <[^>]+>:\s*$", body)
    if next_label:
        body = body[:next_label.start()]
    actual = re.findall(r"(?m)^\s*[0-9a-fA-F]+:\s+(?:[0-9a-fA-F]{2,8}\s+)+dmb\s+sy\s*(?:;.*)?$", body)
    if len(actual) != 1:
        raise HILA1Error("ARMv7 function must contain exactly one DMB SY instruction")
    if re.search(r"(?m)^\s*[0-9a-fA-F]+:\s+.*\b(?:blx?|svc|hvc|smc)\b", body):
        raise HILA1Error("Unexpected branch/call/trap in minimal barrier symbol")


def _run(argv: list[str], *, timeout: int = 90) -> str:
    try:
        result = subprocess.run(
            argv, cwd=REPO, check=True, text=True,
            capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise HILA1Error(f"Trusted tool failed: {Path(argv[0]).name}") from exc
    return result.stdout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output_dir: Path, expected_sha: str) -> dict[str, object]:
    if not SHA_RE.fullmatch(expected_sha):
        raise HILA1Error("Reviewed Git commit SHA must be exactly 40 lowercase hex characters")
    if _run(["git", "rev-parse", "HEAD"]).strip() != expected_sha:
        raise HILA1Error("Checkout changed from authorized GitHub main SHA")
    if not SOURCE.is_file() or SOURCE.is_symlink():
        raise HILA1Error("Reviewed native C source missing or is a symlink")
    if not os.getenv("RUNNER_TEMP"):
        raise HILA1Error("Explicit GitHub Runner temp directory is required")

    temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    output_dir = output_dir.resolve()
    if not output_dir.is_relative_to(temp) or output_dir == temp:
        raise HILA1Error("Build output must be a private child of RUNNER_TEMP")
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    output_dir.chmod(0o700)

    tools = {name: shutil.which(f"{PREFIX}-{name}") for name in ("gcc", "readelf", "objdump")}
    if any(value is None for value in tools.values()):
        raise HILA1Error("ARM hard-float cross compiler and binutils are not installed")
    if _run([tools["gcc"], "-dumpmachine"]).strip() != PREFIX:
        raise HILA1Error("Cross compiler triplet is not ARM GNU EABI hard-float")

    so = output_dir / "libplasma_mmio_barrier.so"
    _run([
        tools["gcc"], "-march=armv7-a", "-marm", "-mfpu=vfpv3",
        "-mfloat-abi=hard", "-O2", "-fPIC", "-shared",
        "-Wl,-z,relro", "-Wl,-z,now",
        "-o", str(so), str(SOURCE),
    ])
    if not so.is_file() or so.is_symlink():
        raise HILA1Error("Compiled output is not an ordinary library file")

    results = {
        "elf-header.txt": _run([tools["readelf"], "-h", str(so)]),
        "elf-attributes.txt": _run([tools["readelf"], "-A", str(so)]),
        "elf-symbols.txt": _run([tools["readelf"], "-Ws", str(so)]),
        "barrier-disassembly.txt": _run([
            tools["objdump"], "-d", f"--disassemble={SYMBOL}", str(so),
        ]),
    }
    validate_elf(
        results["elf-header.txt"], results["elf-attributes.txt"],
        results["elf-symbols.txt"], results["barrier-disassembly.txt"],
    )
    for filename, content in results.items():
        (output_dir / filename).write_text(content, encoding="utf-8")

    receipt = {
        "schema": "plasma-hil-a1-armv7-barrier-build-v1",
        "result": "PASS",
        "scope": "SWPC cross-build and ELF inspection only",
        "github_sha": expected_sha,
        "source_path": SOURCE.relative_to(REPO).as_posix(),
        "source_sha256": _sha256(SOURCE),
        "binary": so.name,
        "binary_sha256": _sha256(so),
        "compiler_triplet": PREFIX,
        "compiler_version": _run([tools["gcc"], "--version"]).splitlines()[0],
        "tool_binaries": {name: str(Path(value).resolve()) for name, value in tools.items()},
        "inspection_sha256": {
            name: _sha256(output_dir / name) for name in sorted(results)
        },
        "z2_native_execution": "NOT_RUN",
        "physical_mmio_or_uio": "NOT_RUN",
        "fpga_or_dut": "NOT_RUN",
        "m1": "NO_GO",
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print("HIL-A1 Cross Compile / ELF / DMB SY: PASS; Z2: NOT_RUN")
    print(f"Binary SHA256: {receipt['binary_sha256']}")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build",))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args(argv)
    try:
        build(args.output_dir, args.expected_sha)
        return 0
    except HILA1Error as exc:
        print(f"HIL-A1 FAIL: {exc}; Z2 NOT_RUN", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
