"""Compile and execute the actual native C SWD FIFO core, HOST-ONLY.

This invokes a Linux hosted C compiler against injected C fake MMIO, not
SWPC Vivado, OpenOCD binary integration, ARMv7 device memory or DUT.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "software/native/swd"


def test_native_c_core_compiles_cleanly_and_blocks_uncertain_replay(tmp_path):
    cc = shutil.which("cc")
    assert cc, "GitHub-hosted C compiler is a required validation dependency"
    executable = tmp_path / "host-only-swd-fifo"
    source = SRC / "plasma_swd_fifo_core.c"
    test = SRC / "tests/test_plasma_swd_fifo_core.c"
    compile_cmd = [
        cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-O2", "-fno-strict-aliasing", "-I", str(SRC),
        str(source), str(test), "-o", str(executable),
    ]
    built = subprocess.run(compile_cmd, text=True, capture_output=True,
                           timeout=30, check=False)
    assert built.returncode == 0, built.stdout + built.stderr
    verified = subprocess.run((str(executable),), text=True,
                              capture_output=True, timeout=10, check=False)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "PLASMA_NATIVE_SWD_C_HOST_ONLY_PASS" in verified.stdout


def test_c_core_is_separate_from_hardware_and_retired_debug_mode():
    c = (SRC / "plasma_swd_fifo_core.c").read_text(encoding="utf-8")
    h = (SRC / "plasma_swd_fifo_core.h").read_text(encoding="utf-8")
    assert "PLASMA_SWD_ABI_V5" in h and "PLASMA_SWD_MAX_QUEUE 16u" in h
    for forbidden in (
        "/dev/mem\"", "open(", "mmap(", "ioctl(", "system(",
        "MODE_DEBUG", "remote_bitbang", "socket(", "execve(",
    ):
        assert forbidden not in c, forbidden
    assert "PLASMA_SWD_ACK_WAIT" in c and "PLASMA_SWD_ACK_FAULT" in c
    assert "PLASMA_SWD_UNSUPPORTED" in c and "s->blocked" in c
