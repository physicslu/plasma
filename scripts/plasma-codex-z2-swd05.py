#!/usr/bin/env python3
"""SWPC dedicated runner -> reviewed Z2 SWD-05 one-shot (Issue #981).

Never executes arbitrary Issue text; target and host key from enrolled private
credentials, root-stage route paths from separately enrolled private config.
No live usage before Gate 2. No sudo password in argv, GitHub logs or artifact.
"""
from __future__ import annotations

import argparse
import importlib.util
import getpass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pty
import fcntl
import re
import select
import shlex
import signal
import stat
import subprocess
import sys
import termios
import time
import tty

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("z2_login", BASE / "plasma-codex-z2-login.py")
assert SPEC and SPEC.loader
LOGIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOGIN)
ROUTE = Path("/home/plasma-codex/.config/plasma/z2-swd05-oneshot.json")
FIELDS = ("source_root", "candidate_bit", "candidate_hwh", "manifest",
          "candidate_bin", "recovery_bin", "recovery_hwh", "output", "sudo_password")
MARKER = "PLASMA_SWD05_REPORT="
REVIEWED_SOURCES = (
    "pl/hil/swd04/one_shot.py",
    "pl/hil/swd04/development.py",
    "pl/hil/swd04/native_qualify.py",
    "pl/hil/swd04/contract.py",
    "pl/hil/swd04/collect.py",
    "pl/hil/swd04/staging.py",
    "pl/hil/swd04/mmio_contract.py",
    "pl/hil/swd04/live.py",
    "software/python/plasma_interfaces/__init__.py",
    "software/python/plasma_interfaces/linux_mmio.py",
    "software/python/plasma_interfaces/swd_transaction.py",
)
TIMEOUT_SECONDS = 185
MAX_REPLY = 20000
STAGES = ("preflight", "candidate_load", "hil01", "hil02",
          "restore", "restoration_verified", "overall")


def valid_target_path(value: object) -> bool:
    if type(value) is not str or len(value) > 220 or "\x00" in value or "\n" in value:
        return False
    p = PurePosixPath(value)
    return p.is_absolute() and str(p) == value and ".." not in p.parts and value != "/"


def load_route() -> dict[str, str]:
    try:
        data = json.loads(LOGIN.private_file(ROUTE))
        if type(data) is not dict or set(data) != set(FIELDS):
            raise ValueError("ROUTE_SCHEMA")
        if not all(valid_target_path(data[key]) for key in FIELDS if key != "sudo_password"):
            raise ValueError("ROUTE_PATHS")
        if not isinstance(data["sudo_password"], str) or not data["sudo_password"]:
            raise ValueError("SUDO_SECRET_MISSING")
        root = data["source_root"]
        if not root.startswith("/opt/plasma/"):
            raise ValueError("SOURCE_ROOT_NOT_PROTECTED")
        if not data["candidate_bin"].startswith("/lib/firmware/") or not data["recovery_bin"].startswith("/lib/firmware/"):
            raise ValueError("FIRMWARE_NOT_DIRECT")
        if not data["output"].startswith("/root/"):
            raise ValueError("EVIDENCE_MUST_BE_ROOT_PRIVATE")
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        raise ValueError("PRIVATE_ROUTE_NOT_READY") from None


def enroll() -> None:
    LOGIN.expect_worker()
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("RUNNER_NAME") or not sys.stdin.isatty():
        raise ValueError("LOCAL_OPERATOR_TTY_REQUIRED")
    if ROUTE.exists() or ROUTE.is_symlink():
        raise ValueError("ROUTE_EXISTS_DO_NOT_OVERWRITE")
    print("Enter already reviewed, root-owned Z2 remote paths. No hardware action.")
    data = {key: input(key + ": ").strip() for key in FIELDS if key != "sudo_password"}
    data["sudo_password"] = getpass.getpass("Z2 sudo password: ")
    # Duplicate validation semantics before writing immutable 0600 file.
    if not all(valid_target_path(data[key]) for key in FIELDS if key != "sudo_password") or not data["sudo_password"]:
        raise ValueError("ROUTE_INVALID")
    if not data["source_root"].startswith("/opt/plasma/") or not data["output"].startswith("/root/"):
        raise ValueError("ROUTE_ROOT_INVALID")
    if any(not data[key].startswith("/lib/firmware/") for key in ("candidate_bin", "recovery_bin")):
        raise ValueError("ROUTE_FIRMWARE_INVALID")
    LOGIN.atomic_private_create(ROUTE, json.dumps(data, sort_keys=True).encode())
    print("Private root route enrolled; NO SSH/FPGA/MMIO/DUT operation performed.")


