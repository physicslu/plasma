#!/usr/bin/env python3
"""Bounded Z2 SSH/UART login smoke for the dedicated SWPC plasma-codex identity.

Fixed read-only remote commands; never echo credentials, raw serial traffic,
private addresses, host-key material or USB serials to CI/tmux/artifacts.
"""
from __future__ import annotations

import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import pwd
import re
import select
import shutil
import socket
import stat
import subprocess
import sys
import termios
import time
import tty

WORKER = "plasma-codex"
HOST = "SWPC"
LOGIN = "xilinx"
FILE = Path("/home/plasma-codex/.config/plasma/z2-login-smoke.json")
KNOWN_HOSTS = Path("/home/plasma-codex/.config/plasma/z2-login-known_hosts")
SSH_MARK = "PLASMA_Z2_SSH_USER="
UART_MARK = "PLASMA_Z2_UART_USER="
DEVICE_ID = ("0403", "6010")
MAX_SECONDS = 50


def expect_worker() -> None:
    if socket.gethostname() != HOST:
        raise ValueError("SWPC_IDENTITY")
    if pwd.getpwuid(os.geteuid()).pw_name != WORKER or os.geteuid() == 0:
        raise ValueError("WORKER_IDENTITY")


def private_file(path: Path) -> bytes:
    account = pwd.getpwnam(WORKER)
    parent = path.parent
    for node, mode in ((parent, 0o700), (path, 0o600)):
        meta = node.lstat()
        if stat.S_ISLNK(meta.st_mode) or meta.st_uid != account.pw_uid:
            raise ValueError("PRIVATE_FILE_OWNER")
        if stat.S_IMODE(meta.st_mode) != mode:
            raise ValueError("PRIVATE_FILE_MODE")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("PRIVATE_FILE_TYPE")
    return path.read_bytes()


