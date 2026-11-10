#!/usr/bin/env python3
"""PPU controller authority: local enrollment, Recovery-Gated Takeover, admission.

LOM-P2A-2 implementation of ``plasma.ppu.local-enrollment.v1``
(docs/development/opf-local-owner-mode-p2a0-enrollment-spec.md, ADR-0008).
Stdlib only; PYNQ Python 3.10. Runs inside the root Bootstrap service and the
root ``ppu-enroll.py`` CLI. Nothing here touches FPGA, DUT, Site power or the
boot partition except ``EnrollmentEngine.boot_consume`` (boot-time unit only).

* ONE controller record (credential, generation, mode) replaced atomically;
  ``ledger.high_water`` detects a restored older record (FAULT).
* ONE enrollment engine for three arming entries: PS-GPIO button (bound to a
  single Control Station request), Engineering CLI (root + root-owned
  Engineering Mode policy) and the SD boot-partition ticket (rescue).
* Recovery-Gated Takeover (owner decision B3 (b)) evaluated under the
  exclusive transition fence; every admission (Bootstrap mutation and Gateway
  write via the admission socket) holds the fence shared, so no write is
  admitted between evaluation and commit.
* The P2A-1 request MAC (``ppu_bootstrap_request_auth.py``) is the only
  request authentication; this module only supplies its credential.

Takeover never cancels, re-sends, clears or rewrites Jobs, deployments,
journals, seals, Active Set, Boot IDs, leases or recovery evidence.
"""
from __future__ import annotations

import fcntl
import grp
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterator, Mapping, Protocol


def _sibling(name: str, module_name: str) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(name))
    if spec is None or spec.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


proto = _sibling("ppu_local_enrollment.py", "plasma_ppu_local_enrollment")
request_auth = _sibling("ppu_bootstrap_request_auth.py", "plasma_ppu_bootstrap_request_auth")

SCHEMA = proto.SCHEMA
MODE_NORMAL = proto.MODE_NORMAL
MODE_RECOVERY_ONLY = proto.MODE_RECOVERY_ONLY
CONTROLLER_RECORD_SCHEMA = "plasma.ppu.controller-record.v1"
ENGINEERING_POLICY_SCHEMA = "plasma.ppu.engineering-mode.v1"
BUTTON_PROFILE_SCHEMA = "plasma.ppu.enrollment-button-profile.v1"
ADMISSION_SCHEMA = "plasma.ppu.controller-admission.v1"
LEGACY_TOKEN_FILE = "control-token"
FENCE_WAIT_S = 10.0
MAX_ENROLLMENT_NONCES = 64
MAX_ADMISSION_LINE = 8192
# P0 recovery: bounded in-memory record of G13-admitted Gateway responses
# (hash + identity only, never a credential). Lost on restart by design.
GATEWAY_RECEIPT_CAPACITY = 32

# Spec-frozen error codes plus the P2A-2 entries (button/engineering/admission).
SPEC_ERROR_CODES = frozenset({
    "ENROLLMENT_NOT_ARMED", "ENROLLMENT_EXPIRED", "ENROLLMENT_NONCE_INVALID",
    "ENROLLMENT_PROOF_INVALID", "ENROLLMENT_LOCKED_OUT", "ENROLLMENT_TICKET_INVALID",
    "ENROLLMENT_TICKET_REPLAYED", "ENROLLMENT_TICKET_CONSUMED", "ENROLLMENT_TICKET_NOT_CONSUMED",
    "ENROLLMENT_LEDGER_FULL", "TAKEOVER_DEFERRED_ACTIVE_OPERATION", "CONTROLLER_NOT_ENROLLED",
    "CONTROLLER_REVOKED", "CONTROLLER_RECOVERY_ONLY", "CONTROLLER_STATE_ROLLBACK",
    "RECOVERY_BLOCKED", "RECOVERY_ACTION_NOT_REQUESTED",
    "ENROLLMENT_BUTTON_DISABLED", "ENROLLMENT_CONTENDED", "ENROLLMENT_BUSY",
    "ENGINEERING_MODE_NOT_AUTHORIZED", "CONTROLLER_STATE_INVALID",
    "CONTROLLER_OPERATION_UNCLASSIFIED", "CONTROLLER_TRANSITION_IN_PROGRESS",
    "CONTROLLER_UNAUTHENTICATED",
})
HTTP_STATUS = {
    "ENROLLMENT_NOT_ARMED": 409, "ENROLLMENT_EXPIRED": 409, "ENROLLMENT_NONCE_INVALID": 401,
    "ENROLLMENT_PROOF_INVALID": 401, "ENROLLMENT_LOCKED_OUT": 401,
    "ENROLLMENT_TICKET_CONSUMED": 409, "ENROLLMENT_BUTTON_DISABLED": 409,
    "ENROLLMENT_CONTENDED": 409, "ENROLLMENT_BUSY": 409,
    "TAKEOVER_DEFERRED_ACTIVE_OPERATION": 409, "CONTROLLER_NOT_ENROLLED": 503,
    "CONTROLLER_REVOKED": 401, "CONTROLLER_UNAUTHENTICATED": 401,
    "CONTROLLER_RECOVERY_ONLY": 403, "CONTROLLER_STATE_ROLLBACK": 503,
    "CONTROLLER_STATE_INVALID": 503, "CONTROLLER_OPERATION_UNCLASSIFIED": 403,
    "CONTROLLER_TRANSITION_IN_PROGRESS": 503, "RECOVERY_BLOCKED": 409,
    "RECOVERY_ACTION_NOT_REQUESTED": 400, "ENGINEERING_MODE_NOT_AUTHORIZED": 403,
}

# Normal writes: denied in RECOVERY_ONLY. ``ppu.settings.write``,
# ``site.job.cancel`` and ``engineering.write`` are the Gateway classes added
# by the G13 inventory (docs/development/opf-local-owner-mode-p2a2-gate1-20261109.md).
NORMAL_WRITES = frozenset({
    "bundle.upload", "bundle.admit", "bundle.install", "runtime.deploy",
    "fpga.load", "site.job.submit", "site.settings.write", "site.activation",
    "site.job.cancel", "ppu.settings.write", "engineering.write",
})
RECOVERY_ACTIONS = frozenset({
    "status.read", "site.diagnose", "site.recover", "outcome.reconcile",
    "recovery.complete", "deployment.reconcile",
})
RECONCILIATION_DECISIONS = frozenset({
    "CONFIRMED_NOT_EXECUTED", "CONFIRMED_EXECUTED_VERIFIED", "CONFIRMED_FAILED",
})
CRASH_POINTS = (
    "boot.after_ledger_append", "boot.after_ticket_delete", "boot.after_arm",
    "claim.before_controller_commit", "claim.after_controller_commit",
    "claim.after_high_water", "recovery.before_mode_commit",
)
_RECORD_NAMES = ("controller", "ledger", "pending", "reconciliations")
_CREDENTIAL_RE = re.compile(r"[\x21-\x7e]{32,256}\Z")


