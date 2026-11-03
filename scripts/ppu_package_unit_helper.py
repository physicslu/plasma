#!/usr/bin/env python3
"""Fixed-purpose root helper: manage ONLY ``plasma-package@<32hex>.service``.

Replaces the polkit rule path (Z2 ships polkit 0.105, which cannot restrict
``manage-units`` by unit name). Same pattern as the existing
``plasma-runtime-activation`` helper: one AF_UNIX socket root:plasma 0660,
requests accepted only from the trusted Runtime process (plasma-server
MainPID, via SO_PEERCRED).

Protocol ``plasma.ppu.package-unit-control.v1``, one JSON line each way:

  {op: start|stop|show, job_id}         start also requires the Runtime-owned
                                         job spec to exist (not a symlink)
  {op: kill, job_id, signal: 15|9}
  {op: list}

The helper builds every systemctl argv itself from the op and the 32-hex
job_id; it never accepts a unit name, path, property, command or argument
from the caller. User, ExecStart and sandbox of the Package stay fixed in the
root-owned template unit.
"""
from __future__ import annotations

import json
import os
import re
import socket
import stat
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

PROTOCOL = "plasma.ppu.package-unit-control.v1"
JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
UNIT = re.compile(r"plasma-package@([0-9a-f]{32})\.service\Z")
SIGNALS = frozenset({15, 9})
SHOW_PROPERTIES = "ActiveState,SubState,MainPID,TasksCurrent"
MAX_REQUEST = 1024


def run_systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/systemctl", *args], capture_output=True, text=True,
                          timeout=30, env={"PATH": "/usr/bin:/bin", "LANG": "C"})


class HelperDenied(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise HelperDenied(code)


class PackageUnitHelper:
    def __init__(self, *, runtime_pid: Callable[[], int | None], runtime_uid: int,
                 spec_dir: Path = Path("/run/plasma-package-specs"),
                 systemctl: Callable[..., subprocess.CompletedProcess] = run_systemctl) -> None:
        self.runtime_pid = runtime_pid
        self.runtime_uid = runtime_uid
        self.spec_dir = Path(spec_dir)
        self.systemctl = systemctl

    def handle(self, request: object, peer: tuple[int, int, int]) -> dict[str, Any]:
        try:
            pid, uid, _gid = peer
            trusted = self.runtime_pid()
            _require(trusted is not None and pid == trusted and uid == self.runtime_uid,
                     "PEER_NOT_TRUSTED_RUNTIME")
            _require(isinstance(request, dict) and request.get("protocol") == PROTOCOL
                     and type(request.get("op")) is str, "REQUEST_INVALID")
            op = request["op"]
            if op == "list":
                _require(set(request) == {"protocol", "op"}, "REQUEST_INVALID")
                r = self.systemctl("list-units", "--all", "--plain", "--no-legend", "plasma-package@*")
                units = [line.split()[0] for line in r.stdout.splitlines()
                         if line.split() and UNIT.fullmatch(line.split()[0])]
                return {"ok": True, "rc": r.returncode, "units": units}
            fields = {"protocol", "op", "job_id"} | ({"signal"} if op == "kill" else set())
            _require(op in ("start", "stop", "show", "kill") and set(request) == fields
                     and type(request["job_id"]) is str and JOB_ID.fullmatch(request["job_id"]),
                     "REQUEST_INVALID")
            unit = f"plasma-package@{request['job_id']}.service"
            if op == "start":
                spec = self.spec_dir / f"{request['job_id']}.json"
                try:
                    info = os.lstat(spec)
                except FileNotFoundError:
                    raise HelperDenied("JOB_SPEC_MISSING") from None
                _require(stat.S_ISREG(info.st_mode) and info.st_uid == self.runtime_uid
                         and info.st_mode & 0o022 == 0, "JOB_SPEC_UNTRUSTED")
                r = self.systemctl("start", unit)
                return {"ok": True, "rc": r.returncode}
            if op == "stop":
                r = self.systemctl("stop", unit)
                return {"ok": True, "rc": r.returncode}
            if op == "kill":
                _require(type(request["signal"]) is int and request["signal"] in SIGNALS,
                         "SIGNAL_DENIED")
                r = self.systemctl("kill", f"--signal={request['signal']}", "--kill-whom=all", unit)
                return {"ok": True, "rc": r.returncode}
            r = self.systemctl("show", f"--property={SHOW_PROPERTIES}", unit)
            props = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
            return {"ok": True, "rc": r.returncode,
                    "properties": {k: props.get(k, "") for k in SHOW_PROPERTIES.split(",")}}
        except HelperDenied as exc:
            return {"ok": False, "error": exc.code}


def _peer(conn: socket.socket) -> tuple[int, int, int]:
    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", raw)


class HelperServer:
    def __init__(self, helper: PackageUnitHelper, socket_path: Path, *, group: int | None = None,
                 mode: int = 0o660) -> None:
        self.helper, self.socket_path, self.group, self.mode = helper, Path(socket_path), group, mode
        self._sock: socket.socket | None = None

    def start(self) -> None:
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.socket_path))
        os.chmod(self.socket_path, self.mode)
        if self.group is not None:
            os.chown(self.socket_path, -1, self.group)
        sock.listen(16)
        self._sock = sock
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(35)
            try:
                peer = _peer(conn)
                data = b""
                while not data.endswith(b"\n") and len(data) <= MAX_REQUEST:
                    chunk = conn.recv(MAX_REQUEST + 1)
                    if not chunk:
                        break
                    data += chunk
                try:
                    request = json.loads(data) if data.endswith(b"\n") and len(data) <= MAX_REQUEST else None
                except ValueError:
                    request = None
                reply = self.helper.handle(request, peer)
                conn.sendall((json.dumps(reply, sort_keys=True) + "\n").encode())
            except OSError:
                pass

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass


