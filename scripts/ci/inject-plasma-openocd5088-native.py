#!/usr/bin/env python3
"""Fail-closed source-locked integration of PLASMA C SWD into OpenOCD.

This only modifies an ephemeral, clean checkout of OpenOCD pinned at
5088db4c9154ca833c6d558381074b33672e127a on GitHub-hosted CI.
Does not touch a system OpenOCD binary, /dev/mem, DUT or SWPC.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys


OPENOCD_SHA = "5088db4c9154ca833c6d558381074b33672e127a"
NATIVE = Path("software/native/swd")
COPIES = (
    "plasma_swd_fifo_core.h",
    "plasma_swd_fifo_core.c",
    "plasma_swd_lease_word_port.h",
    "plasma_swd_lease_word_port.c",
    "plasma_swd_owner_lock.h",
    "plasma_swd_owner_lock.c",
    "plasma_swd_native_words.h",
    "plasma_swd_native_words.c",
    "plasma_swd_openocd5088_binding.h",
    "plasma_swd_openocd5088_callbacks.c",
    "plasma_swd_openocd5088_driver.c",
)


def replace_once(path: Path, original: str, replacement: str) -> None:
    before = path.read_text(encoding="utf-8")
    if before.count(original) != 1 or "plasma_swd_adapter_driver" in before:
        raise RuntimeError(f"Unrecognized or prepatched OpenOCD source: {path}")
    path.write_text(before.replace(original, replacement, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openocd", type=Path, required=True,
                        help="Clean source-locked ephemeral OpenOCD checkout")
    parser.add_argument("--plasma", type=Path,
                        default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    upstream, plasma = args.openocd.resolve(), args.plasma.resolve()
    if upstream == plasma or plasma in upstream.parents:
        raise RuntimeError("Never modify a checkout within PLASMA repository")
    head = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if head != OPENOCD_SHA:
        raise RuntimeError(f"OpenOCD source SHA mismatch: {head}")
    dirty = subprocess.check_output(
        ["git", "-C", str(upstream), "status", "--porcelain"], text=True)
    if dirty:
        raise RuntimeError("OpenOCD source is not an untouched clean checkout")
    source_dir = plasma / NATIVE
    target_dir = upstream / "src/jtag/drivers"
    for name in COPIES:
        source = source_dir / name
        if not source.is_file() or (target_dir / name).exists():
            raise RuntimeError(f"Missing PLASMA source or duplicate: {name}")
    header = upstream / "src/jtag/interface.h"
    interfaces = upstream / "src/jtag/interfaces.c"
    makefile = upstream / "src/jtag/drivers/Makefile.am"
    guards = (
        (header, "extern struct adapter_driver dummy_adapter_driver;"),
        (interfaces, "#if BUILD_DUMMY == 1\n\t\t&dummy_adapter_driver,\n#endif"),
        (makefile, "DRIVERFILES += %D%/driver.c"),
    )
    for path, marker in guards:
        txt = path.read_text(encoding="utf-8")
        if txt.count(marker) != 1 or "plasma_swd_adapter_driver" in txt:
            raise RuntimeError(f"Unexpected pinned source layout: {path}")
    replace_once(
        header,
        "extern struct adapter_driver dummy_adapter_driver;",
        "extern struct adapter_driver dummy_adapter_driver;\n"
        "extern struct adapter_driver plasma_swd_adapter_driver;",
    )
    replace_once(
        interfaces,
        "#if BUILD_DUMMY == 1\n\t\t&dummy_adapter_driver,\n#endif",
        "#if BUILD_DUMMY == 1\n\t\t&dummy_adapter_driver,\n#endif\n"
        "\t\t&plasma_swd_adapter_driver,",
    )
    replace_once(
        makefile,
        "DRIVERFILES += %D%/driver.c",
        "DRIVERFILES += %D%/driver.c\n"
        "DRIVERFILES += %D%/plasma_swd_fifo_core.c\n"
        "DRIVERFILES += %D%/plasma_swd_lease_word_port.c\n"
        "DRIVERFILES += %D%/plasma_swd_owner_lock.c\n"
        "DRIVERFILES += %D%/plasma_swd_native_words.c\n"
        "DRIVERFILES += %D%/plasma_swd_openocd5088_callbacks.c\n"
        "DRIVERFILES += %D%/plasma_swd_openocd5088_driver.c",
    )
    for name in COPIES:
        shutil.copyfile(source_dir / name, target_dir / name)
        data = (target_dir / name).read_bytes()
        print(f"INJECT {name} sha256={hashlib.sha256(data).hexdigest()}")
    print(f"PLASMA_OPENOCD5088_SOURCE_LOCKED_INJECT_PASS {head}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"SOURCE_LOCK_INJECT_FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
