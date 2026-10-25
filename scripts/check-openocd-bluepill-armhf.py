#!/usr/bin/env python3
"""Development-only ARMhf ABI/closure and QEMU admission; never opens an adapter."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess


def required_glibc(text: str, *, libc_loader_pair: bool = False) -> tuple[int, ...]:
    # Definitions in libc describe exports, not required versions.
    needs = text.split("Version needs section", 1)[-1] if "Version needs section" in text else ""
    versions = [tuple(map(int, v.split('.'))) for v in re.findall(r"Name: GLIBC_([0-9.]+)", needs)]
    if "GLIBC_ABI_" in needs or ("GLIBC_PRIVATE" in needs and not libc_loader_pair):
        raise ValueError("unsupported private/ABI GLIBC requirement")
    maximum = max(versions, default=(0,))
    if maximum > (2, 35):
        raise ValueError(f"requires GLIBC_{'.'.join(map(str, maximum))} > 2.35")
    return maximum


def check_armhf(header: str) -> None:
    for pattern in (r"Class:\s+ELF32", r"Data:.*little endian", r"Machine:\s+ARM\s*$", r"Flags:.*Version5 EABI.*hard-float ABI"):
        if not re.search(pattern, header, re.M):
            raise ValueError(f"not ARM EABI5 hard float: {pattern}")


def check_adapter(text: str) -> None:
    if not re.search(r"^remote_bitbang\s+\{[^}\n]*\bswd\b[^}\n]*\}", text, re.M):
        raise ValueError("missing remote_bitbang SWD adapter")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("sysroot", type=Path)
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--readelf", default="readelf")
    args = parser.parse_args()
    root = args.sysroot.resolve()

    def run(argv: list[str]) -> str:
        print("COMMAND", ' '.join(argv), flush=True)
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        for key in ("LD_PRELOAD", "LD_LIBRARY_PATH", "QEMU_LD_PREFIX", "QEMU_SET_ENV", "QEMU_UNSET_ENV"):
            env.pop(key, None)
        result = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, env=env)
        print(result.stdout, end="" if result.stdout.endswith('\n') else '\n')
        print("EXIT", result.returncode, flush=True)
        if result.returncode:
            raise ValueError("command failed")
        return result.stdout

    def library(name: str) -> Path:
        # Resolve target absolute symlinks within sysroot, never against host /lib.
        paths = [root / name.lstrip('/')] if name.startswith('/') else [root / d / name for d in ("lib", "usr/lib", "lib/arm-linux-gnueabihf", "usr/lib/arm-linux-gnueabihf")]
        for candidate in paths:
            for _ in range(20):
                if not candidate.is_symlink():
                    break
                target = os.readlink(candidate)
                candidate = root / target.lstrip('/') if target.startswith('/') else candidate.parent / target
            if candidate.is_file() and candidate.resolve().is_relative_to(root):
                return candidate.resolve()
        raise ValueError(f"missing/conflicting target library: {name}")

    pending = [args.binary.resolve()]
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        print("ELF", path, "SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
        header = run([args.readelf, "-h", str(path)])
        check_armhf(header)
        program = run([args.readelf, "-l", str(path)])
        dynamic = run([args.readelf, "-d", str(path)])
        versions = run([args.readelf, "--version-info", str(path)])
        # Jammy libc and its matching loader use their internal private interface.
        internal = path != args.binary.resolve() and path.name in {"libc.so.6", "ld-linux-armhf.so.3"}
        print("MAX_REQUIRED_GLIBC", required_glibc(versions, libc_loader_pair=internal))
        if re.search(r"\((?:RPATH|RUNPATH)\)", dynamic):
            raise ValueError("unexpected runtime search path")
        for needed in re.findall(r"\(NEEDED\).*\[([^]]+)\]", dynamic):
            pending.append(library(needed))
        loader = re.search(r"Requesting program interpreter:\s*([^]\s]+)", program)
        if path == args.binary.resolve():
            if not loader or loader[1] != "/lib/ld-linux-armhf.so.3":
                raise ValueError("unexpected ARMhf loader")
            attributes = run([args.readelf, "-A", str(path)])
            if not re.search(r"Tag_CPU_arch:\s+v7\s*$", attributes, re.M):
                raise ValueError("expected ARMv7")
        if loader:
            pending.append(library(loader[1]))
    base = [args.qemu, "-cpu", "cortex-a9", "-L", str(root), str(args.binary.resolve())]
    run(base + ["--version"])
    check_adapter(run(base + ["-c", "adapter list", "-c", "shutdown"]))
    selected = run(base + ["-c", "adapter driver remote_bitbang", "-c", "transport select swd", "-c", "echo [transport select]", "-c", "shutdown"])
    if not re.search(r"^swd\s*$", selected, re.M):
        raise ValueError("SWD selection not observed")
    print("PASS: ARMv7 hard-float closure GLIBC <=2.35; QEMU admission only; native Z2/hardware NOT_RUN")


if __name__ == "__main__":
    main()
