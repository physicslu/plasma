#!/usr/bin/env python3
"""One-shot, owner-approved Blue Pill v0.2 SWD via existing Native C bridge.

Path 2 uses --role swpc (pinned SSH); standalone Z2 uses --role z2.
Neither route installs software, loads an FPGA Image, retries, or resets DUT.
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
Z2_ENTRY = BUNDLE / "scripts/plasma_native_wordport_v02.py"
ROOT = Path("/root/plasma-path2-approved")
PYTHON = "/opt/plasma/python/3.12.13/bin/python3"
OPENOCD = "/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/bin/openocd"
OPENOCD_SCRIPTS = "/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/share/openocd/scripts"
NATIVE_SHA = "66261cef851c9777469b393b7539c5b0f8c2b039a032f1a5b4cbf9e93460e447"
V02_SHA = "e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c"
V02_BYTES = 62800
ERASE_BYTES = 0xF800  # 62 x 1-KiB pages, not a 64-KiB mass erase
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


def make_tcl(socket: Path, firmware: Path, readback: Path, operation: str) -> str:
    """On program failure capture status in SAME OpenOCD process before halt."""
    config = f"""gdb_port disabled
tcl_port disabled
telnet_port disabled
adapter driver remote_bitbang
remote_bitbang host {socket}
remote_bitbang port 0
transport select swd
adapter speed 100
source [find target/stm32f1x.cfg]
proc plasma_diag {{stage cause}} {{
    echo "PLASMA_DIAG_BEGIN $stage"
    echo "PLASMA_DIAG_CAUSE $cause"
    foreach command {{
        {{mdw 0xE000EDF0 1}}
        {{mdw 0x2000003C 2}}
        {{mdw 0x20000040 8}}
        {{mdw 0x4002200C 1}}
        {{mdw 0x40022010 1}}
        {{mdw 0xE000ED28 1}}
        {{mdw 0xE000ED2C 1}}
    }} {{
        echo "PLASMA_DIAG_PREHALT $command"
        if {{[catch {{eval $command}} failure]}} {{echo "PLASMA_DIAG_READ_FAIL $failure"}}
    }}
    echo "PLASMA_DIAG_NOW_HALT"
    if {{[catch {{halt}} failure]}} {{echo "PLASMA_DIAG_HALT_FAIL $failure"}}
    foreach command {{{{reg pc}} {{reg lr}} {{reg sp}} {{reg xPSR}} {{reg primask}} {{debug_reason}}}} {{
        echo "PLASMA_DIAG_POSTHALT $command"
        if {{[catch {{eval $command}} failure]}} {{echo "PLASMA_DIAG_REG_FAIL $failure"}}
    }}
    echo "PLASMA_DIAG_END $stage"
}}
init
"""
    if operation == "diagnose-after":
        return config + 'plasma_diag POST_SESSION "REATTACH_NOT_FAILURE_INSTANT"\nshutdown\n'
    if operation != "program-v02":
        raise ValueError("UNKNOWN_OPERATION")
    return config + f"""halt