def fixed_remote_cmd(route: dict[str, str]) -> str:
    """Shell quote every operator-enrolled path, never interpolate Issue text."""
    root = route["source_root"]
    repository_root = Path(__file__).resolve().parents[1]
    # Check the exact reviewed code for EVERY imported target dependency,
    # rather than pinning the supervisor module alone. Remote files must
    # be root-owned, not writable by the Linux login account.
    checks = []
    for relpath in REVIEWED_SOURCES:
        expected = hashlib.sha256((repository_root / relpath).read_bytes()).hexdigest()
        remote = root + "/" + relpath
        q = shlex.quote(remote)
        checks.append("test \"$(sha256sum " + q + " | cut -d' ' -f1)\" = "
                      + shlex.quote(expected))
        checks.append("test \"$(stat -c %u " + q + ")\" = 0")
        checks.append("test $((0$(stat -c %a " + q + ") & 0022)) -eq 0")
    quoted_root = shlex.quote(root)
    checks.insert(0, "test \"$(stat -c %u " + quoted_root + ")\" = 0")
    checks.insert(1, "test $((0$(stat -c %a " + quoted_root + ") & 0022)) -eq 0")
    check = " && ".join(checks)
    argv = [
        "sudo", "-S", "-p", "PLASMA_SWD05_SUDO_PROMPT:",
        "env", "PYTHONPATH=" + root + ":" + root + "/software/python",
        "/opt/plasma/python/3.12.13/bin/python3",
        "-m", "pl.hil.swd04.one_shot",
    ]
    for key in FIELDS:
        if key == "sudo_password" or key == "source_root":
            continue
        argv.extend(["--" + key.replace("_", "-"), route[key]])
    argv.extend(["--execute-live", "--ack-unrecoverable-axi-stall-risk"])
    return check + " && " + shlex.join(argv)


def sanitize_report(data: object, exit_code: int) -> dict:
    if type(data) is not dict or set(data) != {
        "schema", "stages", "site", "candidate_source", "candidate_bin_sha256",
        "recovery_bin_sha256", "external_dut", "physical_swd"
    }:
        raise ValueError("RECEIPT_SCHEMA")
    from typing import Any
    s: Any = data["stages"]
    if (data["schema"] != "plasma.z2.swd05.oneshot.v1"
            or data["site"] != 1 or type(s) is not dict or set(s) != set(STAGES)
            or any(v not in ("PASS", "NOT_RUN", "FAIL_OR_BLOCKED",
                             "FAIL_OR_UNKNOWN", "NO_GO",
                             "PASS_DEVELOPMENT_INTERNAL_FIXTURE")
                   for v in s.values())):
        raise ValueError("RECEIPT_STAGES")
    if data["external_dut"] != "NOT_RUN" or data["physical_swd"] != "NOT_RUN":
        raise ValueError("UNAUTHORIZED_HARDWARE_SCOPE")
    from pl.hil.swd04 import contract as pins
    if (data["candidate_source"] != pins.SOURCE_SHA
            or data["candidate_bin_sha256"] != pins.CANDIDATE_BIN_SHA256
            or data["recovery_bin_sha256"] != pins.RECOVERY_BIN_SHA256):
        raise ValueError("WRONG_FIRMWARE_PIN")
    good = s["overall"] == "PASS_DEVELOPMENT_INTERNAL_FIXTURE"
    if good != (exit_code == 0):
        raise ValueError("REMOTE_EXIT_MISMATCH")
    if good and any(s[key] != "PASS" for key in STAGES[:-1]):
        raise ValueError("FALSE_HARDWARE_PASS")
    return {
        "schema": data["schema"], "stages": s, "site": 1,
        "candidate_source": data["candidate_source"],
        "candidate_bin_sha256": data["candidate_bin_sha256"],
        "recovery_bin_sha256": data["recovery_bin_sha256"],
        "external_dut": "NOT_RUN", "physical_swd": "NOT_RUN",
    }