class HelperSystemctl:
    """Runtime-side drop-in for ``run_systemctl`` used by SystemdUnitSpawner.

    Translates the spawner's fixed calls into helper ops; any other call is
    refused locally. Never forwards a unit name: only the 32-hex job_id.
    """

    def __init__(self, socket_path: Path = Path("/run/plasma-package-control/helper.sock"),
                 timeout_s: float = 40.0) -> None:
        self.socket_path, self.timeout_s = Path(socket_path), timeout_s

    def _call(self, request: dict) -> dict:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout_s)
            sock.connect(str(self.socket_path))
            sock.sendall((json.dumps({"protocol": PROTOCOL, **request}) + "\n").encode())
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        return json.loads(data)

    @staticmethod
    def _job(unit: str) -> str:
        match = UNIT.fullmatch(unit)
        if match is None:
            raise HelperDenied("UNIT_DENIED")
        return match.group(1)

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        try:
            if args[:1] == ("list-units",):
                reply = self._call({"op": "list"})
                out = "".join(f"{u} loaded\n" for u in reply.get("units", []))
            elif len(args) == 2 and args[0] in ("start", "stop"):
                reply = self._call({"op": args[0], "job_id": self._job(args[1])})
                out = ""
            elif (len(args) == 4 and args[0] == "kill" and args[2] == "--kill-whom=all"
                  and args[1].startswith("--signal=") and args[1][9:].isdigit()):
                reply = self._call({"op": "kill", "job_id": self._job(args[3]), "signal": int(args[1][9:])})
                out = ""
            elif len(args) == 3 and args[0] == "show":
                reply = self._call({"op": "show", "job_id": self._job(args[2])})
                out = "".join(f"{k}={v}\n" for k, v in (reply.get("properties") or {}).items())
            else:
                raise HelperDenied("CALL_DENIED")
        except (OSError, ValueError, HelperDenied) as exc:
            code = exc.code if isinstance(exc, HelperDenied) else type(exc).__name__
            return subprocess.CompletedProcess(args, 1, "", code)
        if not reply.get("ok"):
            return subprocess.CompletedProcess(args, 1, "", str(reply.get("error")))
        return subprocess.CompletedProcess(args, int(reply.get("rc", 1)), out, "")


def main() -> int:  # pragma: no cover - systemd wiring
    import grp
    import pwd
    import signal as sig
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ppu_site_worker import systemd_main_pid
    if os.geteuid() != 0:
        print("PACKAGE_UNIT_HELPER_REQUIRES_ROOT", file=sys.stderr)
        return 77
    run_dir = Path(os.environ.get("RUNTIME_DIRECTORY", "/run/plasma-package-control"))
    helper = PackageUnitHelper(runtime_pid=systemd_main_pid("plasma-server.service"),
                               runtime_uid=pwd.getpwnam("plasma").pw_uid)
    server = HelperServer(helper, run_dir / "helper.sock", group=grp.getgrnam("plasma").gr_gid)
    server.start()
    stop = threading.Event()
    sig.signal(sig.SIGTERM, lambda *_: stop.set())
    stop.wait()
    server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