flash probe 0
echo "PLASMA_ERASE_BEGIN"
if {{[catch {{flash erase_address 0x08000000 0x{ERASE_BYTES:X}}} failure]}} {{
    plasma_diag ERASE "$failure"
    shutdown error
}}
echo "PLASMA_ERASE_OK"
echo "PLASMA_PROGRAM_BEGIN"
if {{[catch {{flash write_image {firmware} 0x08000000 bin}} failure]}} {{
    plasma_diag PROGRAM "$failure"
    shutdown error
}}
echo "PLASMA_PROGRAM_OK"
if {{[catch {{verify_image {firmware} 0x08000000 bin}} failure]}} {{
    plasma_diag VERIFY "$failure"
    shutdown error
}}
echo "PLASMA_VERIFY_OK"
if {{[catch {{dump_image {readback} 0x08000000 {V02_BYTES}}} failure]}} {{
    plasma_diag READBACK "$failure"
    shutdown error
}}
echo "PLASMA_READBACK_OK"
echo "PLASMA_V02_COMPLETED_NO_RESET"
shutdown
"""


def z2_preflight(args):
    if os.geteuid() != 0:
        raise NotRun(77, "ROOT_REQUIRED_ON_Z2")
    check_source(args.source_sha256)
    if not args.owner_attested or Path(__file__).resolve() != Z2_ENTRY.resolve():
        raise NotRun(77, "OWNER_OR_Z2_INSTALL_PATH_DENIED")
    firmware = file_at(args.firmware)
    if firmware.stat().st_size != V02_BYTES or sha(firmware) != V02_SHA:
        raise NotRun(77, "PINNED_V02_FIRMWARE_MISMATCH")
    native = file_at(str(BUNDLE / "libplasma_wordport_armv7.so"))
    if sha(native) != NATIVE_SHA:
        raise NotRun(77, "PINNED_NATIVE_LIBRARY_MISMATCH")
    barrier = file_at(str(BUNDLE / "software/python/native/libplasma_mmio_barrier.so"))
    file_at(str(BUNDLE / "scripts/bluepill-wordport-session.py"))
    file_at(OPENOCD)
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
    return firmware, native, barrier, boot, root_sha


def on_z2(args):
    firmware, native, barrier, boot, root_sha = z2_preflight(args)
    base = BUNDLE / ".work/native-v02-path2"
    if base.is_symlink():
        raise NotRun(77, "EVIDENCE_SYMLINK_DENIED")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence = base / f"run-{time.time_ns()}-{os.getpid()}"
    evidence.mkdir(mode=0o700)
    socketdir = Path(f"/run/plasma-native-v02-{os.getpid()}")
    socketdir.mkdir(mode=0o700)
    socket = socketdir / "swd.sock"
    readback = evidence / "readback-v02.bin"
    tcl = evidence / "openocd.tcl"
    tcl.write_text(make_tcl(socket, firmware, readback, args.operation))
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
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        if bridge is not None:
            if bridge.poll() is None:
                bridge.terminate()
            try:
                bridge_stdout, bridge_stderr = bridge.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                bridge.kill()
                bridge_stdout, bridge_stderr = bridge.communicate(timeout=5)
        if socketdir.exists() and not socket.exists():
            socketdir.rmdir()
    log = (completed.stdout + completed.stderr) if completed is not None else ""
    (evidence / "openocd.log").write_text(log)
    (evidence / "bridge.log").write_text(bridge_stdout + bridge_stderr)
    eligible = (completed is not None and completed.returncode == 0 and
                bridge is not None and bridge.returncode == 0 and not socket.exists())
    if args.operation == "program-v02":
        success = (eligible and "PLASMA_V02_COMPLETED_NO_RESET" in log and
                   readback.is_file() and readback.stat().st_size == V02_BYTES and
                   sha(readback) == V02_SHA)
        diagnostic = "POST_ERROR_SAME_SESSION" if "PLASMA_DIAG_BEGIN" in log else "NOT_CAPTURED"
    else:
        success = eligible and "PLASMA_DIAG_END POST_SESSION" in log
        diagnostic = "POST_SESSION_REATTACH_NOT_FAILURE_INSTANT"
    receipt = {
        "operation": args.operation, "result": "PASS" if success else "FAIL",
        "diagnostic": diagnostic, "openocd_exit": completed.returncode if completed else None,
        "bridge_exit": bridge.returncode if bridge else None,
        "error": error, "firmware_sha256": V02_SHA,
        "readback_sha256": sha(readback) if readback.is_file() else None,
        "openocd_log_sha256": sha(evidence / "openocd.log"),
        "evidence_directory": str(evidence), "socket_released": not socket.exists(),
        "no_reset_no_retry": True,
    }
    (evidence / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if success else 1


def on_swpc(args):
    check_source(args.source_sha256)
    if not args.owner_attested:
        raise NotRun(77, "OWNER_ATTESTATION_REQUIRED")
    home = Path.home()
    login = home / ".config/plasma/z2-login-smoke.json"
    key = home / ".ssh/plasma_z2_ed25519"
    hosts = home / ".ssh/known_hosts"
    if (not login.is_file() or stat.S_IMODE(login.stat().st_mode) != 0o600
            or not key.is_file() or not hosts.is_file()):
        raise NotRun(69, "ENROLLED_SSH_CREDENTIALS_UNAVAILABLE")
    credentials = json.loads(login.read_text())
    if (set(credentials) != {"ssh_host", "ssh_username", "ssh_password", "sudo_password"}
            or credentials["ssh_username"] != "xilinx"):
        raise NotRun(77, "SSH_CREDENTIAL_SCHEMA_DENIED")
    pinned = subprocess.run(["ssh-keygen", "-F", credentials["ssh_host"], "-f", str(hosts)],
                            capture_output=True, timeout=5)
    if pinned.returncode:
        raise NotRun(77, "Z2_HOST_KEY_NOT_PINNED")
    command = [PYTHON, "-I", "-B", str(Z2_ENTRY), "--role", "z2",
               "--operation", args.operation, "--firmware", args.firmware,
               "--source-sha256", args.source_sha256, "--owner-attested"]
    ssh = ["ssh", "-F", "/dev/null", "-i", str(key), "-o", "BatchMode=yes",
           "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", "UserKnownHostsFile=" + str(hosts),
           "-o", "ConnectTimeout=8", "-o", "ConnectionAttempts=1",
           "--", credentials["ssh_username"] + "@" + credentials["ssh_host"],
           "sudo -S -p '' " + " ".join(shlex.quote(x) for x in command)]
    completed = subprocess.run(ssh, input=credentials["sudo_password"] + "\n",
                               capture_output=True, text=True, timeout=750)
    for data, stream in ((completed.stdout, sys.stdout), (completed.stderr, sys.stderr)):
        clean = data.replace(credentials["sudo_password"], "[REDACTED]")
        clean = clean.replace(credentials["ssh_password"], "[REDACTED]")
        if clean:
            print(clean[-16000:], end="", file=stream)
    return completed.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("swpc", "z2"), required=True)
    parser.add_argument("--operation", choices=("program-v02", "diagnose-after"), required=True)
    parser.add_argument("--firmware", required=True, help="Absolute firmware path on Z2")
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--owner-attested", required=True, action="store_true")
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
