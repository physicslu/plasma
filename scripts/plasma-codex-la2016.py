#!/usr/bin/env python3
"""Issue 981: real Codex requests a narrowly scoped KINGST LA2016 loopback.

Agent runs inside a bubblewrap mount namespace with a replacement /dev.
Only this reviewed supervisor can open the LA. Missing prerequisites are NO_GO.
No Z2, FPGA Manager, JTAG, USB Hub, DUT, or arbitrary shell task execution.
"""
from __future__ import annotations

import argparse
import configparser
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import socket
import statistics
import struct
import subprocess
import sys
import time
import zipfile

WORKER = "plasma-codex"
RUNNER = "SWPC-plasma-codex"
APPIMAGE = Path("/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage")
EXPECTED_IMAGE_HASH = "b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475"
LOCK = Path("/run/lock/plasma-la2016.lock")
USB_ROOT = Path("/sys/bus/usb/devices")
PROFILE = ((1000, 50), (2000, 25))
SCHEMA = "plasma.la2016.agent-request.v1"
MAX_SAMPLES = 250000
OUTPUT_NAMES = ("1000hz-on.sr", "1000hz-off.sr", "2000hz-on.sr", "2000hz-off.sr")
RUN_COMMAND = "/plasma-codex la2016 981"

def worker_identity() -> None:
    if (socket.gethostname() != "SWPC" or os.geteuid() == 0 or
            pwd.getpwuid(os.geteuid()).pw_name != WORKER or
            os.getenv("RUNNER_NAME") != RUNNER or
            os.getenv("GITHUB_ACTIONS") != "true" or
            os.getenv("GITHUB_EVENT_NAME") != "issue_comment" or
            os.getenv("GITHUB_REPOSITORY") != "physicslu/plasma" or
            os.getenv("GITHUB_REF") != "refs/heads/main"):
        raise ValueError("WORKER_OR_GITHUB_IDENTITY")

def validate_agent_request(value: object) -> dict:
    """An agent can request only the two owner-approved loopback cases."""
    if (type(value) is not dict or set(value) !=
            {"schema", "operation", "fixture", "cases", "shutdown_check"}):
        raise ValueError("AGENT_REQUEST_SCHEMA")
    if (value["schema"] != SCHEMA or
            value["operation"] != "execute_bounded_la2016_loopback" or
            value["fixture"] != "KINGST_PWM1_TO_SAME_KINGST_CH0" or
            value["shutdown_check"] != "CAPTURE_LOW"):
        raise ValueError("AGENT_CAPABILITY_DENIED")
    if type(value["cases"]) is not list or len(value["cases"]) != 2:
        raise ValueError("AGENT_CASES_NOT_ALLOWLISTED")
    for case, expected in zip(value["cases"], PROFILE):
        if (type(case) is not dict or set(case) != {"frequency_hz", "duty_percent"} or
                type(case["frequency_hz"]) is not int or
                type(case["duty_percent"]) is not int or
                (case["frequency_hz"], case["duty_percent"]) != expected):
            raise ValueError("AGENT_CASE_NOT_ALLOWLISTED")
    return value

def request_prompt() -> str:
    return (
        "PLASMA Issue #981: owner-approved, physically confirmed wiring "
        "is KINGST LA2016 PWM1 -> the SAME instrument CH0. You are the "
        "Codex Agent preparing one bounded hardware capability request. "
        "Inspect only PUBLIC checked-in documentation at "
        "docs/evidence/la2016-pwm-loopback/2026-10-16/README.md and "
        "docs/development/plasma-codex-hardware-parity.md. "
        "You have NO hardware access. Do not execute shell commands, "
        "open USB devices or write files. If the documented previous "
        "real-test profile is appropriate, reply with EXACTLY one JSON "
        "object and no markdown: "
        '{"schema":"plasma.la2016.agent-request.v1",'
        '"operation":"execute_bounded_la2016_loopback",'
        '"fixture":"KINGST_PWM1_TO_SAME_KINGST_CH0",'
        '"cases":[{"frequency_hz":1000,"duty_percent":50},'
        '{"frequency_hz":2000,"duty_percent":25}],'
        '"shutdown_check":"CAPTURE_LOW"}. '
        "Otherwise reply with the JSON object "
        '{"schema":"plasma.la2016.agent-decline.v1"}. '
        "This output is only a REQUEST, not evidence of hardware PASS."
    )

