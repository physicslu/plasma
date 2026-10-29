"""Compile/execute inactive Native C Site recovery session gate, HOST-ONLY.

This test deliberately does NOT build PR #1189's FIFO or grant Root access.
It validates a future callsite contract, not deployed SWD safety.
"""
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "software/native/swd"


def test_native_c_recovery_guard_host_only(tmp_path):
    cc = shutil.which("cc")
    assert cc, "Linux C compiler is a required CI dependency"
    binary = tmp_path / "native-swd-recovery-gate"
    command = [
        cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-O2", "-I", str(NATIVE),
        str(NATIVE / "plasma_swd_recovery_gate.c"),
        str(NATIVE / "tests/test_plasma_swd_recovery_gate.c"),
        "-o", str(binary),
    ]
    built = subprocess.run(command, capture_output=True, text=True,
                           timeout=30, check=False)
    assert built.returncode == 0, built.stdout + built.stderr
    done = subprocess.run([str(binary)], capture_output=True, text=True,
                          timeout=15, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PLASMA_SWD_RECOVERY_GATE_HOST_ONLY_PASS" in done.stdout


def test_native_c_gate_has_no_root_hardware_or_automatic_recovery():
    source = (NATIVE / "plasma_swd_recovery_gate.c").read_text()
    header = (NATIVE / "plasma_swd_recovery_gate.h").read_text()
    fake = (NATIVE / "tests/test_plasma_swd_recovery_gate.c").read_text()
    assert "authority->begin(" in source
    assert "authority->check(" in source
    assert "authority.execute_while_owned(" in source
    assert "gate->owner_pid != getpid()" in source
    assert "push(push_ctx)" not in source
    assert "push(push_ctx)" in fake
    assert "a->inside_guard" in fake
    assert "PLASMA_RECOVERY_UNCERTAIN" in source
    # Scan C tokens, not explanatory comments mentioning prohibited paths.
    code = re.sub(r"/\*.*?\*/", "", source + "\n" + header, flags=re.DOTALL)
    for forbidden in ("/dev/mem", "mmap(", "ioctl(", "system(",
                      "execve(", "mark_ready", "clear_uncertain",
                      "retry_write", "sudo "):
        assert forbidden not in code
