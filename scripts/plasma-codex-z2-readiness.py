#!/usr/bin/env python3
"""Issue #981: bounded, password-authenticated SSH-only Z2 PS/PL readiness.

Neither local nor remote code opens /dev/mem, /dev/uio, UART, JTAG or USB.
Only a fixed allowlisted remote Python sysfs/status observer is executed.
No passwords, addresses, known-host keys, raw remote output or kernel paths
are included in Actions logs or uploaded artifacts.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import pty
import re
import select
import shlex
import signal
import socket
import subprocess
import sys
import termios
import time
import tty
import fcntl

SOURCE = Path(__file__).resolve().with_name("plasma-codex-z2-login.py")
SPEC = importlib.util.spec_from_file_location("plasma_z2_login", SOURCE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("REVIEWED_SSH_HELPER_MISSING")
LOGIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOGIN)

COMMAND = "/plasma-codex z2-readiness 981"
MARKER = "PLASMA_Z2_READINESS_V1="
MAX_BYTES = 16384
TIMEOUT = 65

# This is the complete fixed remote command. No arbitrary Issue body,
# host-supplied code, sudo, /dev reads or write operations are permitted.
REMOTE_PY = r"""
import json, os, platform, subprocess
from pathlib import Path

def read(path, limit=256):
    try:
        return Path(path).read_bytes()[:limit]
    except (OSError, ValueError):
        return b""

def manager_state():
    states = []
    try:
        managers = sorted(Path("/sys/class/fpga_manager").glob("fpga*"))[:4]
    except OSError:
        managers = []
    for manager in managers:
        state = read(manager / "state").decode("ascii", "ignore").strip()
        states.append(state if state in ("operating", "unknown", "power off",
                                          "reset", "firmware request", "write",
                                          "write complete", "write init",
                                          "write init err", "write err")
                      else "unrecognized")
    return "OPERATING" if "operating" in states else (
        "NO_MANAGER" if not states else "NOT_OPERATING")

def uio_snapshot():
    names = []
    try:
        nodes = sorted(Path("/sys/class/uio").glob("uio*"))[:32]
    except OSError:
        nodes = []
    for item in nodes:
        name = read(item / "name").decode("utf-8", "replace").strip()
        if name == "fabric":
            names.append("FABRIC")
        elif name == "audio-codec-ctrl":
            names.append("AUDIO_CODEC_CTRL")
        else:
            names.append("OTHER")
    return {
        "count": len(nodes),
        "fabric_detected": "FABRIC" in names,
        "audio_codec_detected": "AUDIO_CODEC_CTRL" in names,
    }

def fclk0():
    # debugfs may be intentionally unavailable to the unprivileged xilinx
    # account. Never escalate or write to clocks to discover a frequency.
    b = read("/sys/kernel/debug/clk/fclk0/clk_rate", 32).strip()
    if b.isdigit():
        n = int(b)
        return {"visibility": "OBSERVED", "hz": n if 0 < n < 1000000000 else None}
    return {"visibility": "NOT_OBSERVED_UNPRIVILEGED", "hz": None}

def services():
    result = {}
    for unit in ("plasma-bootstrap", "plasma-server", "plasma-web",
                 "plasma-runtime-activation"):
        try:
            p = subprocess.run(
                ["systemctl", "is-active", "--quiet", unit],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=2, check=False)
            result[unit] = "ACTIVE" if p.returncode == 0 else "NOT_ACTIVE_OR_UNAVAILABLE"
        except (OSError, subprocess.TimeoutExpired):
            result[unit] = "NOT_OBSERVED"
    return result

compatible = read("/proc/device-tree/compatible", 4096).split(b"\0")
data = {
    "schema": "plasma.z2.readiness.remote.v1",
    "remote_user_is_xilinx": os.geteuid() != 0 and (
        __import__("getpass").getuser() == "xilinx"),
    "os_linux": platform.system() == "Linux",
    "machine_armv7": platform.machine().startswith("armv7"),
    "device_tree_zynq7000": b"xlnx,zynq-7000" in compatible,
    "device_tree_board_model_available": bool(read("/proc/device-tree/model").strip()),
    "fpga_manager_state": manager_state(),
    "uio": uio_snapshot(),
    "fclk0": fclk0(),
    "services": services(),
}
print("PLASMA_Z2_READINESS_V1=" + json.dumps(data, separators=(",", ":"), sort_keys=True),
      flush=True)
