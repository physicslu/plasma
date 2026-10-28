#!/usr/bin/env python3
"""Profile-gated, image-agnostic Native C WordPort programming prototype.

Path 2 uses --role swpc (pinned SSH); standalone Z2 uses --role z2.
Neither route installs software, loads an FPGA Image or automatically retries.
DUT reset is allowed ONLY in explicitly owner-attested reset-run mode.
This PoC exposes one currently verified physical route, not unrestricted IC support.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import time

BUNDLE = Path("/home/xilinx/plasma-native-c-wordport-1199")
Z2_ENTRY = BUNDLE / "scripts/plasma_wordport_program.py"
ROOT = Path("/root/plasma-path2-approved")
PYTHON = "/opt/plasma/python/3.12.13/bin/python3"
OPENOCD = "/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/bin/openocd"
OPENOCD_SCRIPTS = "/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/share/openocd/scripts"
NATIVE_SHA = "66261cef851c9777469b393b7539c5b0f8c2b039a032f1a5b4cbf9e93460e447"
SESSION_SHA = "ce325d8c965f36208036158a2bce810f445f4ff053415f96e62fba156ff41650"
PY_MODULE_SHA = "57dfad519993910ae04e1b05b1592b06d9db856b665a50bd81dd47dc6154b3ef"
# Flash geometry belongs to the exact target/provider, never to a firmware revision.
# Additional target support must be admitted through a reviewed Programming Profile.
PROFILE = {
    "icpn": "STM32F103C8T6", "site_id": 1,
    "target_cfg": "target/stm32f1x.cfg", "main_flash_base": 0x08000000,
    "main_flash_bytes": 65536, "erase_granularity_bytes": 1024,
    "program_granularity_bytes": 2,
    # Until independently qualified, leave the final two 1-KiB pages untouched.
    # Prior physical backup showed non-erased content in the last page.
    "max_erase_bytes": 0xF800,
}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./-]+\Z")


class NotRun(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_at(value: str) -> Path:
    if not SAFE_PATH.fullmatch(value) or ".." in Path(value).parts:
        raise NotRun(77, "UNSAFE_PATH")
    p = Path(value)
    if p.is_symlink() or not p.is_file() or not stat.S_ISREG(p.stat().st_mode):
        raise NotRun(69, "FILE_NOT_AVAILABLE")
    return p


def check_source(expected: str) -> None:
    if not HEX64.fullmatch(expected) or sha(Path(__file__).resolve()) != expected:
        raise NotRun(77, "REVIEWED_SOURCE_SHA_MISMATCH")


def admit_image(operation: str, path: str | None, expected_sha: str | None):
    """Admit any caller-selected BIN by expected SHA and target geometry.

    SHA must originate from the independent owner-approved Work Order / Asset,
    not from trusting a digest recomputed from the device file at invocation.
    """
    if bool(path) != bool(expected_sha):
        raise NotRun(77, "IMAGE_PATH_AND_SHA_REQUIRED_TOGETHER")
    if operation == "program" and not path:
        raise NotRun(77, "PROGRAM_IMAGE_REQUIRED")
    if not path:
        return None, 0, None, 0
    source = file_at(path)
    size = source.stat().st_size
    if not HEX64.fullmatch(expected_sha) or sha(source) != expected_sha:
        raise NotRun(77, "IMAGE_SHA256_MISMATCH")
    if not 0 < size <= PROFILE["main_flash_bytes"]:
        raise NotRun(77, "IMAGE_OUTSIDE_TARGET_FLASH")
    if size % PROFILE["program_granularity_bytes"]:
        raise NotRun(77, "IMAGE_PROGRAM_ALIGNMENT_UNSUPPORTED")
    gran = PROFILE["erase_granularity_bytes"]
    erase = (size + gran - 1) // gran * gran
    if erase > PROFILE["main_flash_bytes"]:
        raise NotRun(77, "ERASE_OUTSIDE_TARGET_FLASH")
    if erase > PROFILE["max_erase_bytes"]:
        raise NotRun(77, "ERASE_OUTSIDE_APPROVED_RANGE")
    return source, size, expected_sha, erase


# Runs ONLY when a Flash Erase/Program/Verify/Readback call raises an error.
# This is same-session forensic capture, not a subsequent fresh SWD attach.
# Read every individual address independently: a locked-up Cortex-M may reject
# some reads while still allowing useful FLASH_SR and SCB fault registers.
# Never clear W1C fault flags, reset, retry or resume a partially written image.
FAILURE_DIAGNOSTIC_TCL = r"""
proc plasma_diag {stage cause} {
    echo "PLASMA_DIAG_BEGIN $stage"
    echo "PLASMA_DIAG_CAUSE $cause"
    echo "PLASMA_DIAG_SNAPSHOT_IN_SESSION"
    foreach spec {
        {DHCSR 0xE000EDF0}
        {DBGMCU_IDCODE 0xE0042000}
        {SCB_CPUID 0xE000ED00}
        {ICSR 0xE000ED04}
        {SHCSR 0xE000ED24}
        {CFSR 0xE000ED28}
        {HFSR 0xE000ED2C}
        {DFSR 0xE000ED30}
        {MMFAR 0xE000ED34}
        {BFAR 0xE000ED38}
        {FLASH_SR 0x4002200C}
        {FLASH_CR 0x40022010}
        {FLASH_AR 0x40022014}
    } {
        set name [lindex $spec 0]
        set address [lindex $spec 1]
        if {[catch {set values [read_memory $address 32 1]} reason]} {
            echo "PLASMA_DIAG_MEM_FAIL $name $reason"
            continue
        }
        if {[llength $values] != 1 || ![string is integer -strict [lindex $values 0]]} {
            echo "PLASMA_DIAG_MEM_FAIL $name INVALID_READ_VALUE"
            continue
        }
        echo "PLASMA_DIAG_MEM_PASS $name [format 0x%08X [expr {[lindex $values 0] & 0xFFFFFFFF}]]"
    }
    # Capture memory-mapped fault registers BEFORE poll/halt, which can alter
    # the target fault context. Never resume after a failed Flash operation.
    if {[catch {poll} reason]} {
        echo "PLASMA_DIAG_POLL_FAIL $reason"
        echo "PLASMA_DIAG_CORE_SKIP POLL_FAILED"
    } else {
        set before [stm32f1x.cpu curstate]
        echo "PLASMA_DIAG_STATE_BEFORE $before"
        if {$before eq "running"} {
            echo "PLASMA_DIAG_HALT_REQUESTED"
            if {[catch {halt} reason]} {
                echo "PLASMA_DIAG_HALT_FAIL $reason"
            }
        }
        set after [stm32f1x.cpu curstate]
        echo "PLASMA_DIAG_STATE_AFTER $after"
        if {$after ne "halted"} {
            echo "PLASMA_DIAG_CORE_SKIP TARGET_NOT_HALTED"
        } else {
            # OpenOCD uses the lowercase register key 'xpsr' (NOT 'xPSR').
            foreach spec {{pc pc} {sp sp} {lr lr} {xpsr xPSR}} {
                set key [lindex $spec 0]
                set label [lindex $spec 1]
                if {[catch {set values [get_reg -force [list $key]]} reason]} {
                    echo "PLASMA_DIAG_REG_FAIL $label $reason"
                    continue
                }
                if {![dict exists $values $key] || ![string is integer -strict [dict get $values $key]]} {
                    echo "PLASMA_DIAG_REG_FAIL $label INVALID_READ_VALUE"
                    continue
                }
                echo "PLASMA_DIAG_REG_PASS $label [format 0x%08X [expr {[dict get $values $key] & 0xFFFFFFFF}]]"
            }
        }
    }
    echo "PLASMA_DIAG_END $stage"
}
"""


FAILURE_MEMORY_REGISTERS = (
    "DHCSR", "DBGMCU_IDCODE", "SCB_CPUID", "ICSR", "SHCSR",
    "CFSR", "HFSR", "DFSR", "MMFAR", "BFAR",
    "FLASH_SR", "FLASH_CR", "FLASH_AR",
)
FAILURE_CORE_REGISTERS = ("pc", "sp", "lr", "xPSR")


def read_failure_diagnostics(log: str) -> dict:
    """Extract partial REAL same-session values, never infer missing registers.

    Flash timeout may prevent even the best-effort diagnostic; each missing
    register is an explicit failure/absence, not a synthetic zero or PASS.
    """
    begin = re.findall(r"(?m)^PLASMA_DIAG_BEGIN (ERASE|PROGRAM|VERIFY|READBACK)$", log)
    end = re.findall(r"(?m)^PLASMA_DIAG_END (ERASE|PROGRAM|VERIFY|READBACK)$", log)
    if not begin:
        return {"status": "NOT_CAPTURED", "source": "SAME_OPENOCD_SESSION",
                "stage": None, "memory_registers": {}, "core_registers": {},
                "missing_memory": list(FAILURE_MEMORY_REGISTERS),
                "missing_core": list(FAILURE_CORE_REGISTERS), "read_errors": {}}
    stage = begin[0] if len(begin) == 1 else None
    errors: dict[str, str] = {}
    def extract(group: str, names: tuple[str, ...]) -> dict[str, str]:
        values = {}
        for name in names:
            found = re.findall(
                rf"(?m)^PLASMA_DIAG_{group}_PASS {re.escape(name)} (0x[0-9A-Fa-f]{{8}})$", log)
            rejected = re.findall(
                rf"(?m)^PLASMA_DIAG_{group}_FAIL {re.escape(name)}(?: (.*))?$", log)
            if len(found) == 1 and not rejected:
                values[name] = found[0]
            else:
                if rejected:
                    errors[name] = (rejected[0] or "READ_FAILED")[:200]
                elif len(found) > 1:
                    errors[name] = "DUPLICATE_REGISTER_VALUE"
        return values
    memory = extract("MEM", FAILURE_MEMORY_REGISTERS)
    core = extract("REG", FAILURE_CORE_REGISTERS)
    missing_memory = [k for k in FAILURE_MEMORY_REGISTERS if k not in memory]
    missing_core = [k for k in FAILURE_CORE_REGISTERS if k not in core]
    complete = stage is not None and end == begin and not missing_memory and not missing_core
    state_before = re.findall(r"(?m)^PLASMA_DIAG_STATE_BEFORE (\w+)$", log)
    state_after = re.findall(r"(?m)^PLASMA_DIAG_STATE_AFTER (\w+)$", log)
    skip = re.findall(r"(?m)^PLASMA_DIAG_CORE_SKIP ([^\r\n]+)$", log)
    cause = re.findall(r"(?m)^PLASMA_DIAG_CAUSE (.*)$", log)
    return {
        "status": "COMPLETE" if complete else "PARTIAL",
        "source": "SAME_OPENOCD_SESSION", "stage": stage,
        "cause": cause[0][:500] if len(cause) == 1 else None,
        "memory_registers": memory, "core_registers": core,
        "missing_memory": missing_memory, "missing_core": missing_core,
        "read_errors": errors,
        "core_state_before": state_before[0] if len(state_before) == 1 else None,
        "core_state_after": state_after[0] if len(state_after) == 1 else None,
        "core_skip": skip[0] if len(skip) == 1 else None,
        "halt_attempted": "PLASMA_DIAG_HALT_REQUESTED" in log,
        "reset_or_resume_in_diagnostic": False,
        "end_marker_present": len(begin) == 1 and end == begin,
    }


def make_tcl(socket: Path, firmware: Path | None, readback: Path, operation: str,
             *, image_bytes: int = 0, erase_bytes: int = 0) -> str:
    """Compile a bounded OpenOCD command for a verified target profile."""
    if operation == "program" and (
        firmware is None or image_bytes < 1 or
        image_bytes > PROFILE["main_flash_bytes"] or
        erase_bytes < image_bytes or erase_bytes > PROFILE["max_erase_bytes"] or
        erase_bytes % PROFILE["erase_granularity_bytes"]
    ):
        raise ValueError("INVALID_IMAGE_PLAN")
    config = f"""gdb_port disabled
