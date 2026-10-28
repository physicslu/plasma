"""Host-only PS-local durable SWD Site uncertainty journal (Gate 1R candidate).

No hardware/Root credentials, recovery approval, or OpenOCD C binding exists
here. This component is NOT a deployed write admission authority. A missing,
corrupt, stale or uncertain record always denies the next candidate write.

The trusted PS Root/owner must eventually provision a verified READY record
and enforce this gate on *every* real Native C FIFO PUSH. That privileged
integration is deliberately outside this Host-only Gate 1R increment.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Callable, Iterator, TypeVar


T = TypeVar("T")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_SCHEMA = 1
_MAX_BYTES = 4096


class SiteRecoveryBlocked(RuntimeError):
    """Fail-closed until external trusted PS-local recovery decision."""


@dataclass(frozen=True)
class SiteRecoveryIdentity:
    site_id: int
    boot_id: str
    image_sha256: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        if type(self.site_id) is not int or not 1 <= self.site_id <= 8:
            raise ValueError("One-based logical Site identity 1..8 required")
        if type(self.boot_id) is not str or not _ID.fullmatch(self.boot_id):
            raise ValueError("Exact current Boot identity required")
        for item in (self.image_sha256, self.manifest_sha256):
            if type(item) is not str or not _SHA.fullmatch(item):
                raise ValueError("Exact lowercase SHA-256 required")


def _canonical(data: dict[str, object]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def _checksum(data: dict[str, object]) -> str:
    # Corruption detection only; NOT an authenticity signature.
    return hashlib.sha256(_canonical(data)).hexdigest()


def _verified_record(raw: bytes, identity: SiteRecoveryIdentity) -> dict:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        out: dict = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = value
        return out

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {
        "schema", "state", "identity", "generation", "operation_id", "checksum"
    }:
        raise ValueError("Unknown journal shape")
    payload = {key: v for key, v in value.items() if key != "checksum"}
    if value["checksum"] != _checksum(payload):
        raise ValueError("Journal checksum mismatch")
    if type(value["schema"]) is not int or value["schema"] != _SCHEMA:
        raise ValueError("Unknown journal schema")
    if value["state"] not in ("READY", "UNCERTAIN"):
        raise ValueError("Unknown Site recovery state")
    if value["identity"] != asdict(identity):
        raise ValueError("Stale Site Boot/Image/Manifest identity")
    generation = value["generation"]
    if type(generation) is not int or not 0 <= generation < 2**63 - 1:
        raise ValueError("Invalid journal generation")
    op = value["operation_id"]
    if value["state"] == "READY":
        if op is not None:
            raise ValueError("READY cannot have pending operation")
    elif type(op) is not str or not _ID.fullmatch(op):
        raise ValueError("UNCERTAIN requires exact operation identity")
    return value


def _check_fd(fd: int, *, directory: bool) -> None:
    meta = os.fstat(fd)
    allowed = stat.S_ISDIR(meta.st_mode) if directory else stat.S_ISREG(meta.st_mode)
    if (not allowed or meta.st_uid != os.geteuid() or
            (meta.st_mode & 0o077) or (not directory and meta.st_nlink != 1)):
        raise SiteRecoveryBlocked("Unsafe journal inode, owner or DAC")


class SiteRecoveryJournal:
    """Fail-closed Host-only guard; no method can grant READY or clear uncertainty.

    The root directory must be pre-provisioned privately (0700, same UID).
    Neither obtaining a Site flock nor successful callback completion clears
    UNCERTAIN. Test fixtures synthesize READY; deployed authority does not.
    """

    def __init__(self, root: Path, identity: SiteRecoveryIdentity) -> None:
        self._root = Path(root)
        self.identity = identity
        self._file = f"site-{identity.site_id}.json"
        self._lock = f"site-{identity.site_id}.lock"

    @contextmanager
    def _exclusive(self) -> Iterator[int]:
        dir_fd = -1
        lock_fd = -1
        try:
            dir_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            _check_fd(dir_fd, directory=True)
            lock_fd = os.open(self._lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                              0o600, dir_fd=dir_fd)
            _check_fd(lock_fd, directory=False)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield dir_fd
        except (OSError, ValueError) as exc:
            raise SiteRecoveryBlocked("Site journal ownership/lock unavailable") from exc
        finally:
            if lock_fd >= 0:
                os.close(lock_fd)
            if dir_fd >= 0:
                os.close(dir_fd)

    def _read(self, dir_fd: int) -> dict:
        # A leftover pre-rename temp file is a conservative recovery blocker.
        if any(name.startswith(self._file + ".pending-") for name in os.listdir(dir_fd)):
            raise SiteRecoveryBlocked("Incomplete durable journal replacement")
        fd = -1
        try:
            fd = os.open(self._file, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
            _check_fd(fd, directory=False)
            raw = os.read(fd, _MAX_BYTES + 1)
            if not raw or len(raw) > _MAX_BYTES:
                raise ValueError("Invalid journal size")
            return _verified_record(raw, self.identity)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise SiteRecoveryBlocked("Missing, stale or corrupt Site journal") from exc
        finally:
            if fd >= 0:
                os.close(fd)

    def status(self) -> str:
        """Inspection is never a write authorization by itself."""
        with self._exclusive() as directory:
            return self._read(directory)["state"]

    def assert_ready(self) -> None:
        with self._exclusive() as directory:
            if self._read(directory)["state"] != "READY":
                raise SiteRecoveryBlocked("Prior DUT write outcome is uncertain")

    def _persist_uncertain(self, directory: int, prior: dict,
                           operation_id: str) -> None:
        payload = {
            "schema": _SCHEMA,
            "state": "UNCERTAIN",
            "identity": asdict(self.identity),
            "generation": prior["generation"] + 1,
            "operation_id": operation_id,
        }
        record = dict(payload, checksum=_checksum(payload))
        raw = _canonical(record) + b"\n"
        temp = self._file + ".pending-" + secrets.token_hex(12)
        fd = -1
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=directory)
            _check_fd(fd, directory=False)
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0:
                    raise OSError("Short journal write")
                offset += written
            os.fsync(fd)       # data and inode durable before publishing
            os.close(fd)
            fd = -1
            os.replace(temp, self._file, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)  # rename durable before any injected PUSH
        except OSError as exc:
            # Do NOT remove an incomplete .pending file; block recovery.
            raise SiteRecoveryBlocked("Cannot durably establish UNCERTAIN") from exc
        finally:
            if fd >= 0:
                os.close(fd)

    def guard_write(self, operation_id: str, push: Callable[[], T]) -> T:
        """Persist UNCERTAIN and sync parent directory BEFORE invoking push.

        A successful return does NOT imply DUT completion/verification. This
        guard intentionally has no auto-reset or replay. Any failure leaves
        a durable blocker requiring an out-of-band trusted recovery decision.
        """
        if type(operation_id) is not str or not _ID.fullmatch(operation_id):
            raise ValueError("Exact operation ID required")
        if not callable(push):
            raise TypeError("Explicit injected operation required")
        with self._exclusive() as directory:
            current = self._read(directory)
            if current["state"] != "READY":
                raise SiteRecoveryBlocked("Prior DUT write outcome is uncertain")
            self._persist_uncertain(directory, current, operation_id)
            return push()
