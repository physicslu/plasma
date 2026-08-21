from __future__ import annotations

import asyncio
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_flash import MockFlashState
from plasma_core.mock_image_store import SharedImageStore, default_mock_image_store
from plasma_core.mock_profile import MockProfile, calculate_duration_ms, rng_for_job, should_fail
from plasma_core.mock_profile_io import mock_profile_from_dict
from plasma_core.models import ExecutionImageRef, JobRequest

from .base import BaseInterface, ProgressCallback


OPERATION_ERRORS = {
    "erase": ErrorCode.ERASE_FAILED,
    "program": ErrorCode.PROGRAM_FAILED,
    "verify": ErrorCode.VERIFY_FAILED,
    "read": ErrorCode.READ_FAILED,
}


@dataclass(slots=True)
class MockActivityTracker:
    active: int = 0
    maximum: int = 0

    def enter(self) -> None:
        self.active += 1
        self.maximum = max(self.maximum, self.active)

    def leave(self) -> None:
        self.active -= 1


@dataclass(frozen=True, slots=True)
class MockAttemptContext:
    profile: MockProfile
    batch_seed: int
    batch_id: str
    facility_id: str
    ppu_id: str
    site_id: int
    round_index: int
    attempt: int


@dataclass(slots=True)
class MockInterface(BaseInterface):
    flash_size: int = 256 * 1024
    default_delay_s: float = 0.0
    delays: dict[str, float] = field(default_factory=dict)
    throughput_bytes_per_s: dict[str, float] = field(default_factory=dict)
    operation_overheads_s: dict[str, float] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    failure_recoverable: bool = True
    progress_steps: int = 20
    tracker: MockActivityTracker | None = None
    image_store: SharedImageStore | None = field(default=None, repr=False)
    memory: None = field(init=False, default=None, repr=False)
    flash_state: MockFlashState = field(init=False, repr=False)
    calls: Counter[str] = field(default_factory=Counter, init=False)
    shutdown_count: int = field(default=0, init=False)
    _active_job_id: str | None = field(default=None, init=False, repr=False)
    _active_attempt: int = field(default=0, init=False, repr=False)
    _attempt_context: MockAttemptContext | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.flash_size, bool) or not isinstance(self.flash_size, int) or self.flash_size <= 0:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock flash_size must be a positive integer")
        if (
            isinstance(self.default_delay_s, bool)
            or not isinstance(self.default_delay_s, (int, float))
            or not math.isfinite(self.default_delay_s)
            or self.default_delay_s < 0
        ):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock default_delay_s must be finite and non-negative")
        if (
            isinstance(self.progress_steps, bool)
            or not isinstance(self.progress_steps, int)
            or self.progress_steps <= 0
        ):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock progress_steps must be a positive integer")
        if not isinstance(self.failure_recoverable, bool):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock failure_recoverable must be boolean")
        if not isinstance(self.delays, dict) or not isinstance(self.failures, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock delays and failures must be objects")
        if not isinstance(self.throughput_bytes_per_s, dict) or not isinstance(self.operation_overheads_s, dict):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "mock throughput_bytes_per_s and operation_overheads_s must be objects",
            )
        self.delays = dict(self.delays)
        self.throughput_bytes_per_s = dict(self.throughput_bytes_per_s)
        self.operation_overheads_s = dict(self.operation_overheads_s)
        self.failures = dict(self.failures)
        for operation, delay in self.delays.items():
            self._validate_operation_name(operation, "delay")
            self._validate_finite_number(delay, f"invalid mock delay for {operation}", minimum=0.0)
        for operation, throughput in self.throughput_bytes_per_s.items():
            self._validate_operation_name(operation, "throughput")
            self._validate_finite_number(
                throughput,
                f"invalid mock throughput for {operation}",
                minimum=0.0,
                strictly_greater=True,
            )
        for operation, overhead in self.operation_overheads_s.items():
            self._validate_operation_name(operation, "overhead")
            self._validate_finite_number(
                overhead,
                f"invalid mock operation overhead for {operation}",
                minimum=0.0,
            )
        for operation, count in self.failures.items():
            if operation not in OPERATION_ERRORS:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unknown mock failure operation: {operation}")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"invalid mock failure count for {operation}")

        if self.image_store is None:
            self.image_store = default_mock_image_store()
        self.flash_state = MockFlashState(self.flash_size)

    @property
    def uses_shared_image_store(self) -> bool:
        return True

    @staticmethod
    def _validate_operation_name(operation: str, option_name: str) -> None:
        if operation not in OPERATION_ERRORS:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"unknown mock {option_name} operation: {operation}",
            )

    @staticmethod
    def _validate_finite_number(
        value: Any,
        message: str,
        *,
        minimum: float,
        strictly_greater: bool = False,
    ) -> None:
        invalid = (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < minimum
            or (strictly_greater and value <= minimum)
        )
        if invalid:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, message)

    @classmethod
    def from_options(
        cls,
        options: dict[str, Any],
        tracker: MockActivityTracker | None = None,
        image_store: SharedImageStore | None = None,
    ) -> "MockInterface":
        allowed = {
            "flash_size",
            "default_delay_s",
            "delays",
            "throughput_bytes_per_s",
            "operation_overheads_s",
            "failures",
            "failure_recoverable",
            "progress_steps",
        }
        unknown = sorted(set(options) - allowed)
        if unknown:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "unknown MockInterface options",
                context={"unknown_options": unknown},
            )
        return cls(tracker=tracker, image_store=image_store, **options)

    def prepare_request(self, request: JobRequest) -> None:
        if request.job_id == self._active_job_id:
            self._active_attempt += 1
        else:
            self._active_job_id = request.job_id
            self._active_attempt = 1

        raw = request.metadata.get("mock_runtime")
        if raw is None:
            self._attempt_context = None
            return
        if not isinstance(raw, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock_runtime Job metadata must be an object")
        required = {
            "profile",
            "resolved_seed",
            "batch_id",
            "facility_id",
            "ppu_id",
            "site_id",
            "round_index",
        }
        missing = sorted(required - set(raw))
        if missing:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "mock_runtime Job metadata is incomplete",
                context={"missing_fields": missing},
            )
        profile = mock_profile_from_dict(raw["profile"])
        batch_seed = raw["resolved_seed"]
        site_id = raw["site_id"]
        round_index = raw["round_index"]
        if isinstance(batch_seed, bool) or not isinstance(batch_seed, int) or batch_seed < 0:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock resolved_seed must be a non-negative integer")
        if site_id != request.site_id:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock_runtime site_id does not match Job site_id")
        if isinstance(round_index, bool) or not isinstance(round_index, int) or round_index < 1:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock round_index must be a positive integer")
        for field_name in ("batch_id", "facility_id", "ppu_id"):
            if not isinstance(raw[field_name], str) or not raw[field_name]:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"mock {field_name} is required")
        self._attempt_context = MockAttemptContext(
            profile=profile,
            batch_seed=batch_seed,
            batch_id=raw["batch_id"],
            facility_id=raw["facility_id"],
            ppu_id=raw["ppu_id"],
            site_id=site_id,
            round_index=round_index,
            attempt=self._active_attempt,
        )

    def _profile_rng(self, operation: str):
        context = self._attempt_context
        if context is None or not context.profile.enabled:
            return None
        return rng_for_job(
            batch_seed=context.batch_seed,
            batch_id=context.batch_id,
            facility_id=context.facility_id,
            ppu_id=context.ppu_id,
            site_id=context.site_id,
            round_index=context.round_index,
            operation=operation,
            attempt=context.attempt,
            profile_revision=context.profile.revision,
        )

    def estimated_delay_s(self, operation: str, total_bytes: int) -> float:
        """Return the configured Mock execution time for one operation."""
        if operation not in OPERATION_ERRORS:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unknown mock operation: {operation}")
        if isinstance(total_bytes, bool) or not isinstance(total_bytes, int) or total_bytes < 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "mock timing byte count must be non-negative")
        context = self._attempt_context
        rng = self._profile_rng(operation)
        if context is not None and context.profile.enabled and rng is not None:
            return calculate_duration_ms(
                profile=context.profile.operation(operation),
                data_size_bytes=total_bytes,
                rng=rng,
            ) / 1000.0
        if operation in self.delays:
            return max(0.0, float(self.delays[operation]))
        throughput = self.throughput_bytes_per_s.get(operation)
        if throughput is None:
            return max(0.0, float(self.default_delay_s))
        overhead = float(self.operation_overheads_s.get(operation, 0.0))
        return max(0.0, overhead + total_bytes / float(throughput))

    async def _before(
        self,
        operation: str,
        progress: ProgressCallback | None,
        total_units: int,
    ) -> None:
        self.calls[operation] += 1
        if self.tracker:
            self.tracker.enter()
        try:
            context = self._attempt_context
            rng = self._profile_rng(operation)
            if context is not None and context.profile.enabled and rng is not None:
                operation_profile = context.profile.operation(operation)
                delay_s = calculate_duration_ms(
                    profile=operation_profile,
                    data_size_bytes=total_units,
                    rng=rng,
                ) / 1000.0
            else:
                operation_profile = None
                delay_s = self.estimated_delay_s(operation, total_units)

            steps = max(1, int(self.progress_steps))
            if progress:
                await progress(0, total_units)
            if delay_s == 0:
                await asyncio.sleep(0)
            else:
                for step in range(1, steps + 1):
                    await asyncio.sleep(delay_s / steps)
                    if progress:
                        await progress(round(total_units * step / steps), total_units)
            if progress and delay_s == 0:
                await progress(total_units, total_units)

            if operation_profile is not None and rng is not None and should_fail(
                rng,
                operation_profile.error_rate_per_mille,
            ):
                assert context is not None
                raise PlasmaError(
                    OPERATION_ERRORS[operation],
                    f"injected Mock Profile {operation} failure",
                    recoverable=True,
                    context={
                        "operation": operation,
                        "failure_source": "injected",
                        "profile_id": context.profile.profile_id,
                        "profile_revision": context.profile.revision,
                        "batch_seed": context.batch_seed,
                        "round_index": context.round_index,
                        "attempt": context.attempt,
                    },
                )

            remaining = int(self.failures.get(operation, 0))
            if remaining > 0:
                self.failures[operation] = remaining - 1
                raise PlasmaError(
                    OPERATION_ERRORS[operation],
                    f"injected MockInterface {operation} failure",
                    recoverable=self.failure_recoverable,
                    context={
                        "operation": operation,
                        "remaining_failures": remaining - 1,
                        "failure_source": "injected",
                    },
                )
        finally:
            if self.tracker:
                self.tracker.leave()

    def _validate_range(self, address: int, length: int) -> None:
        if address < 0 or length < 0 or address + length > self.flash_size:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "flash address range is outside the mock target",
                context={"address": address, "length": length, "flash_size": self.flash_size},
            )

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        await self._before("erase", progress, self.flash_size)
        self.flash_state.erase()

    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._validate_range(address, len(image))
        await self._before("program", progress, len(image))
        assert self.image_store is not None
        ref = self.image_store.put(image)
        self.flash_state.program_shared(
            image_sha256=ref.sha256,
            image_size_bytes=ref.size_bytes,
            address=address,
        )

    async def program_image_ref(
        self,
        image_ref: ExecutionImageRef,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._validate_range(address, image_ref.size_bytes)
        await self._before("program", progress, image_ref.size_bytes)
        assert self.image_store is not None
        self.image_store.resolve(image_ref.sha256, expected_size=image_ref.size_bytes)
        self.flash_state.program_shared(
            image_sha256=image_ref.sha256,
            image_size_bytes=image_ref.size_bytes,
            address=address,
        )

    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._validate_range(address, len(image))
        await self._before("verify", progress, len(image))
        assert self.image_store is not None
        mismatch = self.flash_state.verify(self.image_store, image, address)
        if mismatch is None:
            return
        raise PlasmaError(
            ErrorCode.VERIFY_FAILED,
            "flash verification mismatch",
            recoverable=True,
            context={"address": mismatch, "failure_source": "mismatch"},
        )

    async def verify_image_ref(
        self,
        image_ref: ExecutionImageRef,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._validate_range(address, image_ref.size_bytes)
        await self._before("verify", progress, image_ref.size_bytes)
        assert self.image_store is not None
        mismatch = self.flash_state.verify_shared(
            self.image_store,
            expected_sha256=image_ref.sha256,
            expected_size_bytes=image_ref.size_bytes,
            address=address,
        )
        if mismatch is None:
            return
        raise PlasmaError(
            ErrorCode.VERIFY_FAILED,
            "flash verification mismatch",
            recoverable=True,
            context={"address": mismatch, "failure_source": "mismatch"},
        )

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        self._validate_range(address, length)
        await self._before("read", progress, length)
        assert self.image_store is not None
        return self.flash_state.read(self.image_store, address, length)

    async def safe_shutdown(self) -> None:
        self.shutdown_count += 1
        await asyncio.sleep(0)
