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
* the trusted Runtime may also open a session for its own REST Job
  (``open_job_session``) and run an allowlisted operation on the control
  socket (``run``); such a session has no Package peer;
* fail-closed: an adapter outcome that cannot be proven safe seals the Site
  (persisted marker, never auto-retried); an FPGA identity change invalidates
  the session; expiry / cancel / close end the session. FPGA Image management
  belongs to the PPU Loader.

The target (OpenOCD target config, Flash geometry) of a Flash operation is
resolved by the Runtime from the exact-ICPN IC Support and bound per session;
this core holds no IC, image ID, build or versioned path.

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
# Same canonical Job ID rule as plasma_core.models.JOB_ID_PATTERN (REST Jobs
# and Package Action Jobs share it; a test keeps the two in lockstep).
JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SESSION_ID = re.compile(r"[0-9a-f]{32}\Z")
CONTROL_OPS = frozenset({"open_session", "open_job_session", "close_session", "status",
                         "bind_image", "run"})
TARGET_CONFIG = re.compile(r"target/[A-Za-z0-9_][A-Za-z0-9._-]{0,63}(/[A-Za-z0-9_][A-Za-z0-9._-]{0,63}){0,3}\.cfg\Z")
MAX_SESSION_S = 3600
OWNER_PACKAGE = "package_action"
OWNER_REST_JOB = "rest_job"


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
class FlashProfile:
    """Runtime-resolved exact-ICPN Flash target, bound once per session."""
    icpn: str
    target_config: str
    flash_base: int
    flash_size: int
    erase_granularity: int

    def erase_length(self, size: int) -> int:
        """Image size rounded up to whole erase units."""
        unit = self.erase_granularity
        return -(-size // unit) * unit


@dataclass(frozen=True)
class FlashImage:
    profile: FlashProfile
    payload: bytes
    sha256: str

    @property
    def icpn(self) -> str:
        return self.profile.icpn


def parse_flash_profile(raw: object) -> FlashProfile:
    """Validate the Runtime-supplied profile shape; raises SiteWorkerDenied."""
    _require(isinstance(raw, dict) and set(raw) == {
        "icpn", "target_config", "flash_base", "flash_size", "erase_granularity"},
        "PROFILE_INVALID")
    icpn, cfg = raw["icpn"], raw["target_config"]
    base, size, unit = raw["flash_base"], raw["flash_size"], raw["erase_granularity"]
    _require(type(icpn) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", icpn)
             is not None, "PROFILE_ICPN_INVALID")
    _require(type(cfg) is str and TARGET_CONFIG.fullmatch(cfg) is not None
             and ".." not in cfg.split("/"), "PROFILE_TARGET_CONFIG_INVALID")
    _require(all(type(v) is int for v in (base, size, unit)) and base >= 0 and size > 0
             and unit > 0 and unit & (unit - 1) == 0 and size % unit == 0
             and base % unit == 0 and base + size <= 1 << 32, "PROFILE_GEOMETRY_INVALID")
    return FlashProfile(icpn, cfg, base, size, unit)


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
    pgid: int | None  # None: Runtime-owned REST Job session (no Package peer)
    uid: int | None
    expires: float
    identity: Mapping[str, Any]
    owner_kind: str = OWNER_PACKAGE
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
                 lease_verifier: Callable[[str, str], bool],
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
        # Reuse the existing Worker, lease, per-Site locks, and persistent seals.
        self._sessions: dict[str, _Session] = {}
        self._site_owners: dict[int, str] = {}
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
        """Cancel stale Runtime sessions without releasing an in-flight Site."""
        current = self.runtime_pid()
        with self._lock:
            for session_id, sess in list(self._sessions.items()):
                if sess.runtime_pid == current and not sess.closed:
                    continue
                sess.closed = True
                sess.cancel.set()
                # Do not re-admit this Site before its adapter has exited.
                if any(self._site_locks[site].locked() for site in sess.sites):
                    continue
                for site in sess.sites:
                    if self._site_owners.get(site) == session_id:
                        del self._site_owners[site]
                del self._sessions[session_id]

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
                sessions = [
                    {"job_id": sess.job_id, "sites": sorted(sess.sites),
                     "owner_kind": sess.owner_kind}
                    for sess in sorted(
                        self._sessions.values(), key=lambda x: (min(x.sites), x.job_id)
                    )
                ]
                return {"epoch": self.epoch, "adapter": self.adapter.name,
                        "supported_sites": sorted(self.adapter.supported_sites),
                        "operations": sorted(self.adapter.operations),
                        "sealed_sites": sorted(self._sealed),
                        "not_ready": getattr(self.adapter, "not_ready", None),
                        "sessions": sessions,
                        "session": sessions[0] if len(sessions) == 1 else None}
        if op == "bind_image":
            _require(set(request) == {
                "protocol", "op", "session_id", "profile", "image_sha256", "image_size"
            }, "REQUEST_INVALID")
            _require(type(request["session_id"]) is str
                     and type(request["image_sha256"]) is str
                     and type(request["image_size"]) is int, "REQUEST_INVALID")
            profile = parse_flash_profile(request["profile"])
            size = request["image_size"]
            _require(0 < size <= profile.flash_size, "IMAGE_SIZE_INVALID")
            digest = request["image_sha256"]
            _require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "IMAGE_SHA256_INVALID")
            with self._lock:
                s = self._sessions.get(request["session_id"])
                _require(s is not None and not s.closed, "SESSION_UNKNOWN")
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
                s.image = FlashImage(profile, payload, digest)
                return {"job_id": s.job_id, "icpn": profile.icpn,
                        "target_config": profile.target_config,
                        "image_sha256": digest, "image_size": size, "bound": True}
        if op == "run":
            _require(set(request) == {"protocol", "op", "session_id", "site", "operation"}
                     and type(request["session_id"]) is str and type(request["site"]) is int
                     and type(request["operation"]) is str, "REQUEST_INVALID")
            with self._lock:
                s = self._sessions.get(request["session_id"])
                _require(s is not None and not s.closed, "SESSION_UNKNOWN")
                _require(s.owner_kind == OWNER_REST_JOB, "SESSION_NOT_RUNTIME_OWNED")
            return self._execute(s, request["site"], request["operation"])
        if op == "close_session":
            _require(set(request) == {"protocol", "op", "session_id"}
                     and type(request["session_id"]) is str, "REQUEST_INVALID")
            with self._lock:
                s = self._sessions.get(request["session_id"])
                _require(s is not None, "SESSION_UNKNOWN")
                s.closed = True
                s.cancel.set()
            # Ownership must outlive an in-flight operation and its SAFE_OFF
            # verification, even when close races a cancellation.
            for site in sorted(s.sites):
                lock = self._site_locks[site]
                lock.acquire()
                lock.release()
            with self._lock:
                if self._sessions.get(s.session_id) is s:
                    del self._sessions[s.session_id]
                    for site in s.sites:
                        if self._site_owners.get(site) == s.session_id:
                            del self._site_owners[site]
            return {"session_id": s.session_id, "closed": True,
                    "sealed_sites": sorted(s.sealed_during)}
        # open_session (Package Action peer) / open_job_session (Runtime REST Job)
        package = op == "open_session"
        fields = {"protocol", "op", "job_id", "sites", "max_runtime_s"}
        if package:
            fields |= {"pgid", "uid"}
        _require(set(request) == fields, "REQUEST_INVALID")
        job, sites = request["job_id"], request["sites"]
        _require(type(job) is str and JOB_ID.fullmatch(job) is not None
                 and type(sites) is list and 0 < len(sites) <= 8
                 and all(type(x) is int for x in sites) and sites == sorted(set(sites))
                 and type(request["max_runtime_s"]) is int
                 and 0 < request["max_runtime_s"] <= MAX_SESSION_S, "REQUEST_INVALID")
        if package:
            _require(type(request["pgid"]) is int and request["pgid"] > 1
                     and type(request["uid"]) is int and request["uid"] > 0, "REQUEST_INVALID")
        not_ready = getattr(self.adapter, "not_ready", None)
        _require(not not_ready, f"ENGINE_NOT_READY:{not_ready}")
        _require(set(sites) <= self.adapter.supported_sites, "SITE_NOT_SUPPORTED")
        owner_kind = OWNER_PACKAGE if package else OWNER_REST_JOB
        _require(self.lease_verifier(job, owner_kind), "JOB_LEASE_NOT_HELD")
        identity = dict(self.adapter.identity())
        with self._lock:
            _require(not (set(sites) & self._sealed), "SITE_SEALED")
            _require(not (set(sites) & self._site_owners.keys()), "SITE_BUSY")
            if package:
                _require(not any(
                    other.owner_kind == OWNER_PACKAGE
                    and other.pgid == request["pgid"] and other.uid == request["uid"]
                    for other in self._sessions.values()
                ), "PACKAGE_SESSION_ALREADY_ACTIVE")
            s = _Session(secrets.token_hex(16), job, frozenset(sites),
                         request["pgid"] if package else None,
                         request["uid"] if package else None,
                         self.clock() + request["max_runtime_s"], identity,
                         owner_kind=owner_kind, runtime_pid=pid)
            self._sessions[s.session_id] = s
            for site in sites:
                self._site_owners[site] = s.session_id
        return {"session_id": s.session_id, "epoch": self.epoch, "sites": sorted(s.sites),
                "owner_kind": owner_kind}

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
            matches = [
                candidate for candidate in self._sessions.values()
                if not candidate.closed and candidate.owner_kind == OWNER_PACKAGE
                and pgid == candidate.pgid and uid == candidate.uid
            ]
            _require(len(matches) == 1, "NO_SESSION_FOR_PEER")
            s = matches[0]
        return self._execute(s, site, op)

    def _execute(self, s: _Session, site: int, op: str) -> dict[str, Any]:
        _require(op in self.adapter.operations, "OPERATION_DENIED")
        with self._lock:
            _require(not s.closed, "SESSION_CLOSED")
            _require(self.clock() < s.expires, "SESSION_EXPIRED")
            _require(site in s.sites, "SITE_NOT_AUTHORIZED")
            _require(site not in self._sealed, "SITE_SEALED")
            if op == "flash_cycle":
                _require(s.image is not None, "IMAGE_NOT_BOUND")
        _require(self.lease_verifier(s.job_id, s.owner_kind), "JOB_LEASE_NOT_HELD")
        if dict(self.adapter.identity()) != s.identity:
            with self._lock:
                if self._sessions.get(s.session_id) is s:
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

    def open_job_session(self, *, job_id: str, sites: list[int],
                         max_runtime_s: int) -> dict[str, Any]:
        return self.call("open_job_session", job_id=job_id, sites=sites,
                         max_runtime_s=max_runtime_s)

    def bind_image(
        self, session_id: str, *, profile: Mapping[str, Any], image_sha256: str, image_size: int
    ) -> dict[str, Any]:
        return self.call("bind_image", session_id=session_id, profile=dict(profile),
                         image_sha256=image_sha256, image_size=image_size)

    def run(self, session_id: str, *, site: int, operation: str) -> dict[str, Any]:
        return self.call("run", session_id=session_id, site=site, operation=operation)


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


def runtime_lease_verifier(control_socket: Path,
                           timeout_s: float = 5.0) -> Callable[[str, str], bool]:
    """Ask the Runtime (C-1 SiteManager) whether job_id holds the PPU execution lease.

    ``package_action``: the lease owner is exactly that Package Action Job.
    ``rest_job``: a Runtime Site Job (REST, batch or client owner) that is one
    of the lease's active Jobs; a Package Action lease never qualifies.
    """
    def verify(job_id: str, owner_kind: str) -> bool:
        lease = runtime_lease_snapshot(control_socket, timeout_s)
        if not (isinstance(lease, dict) and lease.get("busy") is True):
            return False
        if owner_kind == OWNER_PACKAGE:
            return lease.get("owner_kind") == OWNER_PACKAGE and lease.get("owner_id") == job_id
        jobs = lease.get("job_ids")
        return (owner_kind == OWNER_REST_JOB and lease.get("owner_kind") != OWNER_PACKAGE
                and isinstance(jobs, list) and job_id in jobs)
    return verify