tcl_port disabled
telnet_port disabled
adapter driver remote_bitbang
remote_bitbang host {socket}
remote_bitbang port 0
transport select swd
adapter speed 100
source [find {PROFILE["target_cfg"]}]
""" + FAILURE_DIAGNOSTIC_TCL + """
init
"""
    # Read-only register qualification (no Flash operations and no reset).
    # OpenOCD read_memory/get_reg return actual Tcl values; exit/echo alone
    # must never be confused with successful register acquisition.
    register_tcl = r"""
proc plasma_register_probe {} {
    set failures 0
    foreach spec {{DBGMCU_IDCODE 0xE0042000} {SCB_CPUID 0xE000ED00} {FLASH_SR 0x4002200C}} {
        set name [lindex $spec 0]
        set address [lindex $spec 1]
        if {[catch {set values [read_memory $address 32 1]} reason]} {
            echo "PLASMA_REGISTER_FAIL $name $reason"
            incr failures
            continue
        }
        if {[llength $values] != 1 || ![string is integer -strict [lindex $values 0]]} {
            echo "PLASMA_REGISTER_FAIL $name INVALID_READ_VALUE"
            incr failures
            continue
        }
        set value [lindex $values 0]
        if {($name eq "DBGMCU_IDCODE" && ($value & 0xFFF) != 0x410)
            || ($name eq "SCB_CPUID" && ($value & 0xFFF0) != 0xC230)} {
            echo "PLASMA_REGISTER_FAIL $name TARGET_IDENTITY_MISMATCH"
            incr failures
            continue
        }
        echo "PLASMA_REGISTER_PASS $name [format 0x%08X $value]"
    }
    if {$failures != 0} {
        echo "PLASMA_REGISTER_SUMMARY FAIL"
        error "REGISTER_READ_FAILED"
    }
    echo "PLASMA_REGISTER_SUMMARY PASS"
}
proc plasma_core_probe {} {
    # OpenOCD init can leave its cached target state 'unknown'. Poll the
    # actual target before deciding whether a Halt/Resume would be safe.
    # A failed poll never grants permission to halt an unknown-state core.
    if {[catch {poll} reason]} {
        echo "PLASMA_CORE_INITIAL_POLL_FAIL $reason"
        echo "PLASMA_CORE_SUMMARY FAIL"
        error "CORE_INITIAL_POLL_FAILED"
    }
    set before [stm32f1x.cpu curstate]
    echo "PLASMA_CORE_STATE_BEFORE $before"
    if {$before ne "running" && $before ne "halted"} {
        echo "PLASMA_CORE_SUMMARY FAIL"
        error "CORE_INITIAL_STATE_NOT_ADMITTED"
    }
    set failures 0
    if {$before eq "running"} {
        if {[catch {halt} reason]} {
            echo "PLASMA_CORE_HALT_FAIL $reason"
            incr failures
        }
    }
    if {[stm32f1x.cpu curstate] ne "halted"} {
        echo "PLASMA_CORE_HALT_FAIL TARGET_NOT_HALTED"
        incr failures
    } else {
        # OpenOCD renamed the Cortex-M register from xPSR to xpsr.
        # Keep the user-facing receipt label xPSR; use the actual
        # case-sensitive OpenOCD register key for get_reg/dict lookup.
        foreach spec {{pc pc} {sp sp} {lr lr} {xpsr xPSR}} {
            set name [lindex $spec 0]
            set label [lindex $spec 1]
            if {[catch {set values [get_reg -force [list $name]]} reason]} {
                echo "PLASMA_CORE_REGISTER_FAIL $label $reason"
                incr failures
                continue
            }
            if {![dict exists $values $name] || ![string is integer -strict [dict get $values $name]]} {
                echo "PLASMA_CORE_REGISTER_FAIL $label INVALID_READ_VALUE"
                incr failures
                continue
            }
            echo "PLASMA_CORE_REGISTER_PASS $label [format 0x%08X [dict get $values $name]]"
        }
    }
    # Always attempt to restore a formerly running core, even when a read
    # failed. An initially halted core must remain halted.
    if {$before eq "running" && [stm32f1x.cpu curstate] eq "halted"} {
        if {[catch {resume} reason]} {
            echo "PLASMA_CORE_RESUME_FAIL $reason"
            incr failures
        } else {
            echo "PLASMA_CORE_RESUME_OK"
        }
    }
    if {[catch {poll} reason]} {
        echo "PLASMA_CORE_STATE_POLL_FAIL $reason"
        incr failures
    }
    set after [stm32f1x.cpu curstate]
    echo "PLASMA_CORE_STATE_AFTER $after"
    if {$after ne $before} {
        echo "PLASMA_CORE_STATE_RESTORE_FAIL"
        incr failures
    }
    if {$failures != 0} {
        echo "PLASMA_CORE_SUMMARY FAIL"
        error "CORE_REGISTER_READ_OR_STATE_RESTORE_FAILED"
    }
    echo "PLASMA_CORE_SUMMARY PASS"
}
"""
    if operation in ("register-read", "core-register-read", "diagnose-after"):
        commands = []
        if operation != "core-register-read":
            commands.append('if {[catch {plasma_register_probe} reason]} { echo "PLASMA_REGISTER_OPERATION_FAIL $reason"; shutdown error }')
        if operation != "register-read":
            commands.append('if {[catch {plasma_core_probe} reason]} { echo "PLASMA_CORE_OPERATION_FAIL $reason"; shutdown error }')
        if operation == "diagnose-after":
            commands.append('echo "PLASMA_DIAG_END POST_SESSION"')
        commands.append("shutdown")
        return config + register_tcl + "\n".join(commands) + "\n"
    if operation == "reset-run":
        # No flash probe, erase, program, verify, dump, or preparatory halt.
        return config + ('echo "PLASMA_RESET_RUN_BEGIN"\n'
                         'if {[catch {reset run} failure]} {\n'
                         '    echo "PLASMA_RESET_RUN_FAIL $failure"\n'
                         '    shutdown error\n'
                         '}\n'
                         'echo "PLASMA_RESET_RUN_OK"\n'
                         'shutdown\n')
    if operation != "program":
        raise ValueError("UNKNOWN_OPERATION")
    return config + f"""halt