class ControllerError(Exception):
    def __init__(self, code: str, detail: Any = None) -> None:
        if code not in SPEC_ERROR_CODES:
            raise ValueError(f"unknown controller error code {code}")
        super().__init__(code)
        self.code, self.detail = code, detail

    @property
    def http_status(self) -> int:
        return HTTP_STATUS.get(self.code, 409)

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"ok": False, "error": self.code}
        if self.detail is not None:
            body["detail"] = self.detail
        return body


class Crash(RuntimeError):
    """Fault injection: simulated power loss at a named point (tests only)."""


# --- durable records ----------------------------------------------------------

def atomic_write_json(path: Path, payload: Any, *, mode: int = 0o600) -> None:
    """temp + fsync + rename + directory fsync; the old file stays on failure."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=1, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ControllerStore:
    """Root-private records under the Bootstrap state root (0700 dir, 0600 files)."""

    def __init__(self, state_root: Path) -> None:
        self.root = Path(state_root) / "controller"
        self.legacy_token = Path(state_root) / LEGACY_TOKEN_FILE
        self._thread_lock = threading.RLock()

    def path(self, name: str) -> Path:
        if name not in _RECORD_NAMES:
            raise ValueError(name)
        return self.root / f"{name}.json"

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Cross-process (CLI vs service) and in-process mutual exclusion."""
        with self._thread_lock:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.root / "records.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)

    def get(self, name: str) -> Any:
        path = self.path(name)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ControllerError("CONTROLLER_STATE_INVALID", name) from exc
        with os.fdopen(fd, "rb") as stream:
            meta = os.fstat(stream.fileno())
            if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077 or meta.st_size > 1024 * 1024:
                raise ControllerError("CONTROLLER_STATE_INVALID", name)
            try:
                value = json.loads(stream.read().decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ControllerError("CONTROLLER_STATE_INVALID", name) from exc
        if not isinstance(value, dict):
            raise ControllerError("CONTROLLER_STATE_INVALID", name)
        return value

    def put(self, name: str, value: Mapping[str, Any]) -> None:
        atomic_write_json(self.path(name), dict(value))

    def delete(self, name: str) -> None:
        try:
            os.unlink(self.path(name))
        except FileNotFoundError:
            return
        _fsync_dir(self.root)

    def snapshot(self) -> dict[str, Any]:
        return {name: self.get(name) for name in _RECORD_NAMES if self.path(name).exists()}

    # -- validated views
    def ledger(self) -> dict[str, Any]:
        ledger = self.get("ledger") or {"consumed": [], "high_water": 0}
        if (type(ledger.get("consumed")) is not list or type(ledger.get("high_water")) is not int
                or not all(type(x) is str and proto.HEX32_RE.fullmatch(x) for x in ledger["consumed"])):
            raise ControllerError("CONTROLLER_STATE_INVALID", "ledger")
        return ledger

    def controller(self) -> dict[str, Any] | None:
        record = self.get("controller")
        if record is None:
            return None
        if (type(record.get("generation")) is not int or record["generation"] < 1
                or record.get("mode") not in (MODE_NORMAL, MODE_RECOVERY_ONLY)
                or type(record.get("credential")) is not str
                or not _CREDENTIAL_RE.fullmatch(record["credential"])):
            raise ControllerError("CONTROLLER_STATE_INVALID", "controller")
        return record

    def migrate_legacy_token(self) -> bool:
        """P2A-1 ``control-token`` -> controller generation 1, NORMAL, same secret.

        Idempotent and crash-safe: the controller record is committed first;
        the legacy file is removed only once a controller record exists.
        """
        with self.locked():
            if not self.legacy_token.exists():
                return False
            meta = self.legacy_token.lstat()
            if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077:
                raise ControllerError("CONTROLLER_STATE_INVALID", "legacy control-token")
            migrated = False
            if self.get("controller") is None:
                credential = self.legacy_token.read_text(encoding="utf-8").strip()
                if not _CREDENTIAL_RE.fullmatch(credential):
                    raise ControllerError("CONTROLLER_STATE_INVALID", "legacy control-token")
                ledger = self.ledger()
                generation = max(1, ledger["high_water"] + 1 if ledger["high_water"] else 1)
                self.put("controller", {
                    "schema": CONTROLLER_RECORD_SCHEMA, "generation": generation,
                    "credential": credential, "mode": MODE_NORMAL,
                    "controller_id": secrets.token_hex(16), "label": "p2a1-migrated",
                    "last_enrollment": {"source": "p2a1-migration"},
                })
                ledger["high_water"] = max(ledger["high_water"], generation)
                self.put("ledger", ledger)
                migrated = True
            os.unlink(self.legacy_token)
            _fsync_dir(self.legacy_token.parent)
            return migrated


# --- transition fence -------------------------------------------------------------

class TransitionFence:
    """Writer-preferring RW lock. Admissions hold it shared; takeover/recovery
    commit holds it exclusive, so no write is admitted between a takeover
    evaluation and its commit (no TOCTOU)."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._shared = 0
        self._exclusive = False
        self._waiting_exclusive = 0

    def acquire_shared(self, timeout_s: float = FENCE_WAIT_S) -> None:
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while self._exclusive or self._waiting_exclusive:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ControllerError("CONTROLLER_TRANSITION_IN_PROGRESS")
                self._cond.wait(remaining)
            self._shared += 1

    def release_shared(self) -> None:
        with self._cond:
            if self._shared <= 0:
                raise RuntimeError("transition fence shared release without hold")
            self._shared -= 1
            self._cond.notify_all()

    @contextmanager
    def shared(self, timeout_s: float = FENCE_WAIT_S) -> Iterator[None]:
        self.acquire_shared(timeout_s)
        try:
            yield
        finally:
            self.release_shared()

    @contextmanager
    def exclusive(self, timeout_s: float = FENCE_WAIT_S) -> Iterator[None]:
        deadline = time.monotonic() + timeout_s
        with self._cond:
            self._waiting_exclusive += 1
            try:
                while self._exclusive or self._shared:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ControllerError("TAKEOVER_DEFERRED_ACTIVE_OPERATION",
                                              ["write-admission-in-progress"])
                    self._cond.wait(remaining)
                self._exclusive = True
            finally:
                self._waiting_exclusive -= 1
        try:
            yield
        finally:
            with self._cond:
                self._exclusive = False
                self._cond.notify_all()

    def holders(self) -> int:
        with self._cond:
            return self._shared


# --- PPU safety observation (read-only for enrollment) -------------------------

class SafetyProbe(Protocol):
    def active_operations(self) -> list[str]: ...
    def seals(self) -> list[int]: ...
    def unknown_outcomes(self) -> list[str]: ...
    def active_set_recovery_required(self) -> bool: ...
    def extra_blockers(self) -> list[str]: ...
    def diagnose_site(self, site: int) -> dict[str, Any]: ...
    def recover_site(self, site: int, *, operator: str) -> dict[str, Any]: ...


@dataclass
class PPUSafetyProbe:
    """Real PPU observation. Every unknown observation fails toward safety."""

    seal_dir: Path
    runtime_control_socket: Path
    reload_fence: Path
    bootstrap_active: Callable[[], list[str]]
    bootstrap_unknown: Callable[[], list[str]]
    bootstrap_recovery_required: Callable[[], bool]
    site_recovery_script: Path | None = None
    timeout_s: float = 5.0

    def _runtime_lease(self) -> str:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_s)
                sock.connect(str(self.runtime_control_socket))
                sock.sendall(b'{"operation":"execution_lease"}\n')
                data = b""
                while not data.endswith(b"\n") and len(data) < 65536:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
        except (FileNotFoundError, ConnectionRefusedError):
            return "runtime_down"
        except OSError:
            return "unknown"
        try:
            reply = json.loads(data.decode("utf-8"))
            lease = reply.get("result") if isinstance(reply, dict) and reply.get("ok") else None
        except (UnicodeDecodeError, ValueError):
            return "unknown"
        if not isinstance(lease, dict) or type(lease.get("busy")) is not bool:
            return "unknown"
        return "busy" if lease["busy"] else "idle"

    def _reload_fence_held(self) -> bool | None:
        try:
            fd = os.open(self.reload_fence, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return False
        except OSError:
            return None
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)  # never blocks a loader
        except BlockingIOError:
            return True
        except OSError:
            return None
        finally:
            os.close(fd)
        return False

    def active_operations(self) -> list[str]:
        ops = list(self.bootstrap_active())
        if self._runtime_lease() == "busy":
            ops.append("site-job:runtime-execution-lease")
        if self._reload_fence_held() is True:
            ops.append("fpga:reload-fence")
        return sorted(ops)

    def seals(self) -> list[int]:
        sites = []
        try:
            entries = list(self.seal_dir.glob("site*.sealed"))
        except OSError:
            entries = []
        for path in entries:
            match = re.fullmatch(r"site([1-9][0-9]*)\.sealed", path.name)
            if match:
                sites.append(int(match.group(1)))
        return sorted(sites)

    def unknown_outcomes(self) -> list[str]:
        return sorted(self.bootstrap_unknown())

    def active_set_recovery_required(self) -> bool:
        return bool(self.bootstrap_recovery_required())

    def extra_blockers(self) -> list[str]:
        blockers = []
        if self._runtime_lease() == "unknown":
            blockers.append("SITE_RUNTIME_LEASE_UNKNOWN")
        if self._reload_fence_held() is None:
            blockers.append("FPGA_RELOAD_FENCE_UNKNOWN")
        if self.seal_dir.exists() and not os.access(self.seal_dir, os.R_OK):
            blockers.append("SITE_SEAL_STATE_UNKNOWN")
        return blockers

    def _site_recovery(self, argv: list[str]) -> dict[str, Any]:
        if self.site_recovery_script is None or not self.site_recovery_script.is_file():
            return {"result": "NOT_AVAILABLE", "reason": "site recovery procedure is not installed"}
        completed = subprocess.run([sys.executable, str(self.site_recovery_script), *argv],
                                   capture_output=True, text=True, timeout=120, check=False)
        try:
            report = json.loads(completed.stdout)
        except ValueError:
            report = {"stdout_tail": completed.stdout[-2000:]}
        return {"returncode": completed.returncode, "report": report}

    def diagnose_site(self, site: int) -> dict[str, Any]:
        return self._site_recovery(["diagnose", str(site)])

    def recover_site(self, site: int, *, operator: str) -> dict[str, Any]:
        # The existing Embedded seal procedure; it moves the marker into its
        # evidence directory only after all preconditions incl. SAFE_OFF pass.
        return self._site_recovery(["recover", str(site), "--operator", operator])


# --- Engineering Mode policy and button board profile ------------------------

def _trusted_root_file(path: Path) -> dict[str, Any]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        meta = os.fstat(stream.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o022
                or meta.st_size > 65536):
            raise ValueError("policy file must be a root-owned regular file not writable by others")
        value = json.loads(stream.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("policy must be a JSON object")
    return value


def engineering_mode_authorized(path: Path, *, now_epoch: float | None = None,
                                trusted_reader: Callable[[Path], dict[str, Any]] = _trusted_root_file,
                                ) -> tuple[bool, str]:
    """Trusted device-side Engineering Mode: root-owned policy file, explicit
    ``enrollment_cli: true`` and an unexpired ``expires_at_epoch_s``."""
    try:
        policy = trusted_reader(path)
    except FileNotFoundError:
        return False, "engineering mode policy is not installed"
    except (OSError, ValueError) as exc:
        return False, f"engineering mode policy is untrusted: {exc}"
    if policy.get("schema") != ENGINEERING_POLICY_SCHEMA or policy.get("enrollment_cli") is not True:
        return False, "engineering mode policy does not enable the enrollment CLI"
    expires = policy.get("expires_at_epoch_s")
    if type(expires) not in (int, float) or expires <= (time.time() if now_epoch is None else now_epoch):
        return False, "engineering mode policy is expired or has no expiry"
    return True, "engineering mode authorized"


@dataclass(frozen=True)
class ButtonProfile:
    enabled: bool
    chip_label: str
    line: int
    active_low: bool = True
    debounce_ms: int = 50
    hold_ms: int = 3000
    poll_ms: int = 10
    board: str = ""
    disabled_reason: str = ""

    @classmethod
    def load(cls, path: Path,
             reader: Callable[[Path], dict[str, Any]] = _trusted_root_file) -> "ButtonProfile":
        raw = reader(path)
        allowed = {"schema", "board", "enabled", "disabled_reason", "gpio", "debounce_ms",
                   "hold_ms", "poll_ms", "hardware_notes"}
        gpio = raw.get("gpio")
        if (raw.get("schema") != BUTTON_PROFILE_SCHEMA or set(raw) - allowed
                or type(raw.get("enabled")) is not bool or not isinstance(gpio, dict)
                or set(gpio) != {"chip_label", "line", "active_low"}
                or type(gpio["chip_label"]) is not str or not gpio["chip_label"]
                or type(gpio["line"]) is not int or not 0 <= gpio["line"] < 1024
                or type(gpio["active_low"]) is not bool):
            raise ValueError("enrollment button profile is invalid")
        values = {key: raw.get(key, default) for key, default in
                  (("debounce_ms", 50), ("hold_ms", 3000), ("poll_ms", 10))}
        if (not all(type(v) is int for v in values.values())
                or not 10 <= values["debounce_ms"] <= 500
                or not 1000 <= values["hold_ms"] <= 10000
                or not 2 <= values["poll_ms"] <= values["debounce_ms"]):
            raise ValueError("enrollment button timing is out of range")
        return cls(enabled=raw["enabled"], chip_label=gpio["chip_label"], line=gpio["line"],
                   active_low=gpio["active_low"], board=str(raw.get("board", "")),
                   disabled_reason=str(raw.get("disabled_reason", "")), **values)


class LongPressDetector:
    """Debounced long-press state machine (pure; time is injected).

    A level counts only after it is stable for ``debounce_s``. One event fires
    once the debounced press lasts ``hold_s``; the next event needs a debounced
    release first. A line already active at start (stuck/shorted button or a
    board reset holding the line) must be released before any event.
    """

    def __init__(self, *, debounce_s: float, hold_s: float) -> None:
        self.debounce_s, self.hold_s = debounce_s, hold_s
        self._raw: bool | None = None
        self._raw_since = 0.0
        self._stable: bool | None = None
        self._pressed_since: float | None = None
        self._fired = False
        self._armed = False

    def feed(self, active: bool, now: float) -> bool:
        if self._raw is None or active != self._raw:
            self._raw, self._raw_since = active, now
        if now - self._raw_since >= self.debounce_s and self._stable != self._raw:
            self._stable = self._raw
            if self._stable:
                self._pressed_since, self._fired = self._raw_since, False
            else:
                self._pressed_since, self._fired, self._armed = None, False, True
        if self._stable is False:
            self._armed = True
        # The level must still be active NOW: a release sample inside the
        # debounce interval never completes a hold.
        if (self._armed and self._stable and self._raw and not self._fired
                and self._pressed_since is not None and now - self._pressed_since >= self.hold_s):
            self._fired = True
            return True
        return False


class SysfsGpioInput:
    """Read-only GPIO input via sysfs. The line is forced to and verified as
    ``in``; it is never driven (an output would short the button)."""

    def __init__(self, profile: ButtonProfile, sysfs: Path = Path("/sys/class/gpio")) -> None:
        self.sysfs, self.profile = sysfs, profile
        base = None
        for chip in sorted(sysfs.glob("gpiochip*")):
            try:
                label = (chip / "label").read_text().strip()
                ngpio = int((chip / "ngpio").read_text())
                chip_base = int((chip / "base").read_text())
            except (OSError, ValueError):
                continue
            if label == profile.chip_label and profile.line < ngpio:
                if base is not None:
                    raise RuntimeError("enrollment button GPIO chip label is ambiguous")
                base = chip_base
        if base is None:
            raise RuntimeError("enrollment button GPIO chip is not present")
        self.number = base + profile.line
        self.line_dir = sysfs / f"gpio{self.number}"
        if not self.line_dir.exists():
            (sysfs / "export").write_text(str(self.number))
        (self.line_dir / "direction").write_text("in")
        if (self.line_dir / "direction").read_text().strip() != "in":
            raise RuntimeError("enrollment button GPIO line is not an input")
        self._value = self.line_dir / "value"

    def active(self) -> bool:
        level = self._value.read_text().strip() == "1"
        return (not level) if self.profile.active_low else level


# --- the enrollment engine --------------------------------------------------------

def boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError as exc:
        raise ControllerError("CONTROLLER_STATE_INVALID", "boot id unavailable") from exc
    return value


def boot_clock() -> float:
    return time.clock_gettime(getattr(time, "CLOCK_BOOTTIME", time.CLOCK_MONOTONIC))


@dataclass(frozen=True)
class Admission:
    context: Any
    credential: str
    generation: int
    mode: str
    operation: str


class EnrollmentEngine:
    def __init__(self, store: ControllerStore, probe: SafetyProbe, *, device_id: str,
                 boot_id: str, button_enabled: bool = False,
                 crash_at: str | None = None, fence: TransitionFence | None = None,
                 log: Callable[[str], None] | None = None) -> None:
        if not proto.DEVICE_RE.fullmatch(device_id):
            raise ValueError("device identity is invalid")
        self.store, self.probe, self.device_id, self.boot_id = store, probe, device_id, boot_id
        self.button_enabled, self.crash_at = button_enabled, crash_at
        self.fence = fence or TransitionFence()
        self.fence_wait_s = FENCE_WAIT_S
        self.events: list[str] = []
        self._log = log or (lambda line: None)
        self._nonces: dict[str, tuple[str, float]] = {}
        self._lock = threading.RLock()
        self._button: dict[str, Any] = {"requests": {}, "deadline": None, "contended": False}
        self.request_nonces = request_auth.NonceRegistry()
        self._gateway_receipts: list[dict[str, Any]] = []

    # -- helpers
    def _point(self, name: str) -> None:
        if name not in CRASH_POINTS:
            raise ValueError(name)
        if self.crash_at == name:
            raise Crash(name)

    def _event(self, event: str) -> None:
        self.events.append(event)
        self._log(f"plasma-enrollment event={event}")

    def controller(self) -> dict[str, Any] | None:
        return self.store.controller()

    def controller_state(self) -> str:
        try:
            record = self.store.controller()
            if record is None:
                return "UNENROLLED"
            if record["generation"] < self.store.ledger()["high_water"]:
                return "FAULT"
        except ControllerError:
            return "FAULT"
        return record["mode"]

    def _require_controller(self) -> dict[str, Any]:
        try:
            record = self.store.controller()
            high_water = self.store.ledger()["high_water"]
        except ControllerError:
            raise ControllerError("CONTROLLER_STATE_INVALID") from None
        if record is None:
            raise ControllerError("CONTROLLER_NOT_ENROLLED")
        if record["generation"] < high_water:
            raise ControllerError("CONTROLLER_STATE_ROLLBACK")
        return record

    def _pending(self, now: float) -> dict[str, Any]:
        pending = self.store.get("pending")
        if pending is None:
            raise ControllerError("ENROLLMENT_NOT_ARMED")
        if pending.get("boot_id") != self.boot_id or now >= pending.get("deadline", 0):
            with self.store.locked():
                self.store.delete("pending")
            raise ControllerError("ENROLLMENT_EXPIRED")
        return pending

    def enrollment_state(self, now: float) -> str:
        pending = self.store.get("pending")
        if pending is None:
            return "NONE"
        if pending.get("boot_id") != self.boot_id or now >= pending.get("deadline", 0):
            return "EXPIRED"
        record = self.store.get("controller") or {}
        if record.get("last_enrollment", {}).get("enrollment_id") == pending["enrollment_id"]:
            return "CONSUMED"
        return "ARMED"

    def _arm(self, enrollment_id: str, key: bytes, now: float, *, source: str,
             extra: Mapping[str, Any] | None = None) -> None:
        if source not in proto.SOURCES:
            raise ValueError(source)
        record = {"enrollment_id": enrollment_id, "key": key.hex(), "boot_id": self.boot_id,
                  "deadline": now + proto.ENROLLMENT_WINDOW_S, "failures": 0, "source": source}
        record.update(extra or {})
        self.store.put("pending", record)
        self._event("ENROLLMENT_ARMED:" + source)

    def _window_open(self, now: float) -> bool:
        pending = self.store.get("pending")
        return (pending is not None and pending.get("boot_id") == self.boot_id
                and now < pending.get("deadline", 0)
                and self.enrollment_state(now) == "ARMED")

    # -- entry 3: SD boot-partition ticket (boot-time unit only)
    def boot_consume(self, boot_partition: "BootPartition", now: float) -> None:
        with self.store.locked():
            pending = self.store.get("pending")
            if pending is not None and pending.get("boot_id") != self.boot_id:
                self.store.delete("pending")         # a reboot always ends a window
            raw = boot_partition.read()
            if raw is None:
                return
            try:
                ticket = proto.parse_ticket_file(raw)
            except proto.EnrollmentProtocolError:
                boot_partition.delete()
                self._event("ENROLLMENT_TICKET_INVALID")
                return
            tid = proto.ticket_id(ticket)
            ledger = self.store.ledger()
            if tid in ledger["consumed"]:
                boot_partition.delete()
                self._event("ENROLLMENT_TICKET_REPLAYED")
                return
            if len(ledger["consumed"]) >= proto.LEDGER_CAPACITY:
                boot_partition.delete()
                self._event("ENROLLMENT_LEDGER_FULL")
                return
            ledger["consumed"].append(tid)          # durable BEFORE the file can disappear
            self.store.put("ledger", ledger)
            self._point("boot.after_ledger_append")
            try:
                boot_partition.delete()
            except OSError:
                self._event("ENROLLMENT_TICKET_NOT_CONSUMED")
                return                               # not armed; next boot sees a replay
            self._point("boot.after_ticket_delete")
            self._arm(tid, proto.ticket_key(ticket), now, source=proto.SOURCE_SD)
            self._point("boot.after_arm")

    # -- entry 2: Engineering CLI (root + trusted Engineering Mode policy)
    def engineering_arm(self, now: float, *, authorized: bool) -> str:
        if not authorized:
            raise ControllerError("ENGINEERING_MODE_NOT_AUTHORIZED")
        with self.store.locked():
            if self._window_open(now):
                raise ControllerError("ENROLLMENT_BUSY", "an enrollment window is already armed")
            ledger = self.store.ledger()
            if len(ledger["consumed"]) >= proto.LEDGER_CAPACITY:
                raise ControllerError("ENROLLMENT_LEDGER_FULL")
            ticket = secrets.token_hex(32)
            tid = proto.ticket_id(ticket)
            ledger["consumed"].append(tid)
            self.store.put("ledger", ledger)
            self._arm(tid, proto.ticket_key(ticket), now, source=proto.SOURCE_ENGINEERING)
        with self._lock:
            self._button = {"requests": {}, "deadline": None, "contended": False}
        return ticket

    # -- entry 1: PS-GPIO button bound to exactly one Control Station request
    def _button_expire(self, now: float) -> None:
        deadline = self._button["deadline"]
        if deadline is not None and now >= deadline:
            self._button = {"requests": {}, "deadline": None, "contended": False}

    def button_request(self, body: Mapping[str, Any], now: float) -> dict[str, Any]:
        if not self.button_enabled:
            raise ControllerError("ENROLLMENT_BUTTON_DISABLED")
        if not isinstance(body, Mapping) or set(body) - {"controller_public", "label"}:
            raise ControllerError("ENROLLMENT_PROOF_INVALID")
        try:
            public = proto.valid_public_key(body.get("controller_public"))
        except proto.EnrollmentProtocolError:
            raise ControllerError("ENROLLMENT_PROOF_INVALID") from None
        label = body.get("label", "")
        if type(label) is not str or len(label) > proto.MAX_LABEL_CHARS:
            raise ControllerError("ENROLLMENT_PROOF_INVALID")
        with self._lock:
            if self._window_open(now):
                raise ControllerError("ENROLLMENT_BUSY", "an enrollment window is already armed")
            self._button_expire(now)
            if self._button["contended"]:
                raise ControllerError("ENROLLMENT_CONTENDED", {
                    "retry_after_s": max(0, int(self._button["deadline"] - now))})
            requests = self._button["requests"]
            for request_id, existing in requests.items():
                if existing["controller_public"] == public:
                    return self._button_view(request_id, now)
            if requests:
                # A second station inside the window: nobody can be bound. Fail
                # closed for the rest of the window rather than pick a winner.
                self._button["requests"] = {}
                self._button["contended"] = True
                self._event("ENROLLMENT_CONTENDED")
                raise ControllerError("ENROLLMENT_CONTENDED", {
                    "retry_after_s": max(0, int(self._button["deadline"] - now))})
            request_id = secrets.token_hex(16)
            requests[request_id] = {"controller_public": public, "label": label}
            self._button["deadline"] = now + proto.BUTTON_REQUEST_WINDOW_S
            self._event("ENROLLMENT_BUTTON_REQUESTED")
            return self._button_view(request_id, now)

    def _button_view(self, request_id: str, now: float) -> dict[str, Any]:
        return {"schema": SCHEMA, "device_id": self.device_id, "request_id": request_id,
                "state": "AWAITING_BUTTON",
                "expires_in_s": max(0, int(self._button["deadline"] - now))}

    def button_pressed(self, now: float) -> str:
        with self._lock, self.store.locked():
            self._button_expire(now)
            if not self.button_enabled:
                outcome = "BUTTON_PRESS_IGNORED_DISABLED"
            elif self._window_open(now):
                outcome = "BUTTON_PRESS_IGNORED_BUSY"
            elif self._button["contended"]:
                outcome = "BUTTON_PRESS_REFUSED_CONTENDED"
            elif len(self._button["requests"]) != 1:
                outcome = "BUTTON_PRESS_IGNORED_NO_REQUEST"
            else:
                (request_id, request), = self._button["requests"].items()
                private, ppu_public = proto.x25519_keypair()
                key = proto.button_key(private, peer_public=request["controller_public"],
                                       device_id=self.device_id, request_id=request_id,
                                       controller_public=request["controller_public"],
                                       ppu_public=ppu_public)
                self._arm(request_id, key, now, source=proto.SOURCE_BUTTON, extra={
                    "controller_public": request["controller_public"], "ppu_public": ppu_public})
                self._button = {"requests": {}, "deadline": None, "contended": False}
                return "ENROLLMENT_ARMED:" + proto.SOURCE_BUTTON
        self._event(outcome)
        return outcome

    # -- enrollment exchange (LAN-reachable, inert unless ARMED)
    def challenge(self, now: float) -> dict[str, Any]:
        pending = self._pending(now)
        nonce = secrets.token_hex(16)
        with self._lock:
            for key in [k for k, (_e, deadline) in self._nonces.items() if deadline <= now]:
                del self._nonces[key]
            while len(self._nonces) >= MAX_ENROLLMENT_NONCES:
                del self._nonces[next(iter(self._nonces))]
            self._nonces[nonce] = (pending["enrollment_id"], now + 60.0)
        record = self.store.get("controller")
        view = {"schema": SCHEMA, "device_id": self.device_id,
                "enrollment_id": pending["enrollment_id"], "nonce": nonce,
                "current_generation": record["generation"] if record else 0,
                "source": pending["source"]}
        if pending["source"] == proto.SOURCE_BUTTON:
            view["ppu_public"] = pending["ppu_public"]
            view["controller_public"] = pending["controller_public"]
        return view

    def claim(self, request: Mapping[str, Any], now: float) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise ControllerError("ENROLLMENT_PROOF_INVALID")
        pending = self._pending(now)
        if request.get("enrollment_id") != pending["enrollment_id"]:
            raise ControllerError("ENROLLMENT_PROOF_INVALID")
        nonce = request.get("nonce")
        with self._lock:
            issued = self._nonces.pop(nonce, None) if type(nonce) is str else None
        if issued is None or issued[0] != pending["enrollment_id"] or now >= issued[1]:
            raise ControllerError("ENROLLMENT_NONCE_INVALID")
        cn, label = request.get("controller_nonce"), request.get("label", "")
        if (type(cn) is not str or not proto.HEX32_RE.fullmatch(cn) or type(label) is not str
                or len(label) > proto.MAX_LABEL_CHARS or type(request.get("mac")) is not str):
            raise ControllerError("ENROLLMENT_PROOF_INVALID")
        key = bytes.fromhex(pending["key"])
        with self.fence.exclusive(self.fence_wait_s):
            with self.store.locked():
                return self._claim_locked(pending, key, nonce, cn, label, request["mac"], now)

    def _claim_locked(self, pending: dict[str, Any], key: bytes, nonce: str, cn: str, label: str,
                      mac: str, now: float) -> dict[str, Any]:
        current_pending = self.store.get("pending")
        if (current_pending is None or current_pending.get("enrollment_id") != pending["enrollment_id"]
                or current_pending.get("boot_id") != self.boot_id):
            # Locked out, expired or replaced while this claim waited for the fence.
            raise ControllerError("ENROLLMENT_NOT_ARMED")
        pending = current_pending
        record = self.store.get("controller")
        current = record["generation"] if record else 0
        expected = proto.claim_mac(key, device_id=self.device_id,
                                   enrollment_id=pending["enrollment_id"], nonce=nonce,
                                   controller_nonce=cn, current_generation=current, label=label)
        last = (record or {}).get("last_enrollment", {})
        if last.get("enrollment_id") == pending["enrollment_id"]:
            # Lost-response retrieval: same controller only, no new generation.
            if not hmac.compare_digest(expected, mac) or cn != last.get("controller_nonce"):
                raise ControllerError("ENROLLMENT_TICKET_CONSUMED")
            return dict(last["response"])
        if not hmac.compare_digest(expected, mac):
            pending["failures"] = int(pending.get("failures", 0)) + 1
            if pending["failures"] >= proto.MAX_CLAIM_FAILURES:
                self.store.delete("pending")
                self._event("ENROLLMENT_LOCKED_OUT")
                raise ControllerError("ENROLLMENT_LOCKED_OUT")
            self.store.put("pending", pending)
            raise ControllerError("ENROLLMENT_PROOF_INVALID")
        if self.controller_state() == "FAULT":
            raise ControllerError("CONTROLLER_STATE_ROLLBACK")
        # Recovery-Gated Takeover (B3 (b)) under the exclusive transition fence.
        active = self.probe.active_operations()
        if active:
            self._event("TAKEOVER_DEFERRED_ACTIVE_OPERATION")
            raise ControllerError("TAKEOVER_DEFERRED_ACTIVE_OPERATION", active)
        blockers = self.unresolved()
        mode = MODE_RECOVERY_ONLY if blockers else MODE_NORMAL
        generation = max(current, self.store.ledger()["high_water"]) + 1
        credential = secrets.token_hex(32)
        controller_id = secrets.token_hex(16)
        response = {"schema": SCHEMA, "device_id": self.device_id, "generation": generation,
                    "mode": mode, "recovery_blockers": blockers, "wrap_nonce": nonce,
                    "controller_id": controller_id, "source": pending["source"],
                    "wrapped_credential": proto.wrap_credential(
                        key, nonce=nonce, controller_nonce=cn, generation=generation,
                        credential=credential)}
        self._point("claim.before_controller_commit")
        # ONE atomic record: credential, generation, mode and the retrievable
        # response. Every previous credential is invalid from this rename on.
        self.store.put("controller", {
            "schema": CONTROLLER_RECORD_SCHEMA, "generation": generation,
            "credential": credential, "mode": mode, "controller_id": controller_id,
            "label": label,
            "last_enrollment": {"enrollment_id": pending["enrollment_id"],
                                "controller_nonce": cn, "response": response,
                                "source": pending["source"]},
        })
        self._point("claim.after_controller_commit")
        ledger = self.store.ledger()
        ledger["high_water"] = max(ledger["high_water"], generation)
        self.store.put("ledger", ledger)
        self._point("claim.after_high_water")
        self._event(f"CONTROLLER_COMMITTED:generation={generation}:mode={mode}")
        return response

    # -- safety evaluation (read-only)
    def _reconciliations(self) -> dict[str, Any]:
        return self.store.get("reconciliations") or {}

    def unresolved(self) -> list[str]:
        blockers = [f"site{site}.sealed" for site in self.probe.seals()]
        reconciled = self._reconciliations()
        blockers += sorted("OUTCOME_UNKNOWN:" + txn for txn in self.probe.unknown_outcomes()
                           if txn not in reconciled)
        if self.probe.active_set_recovery_required():
            blockers.append("ACTIVE_SET_RECOVERY_REQUIRED")
        blockers += self.probe.extra_blockers()
        return blockers

    # -- authorization of every PPU request (Bootstrap and Gateway)
    def authorize(self, credential: str, operation: str) -> str:
        record = self._require_controller()
        if type(credential) is not str or not hmac.compare_digest(record["credential"], credential):
            raise ControllerError("CONTROLLER_REVOKED", {"current_generation": record["generation"]})
        return self._mode_allows(record, operation)

    def _mode_allows(self, record: Mapping[str, Any], operation: str) -> str:
        if operation not in NORMAL_WRITES | RECOVERY_ACTIONS:
            raise ControllerError("CONTROLLER_OPERATION_UNCLASSIFIED", operation)
        if record["mode"] == MODE_RECOVERY_ONLY and operation in NORMAL_WRITES:
            raise ControllerError("CONTROLLER_RECOVERY_ONLY", self.unresolved())
        return record["mode"]

    def auth_challenge(self) -> dict[str, Any]:
        """P2A-1 challenge plus the current controller generation (not a secret)."""
        record = None
        try:
            record = self.store.controller()
        except ControllerError:
            pass
        return {"ok": True, "schema": request_auth.SCHEMA, "device_id": self.device_id,
                "nonce": self.request_nonces.issue(), "expires_in_s": request_auth.NONCE_TTL_S,
                "controller_generation": record["generation"] if record else 0}

    def admit_header(self, header: object) -> Any:
        record = self._require_controller()
        try:
            return request_auth.admit_request_header(
                header=header, device_id=self.device_id, nonces=self.request_nonces)
        except request_auth.RequestAuthError:
            raise ControllerError("CONTROLLER_UNAUTHENTICATED",
                                  {"controller_generation": record["generation"]}) from None

    def verify_admitted(self, admitted: Any, *, method: str, target: str, operation: str,
                        body: bytes | None = None, body_sha256: str | None = None) -> Admission:
        """Caller MUST hold ``self.fence`` shared from here until the operation is
        admitted. The record is re-read: no session or cache survives a takeover."""
        record = self._require_controller()
        try:
            context = request_auth.verify_request(
                credential=record["credential"], admitted=admitted, method=method,
                path=target, body=body, body_sha256=body_sha256)
        except request_auth.RequestAuthError:
            raise ControllerError("CONTROLLER_UNAUTHENTICATED",
                                  {"controller_generation": record["generation"]}) from None
        mode = self._mode_allows(record, operation)
        return Admission(context, record["credential"], record["generation"], mode, operation)

    # -- G13 Gateway receipts (P0 Runtime reconciliation evidence) ------------
    def record_gateway_receipt(self, admission: Admission, *, status: int,
                               body_sha256: str) -> None:
        """Remember that THIS PPU admitted and MACed one Gateway response.

        Observation only: the Bootstrap never signs a Gateway write itself. The
        record holds method/target/status/body digest/generation, no secret.
        """
        receipt = {
            "method": admission.context.method, "target": admission.context.path,
            "operation": admission.operation, "status": status,
            "body_sha256": body_sha256, "generation": admission.generation,
            "recorded_at_epoch_s": time.time(), "recorded_monotonic_s": time.monotonic(),
        }
        with self._lock:
            self._gateway_receipts.append(receipt)
            del self._gateway_receipts[:-GATEWAY_RECEIPT_CAPACITY]

    def find_gateway_receipt(self, *, method: str, target: str, status: int, body_sha256: str,
                             generation: int, not_before_epoch_s: float,
                             max_age_s: float, consume: bool = False) -> dict[str, Any] | None:
        """Newest matching receipt that is fresh and newer than ``not_before``."""
        now = time.monotonic()
        with self._lock:
            for index in range(len(self._gateway_receipts) - 1, -1, -1):
                item = self._gateway_receipts[index]
                if (item["method"] == method and item["target"] == target
                        and item["status"] == status and item["body_sha256"] == body_sha256
                        and item["generation"] == generation
                        and item["recorded_at_epoch_s"] >= not_before_epoch_s
                        and 0 <= now - item["recorded_monotonic_s"] <= max_age_s):
                    if consume:
                        del self._gateway_receipts[index]
                    return dict(item)
        return None

    # -- explicit recovery actions (§7)
    def recover_site(self, credential: str, site: int, *, explicit_request: bool,
                     operator: str = "controller") -> dict[str, Any]:
        self.authorize(credential, "site.recover")
        if not explicit_request:
            raise ControllerError("RECOVERY_ACTION_NOT_REQUESTED")
        with self.fence.shared():
            self.authorize(credential, "site.recover")
            return self.probe.recover_site(site, operator=operator)

    def diagnose_site(self, credential: str, site: int, *, explicit_request: bool) -> dict[str, Any]:
        self.authorize(credential, "site.diagnose")
        if not explicit_request:
            raise ControllerError("RECOVERY_ACTION_NOT_REQUESTED")
        return self.probe.diagnose_site(site)

    def reconcile(self, credential: str, txn: str, decision: str, evidence: str, *,
                  explicit_request: bool) -> dict[str, Any]:
        record = self.store.controller()
        self.authorize(credential, "outcome.reconcile")
        if not explicit_request:
            raise ControllerError("RECOVERY_ACTION_NOT_REQUESTED")
        if (decision not in RECONCILIATION_DECISIONS or type(evidence) is not str
                or not evidence.strip() or len(evidence) > 2000):
            raise ValueError("reconciliation needs an explicit decision and evidence")
        if txn not in self.probe.unknown_outcomes():
            raise ValueError("no unreconciled OUTCOME_UNKNOWN with this identity")
        with self.fence.shared(), self.store.locked():
            self.authorize(credential, "outcome.reconcile")
            reconciliations = self._reconciliations()
            if txn in reconciliations:
                raise ValueError("outcome is already reconciled; decisions are append-only")
            # Appended decision; the original outcome stays OUTCOME_UNKNOWN.
            reconciliations[txn] = {"decision": decision, "evidence": evidence,
                                    "generation": record["generation"] if record else None,
                                    "recorded_at_epoch_s": time.time()}
            self.store.put("reconciliations", reconciliations)
        return reconciliations[txn]

    def recovery_complete(self, credential: str, *, observed_device_id: str) -> str:
        self.authorize(credential, "recovery.complete")
        with self.fence.exclusive(self.fence_wait_s):
            with self.store.locked():
                self.authorize(credential, "recovery.complete")   # re-check under the fence
                record = self._require_controller()
                if record["mode"] == MODE_NORMAL:
                    return MODE_NORMAL
                blockers = self.probe.active_operations() + self.unresolved()
                if observed_device_id != self.device_id:
                    blockers.append("DEVICE_IDENTITY_MISMATCH")
                if blockers:
                    raise ControllerError("RECOVERY_BLOCKED", blockers)
                record["mode"] = MODE_NORMAL
                self._point("recovery.before_mode_commit")
                self.store.put("controller", record)
                self._event(f"CONTROLLER_RECOVERY_COMPLETE:generation={record['generation']}")
                return MODE_NORMAL

    def public_status(self, now: float) -> dict[str, Any]:
        state = self.controller_state()
        record = None
        try:
            record = self.store.controller()
        except ControllerError:
            pass
        pending = self.store.get("pending") if state != "FAULT" else None
        return {
            "schema": SCHEMA, "controller_state": state,
            "controller_generation": record["generation"] if record else 0,
            "controller_mode": record["mode"] if record else None,
            "enrollment_state": self.enrollment_state(now),
            "enrollment_source": pending.get("source") if pending else None,
            "button_entry": "enabled" if self.button_enabled else "disabled",
        }


class BootPartition:
    """The SD boot-partition ticket file (boot-time consumer only)."""

    def __init__(self, directory: Path) -> None:
        self.path = Path(directory) / proto.TICKET_FILE

    def read(self) -> bytes | None:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            return stream.read(proto.MAX_TICKET_FILE_BYTES + 1)

    def delete(self) -> None:
        os.unlink(self.path)
        _fsync_dir(self.path.parent)


# --- button watcher thread ------------------------------------------------------------

class ButtonWatcher(threading.Thread):
    def __init__(self, engine: EnrollmentEngine, line: Any, profile: ButtonProfile,
                 *, clock: Callable[[], float] = boot_clock,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        super().__init__(name="plasma-enrollment-button", daemon=True)
        self.engine, self.line, self.profile = engine, line, profile
        self.clock, self.sleep = clock, sleep
        self.detector = LongPressDetector(debounce_s=profile.debounce_ms / 1000.0,
                                          hold_s=profile.hold_ms / 1000.0)
        self.stopped = threading.Event()

    def poll_once(self) -> str | None:
        now = self.clock()
        if self.detector.feed(self.line.active(), now):
            return self.engine.button_pressed(now)
        return None

    def run(self) -> None:
        while not self.stopped.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # a GPIO read failure disables the entry, never arms
                self.engine._event(f"BUTTON_WATCHER_FAILED:{type(exc).__name__}")
                return
            self.sleep(self.profile.poll_ms / 1000.0)


# --- Gateway admission service (Unix socket, Bootstrap process) -------------------------

class _AdmissionHandler(socketserver.StreamRequestHandler):
    def _send(self, payload: Mapping[str, Any]) -> None:
        self.wfile.write(json.dumps(payload, sort_keys=True).encode() + b"\n")
        self.wfile.flush()

    def handle(self) -> None:
        engine: EnrollmentEngine = self.server.engine  # type: ignore[attr-defined]
        admitted_header = admission = None
        holding = False
        try:
            while True:
                line = self.rfile.readline(MAX_ADMISSION_LINE + 1)
                if not line or len(line) > MAX_ADMISSION_LINE:
                    return
                try:
                    message = json.loads(line)
                except ValueError:
                    return
                op = message.get("op") if isinstance(message, dict) else None
                try:
                    if op == "challenge":
                        self._send(engine.auth_challenge())
                    elif op == "admit_header" and admitted_header is None:
                        admitted_header = engine.admit_header(message.get("authorization"))
                        self._send({"ok": True})
                    elif op == "admit" and admitted_header is not None and admission is None:
                        engine.fence.acquire_shared()
                        holding = True
                        admission = engine.verify_admitted(
                            admitted_header, method=str(message.get("method")),
                            target=str(message.get("target")),
                            operation=str(message.get("operation")),
                            body_sha256=message.get("body_sha256"))
                        self._send({"ok": True, "generation": admission.generation,
                                    "mode": admission.mode})
                    elif op == "sign_response" and admission is not None:
                        body_sha = message.get("body_sha256")
                        status = message.get("status")
                        if (type(body_sha) is not str or not proto.HEX64_RE.fullmatch(body_sha)
                                or type(status) is not int):
                            return
                        mac = hmac.new(
                            request_auth._key(admission.credential, "response-key"),
                            request_auth._response_message(admission.context, status, body_sha),
                            hashlib.sha256).hexdigest()
                        engine.record_gateway_receipt(admission, status=status,
                                                      body_sha256=body_sha)
                        self._send({"ok": True, "header": f"v1 mac={mac}"})
                    else:
                        return
                except ControllerError as exc:
                    self._send({**exc.payload(), "status": exc.http_status})
                    return
        finally:
            if holding:
                engine.fence.release_shared()  # connection close ends the admission hold


class AdmissionServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, path: Path, engine: EnrollmentEngine, *, group: str | None = "plasma") -> None:
        self.engine = engine
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        super().__init__(str(path), _AdmissionHandler)
        gid = -1
        if group is not None:
            try:
                gid = grp.getgrnam(group).gr_gid
            except KeyError:
                gid = -1
        if gid >= 0 and os.geteuid() == 0:
            os.chown(path, 0, gid)
        os.chmod(path, 0o660 if gid >= 0 else 0o600)