def sandbox_args(output: Path) -> list[str]:
    """Mount-isolate USB/device nodes while preserving Codex network/auth."""
    bwrap = shutil.which("bwrap")
    codex = shutil.which("codex")
    if not bwrap or not codex:
        raise ValueError("ISOLATION_OR_CODEX_MISSING")
    home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    for p in (home / ".codex", home / ".config" / "plasma", home / ".ssh"):
        if p.is_symlink():
            raise ValueError("SYMLINKED_PRIVATE_HOME")
    if not (home / ".codex").is_dir():
        raise ValueError("CODEX_HOME_NOT_READY")
    argv = [
        bwrap, "--die-with-parent", "--new-session", "--unshare-pid",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--bind", str(output / "agent"), str(output / "agent"),
    ]
    # Prevent tool-spawned commands from reading HIL credentials/host keys.
    for private in (home / ".config" / "plasma", home / ".ssh"):
        if private.is_dir():
            argv += ["--tmpfs", str(private)]
    # Codex CLI needs to persist its own session/auth state. A dedicated
    # identity owns that directory; no write to repository or hardware paths.
    argv += ["--bind", str(home / ".codex"), str(home / ".codex"),
             "--chdir", os.environ.get("GITHUB_WORKSPACE", "/"),
             "--", codex, "--ask-for-approval", "never", "exec",
             "--sandbox", "read-only", "--output-last-message",
             str(output / "agent" / "agent-request.json"), "-"]
    return argv

