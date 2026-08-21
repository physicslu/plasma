from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from .errors import ErrorCode, PlasmaError


@dataclass(frozen=True, slots=True)
class MockOperationProfile:
    error_rate_per_mille: int
    base_time_ms: int
    throughput_bytes_per_second: int
    jitter_ms: int

    def validate(self, operation: str) -> None:
        if isinstance(self.error_rate_per_mille, bool) or not isinstance(self.error_rate_per_mille, int):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{operation} error_rate_per_mille must be an integer")
        if not 0 <= self.error_rate_per_mille <= 1000:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{operation} error_rate_per_mille must be 0..1000")
        if isinstance(self.base_time_ms, bool) or not isinstance(self.base_time_ms, int) or self.base_time_ms < 0:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{operation} base_time_ms must be a non-negative integer")
        if (
            isinstance(self.throughput_bytes_per_second, bool)
            or not isinstance(self.throughput_bytes_per_second, int)
            or self.throughput_bytes_per_second <= 0
        ):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"{operation} throughput_bytes_per_second must be a positive integer",
            )
        if isinstance(self.jitter_ms, bool) or not isinstance(self.jitter_ms, int) or self.jitter_ms < 0:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{operation} jitter_ms must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class MockProfile:
    profile_id: str
    revision: int
    enabled: bool
    default_image_size_bytes: int
    erase: MockOperationProfile
    program: MockOperationProfile
    verify: MockOperationProfile
    read: MockOperationProfile

    def validate(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock profile_id is required")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock profile revision must be a positive integer")
        if not isinstance(self.enabled, bool):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock profile enabled must be boolean")
        if (
            isinstance(self.default_image_size_bytes, bool)
            or not isinstance(self.default_image_size_bytes, int)
            or not 65_536 <= self.default_image_size_bytes <= 4_194_304
            or self.default_image_size_bytes % 65_536 != 0
        ):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "mock default_image_size_bytes must be 64 KiB..4 MiB in 64 KiB steps",
            )
        for name in ("erase", "program", "verify", "read"):
            getattr(self, name).validate(name)

    def operation(self, operation: str) -> MockOperationProfile:
        try:
            value = getattr(self, operation)
        except AttributeError as exc:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unknown mock operation: {operation}") from exc
        if not isinstance(value, MockOperationProfile):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unknown mock operation: {operation}")
        return value


DEFAULT_MOCK_PROFILE = MockProfile(
    profile_id="default",
    revision=1,
    enabled=True,
    default_image_size_bytes=256 * 1024,
    erase=MockOperationProfile(1, 1000, 2 * 1024 * 1024, 200),
    program=MockOperationProfile(50, 500, 512 * 1024, 200),
    verify=MockOperationProfile(20, 300, 1024 * 1024, 100),
    read=MockOperationProfile(5, 200, 1024 * 1024, 100),
)


def derive_job_seed(
    *,
    batch_seed: int,
    batch_id: str,
    facility_id: str,
    ppu_id: str,
    site_id: int,
    round_index: int,
    operation: str,
    attempt: int,
    profile_revision: int,
) -> int:
    """Return a stable per-attempt seed independent of Python hash randomization."""
    material = "\x1f".join(
        (
            str(batch_seed),
            batch_id,
            facility_id,
            ppu_id,
            str(site_id),
            str(round_index),
            operation,
            str(attempt),
            str(profile_revision),
        )
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=False)


def rng_for_job(**seed_fields: object) -> random.Random:
    return random.Random(derive_job_seed(**seed_fields))


def should_fail(rng: random.Random, error_rate_per_mille: int) -> bool:
    if isinstance(error_rate_per_mille, bool) or not isinstance(error_rate_per_mille, int):
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "error_rate_per_mille must be an integer")
    if not 0 <= error_rate_per_mille <= 1000:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "error_rate_per_mille must be 0..1000")
    return rng.randrange(1000) < error_rate_per_mille


def calculate_duration_ms(
    *,
    profile: MockOperationProfile,
    data_size_bytes: int,
    rng: random.Random,
) -> int:
    if isinstance(data_size_bytes, bool) or not isinstance(data_size_bytes, int) or data_size_bytes < 0:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "mock timing data size must be a non-negative integer")
    transfer_ms = data_size_bytes * 1000 / profile.throughput_bytes_per_second
    jitter = rng.randint(-profile.jitter_ms, profile.jitter_ms) if profile.jitter_ms else 0
    return max(0, round(profile.base_time_ms + transfer_ms + jitter))
