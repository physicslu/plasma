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
ROOT_ENTRY = "/usr/local/libexec/plasma/z2-path2-root-entry"
MARK = "PLASMA_PATH2_STAGE="
PROMPT = "PLASMA_PATH2_SUDO_PROMPT:"
TIMEOUT = 105
MAX_OUTPUT = 8192
# Transport accepts bounded stage tokens; Dispatcher authorizes a request
# and the installed root-owned entry independently enforces its allowed verbs.
STAGE_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


class Blocked(ValueError):
    pass


# Only these exact local exception codes may cross the dispatcher boundary.
# Never serialize exception text, SSH configuration or PTY output.
SAFE_FAILURE_CODES = frozenset({
    "LOCAL_ENROLLMENT_DENIED", "SSH_CONNECT_TIMEOUT_OR_UNREACHABLE",
    "HOST_KEY_REJECTED", "REMOTE_AUTH_OR_SUDO_FAILED",
    "Z2_ROOT_SOURCE_OR_IMAGE_BLOCKED", "REMOTE_TIMEOUT_MANUAL_STATE_REVIEW",
    "REMOTE_RECEIPT_INVALID", "CHILD_OWNERSHIP_UNCERTAIN", "UNKNOWN",
    "PRIVATE_CREDENTIAL_NOT_ENROLLED", "SWPC_RUNNER_IDENTITY_DENIED",
    "SSH_OR_SUDO_ROUTE_NOT_ENROLLED", "HOST_KEY_FILE_DENIED",
    "HOST_KEY_NOT_PINNED", "STAGE_NOT_ALLOWLISTED", "SOURCE_SHA_INVALID",
    "REMOTE_EXIT_OR_PRIVILEGE_FAILED", "REMOTE_PTY_NOT_DRAINED",
    "REMOTE_OUTPUT_TOO_LARGE", "EXACTLY_ONE_REMOTE_RECEIPT_REQUIRED",
    "REMOTE_RESULT_NOT_VERIFIED", "PROJECT_NOT_ALLOWLISTED",
})


def failure_code(exc: BaseException) -> str:
    """Preserve exact allowlisted Blocked reasons; fail closed on unknown text."""
    if type(exc) is Blocked and len(exc.args) == 1:
        code = exc.args[0]
        if type(code) is str and code in SAFE_FAILURE_CODES:
            return code
    return "UNKNOWN"


# Exact diagnostics supported by the protected root entry/source. These only
# categorize a failed command; they do not authenticate image/restore state.
ROOT_MANIFEST_DIAGNOSTICS = frozenset({
    "PATH2_APPROVED_ROOT_SOURCE_NOT_INSTALLED",
    "PATH2_PINNED_PYTHON_NOT_INSTALLED", "PATH2_SOURCE_NOT_ROOT_OWNED",
    "PATH2_SOURCE_WRITABLE_BY_OTHERS", "PATH2_REQUIRED_SOURCE_NOT_PINNED",
    "PATH2_APPROVED_SOURCE_HASH_MISMATCH",
    "PATH2_APPROVED_PROFILE_INVALID", "PATH2_APPROVED_PROFILE_MISMATCH",
    "PATH2_REQUEST_NOT_PINNED",
})


def remote_failure(returncode: int, output: bytes) -> str:
    """Classify failed SSH, never interpret diagnostic text as a root receipt.

    These are transport diagnostics, not authenticated root state assertions.
    No remote diagnostic alone proves image or recovery state.
    """
    if returncode < 0:
        return "CHILD_OWNERSHIP_UNCERTAIN"
    text = output.decode("utf-8", "replace")
    if returncode in (1, 2) and any(line in {
            "pl.hil.swd04.contract.SafetyError: MMIO_CHILD_UNREAPED_NO_RELOAD",
            "pl.hil.swd04.contract.SafetyError: MMIO_CHILD_TIMEOUT",
            "pl.hil.swd04.contract.SafetyError: MMIO child failed or SIGBUS",
            } for line in text.splitlines()):
        return "CHILD_OWNERSHIP_UNCERTAIN"
    if returncode == 255:
        if re.search(r"(?m)^ssh: (?:connect to host [^\r\n]+ port [0-9]+: "
                     r"(?:Connection timed out|No route to host|Network is unreachable|Connection refused)"
                     r"|Could not resolve hostname [^\r\n]+)\r?$", text):
            return "SSH_CONNECT_TIMEOUT_OR_UNREACHABLE"
        if re.search(r"(?m)^(?:Host key verification failed\.|"
                     r"WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!)\r?$", text):
            return "HOST_KEY_REJECTED"
        if re.search(r"(?m)^[^\r\n]+: Permission denied "
                     r"\([a-z,-]+\)\.\r?$", text):
            return "REMOTE_AUTH_OR_SUDO_FAILED"
    if re.search(r"(?m)^sudo: (?:a password is required|"
                 r"[0-9]+ incorrect password attempts?)\r?$", text):
        return "REMOTE_AUTH_OR_SUDO_FAILED"
    # Reject mixed/duplicate root diagnostic claims and all arbitrary stderr.
    # Do not interpret diagnostics on SSH's own failure exit (255).
    lines = text.splitlines()
    root_codes = [line for line in lines
                  if line in ROOT_MANIFEST_DIAGNOSTICS]
    if returncode == 2 and len(root_codes) == 1:
        return "Z2_ROOT_SOURCE_OR_IMAGE_BLOCKED"
    return "REMOTE_EXIT_OR_PRIVILEGE_FAILED"