def codex_request(out: Path) -> dict:
    argv = sandbox_args(out)
    proc = subprocess.run(
        argv, input=request_prompt(), text=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=120, check=False,
    )
    if proc.returncode != 0:
        raise ValueError("CODEX_EXEC_NOT_SUCCESS")
    path = out / "agent" / "agent-request.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("NO_AGENT_REQUEST")
    try:
        return validate_agent_request(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError("INVALID_AGENT_JSON") from None

def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()

def trusted_appimage() -> None:
    if APPIMAGE.is_symlink() or not APPIMAGE.is_file() or not os.access(APPIMAGE, os.X_OK):
        raise ValueError("PINNED_KINGST_APPIMAGE_NOT_INSTALLED")
    if sha256(APPIMAGE) != EXPECTED_IMAGE_HASH:
        raise ValueError("KINGST_APPIMAGE_SHA_MISMATCH")

def kingst_connection() -> tuple[str, Path]:
    matches = []
    for node in USB_ROOT.iterdir():
        try:
            if (node.joinpath("idVendor").read_text().strip().lower() != "77a1" or
                    node.joinpath("idProduct").read_text().strip().lower() != "01a2"):
                continue
            bus = int(node.joinpath("busnum").read_text().strip())
            dev = int(node.joinpath("devnum").read_text().strip())
            if not (1 <= bus <= 999 and 1 <= dev <= 999):
                continue
            matches.append((f"{bus}.{dev}", Path(f"/dev/bus/usb/{bus:03}/{dev:03}")))
        except (OSError, ValueError):
            continue
    if len(matches) != 1:
        raise ValueError("KINGST_UNIQUE_USB_MAPPING_NOT_READY")
    conn, device = matches[0]
    if not device.is_char_device() or not os.access(device, os.R_OK | os.W_OK):
        raise ValueError("KINGST_USB_DAC_DENIED")
    if not shutil.which("fuser"):
        raise ValueError("USB_OWNER_CHECK_UNAVAILABLE")
    busy = subprocess.run(["fuser", "-s", str(device)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=3, check=False)
    if busy.returncode != 1:
        raise ValueError("KINGST_BUSY_OR_OWNER_UNCERTAIN")
    return conn, device

def sigrok(conn: str, *args: str, timeout: int = 15) -> None:
    """Driver executable and arguments are composed exclusively here."""
    cmd = [str(APPIMAGE), "--appimage-extract-and-run", "--loglevel", "4",
           "--driver", "kingst-la2016:conn=" + conn, *args]
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=timeout, check=False)
    if proc.returncode != 0:
        raise ValueError("SIGROK_OPERATION_FAILED")

def turn_off(conn: str) -> None:
    sigrok(conn, "--config", "channel_group=PWM1:enabled=off", "--set",
           timeout=12)

def capture(conn: str, path: Path, freq: int | None = None,
            duty: int | None = None) -> None:
    if path.exists():
        raise ValueError("CAPTURE_EXISTS")
    params = ["--config", "samplerate=1m"]
    if freq is not None:
        if (freq, duty) not in PROFILE:
            raise ValueError("PWM_SETTING_DENIED")
        params += ["--config", "channel_group=PWM1:output_frequency="
                   + str(freq) + ":output_duty_cycle=" + str(duty) + ":enabled=on"]
        count = "100000"
    else:
        count = "20000"
    sigrok(conn, *params, "--channels", "CH0", "--samples", count,
           "--output-file", str(path), timeout=18)
    if not path.is_file() or not 0 < path.stat().st_size < 1500000:
        raise ValueError("EMPTY_OR_LARGE_CAPTURE")

def read_ch0(path: Path) -> list[int]:
    """Same .sr format as the archived real 2026-10-16 loopback verifier."""
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("metadata")
        if info.file_size > 8192:
            raise ValueError("SR_METADATA_SIZE")
        meta = configparser.ConfigParser()
        meta.read_string(archive.read("metadata").decode("utf-8"))
        device = meta["device 1"]
        if (device["probe1"] != "CH0" or device["samplerate"] != "1 MHz"
                or device["unitsize"] != "2"):
            raise ValueError("SR_CAPTURE_METADATA")
        chunks = sorted((x for x in archive.namelist() if x.startswith("logic-1-")),
                        key=lambda name: int(name.rsplit("-", 1)[1]))
        if (not chunks or sum(archive.getinfo(x).file_size for x in chunks) >
                MAX_SAMPLES * 2):
            raise ValueError("SR_CAPTURE_BOUNDS")
        raw = b"".join(archive.read(x) for x in chunks)
    if not raw or len(raw) % 2:
        raise ValueError("SR_CAPTURE_EMPTY")
    return [word[0] & 1 for word in struct.iter_unpack("<H", raw)]

def measure(values: list[int], freq: int, duty: int) -> tuple[dict, list[int]]:
    if len(values) < 20000 or len(values) > MAX_SAMPLES:
        raise ValueError("CAPTURE_SAMPLE_COUNT")
    edges = [n for n in range(1, len(values)) if values[n] != values[n-1]]
    rises = [n for n in edges if values[n]]
    falls = [n for n in edges if not values[n]]
    periods, highs = [], []
    for first, last in zip(rises, rises[1:]):
        between = [n for n in falls if first < n < last]
        if len(between) != 1:
            raise ValueError("CAPTURE_EDGE_STRUCTURE")
        periods.append(last-first)
        highs.append(between[0]-first)
    expected_period = 1_000_000 // freq
    expected_high = expected_period * duty // 100
    if (len(periods) < 20 or any(abs(x-expected_period) > 1 for x in periods)
            or any(abs(x-expected_high) > 1 for x in highs)):
        raise ValueError("WAVEFORM_OUTSIDE_1US_TOLERANCE")
    observed_freq = 1_000_000 / statistics.mean(periods)
    observed_duty = 100 * sum(highs) / sum(periods)
    return {
        "requested_frequency_hz": freq,
        "requested_duty_percent": duty,
        "measured_frequency_hz": round(observed_freq, 3),
        "measured_duty_percent": round(observed_duty, 3),
        "samples": len(values),
        "edges": len(edges),
        "complete_cycles": len(periods),
        "result": "PASS",
    }, edges

def off_low(values: list[int]) -> int:
    if len(values) < 20000 or len(values) > MAX_SAMPLES or any(values):
        raise ValueError("PWM_OFF_NOT_CONFIRMED_LOW")
    return len(values)

def waveform_edges(path: Path, values: list[int], edges: list[int]) -> None:
    # Sanitized digital waveform, only CH0 bit and sample indices, no
    # USB identity, path or private sigrok session metadata.
    with path.open("x", encoding="utf-8") as f:
        f.write("sample_index,CH0\n")
        f.write("0," + str(values[0]) + "\n")
        for n in edges:
            f.write(f"{n},{values[n]}\n")

def watchdog(out: Path, conn: str) -> int:
    """Detached hard deadline: attempt PWM OFF if the parent dies/hangs."""
    worker_identity()
    if not re.fullmatch(r"[1-9][0-9]{0,2}\.[1-9][0-9]{0,2}", conn):
        return 2
    time.sleep(125)
    if (out / "pwm-off-confirmed").exists():
        return 0
    try:
        trusted_appimage()
        turn_off(conn)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return 2

def run() -> int:
    worker_identity()
    def terminate(_signum: int, _frame: object) -> None:
        raise RuntimeError("SUPERVISOR_INTERRUPTED")
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    out = Path(os.environ["PLASMA_LA2016_OUT"])
    if out.is_symlink() or not out.is_dir() or out.stat().st_uid != os.geteuid():
        raise ValueError("BAD_PRIVATE_OUTPUT")
    os.umask(0o077)
    report = {
        "schema": "plasma.la2016.acceptance.v1",
        "agent_exec": "NOT_RUN",
        "agent_request": "NOT_RUN",
        "device": "KINGST_LA2016",
        "loopback": "PWM1_TO_CH0",
        "cases": [],
        "pwm_off_command": "NOT_RUN",
        "off_capture": "NOT_RUN",
        "result": "NO_GO",
        "z2_fpga": "NOT_RUN", "usb_hub_power": "NOT_RUN",
        "external_dut": "NOT_RUN",
    }
    rc = 2
    try:
        # Hardware preflight BEFORE agent: no signal emitted on failure.
        trusted_appimage()
        conn, _device = kingst_connection()
        if not shutil.which("bwrap") or not shutil.which("codex"):
            raise ValueError("AGENT_ISOLATION_NOT_READY")
        with LOCK.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Agent has no physical USB node; it must produce a constrained
            # intent which the separate trusted supervisor validates.
            (out / "agent").mkdir(mode=0o700, exist_ok=False)
            request = codex_request(out)
            validate_agent_request(request)
            report["agent_request_sha256"] = sha256(out / "agent" / "agent-request.json")
            report["agent_exec"] = "PASS"
            report["agent_request"] = "PASS"
            # Never allow PWM output without an independent deadline OFF.
            daemon = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--watchdog",
                 "--output", str(out), "--connection", conn],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
                close_fds=True,
            )
            report["watchdog_armed"] = daemon.pid > 0
            try:
                for freq, duty in PROFILE:
                    label = str(freq) + "hz"
                    onpath = out / (label + "-on.sr")
                    offpath = out / (label + "-off.sr")
                    capture(conn, onpath, freq=freq, duty=duty)
                    values = read_ch0(onpath)
                    result, edges = measure(values, freq, duty)
                    result["waveform_sha256"] = sha256(onpath)
                    waveform_edges(out / (label + "-edges.csv"), values, edges)
                    report["cases"].append(result)
                    # Must disable output before testing low.
                    turn_off(conn)
                    report["pwm_off_command"] = "PASS"
                    capture(conn, offpath)
                    report["off_capture"] = "PASS" if off_low(read_ch0(offpath)) else "NO_GO"
                    result["off_samples"] = len(read_ch0(offpath))
                    result["off_waveform_sha256"] = sha256(offpath)
                rc = 0
                report["result"] = "PASS_REAL_AGENT_LA2016_LOOPBACK"
            finally:
                # Always attempt a bounded OFF on exceptions and SIGTERM.
                try:
                    turn_off(conn)
                    report["pwm_off_command"] = "PASS"
                    # Disarm only after command, NEVER after a missing
                    # waveform check or arbitrary agent statement.
                    if rc == 0:
                        (out / "pwm-off-confirmed").touch(exist_ok=False)
                except (OSError, ValueError, subprocess.SubprocessError):
                    report["pwm_off_command"] = "FAILED_OR_UNKNOWN"
                    rc = 2
                    report["result"] = "NO_GO_PWM_SHUTDOWN"
    except (OSError, ValueError, subprocess.TimeoutExpired,
            subprocess.SubprocessError, zipfile.BadZipFile, KeyError,
            configparser.Error, PermissionError, RuntimeError, KeyboardInterrupt):
        report["result"] = "NO_GO"
    if rc != 0:
        report["result"] = report["result"] if report["result"] == "NO_GO_PWM_SHUTDOWN" else "NO_GO"
    (out / "report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("[LA2016] " + report["result"] + "; diagnostic details withheld", flush=True)
    return rc

def main() -> int:
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true")
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--watchdog", action="store_true")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--connection", type=str)
    args = ap.parse_args()
    if args.self_test:
        validate_agent_request({
            "schema": SCHEMA, "operation": "execute_bounded_la2016_loopback",
            "fixture": "KINGST_PWM1_TO_SAME_KINGST_CH0",
            "cases": [{"frequency_hz": a, "duty_percent": b} for a, b in PROFILE],
            "shutdown_check": "CAPTURE_LOW",
        })
        assert measure(([0]*500 + [1]*500) * 50, 1000, 50)[0]["result"] == "PASS"
        print("LA2016 Codex intent/signal offline self-test PASS")
        return 0
    if args.watchdog:
        if args.output is None or args.connection is None:
            return 2
        return watchdog(args.output, args.connection)
    if args.output is not None or args.connection is not None:
        return 2
    try:
        return run()
    except (OSError, ValueError, KeyError, RuntimeError, KeyboardInterrupt):
        print("[LA2016] NO_GO at trusted host boundary", flush=True)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