flash probe 0
echo "PLASMA_ERASE_BEGIN"
if {{[catch {{flash erase_address 0x{PROFILE["main_flash_base"]:08X} 0x{erase_bytes:X}}} failure]}} {{
    plasma_diag ERASE "$failure"
    shutdown error
}}
echo "PLASMA_ERASE_OK"
echo "PLASMA_PROGRAM_BEGIN"
if {{[catch {{flash write_image {firmware} 0x{PROFILE["main_flash_base"]:08X} bin}} failure]}} {{
    plasma_diag PROGRAM "$failure"
    shutdown error
}}
echo "PLASMA_PROGRAM_OK"
if {{[catch {{verify_image {firmware} 0x{PROFILE["main_flash_base"]:08X} bin}} failure]}} {{
    plasma_diag VERIFY "$failure"
    shutdown error
}}
echo "PLASMA_VERIFY_OK"
if {{[catch {{dump_image {readback} 0x{PROFILE["main_flash_base"]:08X} {image_bytes}}} failure]}} {{
    plasma_diag READBACK "$failure"
    shutdown error
}}
echo "PLASMA_READBACK_OK"
echo "PLASMA_PROGRAM_COMPLETED_NO_RESET"
shutdown
"""


REGISTER_NAMES = ("DBGMCU_IDCODE", "SCB_CPUID", "FLASH_SR")
CORE_NAMES = ("pc", "sp", "lr", "xPSR")


def _observations(log: str, prefix: str, names: tuple[str, ...]) -> tuple[bool, dict]:
    """Require exactly one real 32-bit value for every expected register."""
    observed = {}
    for name in names:
        values = re.findall(
            rf"(?m)^{re.escape(prefix)} {re.escape(name)} (0x[0-9A-Fa-f]{{8}})$", log)
        if len(values) != 1:
            return False, observed
        observed[name] = values[0]
    if observed.get("DBGMCU_IDCODE") and (int(observed["DBGMCU_IDCODE"], 16) & 0xFFF) != 0x410:
        return False, observed
    if observed.get("SCB_CPUID") and (int(observed["SCB_CPUID"], 16) & 0xFFF0) != 0xC230:
        return False, observed
    return True, observed


def read_register_evidence(log: str) -> tuple[bool, dict]:
    valid, observed = _observations(log, "PLASMA_REGISTER_PASS", REGISTER_NAMES)
    return (valid and "PLASMA_REGISTER_SUMMARY PASS" in log
            and "PLASMA_REGISTER_FAIL" not in log), observed


def read_core_evidence(log: str) -> tuple[bool, dict, str | None, str | None]:
    valid, observed = _observations(log, "PLASMA_CORE_REGISTER_PASS", CORE_NAMES)
    before = re.findall(r"(?m)^PLASMA_CORE_STATE_BEFORE (\w+)$", log)
    after = re.findall(r"(?m)^PLASMA_CORE_STATE_AFTER (\w+)$", log)
    state_ok = (len(before) == len(after) == 1
                and before[0] in ("running", "halted")
                and after[0] == before[0]
                and (before[0] != "running" or
                     "PLASMA_CORE_RESUME_OK" in log))
    return (valid and state_ok and "PLASMA_CORE_SUMMARY PASS" in log
            and "PLASMA_CORE_REGISTER_FAIL" not in log
            and "PLASMA_CORE_STATE_RESTORE_FAIL" not in log), observed, (
                before[0] if len(before) == 1 else None), (
                after[0] if len(after) == 1 else None)


def z2_preflight(args):
    if os.geteuid() != 0:
        raise NotRun(77, "ROOT_REQUIRED_ON_Z2")
    check_source(args.source_sha256)
    if Path(__file__).resolve() != Z2_ENTRY.resolve():
        raise NotRun(77, "Z2_REVIEWED_INSTALL_PATH_REQUIRED")
    if args.operation != "preflight" and not args.owner_attested:
        raise NotRun(77, "OWNER_ATTESTATION_REQUIRED_FOR_HARDWARE")
    if args.icpn != PROFILE["icpn"] or args.site_id != PROFILE["site_id"]:
        raise NotRun(77, "UNQUALIFIED_TARGET_OR_SITE")
    firmware, image_bytes, image_sha, erase_bytes = admit_image(
        args.operation, args.firmware, args.image_sha256)
    native = file_at(str(BUNDLE / "libplasma_wordport_armv7.so"))
    if sha(native) != NATIVE_SHA:
        raise NotRun(77, "PINNED_NATIVE_LIBRARY_MISMATCH")
    barrier = file_at(str(BUNDLE / "software/python/native/libplasma_mmio_barrier.so"))
    if sha(file_at(str(BUNDLE / "scripts/bluepill-wordport-session.py"))) != SESSION_SHA:
        raise NotRun(77, "PINNED_BRIDGE_SESSION_SHA_MISMATCH")
    if sha(file_at(str(BUNDLE / "software/python/plasma_interfaces/native_bluepill_word_port.py"))) != PY_MODULE_SHA:
        raise NotRun(77, "PINNED_NATIVE_MODULE_SHA_MISMATCH")
    file_at(OPENOCD)
    if not os.access(OPENOCD, os.X_OK):
        raise NotRun(77, "OPENOCD_NOT_EXECUTABLE")
    if not Path(OPENOCD_SCRIPTS).is_dir():
        raise NotRun(69, "OPENOCD_SCRIPTS_MISSING")
    root_sha = (ROOT / ".plasma-path2-source-commit").read_text().strip()
    if not re.fullmatch(r"[a-f0-9]{40}", root_sha):
        raise NotRun(77, "ROOT_SOURCE_PIN_INVALID")
    subprocess.run(["sha256sum", "--check", "--status", ".plasma-path2-source-sha256"],
                   cwd=ROOT, check=True, timeout=15)
    state = json.loads((ROOT / ".plasma-fpga-image-deployment-state.json").read_text())
    manifest_file = Path("/lib/firmware/plasma-image-manifest.json")
    manifest = json.loads(manifest_file.read_text())
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if (state.get("status") != "IMAGE" or state.get("boot_id") != boot or
            state.get("manifest_sha256") != sha(manifest_file) or
            state.get("firmware_sha256") != manifest["firmware_sha256"] or
            state.get("image") != manifest["firmware_name"] or
            not isinstance(state.get("test_count"), int) or state["test_count"] < 1 or
            Path("/sys/class/fpga_manager/fpga0/state").read_text().strip() != "operating"):
        raise NotRun(69, "HELD_IMAGE_CHECKPOINT_MISMATCH")
    for name, expected in ((manifest["firmware_name"], manifest["firmware_sha256"]),
                           (manifest["recovery_name"], manifest["recovery_sha256"])):
        if sha(file_at("/lib/firmware/" + name)) != expected:
            raise NotRun(77, "FPGA_OR_GOLDEN_SHA_MISMATCH")
    for dev in ("/dev/mem", "/dev/uio1"):
        response = subprocess.run(["fuser", "-s", dev], capture_output=True, timeout=5)
        if response.returncode != 1:
            raise NotRun(69, "MMIO_BUSY_OR_UNKNOWN")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            argv = (proc / "cmdline").read_bytes().split(b"\x00")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if argv and (Path(argv[0].decode(errors="replace")).name == "openocd" or
                     any(b"bluepill-wordport-session.py" in x for x in argv)):
            raise NotRun(69, "EXISTING_SWD_OWNER")
    return firmware, native, barrier, boot, root_sha, image_bytes, image_sha, erase_bytes


def on_z2(args, *, socket_base: Path = Path("/run")):
    firmware, native, barrier, boot, root_sha, image_bytes, image_sha, erase_bytes = z2_preflight(args)
    if args.operation == "preflight":
        print(json.dumps({
            "operation": "preflight", "result": "PASS",
            "checks": {
                "reviewed_script_sha256": "PASS",
                "image_sha256_and_geometry": "PASS" if firmware else "NOT_REQUESTED",
                "native_c_armv7_sha256": "PASS",
                "bridge_session_and_native_python_sha256": "PASS",
                "openocd_executable_and_scripts": "PASS",
                "protected_root_source_pin_and_sha256_manifest": "PASS",
                "fpga_manager": "operating",
                "held_tested_image_manifest_and_golden_sha256": "PASS",
                "mmio_devices_idle": "PASS",
                "openocd_and_swd_owner_idle": "PASS",
            },
            "icpn": args.icpn, "site_id": args.site_id,
            "image_bytes": image_bytes, "image_sha256": image_sha,
            "erase_bytes": erase_bytes, "boot_id": boot,
            "root_source_commit": root_sha,
            # This development-mode prototype has no voltage, continuity or
            # socket-presence sensors. Do not add per-program manual checklist
            # gates or imply that unmeasured values passed physical validation.
            "electrical": "NOT_MEASURED_DEV_MODE_NON_BLOCKING",
            "hw_action": "NONE",
            "no_erase_program_halt_reset": True,
        }, sort_keys=True), flush=True)
        return 0
    base = BUNDLE / ".work/native-wordport-path2"
    if base.is_symlink():
        raise NotRun(77, "EVIDENCE_SYMLINK_DENIED")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence = base / f"run-{time.time_ns()}-{os.getpid()}"
    evidence.mkdir(mode=0o700)
    readback = evidence / "readback-image.bin"
    # Freeze the selected Image in a private, per-run immutable snapshot.
    # Never let OpenOCD read a mutable operator-supplied path after admission.
    staged = None
    if args.operation == "program":
        staged = evidence / "program-image.bin"
        staged.write_bytes(firmware.read_bytes())
        staged.chmod(0o400)
        if staged.stat().st_size != image_bytes or sha(staged) != image_sha:
            raise NotRun(77, "STAGED_IMAGE_CHANGED")
    socketdir = socket_base / f"plasma-wordport-{os.getpid()}"
    socketdir.mkdir(mode=0o700)
    socket = socketdir / "swd.sock"
    tcl = evidence / "openocd.tcl"
    tcl.write_text(make_tcl(socket, staged, readback, args.operation,
                            image_bytes=image_bytes, erase_bytes=erase_bytes))
    bridge_cmd = [
        PYTHON, "-I", "-B", str(BUNDLE / "scripts/bluepill-wordport-session.py"),
        "--root-source-sha", root_sha, "--boot-id", boot,
        "--barrier", str(barrier), "--barrier-sha256", sha(barrier),
        "--native", str(native), "--native-sha256", NATIVE_SHA,
        "--socket", str(socket), "--owner-attested",
    ]
    bridge = None
    completed = None
    bridge_stdout = bridge_stderr = ""
    error = None
    timeout_log = ""
    try:
        bridge = subprocess.Popen(bridge_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, start_new_session=True)
        deadline = time.monotonic() + 8
        while not socket.is_socket():
            if bridge.poll() is not None:
                raise RuntimeError("BRIDGE_EXITED_BEFORE_SOCKET")
            if time.monotonic() > deadline:
                raise RuntimeError("BRIDGE_SOCKET_TIMEOUT")
            time.sleep(0.05)
        completed = subprocess.run([OPENOCD, "-s", OPENOCD_SCRIPTS, "-f", str(tcl)],
                                   capture_output=True, text=True, timeout=570)
    except subprocess.TimeoutExpired as exc:
        fragments = (exc.stdout, exc.stderr)
        timeout_log = "".join(v.decode("utf-8", "replace") if isinstance(v, bytes) else (v or "") for v in fragments)
        error = f"OPENOCD_570S_TIMEOUT: {exc}"[:500]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        if bridge is not None:
            bridge_joined = False
            # OpenOCD can exit before the local WordPort socket service has
            # finished its EOF/QUIT cleanup. Give a successful OpenOCD session
            # a bounded chance to close the Bridge naturally; an immediate
            # SIGTERM causes -15 and masks a verified readback as FAIL.
            if completed is not None and completed.returncode == 0 and error is None:
                try:
                    bridge_stdout, bridge_stderr = bridge.communicate(timeout=8)
                    bridge_joined = True
                except subprocess.TimeoutExpired:
                    error = "BRIDGE_GRACEFUL_CLOSE_TIMEOUT"
            if not bridge_joined:
                if bridge.poll() is None:
                    bridge.terminate()
                try:
                    bridge_stdout, bridge_stderr = bridge.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    bridge.kill()
                    bridge_stdout, bridge_stderr = bridge.communicate(timeout=5)
        if socketdir.exists() and not socket.exists():
            socketdir.rmdir()
    log = (completed.stdout + completed.stderr) if completed is not None else timeout_log
    (evidence / "openocd.log").write_text(log)
    (evidence / "bridge.log").write_text(bridge_stdout + bridge_stderr)
    eligible = (completed is not None and completed.returncode == 0 and
                bridge is not None and bridge.returncode == 0 and not socket.exists())
    if args.operation == "program":
        success = (eligible and "PLASMA_PROGRAM_COMPLETED_NO_RESET" in log and
                   readback.is_file() and readback.stat().st_size == image_bytes and
                   sha(readback) == image_sha)
        failure_diagnostics = read_failure_diagnostics(log)
        diagnostic = ("POST_ERROR_SAME_SESSION" if failure_diagnostics["status"] != "NOT_CAPTURED"
                      else "NOT_CAPTURED")
    elif args.operation in ("register-read", "core-register-read", "diagnose-after"):
        peripheral_ok, peripheral_values = read_register_evidence(log)
        core_ok, core_values, core_before, core_after = read_core_evidence(log)
        required_peripheral = args.operation != "core-register-read"
        required_core = args.operation != "register-read"
        success = (eligible and
                   (not required_peripheral or peripheral_ok) and
                   (not required_core or core_ok) and
                   (args.operation != "diagnose-after" or
                    "PLASMA_DIAG_END POST_SESSION" in log))
        diagnostic = "REGISTER_ACCESS_OBSERVED" if success else "REGISTER_ACCESS_FAILED"
    else:  # Explicit one-shot reset-run, never implicit on program.
        success = (eligible and "PLASMA_RESET_RUN_OK" in log and
                   "PLASMA_RESET_RUN_FAIL" not in log)
        diagnostic = "NOT_APPLICABLE_RESET_RUN"
    receipt = {
        "operation": args.operation, "result": "PASS" if success else "FAIL",
        "diagnostic": diagnostic, "openocd_exit": completed.returncode if completed else None,
        "bridge_exit": bridge.returncode if bridge else None,
        "error": error, "icpn": args.icpn, "site_id": args.site_id,
        "electrical": "NOT_MEASURED_DEV_MODE_NON_BLOCKING",
        "image_bytes": image_bytes, "image_sha256": image_sha,
        "target_cfg": PROFILE["target_cfg"],
        "erase_bytes": erase_bytes,
        "readback_sha256": sha(readback) if readback.is_file() else None,
        "openocd_log_sha256": sha(evidence / "openocd.log"),
        "evidence_directory": str(evidence), "socket_released": not socket.exists(),
        "no_reset_no_retry": args.operation != "reset-run",
        "no_auto_retry": True,
        "no_flash_write": args.operation != "program",
    }
    if args.operation == "program":
        receipt["failure_diagnostics"] = failure_diagnostics
    if args.operation in ("register-read", "core-register-read", "diagnose-after"):
        receipt["peripheral_registers"] = peripheral_values if required_peripheral else None
        receipt["core_registers"] = core_values if required_core else None
        receipt["core_state_before"] = core_before if required_core else None
        receipt["core_state_after"] = core_after if required_core else None
    (evidence / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if success else 1


def z2_login_credentials(home: Path) -> tuple[dict[str, str], Path]:
    """Require the enrolled worker's password plus the independently pinned key.

    Do not reuse an operator's home, create a new private key or trust a freshly
    discovered host key. Credential bytes stay in this process only.
    """
    login = home / ".config/plasma/z2-login-smoke.json"
    hosts = home / ".config/plasma/z2-login-known_hosts"
    for path, mode in ((login.parent, 0o700), (login, 0o600), (hosts, 0o600)):
        try:
            info = path.lstat()
        except OSError:
            raise NotRun(69, "ENROLLED_Z2_PASSWORD_OR_HOST_KEY_UNAVAILABLE") from None
        expected_type = stat.S_ISDIR if path == login.parent else stat.S_ISREG
        if (not expected_type(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != mode):
            raise NotRun(77, "ENROLLED_Z2_CREDENTIAL_OWNER_OR_MODE_INVALID")
    try:
        credentials = json.loads(login.read_text())
    except (ValueError, OSError):
        raise NotRun(77, "ENROLLED_Z2_CREDENTIAL_JSON_INVALID") from None
    if (type(credentials) is not dict
            or not {"ssh_host", "ssh_username", "ssh_password"} <= set(credentials)
            or not set(credentials) <= {"ssh_host", "ssh_username", "ssh_password",
                                        "sudo_password"}
            or credentials.get("ssh_username") != "xilinx"
            or any(type(credentials.get(x)) is not str or not credentials[x]
                   for x in ("ssh_host", "ssh_username", "ssh_password"))
            or (type(credentials.get("sudo_password", credentials["ssh_password"]))
                is not str or not credentials.get("sudo_password", credentials["ssh_password"]))):
        raise NotRun(77, "ENROLLED_Z2_CREDENTIAL_SCHEMA_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,250}", credentials["ssh_host"]):
        raise NotRun(77, "ENROLLED_Z2_HOST_INVALID")
    try:
        pinned = subprocess.run(
            ["ssh-keygen", "-F", credentials["ssh_host"], "-f", str(hosts)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.SubprocessError):
        raise NotRun(69, "Z2_TRUSTED_HOST_KEY_LOOKUP_UNAVAILABLE") from None
    if pinned.returncode != 0:
        raise NotRun(77, "Z2_HOST_KEY_NOT_PINNED")
    return credentials, hosts


def password_ssh_z2(command: list[str], credentials: dict[str, str],
                    hosts: Path, *, timeout: int = 750) -> tuple[int, str]:
    """Run one pinned SSH + sudo command over a private local controlling PTY.

    SSH and sudo passwords are written only to the PTY. Neither password is
    passed in argv, the environment, a log or a child process's command line.
    No host-key fallback, sshpass, agent/key dependency, or shell interpolation
    of credentials. Preserve the actual remote exit code and bounded output.
    """
    import fcntl
    import pty
    import select
    import signal
    import termios
    import tty

    sudo_password = credentials.get("sudo_password", credentials["ssh_password"])
    remote = "sudo -S -p 'PLASMA_SUDO_PROMPT:' " + " ".join(
        shlex.quote(arg) for arg in command)
    argv = [
        "ssh", "-F", "/dev/null", "-T",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + str(hosts),
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "BatchMode=no",
        "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no",
        "-o", "ConnectTimeout=8",
        "-o", "ConnectionAttempts=1",
        "--", credentials["ssh_username"] + "@" + credentials["ssh_host"], remote,
    ]
    master, slave = pty.openpty()
    child = None
    output = bytearray()
    ssh_sent = sudo_sent = False
    expired = False

    def controlling_tty():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    try:
        tty.setraw(slave, termios.TCSANOW)  # no ECHO of typed passwords
        child = subprocess.Popen(
            argv, stdin=slave, stdout=slave, stderr=slave,
            close_fds=True, preexec_fn=controlling_tty)
        os.close(slave)
        slave = -1
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() >= deadline:
                expired = True
                break
            ready, _, _ = select.select([master], [], [], 0.2)
            if not ready:
                if child.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break  # EIO when child closes PTY
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > 131072:
                del output[:-131072]
            tail = output[-512:].decode("utf-8", "replace")
            if not sudo_sent and tail.endswith("PLASMA_SUDO_PROMPT:"):
                os.write(master, sudo_password.encode() + b"\n")
                sudo_sent = True
            elif (not ssh_sent and
                  re.search(r"(?i)(?:password|passphrase)[^\r\n]{0,90}:\s*$", tail)
                  and "PLASMA_SUDO_PROMPT:" not in tail):
                os.write(master, credentials["ssh_password"].encode() + b"\n")
                ssh_sent = True
        if expired:
            return 124, "Z2_SSH_OPERATION_TIMEOUT"
        exit_code = child.wait(timeout=5)
        # Scrub only, never echo the raw PTY transcript.
        clean = output.decode("utf-8", "replace")
        for secret in (credentials["ssh_password"], sudo_password):
            clean = clean.replace(secret, "[REDACTED]")
        return exit_code, clean
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        os.close(master)
        if slave != -1:
            os.close(slave)


def on_swpc(args):
    check_source(args.source_sha256)
    if args.operation != "preflight" and not args.owner_attested:
        raise NotRun(77, "OWNER_ATTESTATION_REQUIRED_FOR_HARDWARE")
    credentials, hosts = z2_login_credentials(Path.home())
    command = [PYTHON, "-I", "-B", str(Z2_ENTRY), "--role", "z2",
               "--operation", args.operation, "--icpn", args.icpn,
               "--site-id", str(args.site_id),
               "--source-sha256", args.source_sha256]
    if args.firmware:
        command += ["--firmware", args.firmware,
                    "--image-sha256", args.image_sha256]
    if args.owner_attested:
        command.append("--owner-attested")
    exit_code, clean = password_ssh_z2(command, credentials, hosts)
    if clean:
        # Keep the receipt at the END for SWPC's parse_receipt().
        print(clean[-16000:], end="" if clean.endswith("\n") else "\n")
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("swpc", "z2"), required=True)
    parser.add_argument("--operation", choices=("preflight", "program", "register-read", "core-register-read", "diagnose-after", "reset-run"), required=True)
    parser.add_argument("--icpn", required=True, help="Exact ICPN to bind the target profile")
    parser.add_argument("--site-id", type=int, required=True, help="One-based physical Site")
    parser.add_argument("--firmware", help="Operator-selected absolute BIN path on Z2")
    parser.add_argument("--image-sha256", help="Independent SHA256 from approved Programming Asset")
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--owner-attested", action="store_true",
                        help="Explicit owner-approved hardware command (not repeated sensor/fixture validation)")
    args = parser.parse_args()
    try:
        return on_swpc(args) if args.role == "swpc" else on_z2(args)
    except NotRun as exc:
        print(json.dumps({"result": "NOT_RUN", "reason": str(exc)}), file=sys.stderr)
        return exc.status
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"result": "FAIL", "reason": type(exc).__name__,
                          "detail": str(exc)[:300]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
