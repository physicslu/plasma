#!/usr/bin/env python3
"""Trusted-main-only development transport. Never import from a candidate tree.

Dispatcher authenticates event, live PR, checkout and stage scope before calling.
No local privileged installation or source SHA PIN is consumed here.
"""
from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import select
import signal
import stat
import subprocess
import sys
import termios
import time
import tty

WORKER = "plasma-codex"
HOME = Path("/home/plasma-codex")
PRIVATE = HOME / ".config/plasma"
LOGIN = PRIVATE / "z2-login-smoke.json"
KNOWN_HOSTS = PRIVATE / "z2-login-known_hosts"
SUDO = PRIVATE / "z2-swd05-oneshot.json"
ROOT_ENTRY = "/usr/local/libexec/plasma/z2-path2-f1b-root-entry"
MARK = "PLASMA_F1B_PATH2_DEV="
PROMPT = "PLASMA_PATH2_SUDO_PROMPT:"
TIMEOUT = 105
MAX_OUTPUT = 8192
STAGES = ("download", "test", "restore")


class Blocked(ValueError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def private_json(path: Path) -> dict:
    owner = pwd.getpwnam(WORKER).pw_uid
    d = path.parent.lstat()
    m = path.lstat()
    need(stat.S_ISDIR(d.st_mode) and d.st_uid == owner and
         stat.S_IMODE(d.st_mode) == 0o700 and
         stat.S_ISREG(m.st_mode) and m.st_uid == owner and
         stat.S_IMODE(m.st_mode) == 0o600 and m.st_size <= 8192,
         "PRIVATE_CREDENTIAL_NOT_ENROLLED")
    return json.loads(path.read_text())


def enrollment() -> tuple[str, str, str]:
    need(pwd.getpwuid(os.geteuid()).pw_name == WORKER and
         os.geteuid() != 0, "SWPC_RUNNER_IDENTITY_DENIED")
    ssh = private_json(LOGIN)
    sudo = private_json(SUDO)
    need(type(ssh) is dict and set(ssh) == {
         "ssh_host", "ssh_username", "ssh_password"} and
         ssh["ssh_username"] == "xilinx" and
         type(ssh["ssh_host"]) is str and
         re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,250}", ssh["ssh_host"]) and
         type(ssh["ssh_password"]) is str and ssh["ssh_password"] and
         type(sudo) is dict and
         type(sudo.get("sudo_password")) is str and
         sudo["sudo_password"], "SSH_OR_SUDO_ROUTE_NOT_ENROLLED")
    kh = KNOWN_HOSTS.lstat()
    need(stat.S_ISREG(kh.st_mode) and
         kh.st_uid == os.geteuid() and
         stat.S_IMODE(kh.st_mode) == 0o600, "HOST_KEY_FILE_DENIED")
    chk = subprocess.run(
        ["/usr/bin/ssh-keygen", "-F", ssh["ssh_host"], "-f", str(KNOWN_HOSTS)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False, timeout=5)
    need(chk.returncode == 0, "HOST_KEY_NOT_PINNED")
    return ssh["ssh_host"], ssh["ssh_password"], sudo["sudo_password"]


def execute(stage: str, source_sha: str) -> dict:
    need(stage in STAGES, "STAGE_NOT_ALLOWLISTED")
    need(bool(re.fullmatch(r"[a-f0-9]{40}", source_sha)), "SOURCE_SHA_INVALID")
    host, password, sudo_password = enrollment()
    # Remote command is fixed; only the three bounded stage tokens vary.
    # Root-side executable itself checks protected code/firmware manifest.
    remote = ("sudo -S -p " + PROMPT + " " + ROOT_ENTRY + " " + stage)
    argv = [
        "/usr/bin/ssh", "-F", "/dev/null", "-T",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + str(KNOWN_HOSTS),
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "BatchMode=no", "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no", "-o", "ConnectTimeout=8",
        "-o", "ConnectionAttempts=1",
        "--", "xilinx@" + host, remote,
    ]
    master, slave = os.openpty()
    tty.setraw(slave, termios.TCSANOW)

    def controlling_tty() -> None:
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    proc = None
    response = bytearray()
    ssh_sent = sudo_sent = False
    try:
        proc = subprocess.Popen(argv, stdin=slave, stdout=slave,
                                stderr=slave, close_fds=True,
                                preexec_fn=controlling_tty,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        os.close(slave)
        slave = -1
        deadline = time.monotonic() + TIMEOUT
        exited_at = None
        while time.monotonic() < deadline:
            # A reaped SSH child does not imply its PTY output was consumed.
            # Keep draining to EOF, but do not hang on inherited slave FDs.
            if proc.poll() is not None and exited_at is None:
                exited_at = time.monotonic()
            if exited_at is not None and time.monotonic() - exited_at > 3:
                raise Blocked("REMOTE_PTY_NOT_DRAINED")
            ready = select.select([master], [], [], 0.2)[0]
            if ready:
                try:
                    part = os.read(master, 2048)
                except OSError as exc:
                    if exc.errno != errno.EIO:  # Linux PTY slave closed.
                        raise
                    break
                if not part:
                    break
                response.extend(part)
                need(len(response) <= MAX_OUTPUT, "REMOTE_OUTPUT_TOO_LARGE")
                tail = response.decode("utf-8", "replace")[-400:]
                if (not ssh_sent and re.search(
                        r"(?i)(?:password|passphrase)[^\r\n]{0,90}:\s*$",
                        tail)):
                    os.write(master, password.encode() + b"\n")
                    ssh_sent = True
                elif not sudo_sent and tail.endswith(PROMPT):
                    os.write(master, sudo_password.encode() + b"\n")
                    sudo_sent = True
        else:
            raise Blocked("REMOTE_TIMEOUT_MANUAL_STATE_REVIEW")
        # sudo -S may be cached or configured to omit a password prompt.
        # Require a successful remote exit and exact root-entry receipt
        # instead of requiring a prompt that may legitimately be absent.
        need(proc.wait(timeout=3) == 0,
             "REMOTE_EXIT_OR_PRIVILEGE_FAILED")
        # SSH and sudo prompts do not require line breaks. A legitimate
        # root-entry marker may follow both prompts on the *same* PTY line.
        # Never trust prompt text: require precisely one complete framed
        # marker with a strict stage-specific JSON payload and exit code 0.
        text = response.decode("utf-8", "replace")
        matched = re.findall(
            re.escape(MARK) + r"([^\r\n]{1,3000})\r?(?:\n|\Z)", text)
        need(text.count(MARK) == 1 and len(matched) == 1,
             "EXACTLY_ONE_REMOTE_RECEIPT_REQUIRED")
        data = json.loads(matched[0])
        need(type(data) is dict and data.get("stage") == stage
             and type(data.get("boot_id")) is str
             and len(data["boot_id"]) >= 8
             and data.get("result") in {
                 "download": ("LOADED_AND_HELD",),
                 "test": ("IDENTITY_PASS",),
                 "restore": ("RESTORED_VERIFIED", "ALREADY_RESTORED"),
             }[stage], "REMOTE_RESULT_NOT_VERIFIED")
        return {"stage": stage, "source_sha": source_sha,
                "real_z2": True, "boot_id": data["boot_id"],
                "result": data["result"]}
    finally:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=2)
        if slave != -1:
            os.close(slave)
        os.close(master)