def parse_receipt(stage: str, source_sha: str, output: bytes,
                  project: str) -> dict:
    text = output.decode("utf-8", "replace")
    matched = re.findall(
        re.escape(MARK) + r"([^\r\n]{1,3000})\r?(?:\n|\Z)", text)
    need(text.count(MARK) == 1 and len(matched) == 1,
         "EXACTLY_ONE_REMOTE_RECEIPT_REQUIRED")
    try:
        data = json.loads(matched[0])
    except (ValueError, RecursionError):
        raise Blocked("REMOTE_RECEIPT_INVALID") from None
    need(type(data) is dict and data.get("stage") == stage
         and data.get("project") == project
         and type(data.get("boot_id")) is str
         and re.fullmatch(r"[a-zA-Z0-9-]{8,64}", data["boot_id"]) is not None
         and (
             data.get("result") in {
                 "download": ("LOADED_AND_HELD",),
                 "test": ("IDENTITY_PASS", "DPIDR_PASS"),
                 "restore": ("RESTORED_VERIFIED", "ALREADY_RESTORED"),
             }[stage] if stage in ("download", "test", "restore")
             else (data.get("result") ==
                   "READ_ONLY_AUDIT_NOT_HARDWARE_ADMISSION"
                   and data.get("hardware_write_authorized") is False)
         ), "REMOTE_RESULT_NOT_VERIFIED")
    return {"stage": stage, "source_sha": source_sha,
            "project": project, "real_z2": True, "boot_id": data["boot_id"],
            "result": data["result"]}


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
    # The ONLY Z2 login/sudo credential file shared by Path 2 and Path 3.
    # Do not select another host through a legacy per-task or operator file.
    ssh = private_json(LOGIN)
    sudo_password = ssh.get("sudo_password", ssh.get("ssh_password")) \
        if type(ssh) is dict else None
    need(type(ssh) is dict and
         {"ssh_host", "ssh_username", "ssh_password"} <= set(ssh) <=
         {"ssh_host", "ssh_username", "ssh_password", "sudo_password"} and
         ssh["ssh_username"] == "xilinx" and
         type(ssh["ssh_host"]) is str and
         re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,250}", ssh["ssh_host"]) and
         type(ssh["ssh_password"]) is str and ssh["ssh_password"] and
         type(sudo_password) is str and sudo_password,
         "SSH_OR_SUDO_ROUTE_NOT_ENROLLED")
    kh = KNOWN_HOSTS.lstat()
    need(stat.S_ISREG(kh.st_mode) and
         kh.st_uid == os.geteuid() and
         stat.S_IMODE(kh.st_mode) == 0o600, "HOST_KEY_FILE_DENIED")
    chk = subprocess.run(
        ["/usr/bin/ssh-keygen", "-F", ssh["ssh_host"], "-f", str(KNOWN_HOSTS)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False, timeout=5)
    need(chk.returncode == 0, "HOST_KEY_NOT_PINNED")
    return ssh["ssh_host"], ssh["ssh_password"], sudo_password


def execute(stage: str, source_sha: str, project: str) -> dict:
    need(type(stage) is str and STAGE_NAME.fullmatch(stage) is not None,
         "STAGE_INVALID")
    need(bool(re.fullmatch(r"[a-f0-9]{40}", source_sha)), "SOURCE_SHA_INVALID")
    need(type(project) is str and re.fullmatch(
        r"pl/projects/[a-z0-9][a-z0-9-]{2,69}", project) is not None,
        "PROJECT_NOT_ALLOWLISTED")
    try:
        host, password, sudo_password = enrollment()
    except Blocked:
        raise
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise Blocked("LOCAL_ENROLLMENT_DENIED") from None
    # Remote command is fixed; only the three bounded stage tokens vary.
    # Root-side executable itself checks protected code/firmware manifest.
    remote = ("sudo -S -p " + PROMPT + " " + ROOT_ENTRY + " " +
              stage + " " + project + " " + source_sha)
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
        try:
            returncode = proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            raise Blocked("CHILD_OWNERSHIP_UNCERTAIN") from None
        need(returncode == 0, remote_failure(returncode, bytes(response)))
        return parse_receipt(stage, source_sha, bytes(response), project)

    finally:
        try:
            if proc is not None and proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        raise Blocked("CHILD_OWNERSHIP_UNCERTAIN") from None
        except (OSError, subprocess.SubprocessError):
            raise Blocked("CHILD_OWNERSHIP_UNCERTAIN") from None
        finally:
            if slave != -1:
                os.close(slave)
            os.close(master)