"""


def validate_remote(data: object) -> dict:
    if not isinstance(data, dict) or set(data) != {
        "schema", "remote_user_is_xilinx", "os_linux", "machine_armv7",
        "device_tree_zynq7000", "device_tree_board_model_available",
        "fpga_manager_state", "uio", "fclk0", "services",
    } or data["schema"] != "plasma.z2.readiness.remote.v1":
        raise ValueError("UNEXPECTED_PROBE_SCHEMA")
    for key in ("remote_user_is_xilinx", "os_linux", "machine_armv7",
                "device_tree_zynq7000", "device_tree_board_model_available"):
        if type(data[key]) is not bool:
            raise ValueError("INVALID_BOOLEAN")
    if data["fpga_manager_state"] not in ("OPERATING", "NOT_OPERATING", "NO_MANAGER"):
        raise ValueError("INVALID_FPGA_MANAGER")
    uio = data["uio"]
    if not isinstance(uio, dict) or set(uio) != {
        "count", "fabric_detected", "audio_codec_detected"
    } or type(uio["count"]) is not int or not 0 <= uio["count"] <= 32:
        raise ValueError("INVALID_UIO")
    if any(type(uio[x]) is not bool for x in ("fabric_detected", "audio_codec_detected")):
        raise ValueError("INVALID_UIO_FIELD")
    clk = data["fclk0"]
    if not isinstance(clk, dict) or set(clk) != {"visibility", "hz"}:
        raise ValueError("INVALID_FCLK")
    if clk["visibility"] not in ("OBSERVED", "NOT_OBSERVED_UNPRIVILEGED"):
        raise ValueError("INVALID_FCLK_STATUS")
    hz = clk["hz"]
    if hz is not None and (type(hz) is not int or not 0 < hz < 1000000000):
        raise ValueError("INVALID_FCLK_RATE")
    if (clk["visibility"] == "OBSERVED") != (hz is not None):
        raise ValueError("INCONSISTENT_FCLK")
    services = data["services"]
    expected = ("plasma-bootstrap", "plasma-server", "plasma-web",
                "plasma-runtime-activation")
    if not isinstance(services, dict) or set(services) != set(expected):
        raise ValueError("INVALID_SERVICES")
    if any(services[k] not in ("ACTIVE", "NOT_ACTIVE_OR_UNAVAILABLE", "NOT_OBSERVED")
           for k in expected):
        raise ValueError("INVALID_SERVICE_STATUS")
    return data


def bounded_ssh_probe(record: dict[str, str], seconds: int = TIMEOUT) -> dict:
    master, slave = pty.openpty()
    tty.setraw(slave, termios.TCSANOW)
    # As in the previously real-hardware PASS SSH smoke, require a controlling
    # PTY to handle a single password prompt, while SSH itself requests -T.
    command = "python3 -c " + shlex.quote(REMOTE_PY)
    args = [
        "ssh", "-T",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={LOGIN.KNOWN_HOSTS}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "BatchMode=no",
        "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no",
        "-o", "ConnectTimeout=8",
        "-o", "ConnectionAttempts=1",
        "--", f"{LOGIN.LOGIN}@{record['ssh_host']}", command,
    ]

    def attach_tty() -> None:
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    process = subprocess.Popen(
        args, stdin=slave, stdout=slave, stderr=slave,
        close_fds=True, preexec_fn=attach_tty)
    os.close(slave)
    buf = bytearray()
    password_sent = False
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            ready = select.select([master], [], [], 0.2)[0]
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) > MAX_BYTES:
                    raise ValueError("SSH_RESPONSE_TOO_LARGE")
                tail = buf.decode("utf-8", "replace")
                if not password_sent and re.search(
                    r"(?i)(?:password|passphrase)[^\r\n]{0,90}:\s*$", tail
                ):
                    os.write(master, record["ssh_password"].encode() + b"\n")
                    password_sent = True
            if process.poll() is not None:
                # Drain any final buffered SSH output before evaluation.
                while select.select([master], [], [], 0)[0]:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf.extend(chunk)
                    if len(buf) > MAX_BYTES:
                        raise ValueError("SSH_RESPONSE_TOO_LARGE")
                break
        else:
            raise ValueError("SSH_PROBE_TIMEOUT")
        if process.wait(timeout=3) != 0:
            raise ValueError("SSH_PROBE_REMOTE_EXIT")
        text = buf.decode("utf-8", "replace")
        matching = re.findall(r"(?m)^" + re.escape(MARKER) + r"([^\r\n]{1,4096})\r?$", text)
        if len(matching) != 1:
            raise ValueError("SSH_PROBE_MARKER_MISSING")
        return validate_remote(json.loads(matching[0]))
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        os.close(master)


def summarize(observed: dict) -> dict:
    core = (
        observed["remote_user_is_xilinx"] and observed["os_linux"]
        and observed["machine_armv7"] and observed["device_tree_zynq7000"]
        and observed["fpga_manager_state"] == "OPERATING"
    )
    return {
        "schema": "plasma.z2.ssh-readiness.v1",
        "transport": "SSH_ONLY",
        "ssh_authenticated": True,
        "baseline_result": "BASELINE_PASS_PARTIAL" if core else "BASELINE_BLOCKED",
        "os_linux": observed["os_linux"],
        "armv7": observed["machine_armv7"],
        "device_tree_zynq7000": observed["device_tree_zynq7000"],
        "board_identity_exact": "NOT_QUALIFIED",
        "fpga_manager_state": observed["fpga_manager_state"],
        "clock_fclk0": observed["fclk0"],
        "uio": observed["uio"],
        "services": observed["services"],
        "bitstream_identity": "NOT_QUALIFIED",
        "mmio_access": "NOT_RUN",
        "fpga_reload": "NOT_RUN",
        "hardware_go": False,
        "uart": "NON_BLOCKING_NOT_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        good = {
            "schema": "plasma.z2.readiness.remote.v1",
            "remote_user_is_xilinx": True, "os_linux": True,
            "machine_armv7": True, "device_tree_zynq7000": True,
            "device_tree_board_model_available": False,
            "fpga_manager_state": "OPERATING",
            "uio": {"count": 2, "fabric_detected": True, "audio_codec_detected": True},
            "fclk0": {"visibility": "NOT_OBSERVED_UNPRIVILEGED", "hz": None},
            "services": {x: "ACTIVE" for x in
                         ("plasma-bootstrap", "plasma-server", "plasma-web",
                          "plasma-runtime-activation")},
        }
        assert summarize(validate_remote(good))["baseline_result"] == "BASELINE_PASS_PARTIAL"
        assert summarize(good)["hardware_go"] is False
        print("SSH-only PS/PL readiness offline self-test PASS")
        return 0
    if not args.run:
        parser.error("either --run or --self-test is required")
    LOGIN.expect_worker()
    if os.environ.get("GITHUB_ACTIONS") != "true" or (
        os.environ.get("RUNNER_NAME") != "SWPC-plasma-codex"
    ):
        raise ValueError("DEDICATED_RUNNER_REQUIRED")
    out = Path(os.environ["PLASMA_Z2_READINESS_OUT"])
    if not out.is_dir() or out.is_symlink():
        raise ValueError("OUTPUT_NOT_READY")
    outcome = {
        "schema": "plasma.z2.ssh-readiness.v1",
        "transport": "SSH_ONLY",
        "ssh_authenticated": False,
        "baseline_result": "BLOCKED_SSH_OR_PROBE",
        "hardware_go": False,
        "uart": "NON_BLOCKING_NOT_RUN",
        "mmio_access": "NOT_RUN",
        "fpga_reload": "NOT_RUN",
    }
    print("[SSH] Pinned-host identity and worker private credential: verify", flush=True)
    try:
        record = LOGIN.creds()
        print("[SSH] Fixed read-only remote PS/PL sysfs and service snapshot: starting", flush=True)
        data = bounded_ssh_probe(record)
        outcome = summarize(data)
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError):
        print("[SSH] BLOCKED_SSH_OR_PROBE (private details withheld)", flush=True)
    report = out / "report.json"
    report.write_text(json.dumps(outcome, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(report, 0o600)
    print("[READINESS] " + outcome["baseline_result"], flush=True)
    print("[SAFETY] MMIO=NOT_RUN FPGA_RELOAD=NOT_RUN UART=NOT_RUN HARDWARE_GO=false",
          flush=True)
    return 0 if outcome["baseline_result"] == "BASELINE_PASS_PARTIAL" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, RuntimeError, ValueError, subprocess.SubprocessError):
        print("SSH-only readiness BLOCKED (details withheld)", file=sys.stderr)
        raise SystemExit(2)
