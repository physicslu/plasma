#!/usr/bin/env python3
"""Local ROOT operator entry for ONE Stage C Package Action (no network API).

1. Verify the owner's ``asset.execute`` Owner Operation Authorization with the
   paired Bootstrap credential, bound to THIS device, the requested Active
   Set, Package identity and job_id.
2. Mint a one-time random credential and re-issue an equivalent
   authorization under it (same action, device, Set, job, Package identity).
3. Send it to the Runtime over its 0600 control socket (root peers only).

The Runtime never receives the Bootstrap token; the one-time credential is
only useful for this job (the C-2 journal allows one launch per job_id).
Closing this process (Ctrl-C) disconnects and cancels the action.

usage: ppu_package_action.py run --request REQUEST.json --authorization AUTH.json
"""
from __future__ import annotations

import importlib.util
import json
import os
import secrets
import socket
import stat
import sys
from pathlib import Path
from typing import Any

BOOTSTRAP_DIR = Path(os.environ.get("PLASMA_BOOTSTRAP_DIR", "/opt/plasma/bootstrap"))
TOKEN_FILE = Path(os.environ.get("PLASMA_BOOTSTRAP_TOKEN", "/var/lib/plasma-bootstrap/control-token"))
MACHINE_ID = Path(os.environ.get("PLASMA_MACHINE_ID", "/etc/machine-id"))
CONTROL_SOCKET = Path(os.environ.get("PLASMA_RUNTIME_CONTROL", "/run/plasma-server/control.sock"))
REQUEST_FIELDS = {"asset_set_sha256", "package_id", "package_version", "package_kind",
                  "package_identity_sha256", "job_id"}


class ActionDenied(Exception):
    pass


def _load(name: str, path: Path):
    if path.is_symlink() or not path.is_file():
        raise ActionDenied(f"CONTROL_PLANE_MISSING:{path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _token() -> str:
    info = os.lstat(TOKEN_FILE)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise ActionDenied("BOOTSTRAP_CREDENTIAL_UNTRUSTED")
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def prepare(request: dict, authorization: dict) -> dict[str, Any]:
    """Verify the owner authorization and build the Runtime control request."""
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        raise ActionDenied("REQUEST_INVALID")
    owner = _load("plasma_operator_owner_auth", BOOTSTRAP_DIR / "ppu_owner_authorization.py")
    identity = _load("plasma_operator_device_identity", BOOTSTRAP_DIR / "ppu-bootstrap.py")
    device_id = identity._machine_device_id(MACHINE_ID)
    try:
        owner.verify(authorization, credential=_token(), action=owner.EXECUTE, device_id=device_id,
                     subject_sha256=request["asset_set_sha256"], transaction_id=request["job_id"],
                     package_identity_sha256=request["package_identity_sha256"])
    except owner.OwnerAuthorizationDenied as exc:
        raise ActionDenied(str(exc)) from None
    one_time = secrets.token_urlsafe(32)
    reissued = owner.issue(credential=one_time, action=owner.EXECUTE, device_id=device_id,
                           subject_sha256=request["asset_set_sha256"], transaction_id=request["job_id"],
                           package_identity_sha256=request["package_identity_sha256"])
    return {"operation": "package_action", "request": request, "authorization": reissued,
            "ephemeral_credential": one_time, "device_id": device_id}


def send(control: dict, socket_path: Path = CONTROL_SOCKET, timeout_s: float = 3700.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_s)
        sock.connect(str(socket_path))
        sock.sendall((json.dumps(control) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(1 << 16)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def main(argv: list[str]) -> int:
    if len(argv) != 5 or argv[0] != "run" or argv[1] != "--request" or argv[3] != "--authorization":
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 64
    if os.geteuid() != 0:
        print("PACKAGE_ACTION_REQUIRES_ROOT_OPERATOR", file=sys.stderr)
        return 77
    try:
        control = prepare(json.loads(Path(argv[2]).read_text()), json.loads(Path(argv[4]).read_text()))
    except (ActionDenied, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    reply = send(control)
    print(json.dumps(reply, sort_keys=True, indent=1))
    return 0 if reply.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
