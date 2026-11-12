from __future__ import annotations

import asyncio
import hashlib
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_flash import MockFlashState
from plasma_core.mock_image_store import SharedImageStore, default_mock_image_store
from plasma_core.mock_profile import MockProfile, calculate_duration_ms, rng_for_job, should_fail
from plasma_core.mock_profile_io import mock_profile_from_dict
from plasma_core.models import ExecutionImageRef, JobRequest

from .base import BaseInterface, ProgressCallback
from .runtime_context import RuntimeJobContext


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
    CONSUMES_JOB_BINDING = True

    flash_size: int = 256 * 1024
    # The simulated device's own Flash window. A Job Binding carries absolute
    # device addresses, so ``programming`` maps them onto this window instead
    # of assuming every write starts at offset 0.
    flash_base: int = 0
    # Byte-granular unless a Site declares the geometry it simulates. A Mock
    # Site standing in for a real target must declare the same granularity as
    # its Resource Set, or its erase evidence will not match the Manager plan.
    erase_granularity: int = 1
    # Makes the closing step fail, so a receipt without a proven SAFE_OFF can
    # be exercised without hand-writing evidence.
    safe_off_fails: bool = False
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
    # Set by the closing step of a programming Job, cleared when a Job starts.
    site_safe: bool = field(default=False, init=False)
    safe_off_count: int = field(default=0, init=False)
    _context: RuntimeJobContext | None = field(default=None, init=False, repr=False)
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
        if not isinstance(self.safe_off_fails, bool):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock safe_off_fails must be boolean")
        if isinstance(self.flash_base, bool) or not isinstance(self.flash_base, int) or self.flash_base < 0:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock flash_base must be a non-negative integer")
        if (isinstance(self.erase_granularity, bool)
                or not isinstance(self.erase_granularity, int)
                or self.erase_granularity <= 0
                or self.flash_size % self.erase_granularity != 0):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "mock erase_granularity must be a positive divisor of flash_size",
            )
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
            "flash_base",
            "erase_granularity",
            "safe_off_fails",
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

    def bind_runtime_job(self, context: RuntimeJobContext) -> None:
        """Bind the Runtime-admitted context for one Job attempt.

        A ``programming`` Job is authorized by its admitted Job Binding alone.
        A trusted Provider Action authorizes a different execution path and is
        never accepted in its place.
        """
        context = self._require_runtime_context(context)
        if context.trusted_provider is not None:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                "mock executes an admitted Job Binding, not a Provider Action",
                context={"job_id": context.job_id, "site_id": context.site_id},
            )
        self._context = context

    def _binding(self, operation: Operation) -> Mapping[str, Any]:
        """The admitted Job Binding of this Job; there is no default."""
        binding = self._context.admitted_job_binding if self._context is not None else None
        job_range = binding.get("range") if isinstance(binding, Mapping) else None
        if (not isinstance(binding, Mapping) or binding.get("operation") != operation.value
                or not isinstance(job_range, Mapping)
                or type(job_range.get("address")) is not int
                or type(job_range.get("length")) is not int):
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"mock {operation.value} requires an admitted Job Binding",
                context={"operation": operation.value},
            )
        return binding

    def _offset(self, address: int, length: int) -> int:
        """Map a Job Binding address onto this Mock target's Flash window."""
        if (isinstance(address, bool) or isinstance(length, bool)
                or not isinstance(address, int) or not isinstance(length, int)):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                              "Job Binding range must be integers")
        offset = address - self.flash_base
        if offset < 0 or length < 0 or offset + length > self.flash_size:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "Job Binding range is outside the mock target",
                context={"address": address, "length": length,
                         "flash_base": self.flash_base, "flash_size": self.flash_size},
            )
        return offset

    def _close_site(self) -> bool:
        """Close this Site's simulated session, leaving it in a defined safe state.

        The analogue of the C-3 session's fixed closing sequence. It runs
        before the evidence is sealed, so ``safe_off`` reports a step that has
        already happened rather than predicting the later ``safe_shutdown``.
        """
        if self.safe_off_fails:
            self.site_safe = False
            return False
        self.site_safe = True
        self.safe_off_count += 1
        return True

    def prepare_request(self, request: JobRequest) -> None:
        if self._context is not None and not self._context.matches(
                request.job_id, request.site_id):
            # A context left over from an earlier Job never authorizes this one.
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "RUNTIME_CONTEXT_JOB_MISMATCH")
        if request.job_id == self._active_job_id:
            self._active_attempt += 1
        else:
            self._active_job_id = request.job_id
            self._active_attempt = 1
        self.site_safe = False

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

    async def run_operations(
        self,
        operations: tuple[str, ...],
        image: bytes,
        progress: ProgressCallback | None = None,
    ) -> dict[str, object]:
        """One ``programming`` Job: the Binding's ordered list on this Site.

        Every evidence field is read back out of the Mock Flash state this call
        actually left behind, never copied from the request, so a write to the
        wrong offset, a skipped erase or a mismatched Verify shows up in the
        receipt instead of being asserted away. The Binding is the only source
        of the list and the range: there is no default for either.
        """
        binding = self._binding(Operation.PROGRAMMING)
        bound = tuple(binding.get("operations") or ())
        job_range = binding["range"]
        address, length = job_range["address"], job_range["length"]
        takes_image = "program" in bound or "verify" in bound
        if (tuple(operations) != bound or bool(image) != takes_image
                or (takes_image and len(image) != length)):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                              "mock programming Job does not match its Job Binding")
        offset = self._offset(address, length)
        steps: dict[str, Any] = {}

        if "erase" in bound:
            # Erase covers the Image's erase window, not the whole device.
            erase_length = -(-length // self.erase_granularity) * self.erase_granularity
            self._offset(address, erase_length)
            await self._before("erase", None, erase_length)
            self.flash_state.erase(offset, erase_length)
            steps["erase"] = {"erase_address": address, "erase_length": erase_length}
            if bound == ("erase",):
                observed = self.flash_state.read(self.image_store, offset, length)
                steps["erase"].update(
                    blank_verified=observed == b"\xff" * length,
                    bytes_verified=length,
                    readback_sha256=hashlib.sha256(observed).hexdigest(),
                )
                if not steps["erase"]["blank_verified"]:
                    raise PlasmaError(
                        ErrorCode.ERASE_FAILED,
                        "mock erase did not leave the bound range blank",
                        recoverable=True,
                        context={"operations": list(bound), "steps": steps,
                                 "failure_source": "mismatch"},
                    )

        if "program" in bound:
            await self._before("program", None, length)
            assert self.image_store is not None
            ref = self.image_store.put(image)
            self.flash_state.program_shared(
                image_sha256=ref.sha256,
                image_size_bytes=ref.size_bytes,
                address=offset,
            )
            written = self.flash_state.read(self.image_store, offset, length)
            steps["program"] = {
                "write_address": address,
                "bytes_written": len(written),
                "image_sha256": hashlib.sha256(written).hexdigest(),
            }

        if "verify" in bound:
            await self._before("verify", None, length)
            observed = self.flash_state.read(self.image_store, offset, length)
            steps["verify"] = {
                "verify_address": address,
                "bytes_verified": len(observed),
                "readback_sha256": hashlib.sha256(observed).hexdigest(),
            }
            if observed != image:
                raise PlasmaError(
                    ErrorCode.VERIFY_FAILED,
                    "mock verify read back something other than the Job Image",
                    recoverable=True,
                    context={"operations": list(bound), "steps": steps,
                             "address": address, "failure_source": "mismatch"},
                )

        if not self._close_site():
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "mock closing step did not leave the Site safe",
                context={"operations": list(bound), "steps": steps, "safe_off": False},
            )
        if progress:
            await progress(length, length)
        return {
            "result": "PASS",
            "operations": list(bound),
            "steps": steps,
            "load_address": address,
            "icpn": binding.get("icpn"),
            "safe_off": True,
        }

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
        # The Runtime context never outlives the Job it was bound for.
        self._context = None
        self.shutdown_count += 1
        await asyncio.sleep(0)
