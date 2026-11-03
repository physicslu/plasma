#!/usr/bin/env python3
"""Stage C-3: single-appliance Site Worker core (one local process, Unix socket).

The Worker is the ONLY path by which a non-root Package Action (C-2) may use a
Programming Site. It is deliberately small:

* one Unix stream socket, one JSON line request -> one JSON line response;
  no TCP/HTTP, no session database (sessions live in memory: a Worker crash
  invalidates every session by design);
* callers are identified by Linux peer credentials, never by claims:
  - control operations (open/close a session) are accepted ONLY from the
    trusted Runtime process (``runtime_pid()``, e.g. plasma-server MainPID)
    and only while the existing C-1 Job lease is held for that job
    (``lease_verifier(job_id)``);
  - transport operations are accepted ONLY from a process whose process
    group is the registered Package Action process group, with the same uid;
* operations are an adapter-declared allowlist (no shell, executable path or
  raw MMIO read/write API); one in-flight operation per Site;
* fail-closed: an adapter outcome that cannot be proven safe seals the Site
  (persisted marker, never auto-retried); an FPGA identity change invalidates
  the session; expiry / cancel / close end the session.

Hardware specifics live behind a replaceable adapter (see
``ppu_site_adapter_abi5.py``); this core knows no FPGA, address or register.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import hashlib
import stat
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

PROTOCOL = "plasma.ppu.site-worker.v1"
MAX_REQUEST = 4096
JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
SESSION_ID = re.compile(r"[0-9a-f]{32}\Z")
CONTROL_OPS = frozenset({"open_session", "close_session", "status", "bind_image"})
MAX_FLASH_IMAGE_BYTES = 64 * 1024  # First exact target: STM32F103C8T6
MAX_SESSION_S = 3600


class SiteWorkerDenied(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class TransportDenied(Exception):
    """Adapter refused BEFORE touching hardware (Site stays usable)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class TransportUnknown(Exception):
    """Hardware outcome cannot be proven safe: the Site must be sealed."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FlashImage:
    icpn: str
    payload: bytes
    sha256: str


class SiteTransportAdapter(Protocol):
    name: str
    supported_sites: frozenset[int]
    operations: frozenset[str]

    def identity(self) -> Mapping[str, Any]: ...
    def startup_sealed_sites(self) -> set[int]: ...
    def run(self, site: int, operation: str, *, deadline: float,
            cancel: threading.Event, image: FlashImage | None = None) -> Mapping[str, Any]: ...


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise SiteWorkerDenied(code)


@dataclass
class _Session:
    session_id: str
    job_id: str
    sites: frozenset[int]
    pgid: int
    uid: int
    expires: float
    identity: Mapping[str, Any]
    runtime_pid: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    closed: bool = False
    sealed_during: set[int] = field(default_factory=set)
    image: FlashImage | None = None


def proc_peer(pid: int, proc_root: Path = Path("/proc")) -> tuple[int, int]:
    """(pgid, sid) of a live peer, read from the kernel, never from the peer."""
    raw = (proc_root / str(pid) / "stat").read_text()
    rest = raw[raw.rindex(")") + 2:].split()
    return int(rest[2]), int(rest[3])


class SiteWorkerCore:
    def __init__(self, adapter: SiteTransportAdapter, *,
                 runtime_pid: Callable[[], int | None],
                 lease_verifier: Callable[[str], bool],
                 seal_dir: Path,
                 image_root: Path = Path("/run/plasma-server/normalized-images"),
                 clock: Callable[[], float] = time.monotonic,
                 peer_groups: Callable[[int], tuple[int, int]] = proc_peer) -> None:
        self.adapter = adapter
        self.runtime_pid = runtime_pid
        self.lease_verifier = lease_verifier
        self.seal_dir = Path(seal_dir)
        self.image_root = Path(image_root)
        self.clock = clock
        self.peer_groups = peer_groups
        self.epoch = secrets.token_hex(16)
        self._lock = threading.Lock()
        self._site_locks = {site: threading.Lock() for site in adapter.supported_sites}
        self._session: _Session | None = None
        self.seal_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._sealed: set[int] = set(self._persisted_seals()) | set(adapter.startup_sealed_sites())
        for site in sorted(self._sealed):
            self._persist_seal(site, "STARTUP_STATE_UNSAFE")

    # --- seals (persisted markers; cleared only by an operator recovery) ---------
    def _persisted_seals(self) -> list[int]:
        out = []
        for path in self.seal_dir.glob("site*.sealed"):
            match = re.fullmatch(r"site([0-9]+)\.sealed", path.name)
            if match:
                out.append(int(match.group(1)))
        return out

    def _persist_seal(self, site: int, code: str) -> None:
        path = self.seal_dir / f"site{site}.sealed"
        if path.exists():
            return
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"site": site, "code": code, "epoch": self.epoch, "time": time.time()}, stream)

    def _seal(self, site: int, code: str, session: _Session | None = None) -> None:
        with self._lock:
            self._sealed.add(site)
            if session is not None:
                # Recorded on the session that ran the operation, even if the
                # Runtime already closed it (cancel race).
                session.sealed_during.add(site)
        self._persist_seal(site, code)

    # --- dispatch ------------------------------------------------------------------
    def _drop_if_runtime_restarted(self) -> None:
        """A session belongs to ONE Runtime process; a Runtime restart ends it."""
        current = self.runtime_pid()
        with self._lock:
            s = self._session
            if s is not None and s.runtime_pid != current:
                s.closed = True
                s.cancel.set()
                self._session = None

    def handle(self, request: object, peer: tuple[int, int, int],
               role: str | None = None) -> dict[str, Any]:
        try:
            _require(isinstance(request, dict) and request.get("protocol") == PROTOCOL
                     and type(request.get("op")) is str, "REQUEST_INVALID")
            op = request["op"]
            # Production uses two sockets: control (Runtime group) and
            # transport (Package group). Each accepts only its own class.
            if role == "control":
                _require(op in CONTROL_OPS, "OPERATION_DENIED_ON_CONTROL_SOCKET")
            elif role == "transport":
                _require(op not in CONTROL_OPS, "CONTROL_PEER_DENIED")
            self._drop_if_runtime_restarted()
            if op in CONTROL_OPS:
                return {"ok": True, "result": self._control(op, request, peer)}
            return {"ok": True, "result": self._transport(op, request, peer)}
        except SiteWorkerDenied as exc:
            return {"ok": False, "error": exc.code}

    def _control(self, op: str, request: dict, peer: tuple[int, int, int]) -> dict[str, Any]:
        pid, _uid, _gid = peer
        trusted = self.runtime_pid()
        _require(trusted is not None and pid == trusted, "CONTROL_PEER_DENIED")
        if op == "status":
            _require(set(request) == {"protocol", "op"}, "REQUEST_INVALID")
            with self._lock:
                s = self._session
                return {"epoch": self.epoch, "adapter": self.adapter.name,
                        "supported_sites": sorted(self.adapter.supported_sites),
                        "operations": sorted(self.adapter.operations),
                        "sealed_sites": sorted(self._sealed),
                        "session": None if s is None else {"job_id": s.job_id, "sites": sorted(s.sites)}}
        if op == "bind_image":
            _require(set(request) == {
                "protocol", "op", "session_id", "icpn", "image_sha256", "image_size"
            }, "REQUEST_INVALID")
            _require(type(request["session_id"]) is str
                     and type(request["icpn"]) is str
                     and type(request["image_sha256"]) is str
                     and type(request["image_size"]) is int, "REQUEST_INVALID")
            _require(request["icpn"] == "STM32F103C8T6", "TARGET_NOT_SUPPORTED")
            size = request["image_size"]
            _require(0 < size <= MAX_FLASH_IMAGE_BYTES, "IMAGE_SIZE_INVALID")
            digest = request["image_sha256"]
            _require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "IMAGE_SHA256_INVALID")
            with self._lock:
                s = self._session
                _require(s is not None and not s.closed
                         and secrets.compare_digest(s.session_id, request["session_id"]),
                         "SESSION_UNKNOWN")
                _require(s.image is None, "IMAGE_ALREADY_BOUND")
                _require(self.clock() < s.expires, "SESSION_EXPIRED")
                # Only the trusted Runtime stages this exact Job-owned image.
                # No file path or command is accepted from the caller.
                path = self.image_root / (s.job_id + ".bin")
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                    with os.fdopen(fd, "rb") as stream:
                        info = os.fstat(stream.fileno())
                        _require(stat.S_ISREG(info.st_mode) and info.st_size == size,
                                 "IMAGE_SIZE_MISMATCH")
                        payload = stream.read(size + 1)
                except (OSError, ValueError) as exc:
                    raise SiteWorkerDenied("IMAGE_NOT_STAGED") from exc
                _require(len(payload) == size, "IMAGE_SIZE_MISMATCH")
                _require(hashlib.sha256(payload).hexdigest() == digest, "IMAGE_SHA256_MISMATCH")
                s.image = FlashImage(request["icpn"], payload, digest)
                return {"job_id": s.job_id, "icpn": s.image.icpn,
                        "image_sha256": digest, "image_size": size, "bound": True}
        if op == "close_session":
            _require(set(request) == {"protocol", "op", "session_id"}
                     and type(request["session_id"]) is str, "REQUEST_INVALID")
            with self._lock:
                s = self._session
                _require(s is not None and secrets.compare_digest(s.session_id, request["session_id"]),
                         "SESSION_UNKNOWN")
                s.closed = True
                s.cancel.set()
                self._session = None
            # Wait for any in-flight operation to stop (adapter honours cancel).
            for site in sorted(s.sites):
                lock = self._site_locks[site]
                lock.acquire()
                lock.release()
            return {"session_id": s.session_id, "closed": True,
                    "sealed_sites": sorted(s.sealed_during)}
        # open_session
        fields = {"protocol", "op", "job_id", "sites", "pgid", "uid", "max_runtime_s"}
        _require(set(request) == fields, "REQUEST_INVALID")
        job, sites = request["job_id"], request["sites"]
        _require(type(job) is str and JOB_ID.fullmatch(job) is not None
                 and type(sites) is list and 0 < len(sites) <= 8
                 and all(type(x) is int for x in sites) and sites == sorted(set(sites))
                 and type(request["pgid"]) is int and request["pgid"] > 1
                 and type(request["uid"]) is int and request["uid"] > 0
                 and type(request["max_runtime_s"]) is int
                 and 0 < request["max_runtime_s"] <= MAX_SESSION_S, "REQUEST_INVALID")
        _require(set(sites) <= self.adapter.supported_sites, "SITE_NOT_SUPPORTED")
        _require(self.lease_verifier(job), "JOB_LEASE_NOT_HELD")
        identity = dict(self.adapter.identity())
        with self._lock:
            _require(self._session is None, "SESSION_ALREADY_ACTIVE")
            _require(not (set(sites) & self._sealed), "SITE_SEALED")
            s = _Session(secrets.token_hex(16), job, frozenset(sites), request["pgid"],
                         request["uid"], self.clock() + request["max_runtime_s"], identity,
                         runtime_pid=pid)
            self._session = s
        return {"session_id": s.session_id, "epoch": self.epoch, "sites": sorted(s.sites)}

    def _transport(self, op: str, request: dict, peer: tuple[int, int, int]) -> dict[str, Any]:
        pid, uid, _gid = peer
        _require(set(request) == {"protocol", "op", "site"} and type(request["site"]) is int,
                 "REQUEST_INVALID")
        _require(op in self.adapter.operations, "OPERATION_DENIED")
        site = request["site"]
        try:
            pgid, _sid = self.peer_groups(pid)
        except (OSError, ValueError, IndexError):
            raise SiteWorkerDenied("PEER_UNVERIFIABLE") from None
        with self._lock:
            s = self._session
            _require(s is not None and not s.closed and pgid == s.pgid and uid == s.uid,
                     "NO_SESSION_FOR_PEER")
            _require(self.clock() < s.expires, "SESSION_EXPIRED")
            _require(site in s.sites, "SITE_NOT_AUTHORIZED")
            _require(site not in self._sealed, "SITE_SEALED")
            if op == "flash_cycle":
                _require(s.image is not None, "IMAGE_NOT_BOUND")
        _require(self.lease_verifier(s.job_id), "JOB_LEASE_NOT_HELD")
        if dict(self.adapter.identity()) != s.identity:
            with self._lock:
                if self._session is s:
                    s.closed = True
                    s.cancel.set()
            raise SiteWorkerDenied("SESSION_INVALIDATED_FPGA_IDENTITY_CHANGED")
        lock = self._site_locks[site]
        _require(lock.acquire(blocking=False), "SITE_BUSY")
        try:
            _require(not s.cancel.is_set(), "SESSION_CLOSED")
            try:
                if op == "flash_cycle":
                    result = dict(self.adapter.run(
                        site, op, deadline=s.expires, cancel=s.cancel, image=s.image
                    ))
                else:
                    result = dict(self.adapter.run(
                        site, op, deadline=s.expires, cancel=s.cancel
                    ))
            except TransportDenied as exc:
                raise SiteWorkerDenied("TRANSPORT_DENIED:" + exc.code) from None
            except TransportUnknown as exc:
                self._seal(site, exc.code, s)
                raise SiteWorkerDenied("OUTCOME_UNKNOWN_SITE_SEALED:" + exc.code) from None
            except Exception as exc:  # any adapter bug is an unknown hardware outcome
                self._seal(site, type(exc).__name__, s)
                raise SiteWorkerDenied("OUTCOME_UNKNOWN_SITE_SEALED:" + type(exc).__name__) from None
            if dict(self.adapter.identity()) != s.identity:
                self._seal(site, "FPGA_IDENTITY_CHANGED_DURING_OPERATION", s)
                raise SiteWorkerDenied("OUTCOME_UNKNOWN_SITE_SEALED:FPGA_IDENTITY_CHANGED_DURING_OPERATION")
            return {"site": site, "operation": op, "adapter": self.adapter.name, **result}
        finally:
            lock.release()


# --- Unix socket transport ---------------------------------------------------------

def peer_credentials(conn: socket.socket) -> tuple[int, int, int]:
    raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", raw)


class SiteWorkerServer:
    """Threaded Unix-socket front end. The socket file is the only endpoint."""

    def __init__(self, core: SiteWorkerCore, socket_path: Path, *, mode: int = 0o660,
                 group: int | None = None, role: str | None = None) -> None:
        if role not in (None, "control", "transport"):
            raise ValueError("role must be control or transport")
        self.role = role
        self.core = core
        self.socket_path = Path(socket_path)
        self.mode = mode
        self.group = group
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

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
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        assert self._sock is not None
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(10)
            try:
                peer = peer_credentials(conn)
                data = b""
                while not data.endswith(b"\n") and len(data) <= MAX_REQUEST:
                    chunk = conn.recv(MAX_REQUEST + 1)
                    if not chunk:
                        break
                    data += chunk
                if len(data) > MAX_REQUEST or not data.endswith(b"\n"):
                    response = {"ok": False, "error": "REQUEST_INVALID"}
                else:
                    try:
                        request = json.loads(data.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        request = None
                    response = self.core.handle(request, peer, self.role)
                conn.sendall((json.dumps(response, sort_keys=True) + "\n").encode())
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


class SiteWorkerClient:
    """Runtime-side client (control ops). Packages speak the same JSON line."""

    def __init__(self, socket_path: Path, timeout_s: float = 60.0) -> None:
        self.socket_path = Path(socket_path)
        self.timeout_s = timeout_s

    def call(self, op: str, **fields: Any) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout_s)
            sock.connect(str(self.socket_path))
            sock.sendall((json.dumps({"protocol": PROTOCOL, "op": op, **fields}) + "\n").encode())
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        reply = json.loads(data.decode("utf-8"))
        if not reply.get("ok"):
            raise SiteWorkerDenied(str(reply.get("error")))
        return reply["result"]

    def open_session(self, *, job_id: str, sites: list[int], pgid: int, uid: int,
                     max_runtime_s: int) -> dict[str, Any]:
        return self.call("open_session", job_id=job_id, sites=sites, pgid=pgid, uid=uid,
                         max_runtime_s=max_runtime_s)

    def close_session(self, session_id: str) -> dict[str, Any]:
        return self.call("close_session", session_id=session_id)

    def bind_image(
        self, session_id: str, *, icpn: str, image_sha256: str, image_size: int
    ) -> dict[str, Any]:
        return self.call("bind_image", session_id=session_id, icpn=icpn,
                         image_sha256=image_sha256, image_size=image_size)


# --- production trust providers ----------------------------------------------------

def systemd_main_pid(unit: str = "plasma-server.service") -> Callable[[], int | None]:
    """The trusted Runtime is the unit's MainPID (a Package child never is)."""
    def provider() -> int | None:
        out = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", unit],
                             capture_output=True, text=True, timeout=5,
                             env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        value = out.stdout.strip()
        return int(value) if out.returncode == 0 and value.isdigit() and int(value) > 1 else None
    return provider


def runtime_lease_snapshot(control_socket: Path, timeout_s: float = 5.0) -> dict | None:
    """Read-only C-1 ``execution_lease`` snapshot; None if the Runtime is unreachable."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_s)
            sock.connect(str(control_socket))
            sock.sendall(b'{"operation":"execution_lease"}\n')
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        reply = json.loads(data.decode("utf-8"))
    except (OSError, ValueError):
        return None
    lease = reply.get("result") if isinstance(reply, dict) and reply.get("ok") else None
    return lease if isinstance(lease, dict) else None


def runtime_lease_verifier(control_socket: Path, timeout_s: float = 5.0) -> Callable[[str], bool]:
    """Ask the Runtime (C-1 SiteManager) whether job_id holds the Package Action lease."""
    def verify(job_id: str) -> bool:
        lease = runtime_lease_snapshot(control_socket, timeout_s)
        return (isinstance(lease, dict) and lease.get("busy") is True
                and lease.get("owner_kind") == "package_action" and lease.get("owner_id") == job_id)
    return verify
