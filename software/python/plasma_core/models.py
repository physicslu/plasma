from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .enums import JobState, Operation
from .errors import ErrorCode, PlasmaError, error_name


JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RESERVED_METADATA_KEYS = frozenset(
    {
        "protocol_version",
        "message_type",
        "job_id",
        "site_id",
        "channel_id",
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


def validate_site_id(site_id: int) -> int:
    if isinstance(site_id, bool) or not isinstance(site_id, int) or site_id < 1:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "site_id must be a positive integer starting at 1")
    return site_id


def site_id_from_legacy_channel(channel_id: int) -> int:
    if isinstance(channel_id, bool) or not isinstance(channel_id, int) or channel_id < 0:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "channel_id must be a non-negative integer")
    return channel_id + 1


def legacy_channel_id_from_site(site_id: int) -> int:
    return validate_site_id(site_id) - 1


def _resolve_site_identity(site_id: int | None, channel_id: int | None) -> int:
    if site_id is None and channel_id is None:
        raise TypeError("site_id is required")
    canonical = validate_site_id(site_id) if site_id is not None else None
    legacy = site_id_from_legacy_channel(channel_id) if channel_id is not None else None
    if canonical is not None and legacy is not None and canonical != legacy:
        raise TypeError("site_id and legacy channel_id disagree")
    return canonical if canonical is not None else legacy  # type: ignore[return-value]


@dataclass(slots=True)
class ErrorDetail:
    error_code: str
    error_type: str
    message: str
    recoverable: bool
    timestamp: str = field(default_factory=iso_now)
    site_id: int | None = None
    job_id: str | None = None
    operation: str | None = None
    retry_count: int = 0
    original_exception: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def channel_id(self) -> int | None:
        """Legacy v3.1 identity derived from the canonical one-based Site ID."""
        return legacy_channel_id_from_site(self.site_id) if self.site_id is not None else None

    @classmethod
    def from_exception(
        cls,
        error: PlasmaError,
        *,
        site_id: int | None = None,
        channel_id: int | None = None,
        job_id: str | None = None,
        operation: Operation | str | None = None,
        retry_count: int = 0,
    ) -> "ErrorDetail":
        resolved_site = (
            _resolve_site_identity(site_id, channel_id)
            if site_id is not None or channel_id is not None
            else None
        )
        return cls(
            error_code=error.code.value,
            error_type=error.error_type,
            message=error.message,
            recoverable=error.recoverable,
            site_id=resolved_site,
            job_id=job_id,
            operation=operation.value if isinstance(operation, Operation) else operation,
            retry_count=retry_count,
            original_exception=error.original_exception,
            context=dict(error.context),
        )

    def to_dict(self, protocol_version: str = "3.2") -> dict[str, Any]:
        data = asdict(self)
        try:
            data["error_type"] = error_name(ErrorCode(self.error_code), protocol_version)
        except ValueError:
            pass
        if protocol_version == "3.1":
            data["channel_id"] = self.channel_id
            data.pop("site_id", None)
        return data


@dataclass(slots=True, init=False)
class JobRequest:
    site_id: int
    operation: Operation
    firmware: bytes
    map_data: dict[str, Any]
    job_id: str
    timeout_s: float
    max_retries: int
    retry_backoff_s: float
    client_id: str
    target: str
    metadata: dict[str, Any]

    def __init__(
        self,
        site_id: int | None = None,
        operation: Operation | None = None,
        firmware: bytes = b"",
        map_data: dict[str, Any] | None = None,
        job_id: str | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 0,
        retry_backoff_s: float = 0.05,
        client_id: str = "local",
        target: str = "STM32F103C8T6",
        metadata: dict[str, Any] | None = None,
        *,
        channel_id: int | None = None,
    ) -> None:
        self.site_id = _resolve_site_identity(site_id, channel_id)
        self.operation = operation  # type: ignore[assignment]
        self.firmware = firmware
        self.map_data = dict(map_data or {})
        self.job_id = job_id or new_job_id()
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s
        self.client_id = client_id
        self.target = target
        self.metadata = dict(metadata or {})
        self.validate()

    @property
    def channel_id(self) -> int:
        """Legacy v3.1 channel identity. New code must use site_id."""
        return legacy_channel_id_from_site(self.site_id)

    def validate(self) -> None:
        validate_site_id(self.site_id)
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

    def protocol_metadata(self, protocol_version: str = "3.2") -> dict[str, Any]:
        self.validate()
        if protocol_version not in {"3.1", "3.2"}:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported protocol version: {protocol_version!r}",
            )
        identity = (
            {"site_id": self.site_id}
            if protocol_version == "3.2"
            else {"channel_id": self.channel_id}
        )
        return {
            **self.metadata,
            "protocol_version": protocol_version,
            "message_type": "request",
            "job_id": self.job_id,
            **identity,
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


@dataclass(slots=True, init=False)
class JobResult:
    job_id: str
    site_id: int
    operation: Operation
    state: JobState
    created_at: str
    started_at: str | None
    finished_at: str
    elapsed_ms: int
    attempts: int
    firmware_name: str | None
    firmware_size: int
    firmware_sha256: str | None
    output_files: list[str]
    error: ErrorDetail | None
    details: dict[str, Any]

    def __init__(
        self,
        job_id: str,
        site_id: int | None = None,
        operation: Operation | None = None,
        state: JobState | None = None,
        created_at: str = "",
        started_at: str | None = None,
        finished_at: str = "",
        elapsed_ms: int = 0,
        attempts: int = 0,
        firmware_name: str | None = None,
        firmware_size: int = 0,
        firmware_sha256: str | None = None,
        output_files: list[str] | None = None,
        error: ErrorDetail | None = None,
        details: dict[str, Any] | None = None,
        *,
        channel_id: int | None = None,
    ) -> None:
        self.job_id = job_id
        self.site_id = _resolve_site_identity(site_id, channel_id)
        self.operation = operation  # type: ignore[assignment]
        self.state = state  # type: ignore[assignment]
        self.created_at = created_at
        self.started_at = started_at
        self.finished_at = finished_at
        self.elapsed_ms = elapsed_ms
        self.attempts = attempts
        self.firmware_name = firmware_name
        self.firmware_size = firmware_size
        self.firmware_sha256 = firmware_sha256
        self.output_files = list(output_files or [])
        self.error = error
        self.details = dict(details or {})

    @property
    def channel_id(self) -> int:
        """Legacy v3.1 channel identity. New code must use site_id."""
        return legacy_channel_id_from_site(self.site_id)

    @property
    def success(self) -> bool:
        return self.state is JobState.SUCCESS

    def to_dict(self, protocol_version: str = "3.2") -> dict[str, Any]:
        data = asdict(self)
        data["operation"] = self.operation.value
        data["state"] = self.state.value
        if self.error is not None:
            data["error"] = self.error.to_dict(protocol_version)
        if protocol_version == "3.1":
            data["channel_id"] = self.channel_id
            data.pop("site_id", None)
        return data
