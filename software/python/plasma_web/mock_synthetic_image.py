from __future__ import annotations

import hashlib
from typing import Any

from plasma_core.assets import ProgrammingAsset
from plasma_core.errors import ErrorCode, PlasmaError


_PATTERN = bytes(range(256))


def synthetic_image_size_from_context(context: dict[str, Any]) -> int:
    profile = context.get("profile")
    if not isinstance(profile, dict):
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "Mock execution context is missing profile")
    size = profile.get("default_image_size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "Mock execution context has invalid default_image_size_bytes")
    return size


def build_synthetic_mock_asset(size_bytes: int) -> ProgrammingAsset:
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes <= 0:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "Mock Synthetic Image size must be a positive integer")
    repeats, remainder = divmod(size_bytes, len(_PATTERN))
    data = _PATTERN * repeats + _PATTERN[:remainder]
    sha256 = hashlib.sha256(data).hexdigest()
    return ProgrammingAsset.from_upload(
        name=f"mock-synthetic-{size_bytes // 1024}KiB.bin",
        asset_type="image",
        asset_format="binary",
        data=data,
        sha256=sha256,
    )


def synthetic_mock_asset_from_context(context: dict[str, Any]) -> ProgrammingAsset:
    return build_synthetic_mock_asset(synthetic_image_size_from_context(context))
