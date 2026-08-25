from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from plasma_core.errors import ErrorCode, PlasmaError


DEFAULT_PPU_REQUEST_TIMEOUT_MS = 10_000
DEFAULT_PPU_RETRY_COUNT = 3
MIN_PPU_REQUEST_TIMEOUT_MS = 1_000
MAX_PPU_REQUEST_TIMEOUT_MS = 120_000
MAX_PPU_RETRY_COUNT = 10


@dataclass(frozen=True, slots=True)
class GatewayCommunicationPolicy:
    revision: int = 1
    ppu_request_timeout_ms: int = DEFAULT_PPU_REQUEST_TIMEOUT_MS
    ppu_retry_count: int = DEFAULT_PPU_RETRY_COUNT

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway settings revision must be a positive integer")
        if (
            isinstance(self.ppu_request_timeout_ms, bool)
            or not isinstance(self.ppu_request_timeout_ms, int)
            or not MIN_PPU_REQUEST_TIMEOUT_MS <= self.ppu_request_timeout_ms <= MAX_PPU_REQUEST_TIMEOUT_MS
        ):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"PPU request timeout must be {MIN_PPU_REQUEST_TIMEOUT_MS}..{MAX_PPU_REQUEST_TIMEOUT_MS} ms",
            )
        if (
            isinstance(self.ppu_retry_count, bool)
            or not isinstance(self.ppu_retry_count, int)
            or not 0 <= self.ppu_retry_count <= MAX_PPU_RETRY_COUNT
        ):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"PPU retry count must be 0..{MAX_PPU_RETRY_COUNT}")

    @property
    def request_timeout_s(self) -> float:
        return self.ppu_request_timeout_ms / 1000.0

    def to_dict(self) -> dict[str, int]:
        return {
            "revision": self.revision,
            "ppu_request_timeout_ms": self.ppu_request_timeout_ms,
            "ppu_retry_count": self.ppu_retry_count,
        }


class GatewaySettingsController:
    """Persistent Gateway communication policy shared by Production and Engineering."""

    def __init__(self, persistence_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._persistence_path = Path(persistence_path).expanduser().resolve() if persistence_path else None
        self._policy = GatewayCommunicationPolicy()
        if self._persistence_path is not None and self._persistence_path.is_file():
            self._policy = self._load(self._persistence_path)

    def snapshot(self) -> GatewayCommunicationPolicy:
        with self._lock:
            return self._policy

    def current(self) -> dict[str, int]:
        return self.snapshot().to_dict()

    def update(self, raw: dict[str, Any]) -> dict[str, int]:
        if not isinstance(raw, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway settings must be an object")
        expected = {"ppu_request_timeout_ms", "ppu_retry_count"}
        if set(raw) != expected:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "Gateway settings have invalid fields",
                context={
                    "unknown_fields": sorted(set(raw) - expected),
                    "missing_fields": sorted(expected - set(raw)),
                },
            )
        with self._lock:
            candidate = GatewayCommunicationPolicy(
                revision=self._policy.revision + 1,
                ppu_request_timeout_ms=raw["ppu_request_timeout_ms"],
                ppu_retry_count=raw["ppu_retry_count"],
            )
            if self._persistence_path is not None:
                self._write_atomic(self._persistence_path, candidate)
            self._policy = candidate
            return candidate.to_dict()

    @staticmethod
    def _load(path: Path) -> GatewayCommunicationPolicy:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"cannot load Gateway settings: {path}",
                original_exception=exc,
            ) from exc
        expected = {"revision", "ppu_request_timeout_ms", "ppu_retry_count"}
        if not isinstance(raw, dict) or set(raw) != expected:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway settings persistence fields are invalid")
        return GatewayCommunicationPolicy(**raw)

    @staticmethod
    def _write_atomic(destination: Path, policy: GatewayCommunicationPolicy) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(yaml.safe_dump(policy.to_dict(), sort_keys=False))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
