#!/usr/bin/env python3
"""SWPC development-only, bounded STM32F103C8T6 Site 1 A/B Flash burn-in.

This is an operator-owned orchestration script, not a new programmer:
OpenOCD/WordPort execute ONLY on Z2 via the existing SHA-guarded engine.
One --cycle means two separate programming attempts, in the selected --order.
On first non-PASS, capture bounded read-only register evidence and STOP.
Ctrl+Q (interactive TTY), SIGINT/SIGTERM or --stop-file requests a safe stop
at the next complete attempt boundary. The foreground terminal is restored.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import termios
import threading
import time
import tty

ENGINE = Path(__file__).with_name("plasma_wordport_program.py")
ICPN = "STM32F103C8T6"
SITE = 1
IMAGES = {
    "v0.1": {
        "path": "/home/xilinx/plasma-bluepill-ab-20261028/plasma-blue-pill-cdc-v0.1.bin",
        "sha256": "8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d",
        "size": 18768,
        "heartbeat_ms": 500,
        "version": "0.1",
    },
    "v0.2": {
        "path": "/home/xilinx/plasma-bluepill-ab-20261028/plasma-blue-pill-cdc-v0.2.bin",
        "sha256": "e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c",
        "size": 62800,
        "heartbeat_ms": 1000,
        "version": "0.2",
    },
}
HB_RE = re.compile(rb"^HB version=(0\.[12]) seq=(\d+) uptime_ms=(\d+)$")


def plan(cycles: int, order: str = "v01-first") -> list[str]:
    if not 1 <= cycles <= 1000:
        raise ValueError("cycles must be 1..1000")
    if order not in ("v01-first", "v02-first"):
        raise ValueError("order must be v01-first or v02-first")
    pair = ["v0.1", "v0.2"] if order == "v01-first" else ["v0.2", "v0.1"]
    return pair * cycles


def cdc_timeout_for(frames: int, period_ms: int, requested: float | None) -> float:
    """Bound a full contiguous heartbeat window; avoid unachievable CLI settings.

    Automatic budgets cover all frames, initial enumeration and timing slack.
    Explicit budgets are accepted only if they can fit the expected frames.
    """
    minimum = 5.0 + (frames - 1) * period_ms / 1000.0
    if requested is not None:
        if requested < minimum:
            raise ValueError(f"CDC timeout {requested:g}s is too short for "
                             f"{frames} frames at {period_ms}ms")
        return requested
    return max(25.0, 15.0 + 1.2 * frames * period_ms / 1000.0)


def parse_receipt(output: str) -> dict:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and "result" in value:
            return value
    return {"result": "FAIL", "reason": "MISSING_JSON_RECEIPT"}


def valid_performance(receipt: dict, operation: str, image: dict | None,
                      *, readback_enabled: bool = False) -> bool:
    evidence = receipt.get("performance")
    versions = receipt.get("versions")
    if (not isinstance(evidence, dict) or evidence.get("schema") != "plasma.swd.performance.v1"
            or not isinstance(versions, dict)
            or not all(isinstance(versions.get(key), str) and
                       re.fullmatch(r"[0-9a-f]{64}", versions[key])
                       for key in ("engine_sha256", "bridge_session_sha256",
                                   "native_python_module_sha256", "stage_module_sha256",
                                   "rbb_module_sha256", "native_c_sha256",
                                   "openocd_sha256", "target_cfg_sha256"))):
        return False
    required = (("erase", "program", "verify") +
                (("readback",) if readback_enabled else ()) if operation == "program"
                else ("reset",))
    stages = evidence.get("stages")
    preflight = evidence.get("preflight")
    reconciliation = evidence.get("counter_reconciliation")
    if (not isinstance(stages, dict) or not isinstance(preflight, dict)
            or preflight.get("result") != "PASS" or not isinstance(reconciliation, dict)
            or reconciliation.get("result") != "PASS"):
        return False
    if any(not isinstance(stages.get(name), dict) or stages[name].get("result") != "PASS"
           for name in required):
        return False
    if operation == "program" and not readback_enabled and (
            not isinstance(stages.get("readback"), dict) or
            stages["readback"] != {"result": "SKIPPED", "bytes": 0}):
        return False
    if operation == "program" and image is not None:
        if (stages["erase"].get("bytes") != receipt.get("erase_bytes") or
                any(stages[name].get("bytes") != image["size"]
                    for name in (("program", "verify", "readback") if readback_enabled
                                 else ("program", "verify")))):
            return False
    try:
        summed = preflight["duration_s"] + evidence["other_duration_s"] + sum(
            stages[name]["duration_s"] for name in required)
        if (evidence["other_duration_s"] < 0 or
                abs(summed - evidence["total_duration_s"]) > 0.001):
            return False
        for key in ("mmio_reads", "mmio_writes", "dmb_count_derived",
                    "wire_bytes", "socket_recv_calls", "socket_sendall_calls"):
            total = reconciliation["total"][key]
            if any(type(value) is not int or value < 0 for value in
                   (total, reconciliation["stages_sum"][key], reconciliation["other"][key])):
                return False
            if total != reconciliation["stages_sum"][key] + reconciliation["other"][key]:
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def valid_receipt(operation: str, receipt: dict, image: dict | None = None,
                  *, expected_source_sha: str | None = None,
                  readback_enabled: bool = False) -> bool:
    if receipt.get("result") != "PASS" or receipt.get("operation") != operation:
        return False
    if operation == "preflight":
        return (receipt.get("hw_action") == "NONE"
                and (image is None or
                     (receipt.get("image_sha256") == image["sha256"]
                      and receipt.get("image_bytes") == image["size"])))
    if (receipt.get("openocd_exit") != 0 or receipt.get("bridge_exit") != 0
            or receipt.get("socket_released") is not True
            or receipt.get("no_auto_retry") is not True):
        return False
    if (operation in ("program", "reset-run") and
            (not valid_performance(receipt, operation, image,
                                   readback_enabled=readback_enabled) or
             (expected_source_sha is not None and
              receipt["versions"]["engine_sha256"] != expected_source_sha))):
        return False
    if operation == "program":
        return (image is not None and receipt.get("image_sha256") == image["sha256"]
                and receipt.get("readback_enabled") is readback_enabled
                and (receipt.get("readback_sha256") == image["sha256"] if readback_enabled
                     else receipt.get("readback_sha256") is None)
                and receipt.get("image_bytes") == image["size"]
                and receipt.get("no_reset_no_retry") is True)
    if operation in ("reset-run", "register-read"):
        return receipt.get("no_flash_write") is True
    return False


def verify_cdc(port: str, version: str, period_ms: int, frames: int, timeout_s: float) -> dict:
    """Validate fresh live USB CDC frames without pyserial or subprocess shell."""
    deadline = time.monotonic() + timeout_s
    path = Path(port)
    fd = None
    samples: list[dict] = []
    wrong_versions: list[str] = []
    read_buffer = b""
    try:
        while time.monotonic() < deadline:
            if fd is None:
                if not path.exists():
                    time.sleep(0.2)
                    continue
                if not path.is_char_device():
                    return {"result": "FAIL", "reason": "NOT_A_CHARACTER_DEVICE"}
                # Existing picocom/minicom owns the TTY: never kill or steal it.
                try:
                    owner = subprocess.run(["fuser", "-s", port],
                                           capture_output=True, timeout=3)
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    return {"result": "FAIL", "reason": "SERIAL_OWNER_UNKNOWN"}
                if owner.returncode != 1:
                    return {"result": "FAIL", "reason": "SERIAL_BUSY_OR_UNKNOWN"}
                try:
                    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                    fcntl.ioctl(fd, termios.TIOCEXCL)
                    tty.setraw(fd)
                    attrs = termios.tcgetattr(fd)
                    attrs[4] = termios.B115200
                    attrs[5] = termios.B115200
                    termios.tcsetattr(fd, termios.TCSANOW, attrs)
                except OSError as exc:
                    if fd is not None:
                        os.close(fd)
                        fd = None
                    if exc.errno == errno.ENOENT:
                        time.sleep(0.2)
                        continue
                    return {"result": "FAIL", "reason": "SERIAL_OPEN_ERROR",
                            "detail": str(exc)[:200]}
            try:
                ready, _, _ = select.select([fd], [], [],
                                            min(0.5, max(0.0, deadline - time.monotonic())))
                if not ready:
                    continue
                chunk = os.read(fd, 4096)
                if not chunk:
                    return {"result": "FAIL", "reason": "SERIAL_DISCONNECTED"}
            except OSError as exc:
                return {"result": "FAIL", "reason": "SERIAL_IO_ERROR",
                        "detail": str(exc)[:200]}
            read_buffer = (read_buffer + chunk)[-16384:]
            while b"\n" in read_buffer:
                line, read_buffer = read_buffer.split(b"\n", 1)
                match = HB_RE.fullmatch(line.strip())
                if not match:
                    continue
                seen_version = match.group(1).decode()
                if seen_version != version:
                    wrong_versions.append(seen_version)
                    samples.clear()
                    continue
                seq, uptime_ms = int(match.group(2)), int(match.group(3))
                sample = {"seq": seq, "uptime_ms": uptime_ms}
                if samples:
                    prev = samples[-1]
                    step = uptime_ms - prev["uptime_ms"]
                    if seq != prev["seq"] + 1 or abs(step - period_ms) > 100:
                        samples.clear()
                samples.append(sample)
                if len(samples) >= frames:
                    return {"result": "PASS", "version": version, "port": port,
                            "heartbeat_ms": period_ms, "frames": samples[:],
                            "wrong_version_samples": len(wrong_versions)}
        return {"result": "FAIL", "reason": "CDC_TIMEOUT_OR_WRONG_VERSION",
                "expected_version": version, "seen_versions": wrong_versions[-10:],
                "last_consecutive_samples": samples}
    finally:
        if fd is not None:
            os.close(fd)


class ForegroundStopHotkey:
    """Receive Ctrl+Q in THIS terminal without sending it to OpenOCD.

    Unix TTY normally reserves Ctrl+Q (0x11) for XON flow control, so disable
    IXON/IXOFF while active, use noncanonical no-echo input, and restore the
    exact original terminal attributes on exit. SIGINT still works via ISIG.
    Noninteractive Runner executions retain signal/stop-file support.
    """

    def __init__(self, burn_in):
        self.burn_in = burn_in
        self.fd = None
        self.saved = None
        self.thread = None
        self.done = threading.Event()

    def __enter__(self):
        if not sys.stdin.isatty():
            return self
        try:
            self.fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(self.fd)
            mode = termios.tcgetattr(self.fd)
            mode[0] &= ~(termios.IXON | termios.IXOFF)
            mode[3] &= ~(termios.ICANON | termios.ECHO)
            mode[6][termios.VMIN] = 0
            mode[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, mode)
        except (OSError, ValueError, termios.error):
            if self.fd is not None and self.saved is not None:
                termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)
            self.fd = None
            self.saved = None
            return self
        self.thread = threading.Thread(target=self._listen, daemon=True,
                                       name="plasma-burn-in-ctrl-q")
        self.thread.start()
        return self

    def _listen(self):
        while not self.done.is_set():
            try:
                ready, _, _ = select.select([self.fd], [], [], 0.2)
                if not ready:
                    continue
                data = os.read(self.fd, 32)
            except (OSError, ValueError):
                break
            if b"\x11" in data:
                self.burn_in.stop_requested = True
                print("\nCtrl+Q: safe stop requested; finish current attempt first.",
                      flush=True)
                break

    def __exit__(self, *_):
        self.done.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        if self.fd is not None and self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)


class BurnIn:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.sequence = plan(args.cycles, getattr(args, "order", "v01-first"))
        self.stop_requested = False
        self.engine_sha = hashlib.sha256(ENGINE.read_bytes()).hexdigest()
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.root = Path(args.output).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory = self.root / (now + "-" + str(os.getpid()))
        self.directory.mkdir(mode=0o700)
        self.record = self.directory / "events.jsonl"
        self.log = self.directory / "progress.log"
        self.status_file = self.directory / "status.json"
        self.current = 0
        self.passed = 0
        self.failed = 0
        self.started = time.monotonic()
        self.status = "INIT"
        self._lock = open(self.root / ".site1-burnin.lock", "a+", encoding="utf-8")
        try:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("ANOTHER_SWPC_BURN_IN_OWNER_IS_ACTIVE") from exc

    def report(self, stage: str, message: str, extra: dict | None = None):
        stamp = datetime.now(timezone.utc).isoformat()
        line = (f"[{stamp}] {self.current}/{len(self.sequence)}"
                f" PASS={self.passed} FAIL={self.failed} [{stage}] {message}")
        print(line, flush=True)
        with self.log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        event = {"time": stamp, "stage": stage, "current": self.current,
                 "total": len(self.sequence), "passed": self.passed,
                 "failed": self.failed, "message": message}
        if extra:
            event.update(extra)
        with self.record.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        state = {**event, "elapsed_s": round(time.monotonic() - self.started, 1),
                 "stop_file": str(Path(self.args.stop_file).expanduser()),
                 "evidence_directory": str(self.directory),
                 "engine_sha256": self.engine_sha}
        temporary = self.status_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(self.status_file)

    def request_stop(self, signum, _frame):
        self.stop_requested = True
        print(f"\nSignal {signum}: graceful stop requested; current attempt will finish.", flush=True)

    def should_stop(self) -> bool:
        return self.stop_requested or Path(self.args.stop_file).expanduser().exists()

    def run_engine(self, operation: str, image: dict | None = None) -> dict:
        command = [sys.executable, str(ENGINE),
                   "--role", "swpc", "--operation", operation,
                   "--icpn", ICPN, "--site-id", str(SITE),
                   "--source-sha256", self.engine_sha]
        if image is not None:
            command += ["--firmware", image["path"], "--image-sha256", image["sha256"]]
        if operation == "program" and getattr(self.args, "readback", False):
            command.append("--readback")
        if operation != "preflight":
            command.append("--owner-attested")
        started = time.monotonic()
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       stdin=subprocess.DEVNULL, timeout=850,
                                       start_new_session=True)
            output = completed.stdout + "\n" + completed.stderr
            receipt = parse_receipt(output)
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            output = (str(exc.stdout or "") + "\n" + str(exc.stderr or ""))
            receipt = {"result": "FAIL", "reason": "SWPC_OPERATION_TIMEOUT"}
            exit_code = 124
        name = f"{self.current:04d}-{operation}"
        if image is not None:
            name += "-" + image["version"].replace(".", "")
        (self.directory / (name + ".log")).write_text(output, encoding="utf-8")
        return {"receipt": receipt, "exit_code": exit_code,
                "elapsed_s": round(time.monotonic() - started, 3),
                "log": str(self.directory / (name + ".log")),
                "pass": exit_code == 0 and valid_receipt(
                    operation, receipt, image, expected_source_sha=self.engine_sha,
                    readback_enabled=operation == "program" and getattr(self.args, "readback", False))}

    def capture_failure(self, version: str, stage: str, failed: dict):
        self.report("FAIL", f"{version} {stage}; stopping future programs",
                    {"receipt": failed})
        receipt = failed.get("receipt", {})
        # Use the original Z2 same-session fault snapshot; do not overwrite
        # a partially captured lockup with a misleading post-failure attach.
        same_session = receipt.get("failure_diagnostics", {})
        if (stage == "PROGRAM_FAIL" and isinstance(same_session, dict) and
                same_session.get("status") in ("COMPLETE", "PARTIAL")):
            self.report("DIAG_SAME_SESSION",
                        "Fault/Core/Flash registers preserved in original program receipt",
                        {"diagnostic_receipt": same_session})
            return
        # The programming engine already runs same-session best-effort
        # register diagnostics on Flash failure; its Z2 openocd.log is
        # preserved in the receipt evidence_directory.
        # CDC_FAIL follows a verified program + reset with the SWD socket
        # already released; no engine receipt exists for the USB-only error.
        safe_released = (stage == "CDC_FAIL" or
                         receipt.get("socket_released") is True)
        if receipt.get("result") == "NOT_RUN" or not safe_released:
            self.report("DIAG_NOT_RUN", "owner/socket state not safely released")
            return
        self.report("DIAG", "attempting one READ-ONLY peripheral register acquisition")
        diag = self.run_engine("register-read")
        self.report("DIAG_PASS" if diag["pass"] else "DIAG_FAIL",
                    "DBGMCU_IDCODE/SCB_CPUID/FLASH_SR after failure",
                    {"diagnostic_receipt": diag})
        # Do NOT re-halt or resume a potentially half-erased MCU.
        # This is NOT a silent retry of Erase/Program.

    def run(self) -> int:
        with ForegroundStopHotkey(self):
            return self._run_sequence()

    def _run_sequence(self) -> int:
        stop_path = Path(self.args.stop_file).expanduser()
        if stop_path.exists():
            self.report("BLOCKED", "stop file already exists; remove deliberately before starting")
            return 2
        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)
        self.report("READY", f"cycles={self.args.cycles}, flash_attempts={len(self.sequence)} "
                    f"order={getattr(self.args, 'order', 'v01-first')} port={self.args.port} frames={self.args.frames} "
                     f"cdc_timeout={self.args.cdc_timeout if self.args.cdc_timeout is not None else 'auto'}; "
                     f"stop: Ctrl+Q / Ctrl+C / touch {stop_path}")
        for version in dict.fromkeys(self.sequence):
            self.report("PREFLIGHT", version)
            result = self.run_engine("preflight", IMAGES[version])
            if not result["pass"]:
                self.failed += 1
                self.report("PREFLIGHT_FAIL", version, {"receipt": result})
                return 1
        for index, version in enumerate(self.sequence, 1):
            if self.should_stop():
                self.report("STOPPED", "stop requested before next Flash operation")
                return 130
            self.current = index
            image = IMAGES[version]
            self.report("PROGRAM", f"{version}: erase/program/verify" +
                        ("/readback" if getattr(self.args, "readback", False) else "") + " begin")
            program = self.run_engine("program", image)
            if not program["pass"]:
                self.failed += 1
                self.capture_failure(version, "PROGRAM_FAIL", program)
                return 1
            self.report("PROGRAM_PASS", f"{version} " +
                        ("readback SHA256 matched" if getattr(self.args, "readback", False)
                         else "OpenOCD Verify passed (independent readback skipped)"),
                        {"program_receipt": program})
            # Even after a stop request, finish this successful attempt by
            # resetting and checking CDC; never leave an intentional halted core.
            self.report("RESET", f"{version}: explicit reset-run")
            reset = self.run_engine("reset-run")
            if not reset["pass"]:
                self.failed += 1
                self.capture_failure(version, "RESET_FAIL", reset)
                return 1
            self.report("RESET_PASS", f"{version}: reset-run completed",
                        {"reset_receipt": reset})
            timeout = cdc_timeout_for(self.args.frames, image["heartbeat_ms"],
                                      self.args.cdc_timeout)
            self.report("CDC", f"{version}: read {self.args.port} for "
                       f"{self.args.frames} frames; timeout={timeout:.1f}s")
            observed = verify_cdc(self.args.port, image["version"],
                                  image["heartbeat_ms"], self.args.frames, timeout)
            if observed["result"] != "PASS":
                self.failed += 1
                self.capture_failure(version, "CDC_FAIL", {"receipt": observed})
                return 1
            self.passed += 1
            self.report("ATTEMPT_PASS", f"{version}: full Program/Reset/CDC PASS",
                        {"cdc_receipt": observed, "program_elapsed_s": program["elapsed_s"]})
        self.report("COMPLETE", f"all {len(self.sequence)} attempts PASS")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, required=True,
                        help="one cycle = both firmware versions; each cycle has two Flash attempts")
    parser.add_argument("--order", choices=("v01-first", "v02-first"),
                        default="v01-first",
                        help="program order per cycle (default: v01-first)")
    parser.add_argument("--port", default="/dev/ttyACM0",
                        help="SWPC Blue Pill USB CDC device; usually /dev/ttyACM0")
    parser.add_argument("--frames", type=int, default=60,
                        help="consecutive valid USB CDC heartbeats per image (3..1000; default 60)")
    parser.add_argument("--readback", action="store_true",
                        help="Opt in to independent Flash readback and SHA256 (default: skip)")
    parser.add_argument("--cdc-timeout", type=float, default=None,
                        help="per-image CDC timeout in seconds (5..1800; default auto by frame count/version)")
    parser.add_argument("--stop-file", default="/tmp/plasma-ab-stop")
    parser.add_argument("--output", default="~/plasma-ab-runs")
    args = parser.parse_args(argv)
    if (not 1 <= args.cycles <= 1000 or not 3 <= args.frames <= 1000
            or (args.cdc_timeout is not None and not 5 <= args.cdc_timeout <= 1800)):
        parser.error("cycles 1..1000, frames 3..1000, cdc-timeout 5..1800 required")
    # Reject too-short budgets before preflight or any hardware operation.
    if args.cdc_timeout is not None:
        try:
            cdc_timeout_for(args.frames, IMAGES["v0.2"]["heartbeat_ms"],
                            args.cdc_timeout)
        except ValueError as exc:
            parser.error(str(exc))
    if args.port != "/dev/ttyACM0" and not args.port.startswith("/dev/serial/by-id/"):
        parser.error("use /dev/ttyACM0 or an explicit /dev/serial/by-id device")
    if not ENGINE.is_file():
        parser.error(f"reviewed engine missing: {ENGINE}")
    os.umask(0o077)
    try:
        return BurnIn(args).run()
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"result": "FAIL", "reason": str(exc)[:300]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
