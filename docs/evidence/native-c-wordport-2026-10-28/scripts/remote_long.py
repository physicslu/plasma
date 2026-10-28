#!/usr/bin/env python3
"""Bounded local SSH transport for the owner-approved Z2 experiment."""
from __future__ import annotations

import json
from pathlib import Path
import shlex
import stat
import subprocess
import sys

LOGIN = Path.home() / ".config/plasma/z2-login-smoke.json"
KEY = Path.home() / ".ssh/plasma_z2_ed25519"
KNOWN = Path.home() / ".ssh/known_hosts"
PYTHON = "/opt/plasma/python/3.12.13/bin/python3"


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: remote_long.py REMOTE_PYTHON_FILE MODE")
    if stat.S_IMODE(LOGIN.stat().st_mode) != 0o600:
        raise SystemExit("PRIVATE_LOGIN_MODE_DENIED")
    config = json.loads(LOGIN.read_text())
    if set(config) != {"ssh_host", "ssh_username", "ssh_password", "sudo_password"}:
        raise SystemExit("PRIVATE_LOGIN_SCHEMA_DENIED")
    if config["ssh_username"] != "xilinx":
        raise SystemExit("Z2_ACCOUNT_DENIED")
    pin = subprocess.run(["ssh-keygen", "-F", config["ssh_host"], "-f", str(KNOWN)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    if pin.returncode:
        raise SystemExit("Z2_HOST_KEY_NOT_PINNED")
    source = Path(sys.argv[1]).read_text()
    remote = "sudo -S -p '' " + PYTHON + " -I -B -c " + shlex.quote(source) + " " + shlex.quote(sys.argv[2])
    argv = ["ssh", "-F", "/dev/null", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + str(KNOWN), "-o", "ConnectTimeout=8",
            "-o", "ConnectionAttempts=1", "--",
            config["ssh_username"] + "@" + config["ssh_host"], remote]
    result = subprocess.run(argv, input=config["sudo_password"] + "\n",
                            capture_output=True, text=True, timeout=7200)
    for stream in (result.stdout, result.stderr):
        clean = stream.replace(config["sudo_password"], "[REDACTED]")
        clean = clean.replace(config["ssh_password"], "[REDACTED]")
        if clean:
            print(clean, end="", file=sys.stdout if stream is result.stdout else sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
