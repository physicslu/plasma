from __future__ import annotations

import os
import secrets
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_profile import DEFAULT_MOCK_PROFILE, MockOperationProfile, MockProfile
from plasma_core.mock_profile_io import mock_profile_from_dict, mock_profile_to_dict


SEED_MODES = frozenset({"auto", "fixed"})
MAX_SEED = (1 << 63) - 1


@dataclass(frozen=True, slots=True)
class MockSeedSettings:
    mode: str = "auto"
    fixed_seed: int | None = None

    def validate(self) -> None:
        if self.mode not in SEED_MODES:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock seed mode must be 'auto' or 'fixed'")
        if self.mode == "auto":
            if self.fixed_seed is not None:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "auto mock seed mode cannot include fixed_seed")
            return
        if (
            isinstance(self.fixed_seed, bool)
            or not isinstance(self.fixed_seed, int)
            or not 0 <= self.fixed_seed <= MAX_SEED
        ):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"fixed mock seed must be 0..{MAX_SEED}")

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "fixed_seed": self.fixed_seed}

    def resolve(self) -> int:
        self.validate()
        if self.mode == "fixed":
            assert self.fixed_seed is not None
            return self.fixed_seed
        return secrets.randbits(63)


class MockRuntimeSettingsController:
    """Authoritative mutable Mock settings with immutable execution snapshots.

    Settings may change while a Batch is running because each Batch freezes a
    profile revision and resolved seed before its first Site Job is submitted.
    Direct Engineering Jobs similarly receive a snapshot before submission.
    """

    def __init__(self, persistence_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._persistence_path = Path(persistence_path).expanduser().resolve() if persistence_path else None
        self._profile = DEFAULT_MOCK_PROFILE
        self._seed = MockSeedSettings()
        if self._persistence_path and self._persistence_path.is_file():
            self._load(self._persistence_path)

    @property
    def profile(self) -> MockProfile:
        with self._lock:
            return self._profile

    def current(self) -> dict[str, Any]:
        with self._lock:
            return {
                **mock_profile_to_dict(self._profile),
                "seed": self._seed.to_dict(),
            }

    def execution_snapshot(self, batch_id: str) -> dict[str, Any]:
        if not isinstance(batch_id, str) or not batch_id:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "mock execution batch_id is required")
        with self._lock:
            profile = self._profile
            seed = self._seed
        return {
            "profile": mock_profile_to_dict(profile),
            "seed_mode": seed.mode,
            "resolved_seed": seed.resolve(),
            "batch_id": batch_id,
        }

    def update(self, raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock runtime settings must be an object")
        allowed = {"enabled", "default_image_size_bytes", "operations", "seed"}
        unknown = sorted(set(raw) - allowed)
        missing = sorted(allowed - set(raw))
        if unknown or missing:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "mock runtime settings have invalid fields",
                context={"unknown_fields": unknown, "missing_fields": missing},
            )
        operations = raw["operations"]
        if not isinstance(operations, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock operations must be an object")
        expected_operations = {"erase", "program", "verify", "read"}
        if set(operations) != expected_operations:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "mock operations must define erase/program/verify/read exactly",
            )

        parsed_operations: dict[str, MockOperationProfile] = {}
        required_operation_fields = {
            "error_rate_per_mille",
            "base_time_ms",
            "throughput_bytes_per_second",
            "jitter_ms",
        }
        for name in sorted(expected_operations):
            values = operations[name]
            if not isinstance(values, dict) or set(values) != required_operation_fields:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"mock operation {name} fields are invalid")
            parsed_operations[name] = MockOperationProfile(
                error_rate_per_mille=values["error_rate_per_mille"],
                base_time_ms=values["base_time_ms"],
                throughput_bytes_per_second=values["throughput_bytes_per_second"],
                jitter_ms=values["jitter_ms"],
            )

        seed_raw = raw["seed"]
        if not isinstance(seed_raw, dict) or set(seed_raw) != {"mode", "fixed_seed"}:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock seed fields are invalid")
        seed = MockSeedSettings(mode=seed_raw["mode"], fixed_seed=seed_raw["fixed_seed"])
        seed.validate()

        with self._lock:
            next_profile = MockProfile(
                profile_id=self._profile.profile_id,
                revision=self._profile.revision + 1,
                enabled=raw["enabled"],
                default_image_size_bytes=raw["default_image_size_bytes"],
                erase=parsed_operations["erase"],
                program=parsed_operations["program"],
                verify=parsed_operations["verify"],
                read=parsed_operations["read"],
            )
            next_profile.validate()
            if self._persistence_path is not None:
                self._write_atomic(self._persistence_path, next_profile, seed)
            self._profile = next_profile
            self._seed = seed
            return self.current()

    def _load(self, path: Path) -> None:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"cannot load Mock runtime settings: {path}",
                original_exception=exc,
            ) from exc
        if not isinstance(raw, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Mock runtime settings root must be a mapping")
        profile = mock_profile_from_dict(raw)
        seed_raw = raw.get("seed", {"mode": "auto", "fixed_seed": None})
        if not isinstance(seed_raw, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Mock runtime seed must be a mapping")
        seed = MockSeedSettings(mode=seed_raw.get("mode"), fixed_seed=seed_raw.get("fixed_seed"))
        seed.validate()
        with self._lock:
            self._profile = profile
            self._seed = seed

    def _write_atomic(
        self,
        destination: Path,
        profile: MockProfile,
        seed: MockSeedSettings,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            **mock_profile_to_dict(profile),
            "seed": seed.to_dict(),
        }
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
