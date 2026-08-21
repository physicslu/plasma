from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .errors import ErrorCode, PlasmaError
from .mock_profile import MockOperationProfile, MockProfile


OPERATION_NAMES = ("erase", "program", "verify", "read")


def mock_profile_from_dict(raw: dict[str, Any]) -> MockProfile:
    if not isinstance(raw, dict):
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock profile root must be a mapping")
    operations = raw.get("operations")
    if not isinstance(operations, dict):
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock profile operations must be a mapping")

    parsed: dict[str, MockOperationProfile] = {}
    for name in OPERATION_NAMES:
        values = operations.get(name)
        if not isinstance(values, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"mock profile operation {name} is required")
        try:
            parsed[name] = MockOperationProfile(
                error_rate_per_mille=values["error_rate_per_mille"],
                base_time_ms=values["base_time_ms"],
                throughput_bytes_per_second=values["throughput_bytes_per_second"],
                jitter_ms=values["jitter_ms"],
            )
        except KeyError as exc:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"mock profile operation {name} is incomplete",
                original_exception=exc,
            ) from exc

    try:
        profile = MockProfile(
            profile_id=raw["profile_id"],
            revision=raw["revision"],
            enabled=raw["enabled"],
            default_image_size_bytes=raw["default_image_size_bytes"],
            erase=parsed["erase"],
            program=parsed["program"],
            verify=parsed["verify"],
            read=parsed["read"],
        )
    except KeyError as exc:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock profile is incomplete", original_exception=exc) from exc
    profile.validate()
    return profile


def mock_profile_to_dict(profile: MockProfile) -> dict[str, Any]:
    profile.validate()
    return {
        "profile_id": profile.profile_id,
        "revision": profile.revision,
        "enabled": profile.enabled,
        "default_image_size_bytes": profile.default_image_size_bytes,
        "operations": {
            name: {
                "error_rate_per_mille": operation.error_rate_per_mille,
                "base_time_ms": operation.base_time_ms,
                "throughput_bytes_per_second": operation.throughput_bytes_per_second,
                "jitter_ms": operation.jitter_ms,
            }
            for name, operation in ((name, profile.operation(name)) for name in OPERATION_NAMES)
        },
    }


def load_mock_profile(path: str | Path) -> MockProfile:
    profile_path = Path(path).expanduser().resolve()
    try:
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            f"cannot load Mock profile: {profile_path}",
            original_exception=exc,
        ) from exc
    return mock_profile_from_dict(raw)


def write_mock_profile_atomic(path: str | Path, profile: MockProfile) -> None:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(mock_profile_to_dict(profile), sort_keys=False, allow_unicode=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
