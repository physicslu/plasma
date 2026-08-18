from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "E1001"
    CONFIG_INVALID = "E1002"
    CONNECTION_FAILED = "E2001"
    CONNECTION_TIMEOUT = "E2002"
    PROTOCOL_HEADER_INVALID = "E3001"
    PROTOCOL_INCOMPLETE = "E3002"
    PROTOCOL_VERSION_UNSUPPORTED = "E3003"
    PROTOCOL_PAYLOAD_TOO_LARGE = "E3004"
    PROTOCOL_JSON_INVALID = "E3005"
    PROTOCOL_CHECKSUM_MISMATCH = "E3006"
    SITE_INVALID = "E4001"
    SITE_DISABLED = "E4002"
    SITE_BUSY = "E4003"
    # Legacy symbolic aliases. E400x values and serialized error_type names are
    # retained for v3.1 compatibility while Site is canonical in Python code.
    CHANNEL_INVALID = "E4001"
    CHANNEL_DISABLED = "E4002"
    CHANNEL_BUSY = "E4003"
    JOB_NOT_FOUND = "E4004"
    OPERATION_UNSUPPORTED = "E4005"
    DUPLICATE_JOB = "E4006"
    TARGET_NOT_FOUND = "E5001"
    INTERFACE_FAILURE = "E5002"
    INTERFACE_NOT_CONFIGURED = "E5003"
    ERASE_FAILED = "E6001"
    PROGRAM_FAILED = "E6002"
    VERIFY_FAILED = "E6003"
    READ_FAILED = "E6004"
    OPERATION_TIMEOUT = "E7001"
    OPERATION_CANCELLED = "E7002"
    OUTPUT_WRITE_FAILED = "E8001"
    INTERNAL_ERROR = "E9001"
    JOB_ABORTED = "E9002"


ERROR_NAMES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_ARGUMENT: "INVALID_ARGUMENT",
    ErrorCode.CONFIG_INVALID: "CONFIG_INVALID",
    ErrorCode.CONNECTION_FAILED: "CONNECTION_FAILED",
    ErrorCode.CONNECTION_TIMEOUT: "CONNECTION_TIMEOUT",
    ErrorCode.PROTOCOL_HEADER_INVALID: "PROTOCOL_HEADER_INVALID",
    ErrorCode.PROTOCOL_INCOMPLETE: "PROTOCOL_INCOMPLETE",
    ErrorCode.PROTOCOL_VERSION_UNSUPPORTED: "PROTOCOL_VERSION_UNSUPPORTED",
    ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE: "PROTOCOL_PAYLOAD_TOO_LARGE",
    ErrorCode.PROTOCOL_JSON_INVALID: "PROTOCOL_JSON_INVALID",
    ErrorCode.PROTOCOL_CHECKSUM_MISMATCH: "PROTOCOL_CHECKSUM_MISMATCH",
    # Keep the published v3.1 error_type strings stable even though Python
    # code now uses ErrorCode.SITE_* as the canonical symbolic names.
    ErrorCode.SITE_INVALID: "CHANNEL_INVALID",
    ErrorCode.SITE_DISABLED: "CHANNEL_DISABLED",
    ErrorCode.SITE_BUSY: "CHANNEL_BUSY",
    ErrorCode.JOB_NOT_FOUND: "JOB_NOT_FOUND",
    ErrorCode.OPERATION_UNSUPPORTED: "OPERATION_UNSUPPORTED",
    ErrorCode.DUPLICATE_JOB: "DUPLICATE_JOB",
    ErrorCode.TARGET_NOT_FOUND: "TARGET_NOT_FOUND",
    ErrorCode.INTERFACE_FAILURE: "INTERFACE_FAILURE",
    ErrorCode.INTERFACE_NOT_CONFIGURED: "INTERFACE_NOT_CONFIGURED",
    ErrorCode.ERASE_FAILED: "ERASE_FAILED",
    ErrorCode.PROGRAM_FAILED: "PROGRAM_FAILED",
    ErrorCode.VERIFY_FAILED: "VERIFY_FAILED",
    ErrorCode.READ_FAILED: "READ_FAILED",
    ErrorCode.OPERATION_TIMEOUT: "OPERATION_TIMEOUT",
    ErrorCode.OPERATION_CANCELLED: "OPERATION_CANCELLED",
    ErrorCode.OUTPUT_WRITE_FAILED: "OUTPUT_WRITE_FAILED",
    ErrorCode.INTERNAL_ERROR: "INTERNAL_ERROR",
    ErrorCode.JOB_ABORTED: "JOB_ABORTED",
}


class PlasmaError(Exception):
    """A stable, serializable error crossing Plasma module boundaries."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        recoverable: bool = False,
        original_exception: BaseException | str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.error_type = ERROR_NAMES[code]
        self.message = message
        self.recoverable = recoverable
        self.original_exception = (
            type(original_exception).__name__ + ": " + str(original_exception)
            if isinstance(original_exception, BaseException)
            else original_exception
        )
        self.context = context or {}

    def with_context(self, **values: Any) -> "PlasmaError":
        self.context.update({key: value for key, value in values.items() if value is not None})
        return self