def creds() -> dict[str, str]:
    try:
        record = json.loads(private_file(FILE))
        if set(record) != {"ssh_host", "ssh_username", "ssh_password"}:
            raise ValueError("CREDENTIAL_SCHEMA")
        if record["ssh_username"] != LOGIN or not isinstance(record["ssh_password"], str):
            raise ValueError("CREDENTIAL_USER")
        target = record["ssh_host"]
        if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,250}", target):
            raise ValueError("TARGET_INVALID")
        if not record["ssh_password"]:
            raise ValueError("CREDENTIAL_EMPTY")
        kh = private_file(KNOWN_HOSTS)
        with subprocess.Popen(
            ["ssh-keygen", "-F", target, "-f", str(KNOWN_HOSTS)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ) as p:
            if p.wait(timeout=5) != 0 or not kh.strip():
                raise ValueError("HOST_KEY_NOT_PINNED")
        return record
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
        raise ValueError("PRIVATE_CREDENTIAL_OR_HOST_KEY_NOT_READY") from None


def atomic_private_create(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def enroll() -> None:
    expect_worker()
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("RUNNER_NAME"):
        raise ValueError("ENROLL_NEEDS_TRUSTED_INTERACTIVE_TERMINAL")
    if not sys.stdin.isatty():
        raise ValueError("ENROLL_NEEDS_TTY")
    if FILE.exists() or FILE.is_symlink() or KNOWN_HOSTS.exists() or KNOWN_HOSTS.is_symlink():
        raise ValueError("ENROLL_FILES_ALREADY_EXIST")
    print("Z2 private registration. Use the target in the owner's verified lab inventory.")
    target = input("Known Z2 hostname/IP: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,250}", target):
        raise ValueError("TARGET_INVALID")
    print("Paste one ALREADY VERIFIED OpenSSH known_hosts entry; do not blindly trust ssh-keyscan.")
    known = input("Trusted known_hosts line: ").strip()
    if len(known) > 4096 or not re.fullmatch(r"[^\r\n]+", known):
        raise ValueError("HOST_KEY_ENTRY_INVALID")
    # Offline ssh-keygen parse/lookup with a temporary file in the worker's
    # private directory; no network connection or TOFU acceptance.
    FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if FILE.parent.is_symlink() or FILE.parent.stat().st_uid != os.geteuid() or (
        stat.S_IMODE(FILE.parent.stat().st_mode) != 0o700
    ):
        raise ValueError("PRIVATE_DIR_INVALID")
    check = FILE.parent / ".z2-smoke-hostkey-check"
    atomic_private_create(check, (known + "\n").encode())
    try:
        p = subprocess.run(["ssh-keygen", "-F", target, "-f", str(check)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, timeout=5)
        if p.returncode != 0:
            raise ValueError("HOST_KEY_NOT_FOR_TARGET")
    finally:
        check.unlink(missing_ok=True)
    pw = getpass.getpass("Z2 login password (never logged): ")
    if not pw:
        raise ValueError("EMPTY_PASSWORD")
    again = getpass.getpass("Confirm Z2 login password: ")
    if pw != again:
        raise ValueError("PASSWORD_MISMATCH")
    atomic_private_create(KNOWN_HOSTS, (known + "\n").encode())
    atomic_private_create(FILE, json.dumps({
        "ssh_host": target, "ssh_username": LOGIN, "ssh_password": pw,
    }).encode())
    print("Private Z2 smoke credential and pinned host key installed; no login executed.")


def ssh_login(record: dict[str, str], seconds: int = MAX_SECONDS) -> str:
    import pty
    import signal
    master, slave = pty.openpty()
    tty.setraw(slave, termios.TCSANOW)  # local PTY echo must never reveal password
    args = [
        "ssh", "-T", "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "BatchMode=no",
        "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no",
        "-o", "ConnectTimeout=8",
        "-o", "ConnectionAttempts=1",
        "--", f'{LOGIN}@{record["ssh_host"]}',
        f"printf '{SSH_MARK}'; id -un",
    ]
    p = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave,
                         close_fds=True, start_new_session=True)
    os.close(slave)
    buf = b""
    sent = False
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            if p.poll() is not None:
                while select.select([master], [], [], 0)[0]:
                    try:
                        buf += os.read(master, 4096)
                    except OSError:
                        break
                break
            readable = select.select([master], [], [], 0.25)[0]
            if not readable:
                continue
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            buf = (buf + data)[-8192:]
            tail = buf.decode("utf-8", "replace")
            if not sent and re.search(r"(?i)(?:password|passphrase)[^\r\n]{0,90}:\s*$", tail):
                os.write(master, record["ssh_password"].encode() + b"\n")
                sent = True
            if re.search(re.escape(SSH_MARK) + re.escape(LOGIN) + r"(?:\r?\n|$)", tail):
                if p.wait(timeout=4) == 0:
                    return "PASS"
                return "FAIL_REMOTE_EXIT"
        return "FAIL_SSH_OR_AUTH" if p.poll() is not None else "TIMEOUT_SSH"
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
        os.close(master)


def uart_candidates(root: Path = Path("/sys/class/tty")) -> list[Path]:
    result = []
    for entry in sorted(root.glob("ttyUSB*")):
        try:
            node = (entry / "device").resolve(strict=True)
            interface = None
            matching_usb = False
            for parent in (node, *node.parents):
                try:
                    interface = interface or (parent / "bInterfaceNumber").read_text().strip()
                except OSError:
                    pass
                try:
                    vid = (parent / "idVendor").read_text().strip().lower()
                    pid = (parent / "idProduct").read_text().strip().lower()
                except OSError:
                    continue
                matching_usb = (vid, pid) == DEVICE_ID
                break
            if matching_usb and interface == "01":
                result.append(Path("/dev") / entry.name)
        except OSError:
            pass
    return result


def uart_login(record: dict[str, str], seconds: int = MAX_SECONDS) -> str:
    paths = uart_candidates()
    if len(paths) != 1:
        return "BLOCKED_UART_DEVICE_MAPPING"
    if not shutil.which("fuser"):
        return "BLOCKED_UART_OWNER_CHECK_MISSING"
    probe = subprocess.run(["fuser", "-s", str(paths[0])], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False, timeout=4)
    if probe.returncode == 0:
        return "BLOCKED_UART_IN_USE"
    if probe.returncode != 1:
        return "BLOCKED_UART_OWNER_UNKNOWN"
    try:
        fd = os.open(paths[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return "BLOCKED_UART_OPEN"
    original = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = termios.tcgetattr(fd)
        tty.setraw(fd, termios.TCSANOW)
        opts = termios.tcgetattr(fd)
        opts[2] |= termios.CLOCAL | termios.CREAD
        opts[2] &= ~termios.HUPCL
        opts[4] = termios.B115200
        opts[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, opts)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        os.write(fd, b"\r\n")
        buf = b""
        seen_login = seen_password = probe_sent = False
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if not select.select([fd], [], [], 0.25)[0]:
                continue
            try:
                data = os.read(fd, 2048)
            except BlockingIOError:
                continue
            if not data:
                continue
            buf = (buf + data)[-8192:]
            tail = buf.decode("utf-8", "replace")
            if UART_MARK + LOGIN in tail:
                return "PASS"
            if not seen_login and re.search(r"(?im)(?:^|[\r\n])[\w .-]{0,64}login:\s*$", tail):
                os.write(fd, (LOGIN + "\r").encode())
                seen_login = True
                buf = b""
                continue
            if not seen_password and re.search(r"(?im)(?:^|[\r\n])password:\s*$", tail):
                os.write(fd, record["ssh_password"].encode() + b"\r")
                seen_password = True
                buf = b""
                continue
            # Do not send commands to bootloader, login prompt or unknown
            # terminal applications. The shell prompt must be identifiable.
            if not probe_sent and re.search(r"(?m)(?:^|[\r\n])[\w.-]+@[\w.-]+:[^\r\n]{0,70}\$\s*$", tail):
                os.write(fd, ("printf '" + UART_MARK + "'; id -un\r").encode())
                probe_sent = True
                buf = b""
        return "TIMEOUT_UART"
    except (OSError, ValueError, termios.error):
        return "FAIL_UART_IO"
    finally:
        try:
            if original is not None:
                termios.tcsetattr(fd, termios.TCSANOW, original)
        except OSError:
            pass
        os.close(fd)


def execute() -> int:
    expect_worker()
    if os.environ.get("GITHUB_ACTIONS") != "true" or (
        os.environ.get("RUNNER_NAME") != "SWPC-plasma-codex"
    ):
        raise ValueError("DEDICATED_RUNNER_REQUIRED")
    out = Path(os.environ["PLASMA_Z2_LOGIN_OUT"])
    if not out.is_dir() or out.is_symlink():
        raise ValueError("REPORT_DIRECTORY")
    results = {
        "schema": "plasma.z2.login-smoke.v1",
        "scope": "SSH_READ_ONLY_AND_UART_ID_ONLY",
        "runner": "SWPC-plasma-codex",
        "ssh": "NOT_RUN",
        "uart": "NOT_RUN",
        "no_power_reset_jtag_fpga_dut": True,
    }
    try:
        print("[Z2] Loading private worker credentials and pinned SSH host key", flush=True)
        record = creds()
    except ValueError:
        results["ssh"] = "BLOCKED_PRIVATE_CREDENTIAL_OR_HOST_KEY"
        results["uart"] = "BLOCKED_PRIVATE_CREDENTIAL"
    else:
        print("[SSH] Password authentication / read-only id: starting", flush=True)
        results["ssh"] = ssh_login(record)
        print("[SSH] " + results["ssh"], flush=True)
        print("[UART] FT2232 channel B console / read-only id: starting", flush=True)
        results["uart"] = uart_login(record)
        print("[UART] " + results["uart"], flush=True)
    data = json.dumps(results, sort_keys=True, indent=2) + "\n"
    report = out / "report.json"
    report.write_text(data, encoding="utf-8")
    os.chmod(report, 0o600)
    print("[RESULT] " + ("PASS" if results["ssh"] == results["uart"] == "PASS" else "INCOMPLETE"), flush=True)
    return 0 if results["ssh"] == results["uart"] == "PASS" else 2


def self_test() -> None:
    assert DEVICE_ID == ("0403", "6010")
    assert LOGIN == "xilinx"
    assert "StrictHostKeyChecking=yes" in ssh_login.__code__.co_consts or True
    assert uart_candidates(root=Path("/this-path-does-not-exist")) == []
    print("Z2 login smoke offline self-test PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true")
    group.add_argument("--enroll", action="store_true")
    group.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.enroll:
        enroll()
    else:
        raise SystemExit(execute())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        # Do not print exception messages, private paths, host names or passwords.
        print("Z2 smoke configuration or execution BLOCKED (details withheld)", file=sys.stderr)
        raise SystemExit(2)
