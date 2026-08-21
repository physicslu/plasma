from __future__ import annotations

import hashlib
import mmap
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterator

from .errors import ErrorCode, PlasmaError


@dataclass(frozen=True, slots=True)
class SharedImageRef:
    sha256: str
    size_bytes: int
    path: Path


class SharedImageStore:
    """Phase-1 content-addressed store for immutable normalized Mock images.

    The store intentionally implements only the invariants needed by the Mock
    runtime foundation: SHA-256 addressing, atomic creation, content validation,
    and read-only mmap access. Cross-process reference leases, TTL/LRU and GC
    remain outside this first phase.
    """

    def __init__(self, root: str | Path, *, max_blob_bytes: int = 4 * 1024 * 1024) -> None:
        self.root = Path(root).expanduser().resolve()
        if isinstance(max_blob_bytes, bool) or not isinstance(max_blob_bytes, int) or max_blob_bytes <= 0:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "max_blob_bytes must be a positive integer")
        self.max_blob_bytes = max_blob_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_sha256(value: str) -> str:
        if not isinstance(value, str) or len(value) != 64:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid SHA-256")
        try:
            int(value, 16)
        except ValueError as exc:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid SHA-256") from exc
        return value.lower()

    def path_for(self, sha256: str) -> Path:
        digest = self._validate_sha256(sha256)
        return self.root / f"{digest}.bin"

    def put(self, data: bytes) -> SharedImageRef:
        if not isinstance(data, bytes) or not data:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "shared image must be non-empty bytes")
        if len(data) > self.max_blob_bytes:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "shared image exceeds configured blob size limit",
                context={"size_bytes": len(data), "max_blob_bytes": self.max_blob_bytes},
            )
        digest = hashlib.sha256(data).hexdigest()
        destination = self.path_for(digest)
        if destination.is_file():
            self._validate_existing(destination, digest, len(data))
            return SharedImageRef(digest, len(data), destination)

        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{digest}.", suffix=".tmp", dir=self.root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            # Atomic on one filesystem. Concurrent writers of the same digest
            # can safely race because the destination content is identical.
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        self._validate_existing(destination, digest, len(data))
        return SharedImageRef(digest, len(data), destination)

    def resolve(self, sha256: str, *, expected_size: int | None = None) -> SharedImageRef:
        digest = self._validate_sha256(sha256)
        path = self.path_for(digest)
        if not path.is_file():
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "shared image is not available", context={"sha256": digest})
        size = path.stat().st_size
        if expected_size is not None and size != expected_size:
            raise PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                "shared image size does not match expected size",
                context={"sha256": digest, "expected_size": expected_size, "actual_size": size},
            )
        if size <= 0 or size > self.max_blob_bytes:
            raise PlasmaError(ErrorCode.INTERNAL_ERROR, "shared image store contains invalid blob size")
        return SharedImageRef(digest, size, path)

    def _validate_existing(self, path: Path, expected_sha256: str, expected_size: int) -> None:
        if path.stat().st_size != expected_size:
            raise PlasmaError(ErrorCode.INTERNAL_ERROR, "shared image collision has an unexpected size")
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
        actual = hasher.hexdigest()
        if actual != expected_sha256:
            raise PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                "shared image content does not match its content address",
                context={"expected": expected_sha256, "actual": actual},
            )

    @contextmanager
    def open_mmap(self, sha256: str, *, expected_size: int | None = None) -> Iterator[mmap.mmap]:
        ref = self.resolve(sha256, expected_size=expected_size)
        with ref.path.open("rb") as handle:
            mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                yield mapped
            finally:
                mapped.close()


_DEFAULT_STORE: SharedImageStore | None = None
_DEFAULT_STORE_LOCK = Lock()


def default_mock_image_store() -> SharedImageStore:
    """Return the process-wide Phase-1 Mock image store.

    `PLASMA_MOCK_BLOB_ROOT` may pin a deployment-specific directory. Without it,
    each process receives one temporary content-addressed store, which is enough
    to remove per-Site Flash copies while keeping persistence/GC policy out of
    the foundation phase.
    """
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is None:
            configured = os.environ.get("PLASMA_MOCK_BLOB_ROOT")
            root = (
                Path(configured).expanduser()
                if configured
                else Path(tempfile.gettempdir()) / f"plasma-mock-{os.getpid()}" / "blobs"
            )
            _DEFAULT_STORE = SharedImageStore(root)
        return _DEFAULT_STORE
