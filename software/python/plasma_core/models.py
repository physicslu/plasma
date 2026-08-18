from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .enums import JobState, Operation
from .errors import ErrorCode, PlasmaError


JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RESERVED_METADATA_KEYS = frozenset(
    {
        "protocol_version",
        "message_type",
        "job_id",
        "channel_id",
        "site_id",
        "operation",
        "timeout_s",
        "max_retries",
        "retry_backoff_s",
        "client_id",
        "target",
        "firmware_size",
        "firmware_sha256",
        "wait_for_completion",
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def new_job_id() -> str:
    stamp = utc_now().strftime("%Y%m%d-%H%M%S")
    return f"job-{stamp}-{uuid.uuid4().hex[:8]}"


def validate_job_id(job_id: str) -> None:
    """Reject path-like or unbounded IDs before they reach logs and output paths."""
    if not isinstance(job_id, str) or JOB_ID_PATTERN.fullmatch(job_id) is None:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            "job_id must be 1-128 ASCII letters, digits, '.', '_' or '-', starting with a letter or digit",
        )


@dataclass(slots=True)
class ErrorDetail:
    error_code: str
    error_type: str
    message: str
    recoverable: bool
    timestamp: str = field(default_factory=iso_now)
    channel_id: int | None = None
    job_id: str | None = None
    operation: str | None = None
    retry_count: int = 0
    original_exception: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def site_id(self) -> int | None:
        return self.channel_id

    @classmethod
    def from_exception(
        cls,
        error: PlasmaError,
        *,
        channel_id: int | None = None,
        job_id: str | None = None,
        operation: Operation | str | None = None,
        retry_count: int = 0,
    ) -> "ErrorDetail":
        return cls(
            error_code=error.code.value,
            error_type=error.error_type,
            message=error.message,
            recoverable=error.recoverable,
            channel_id=channel_id,
            job_id=job_id,
            operation=operation.value if isinstance(operation, Operation) else operation,
            retry_count=retry_count,
            original_exception=error.original_exception,
            context=dict(error.context),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["site_id"] = self.channel_id
        return data


@dataclass(slots=True)
class JobRequest:
    # channel_id remains the Plasma v3.1 wire field. Domain/API code should
    # treat the same local resource as a Programming Site via site_id.
    channel_id: int
    operation: Operation
    firmware: bytes = b""
    map_data: dict[str, Any] = field(default_factory=dict)
    job_id: str = field(default_factory=new_job_id)
    timeout_s: float = 30.0
    max_retries: int = 0
    retry_backoff_s: float = 0.05
    client_id: str = "local"
    target: str = "STM32F103C8T6"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    @property
    def site_id(self) -> int:
        return self.channel_id

    def validate(self) -> None:
        if isinstance(self.channel_id, bool) or not isinstance(self.channel_id, int) or self.channel_id < 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "channel_id must be a non-negative integer")
        if not isinstance(self.operation, Operation):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "operation must be a valid Operation")
        validate_job_id(self.job_id)
        if not isinstance(self.firmware, bytes):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "firmware must be bytes")
        if not isinstance(self.map_data, dict):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "map_data must be an object")
        if not isinstance(self.metadata, dict):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "metadata must be an object")
        reserved = sorted(RESERVED_METADATA_KEYS.intersection(self.metadata))
        if reserved:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "metadata cannot override reserved protocol fields",
                context={"reserved_fields": reserved},
            )
        if (
            isinstance(self.timeout_s, bool)
            or not isinstance(self.timeout_s, (int, float))
            or not math.isfinite(self.timeout_s)
            or self.timeout_s <= 0
        ):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "timeout_s must be a positive finite number")
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "max_retries must be a non-negative integer")
        if (
            isinstance(self.retry_backoff_s, bool)
            or not isinstance(self.retry_backoff_s, (int, float))
            or not math.isfinite(self.retry_backoff_s)
            or self.retry_backoff_s < 0
        ):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "retry_backoff_s must be a finite non-negative number")
        if not isinstance(self.client_id, str) or not self.client_id or len(self.client_id) > 256:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "client_id must be 1-256 characters")
        if not isinstance(self.target, str) or not self.target or len(self.target) > 256:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "target must be 1-256 characters")

    @property
    def firmware_sha256(self) -> str:
        return hashlib.sha256(self.firmware).hexdigest()

    def protocol_metadata(self) -> dict[str, Any]:
        self.validate()
        return {
            **self.metadata,
            "protocol_version": "3.1",
            "message_type": "request",
            "job_id": self.job_id,
            # Deliberately preserved until a protocol-version migration.
            "channel_id": self.channel_id,
            "operation": self.operation.value,
            "timeout_s": self.timeout_s,
            "max_retries": self.max_retries,
            "retry_backoff_s": self.retry_backoff_s,
            "client_id": self.client_id,
            "target": self.target,
            "firmware_size": len(self.firmware),
            "firmware_sha256": self.firmware_sha256,
        }


@dataclass(slots=True)
class ExecutionOutput:
    read_sections: dict[str, bytes] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JobResult:
    job_id: str
    channel_id: int
    operation: Operation
    state: JobState
    created_at: str
    started_at: str | None
    finished_at: str
    elapsed_ms: int
    attempts: int
    firmware_name: str | None = None
    firmware_size: int = 0
    firmware_sha256: str | None = None
    output_files: list[str] = field(default_factory=list)
    error: ErrorDetail | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def site_id(self) -> int:
        return self.channel_id

    @property
    def success(self) -> bool:
        return self.state is JobState.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["site_id"] = self.channel_id
        data["operation"] = self.operation.value
        data["state"] = self.state.value
        return data
