from __future__ import annotations

import re
import zlib
from typing import Any

from .errors import ErrorCode, PlasmaError


DIAGNOSTIC_PROTOCOL_VERSION = "1"
DIAGNOSTIC_REQUEST_MESSAGE_TYPE = "diagnostic_request"
DIAGNOSTIC_RESPONSE_MESSAGE_TYPE = "diagnostic_response"
LOOPBACK_DIAGNOSTIC_TYPE = "loopback"
PS_LOOPBACK_ENDPOINT = "ps"
ECHO_TRANSFORM = "echo"
MAX_LOOPBACK_TEST_ID_LENGTH = 128
CRC32_PATTERN = re.compile(r"^[0-9a-f]{8}$")


def crc32_hex(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def require_nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"{field} must be a non-negative integer")
    return value


def require_positive_int(value: Any, field: str) -> int:
    parsed = require_nonnegative_int(value, field)
    if parsed <= 0:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"{field} must be a positive integer")
    return parsed


def require_test_id(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_LOOPBACK_TEST_ID_LENGTH:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"test_id must be a non-empty string of at most {MAX_LOOPBACK_TEST_ID_LENGTH} characters",
        )
    return value


def require_crc32(value: Any, field: str) -> str:
    if not isinstance(value, str) or CRC32_PATTERN.fullmatch(value) is None:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"{field} must be an 8-character lowercase CRC32 hex string")
    return value
