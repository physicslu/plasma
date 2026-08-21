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
from .failure_policy import failure_source


PROTOCOL_VERSION = "3.3"
JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LOCAL_MOCK_BLOB_SCHEME = "local_mock_blob"
RESERVED_METADATA_KEYS = frozenset(
    {
        "protocol_version",
        "message_type",
        "job_id",
        "site_id",
        "operation",
        "timeout_s",
        "max_retries",
        "retry_backoff_s",
        "client_id",
        "target",
        "image_size",
        "image_sha256",
        "execution_image_ref",
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


@dataclass(frozen=True, slots=True)
class ExecutionImageRef:
    """Reference to an immutable execution image already available to a PPU runtime.

    Phase 1 supports only ``local_mock_blob``. The contract carries a content
    identity and size, never a filesystem path. Real PPUs may continue using
    inline Protocol v3.3 binary without implementing this optional capability.
    """

    scheme: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if self.scheme != LOCAL_MOCK_BLOB_SCHEME:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"unsupported execution image reference scheme: {self.scheme!r}",
            )
        if not isinstance(self.sha256, str) or SHA256_PATTERN.fullmatch(self.sha256) is None:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid execution image reference SHA-256")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes <= 0
        ):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "execution image reference size_bytes must be a positive integer",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ExecutionImageRef":
        if not isinstance(value, dict):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "execution_image_ref must be an object")
        unknown = sorted(set(value) - {"scheme", "sha256", "size_bytes"})
        missing = sorted({"scheme", "sha256", "size_bytes"} - set(value))
        if unknown or missing:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "execution_image_ref has invalid fields",
                context={"unknown_fields": unknown, "missing_fields": missing},
            )
        return cls(
            scheme=str(value["scheme"]),
            sha256=str(value["sha256"]),
            size_bytes=value["size_bytes"],
        )


@dataclass(slots=True)
class ErrorDetail:
    error_code: str
    error_type: str
    message: str
    recoverable: bool
    failure_source: str | None = None
    timestamp: str = field(default_factory=iso_now)
    site_id: int | None = None
    job_id: str | None = None
    operation: str | None = None
    retry_count: int = 0
    original_exception: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_exception(
        cls,
        error: PlasmaError,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
        operation: Operation | str | None = None,
        retry_count: int = 0,
    ) -> "ErrorDetail":
        resolved_site = validate_site_id(site_id) if site_id is not None else None
        return cls(
            error_code=error.code.value,
            error_type=error.error_type,
            message=error.message,
            recoverable=error.recoverable,
            failure_source=failure_source(error),
            site_id=resolved_site,
            job_id=job_id,
            operation=operation.value if isinstance(operation, Operation) else operation,
            retry_count=retry_count,
            original_exception=error.original_exception,
            context=dict(error.context),
        )

    def to_dict(self, protocol_version: str = PROTOCOL_VERSION) -> dict[str, Any]:
        data = asdict(self)
        data["error_type"] = error_name(ErrorCode(self.error_code), protocol_version)
        return data


@dataclass(slots=True)
class JobAttemptResult:
    attempt: int
    state: JobState
    started_at: str
    finished_at: str
    elapsed_ms: int
    retry_scheduled: bool = False
    error: ErrorDetail | None = None

    def to_dict(self, protocol_version: str = PROTOCOL_VERSION) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        if self.error is not None:
            data["error"] = self.error.to_dict(protocol_version)
        return data


@dataclass(slots=True, init=False)
class JobRequest:
    site_id: int
    operation: Operation
    image: bytes
    image_ref: ExecutionImageRef | None
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
        site_id: int,
        operation: Operation,
        image: bytes = b"",
        image_ref: ExecutionImageRef | None = None,
        map_data: dict[str, Any] | None = None,
        job_id: str | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 0,
        retry_backoff_s: float = 0.05,
        client_id: str = "local",
        target: str = "STM32F103C8T6",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.site_id = validate_site_id(site_id)
        self.operation = operation
        self.image = image
        self.image_ref = image_ref
        self.map_data = dict(map_data or {})
        self.job_id = job_id or new_job_id()
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s
        self.client_id = client_id
        self.target = target
        self.metadata = dict(metadata or {})
        self.validate()

    def validate(self) -> None:
        validate_site_id(self.site_id)
        if not isinstance(self.operation, Operation):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "operation must be a valid Operation")
        validate_job_id(self.job_id)
        if not isinstance(self.image, bytes):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "image must be bytes")
        if self.image_ref is not None and not isinstance(self.image_ref, ExecutionImageRef):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "image_ref must be an ExecutionImageRef")
        if self.image and self.image_ref is not None:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "inline image and execution image reference are mutually exclusive",
            )
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
    def image_size(self) -> int:
        return self.image_ref.size_bytes if self.image_ref is not None else len(self.image)

    @property
    def has_image(self) -> bool:
        return self.image_ref is not None or bool(self.image)

    @property
    def image_sha256(self) -> str:
        if self.image_ref is not None:
            return self.image_ref.sha256
        return hashlib.sha256(self.image).hexdigest()

    def protocol_metadata(self, protocol_version: str = PROTOCOL_VERSION) -> dict[str, Any]:
        self.validate()
        if protocol_version != PROTOCOL_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported protocol version: {protocol_version!r}",
            )
        result: dict[str, Any] = {
            **self.metadata,
            "protocol_version": protocol_version,
            "message_type": "request",
            "job_id": self.job_id,
            "site_id": self.site_id,
            "operation": self.operation.value,
            "timeout_s": self.timeout_s,
            "max_retries": self.max_retries,
            "retry_backoff_s": self.retry_backoff_s,
            "client_id": self.client_id,
            "target": self.target,
            "image_size": self.image_size,
            "image_sha256": self.image_sha256,
        }
        if self.image_ref is not None:
            result["execution_image_ref"] = self.image_ref.to_dict()
        return result


@dataclass(slots=True)
class ExecutionOutput:
    read_sections: dict[str, bytes] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JobResult:
    job_id: str
    site_id: int
    operation: Operation
    state: JobState
    created_at: str = ""
    started_at: str | None = None
    finished_at: str = ""
    elapsed_ms: int = 0
    attempts: int = 0
    retry_exhausted: bool = False
    attempt_history: list[JobAttemptResult] = field(default_factory=list)
    image_name: str | None = None
    image_size: int = 0
    image_sha256: str | None = None
    output_files: list[str] = field(default_factory=list)
    error: ErrorDetail | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.site_id = validate_site_id(self.site_id)
        self.attempt_history = list(self.attempt_history)
        self.output_files = list(self.output_files)
        self.details = dict(self.details)

    @property
    def success(self) -> bool:
        return self.state is JobState.SUCCESS

    def to_dict(self, protocol_version: str = PROTOCOL_VERSION) -> dict[str, Any]:
        if protocol_version != PROTOCOL_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported protocol version: {protocol_version!r}",
            )
        data = asdict(self)
        data["operation"] = self.operation.value
        data["state"] = self.state.value
        data["attempt_history"] = [item.to_dict(protocol_version) for item in self.attempt_history]
        if self.error is not None:
            data["error"] = self.error.to_dict(protocol_version)
        return data