def ssh_execute(record: dict[str, str], route: dict[str, str]) -> dict:
    master, slave = pty.openpty()
    tty.setraw(slave, termios.TCSANOW)
    cmd = fixed_remote_cmd(route)
    argv = [
        "ssh", "-T", "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={LOGIN.KNOWN_HOSTS}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "BatchMode=no", "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no", "-o", "ConnectTimeout=8",
        "-o", "ConnectionAttempts=1",
        "--", f"{LOGIN.LOGIN}@{record['ssh_host']}", cmd,
    ]
    def attached():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave,
                            preexec_fn=attached, close_fds=True)
    os.close(slave)
    buf = bytearray()
    ssh_sent = sudo_sent = False
    try:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            readable = select.select([master], [], [], 0.25)[0]
            if readable:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                if not data:
                    break
                buf.extend(data)
                if len(buf) > MAX_REPLY:
                    raise ValueError("REMOTE_OUTPUT_TOO_LARGE")
                tail = buf.decode("utf-8", "replace")
                if not ssh_sent and re.search(r"(?i)(?:password|passphrase)[^\r\n]{0,90}:\s*$", tail):
                    os.write(master, record["ssh_password"].encode() + b"\n")
                    ssh_sent = True
                elif not sudo_sent and tail.endswith("PLASMA_SWD05_SUDO_PROMPT:"):
                    os.write(master, route["sudo_password"].encode() + b"\n")
                    sudo_sent = True
            if proc.poll() is not None:
                break
        else:
            raise ValueError("REMOTE_SUPERVISOR_TIMEOUT_MANUAL_RECOVERY_CHECK_REQUIRED")
        # A remote failure is never converted to PASS by reading a stale receipt.
        exitcode = proc.wait(timeout=3)
        text = buf.decode("utf-8", "replace")
        found = re.findall(r"(?m)^" + re.escape(MARKER) + r"([^\r\n]{1,10000})\r?$", text)
        if len(found) != 1 or exitcode not in (0, 2):
            raise ValueError("MISSING_OR_UNTRUSTED_REMOTE_RECEIPT")
        return sanitize_report(json.loads(found[0]), exitcode)
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
        os.close(master)


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", action="store_true")
    g.add_argument("--enroll", action="store_true")
    g.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        assert not valid_target_path("relative")
        assert valid_target_path("/opt/plasma/swd05-reviewed")
        assert not valid_target_path("/root/../etc")
        print("SWD05 SSH launcher offline self-test PASS")
        return 0
    if args.enroll:
        enroll()
        return 0
    LOGIN.expect_worker()
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_NAME") != "SWPC-plasma-codex":
        raise ValueError("OWNER_CONTROLLED_RUNNER_REQUIRED")
    out = Path(os.environ["PLASMA_SWD05_OUT"])
    if not out.is_dir() or out.is_symlink():
        raise ValueError("PRIVATE_OUTPUT_MISSING")
    outcome = {"schema": "plasma.z2.swd05.host.v1", "result": "NO_GO",
               "hardware_go": False, "uart": "NOT_RUN", "external_dut": "NOT_RUN"}
    try:
        route = load_route()
        creds = LOGIN.creds()
        print("[SWD05] SSH target and pinned source: verified locally", flush=True)
        result = ssh_execute(creds, route)
        outcome.update(result=result["stages"]["overall"], remote=result)
        outcome["hardware_go"] = False  # Not product/electrical clearance.
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
        print("[SWD05] NO_GO_OR_INCOMPLETE; private details withheld", flush=True)
    (out / "report.json").write_text(json.dumps(outcome, sort_keys=True, indent=2) + "\n")
    os.chmod(out / "report.json", 0o600)
    print("[SWD05] " + outcome["result"], flush=True)
    return 0 if outcome["result"] == "PASS_DEVELOPMENT_INTERNAL_FIXTURE" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("SWD05 SSH one-shot BLOCKED (details withheld)", file=sys.stderr)
        raise SystemExit(2)
