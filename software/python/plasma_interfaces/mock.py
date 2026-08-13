from __future__ import annotations

import asyncio
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError

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


@dataclass(slots=True)
class MockInterface(BaseInterface):
    flash_size: int = 256 * 1024
    default_delay_s: float = 0.0
    delays: dict[str, float] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    failure_recoverable: bool = True
    progress_steps: int = 20
    tracker: MockActivityTracker | None = None
    memory: bytearray = field(init=False)
    calls: Counter[str] = field(default_factory=Counter, init=False)
    shutdown_count: int = field(default=0, init=False)

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
        self.delays = dict(self.delays)
        self.failures = dict(self.failures)
        for operation, delay in self.delays.items():
            if operation not in OPERATION_ERRORS:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unknown mock delay operation: {operation}")
            if (
                isinstance(delay, bool)
                or not isinstance(delay, (int, float))
                or not math.isfinite(delay)
                or delay < 0
            ):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"invalid mock delay for {operation}")
        for operation, count in self.failures.items():
            if operation not in OPERATION_ERRORS:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unknown mock failure operation: {operation}")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"invalid mock failure count for {operation}")
        self.memory = bytearray([0xFF]) * self.flash_size

    @classmethod
    def from_options(
        cls,
        options: dict[str, Any],
        tracker: MockActivityTracker | None = None,
    ) -> "MockInterface":
        allowed = {
            "flash_size",
            "default_delay_s",
            "delays",
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
        return cls(tracker=tracker, **options)

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
            delay_s = max(0.0, float(self.delays.get(operation, self.default_delay_s)))
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
            remaining = int(self.failures.get(operation, 0))
            if remaining > 0:
                self.failures[operation] = remaining - 1
                raise PlasmaError(
                    OPERATION_ERRORS[operation],
                    f"injected MockInterface {operation} failure",
                    recoverable=self.failure_recoverable,
                    context={"operation": operation, "remaining_failures": remaining - 1},
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
        await self._before("erase", progress, 100)
        self.memory[:] = bytes([0xFF]) * self.flash_size

    async def program(
        self,
        firmware: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._validate_range(address, len(firmware))
        await self._before("program", progress, len(firmware))
        self.memory[address : address + len(firmware)] = firmware

    async def verify(
        self,
        firmware: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._validate_range(address, len(firmware))
        await self._before("verify", progress, len(firmware))
        actual = bytes(self.memory[address : address + len(firmware)])
        if actual != firmware:
            mismatch = next(
                (index for index, pair in enumerate(zip(actual, firmware, strict=True)) if pair[0] != pair[1]),
                None,
            )
            raise PlasmaError(
                ErrorCode.VERIFY_FAILED,
                "flash verification mismatch",
                recoverable=True,
                context={"address": address + (mismatch or 0)},
            )

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        self._validate_range(address, length)
        await self._before("read", progress, length)
        return bytes(self.memory[address : address + length])

    async def safe_shutdown(self) -> None:
        self.shutdown_count += 1
        await asyncio.sleep(0)
