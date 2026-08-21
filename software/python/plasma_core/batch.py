from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .enums import Operation
from .errors import ErrorCode, PlasmaError


MAX_BATCH_REPEAT_COUNT = 10_000
MAX_BATCH_SITE_RETRY_LIMIT = 20


class BatchState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    STOPPING = "stopping"
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {
            BatchState.SUCCESS,
            BatchState.PARTIAL,
            BatchState.ERROR,
            BatchState.CANCELLED,
        }


class BatchSiteState(StrEnum):
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAULTED = "faulted"
    ERROR = "error"
    STOPPED = "stopped"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {
            BatchSiteState.SUCCESS,
            BatchSiteState.FAULTED,
            BatchSiteState.ERROR,
            BatchSiteState.STOPPED,
            BatchSiteState.CANCELLED,
        }


@dataclass(frozen=True, slots=True)
class BatchExecutionPolicy:
    """Immutable execution policy bound to one Batch.

    ``site_retry_limit`` is the number of retries after the first attempt. A
    value of 2 therefore permits at most three attempts for one operation.

    ``failed_site_stop_threshold`` is fail-closed: once the number of FAULTED
    Sites is greater than or equal to the configured threshold, the Batch
    enters STOPPING and terminates as ERROR. ``None`` disables this circuit
    breaker.
    """

    repeat_count: int = 1
    site_retry_limit: int = 0
    failed_site_stop_threshold: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.repeat_count, bool)
            or not isinstance(self.repeat_count, int)
            or self.repeat_count < 1
            or self.repeat_count > MAX_BATCH_REPEAT_COUNT
        ):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"repeat_count must be an integer between 1 and {MAX_BATCH_REPEAT_COUNT}",
            )
        if (
            isinstance(self.site_retry_limit, bool)
            or not isinstance(self.site_retry_limit, int)
            or self.site_retry_limit < 0
            or self.site_retry_limit > MAX_BATCH_SITE_RETRY_LIMIT
        ):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"site_retry_limit must be an integer between 0 and {MAX_BATCH_SITE_RETRY_LIMIT}",
            )
        threshold = self.failed_site_stop_threshold
        if threshold is not None and (
            isinstance(threshold, bool)
            or not isinstance(threshold, int)
            or threshold < 1
        ):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "failed_site_stop_threshold must be null or a positive integer",
            )

    def validate_target_count(self, target_count: int) -> None:
        if target_count < 1:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch requires at least one Site")
        threshold = self.failed_site_stop_threshold
        if threshold is not None and threshold > target_count:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "failed_site_stop_threshold cannot exceed selected Site count",
                context={"threshold": threshold, "selected_sites": target_count},
            )

    def to_dict(self) -> dict[str, int | None]:
        return {
            "repeat_count": self.repeat_count,
            "site_retry_limit": self.site_retry_limit,
            "failed_site_stop_threshold": self.failed_site_stop_threshold,
        }


@dataclass(frozen=True, slots=True)
class BatchTarget:
    facility_id: str
    ppu_id: str
    site_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.facility_id, str) or not self.facility_id.strip():
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch target facility_id is required")
        if not isinstance(self.ppu_id, str) or not self.ppu_id.strip():
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch target ppu_id is required")
        if isinstance(self.site_id, bool) or not isinstance(self.site_id, int) or self.site_id < 1:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch target site_id must start at 1")

    @property
    def key(self) -> str:
        return f"{self.facility_id}::{self.ppu_id}::SITE{self.site_id}"

    @property
    def ppu_key(self) -> str:
        return f"{self.facility_id}::{self.ppu_id}"

    def to_dict(self) -> dict[str, str | int]:
        return {
            "facility_id": self.facility_id,
            "ppu_id": self.ppu_id,
            "site_id": self.site_id,
        }


def normalize_batch_operations(values: list[str] | tuple[str, ...]) -> tuple[Operation, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch requires at least one operation")
    try:
        requested = {Operation(str(value)) for value in values}
    except ValueError as exc:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch contains an unsupported operation") from exc
    supported = {Operation.ERASE, Operation.PROGRAM, Operation.VERIFY, Operation.READ}
    if not requested.issubset(supported):
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch supports only Erase, Program, Verify, and Read")
    canonical = (Operation.ERASE, Operation.PROGRAM, Operation.VERIFY, Operation.READ)
    return tuple(operation for operation in canonical if operation in requested)
