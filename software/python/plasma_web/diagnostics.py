from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any

from plasma_client.client import PlasmaClient
from plasma_core.diagnostics import (
    DIAGNOSTIC_PROTOCOL_VERSION,
    DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
    ECHO_TRANSFORM,
    LOOPBACK_DIAGNOSTIC_TYPE,
    PS_LOOPBACK_ENDPOINT,
    crc32_hex,
    require_crc32,
    require_nonnegative_int,
    require_positive_int,
    require_test_id,
)
from plasma_core.errors import ErrorCode, PlasmaError


MAX_LOOPBACK_PAYLOAD_BYTES = 4 * 1024 * 1024
MIN_LOOPBACK_TIMEOUT_MS = 100
MAX_LOOPBACK_TIMEOUT_MS = 120_000


def _require_declared_keys(values: dict[str, Any]) -> None:
    required = {
        "endpoint",
        "test_id",
        "sequence",
        "pattern",
        "seed",
        "payload_length",
        "payload_base64",
        "tx_crc32",
        "timeout_ms",
    }
    unknown = sorted(set(values) - required)
    missing = sorted(required - set(values))
    if unknown:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"Loopback request contains unexpected fields: {', '.join(unknown)}",
        )
    if missing:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"Loopback request is missing required fields: {', '.join(missing)}",
        )


def _parse_timeout_ms(value: Any) -> int:
    timeout_ms = require_positive_int(value, "timeout_ms")
    if timeout_ms < MIN_LOOPBACK_TIMEOUT_MS or timeout_ms > MAX_LOOPBACK_TIMEOUT_MS:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"timeout_ms must be between {MIN_LOOPBACK_TIMEOUT_MS} and {MAX_LOOPBACK_TIMEOUT_MS}",
        )
    return timeout_ms


def _parse_payload(body: dict[str, Any]) -> tuple[bytes, str]:
    encoded = body["payload_base64"]
    if not isinstance(encoded, str) or not encoded:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "payload_base64 must be a non-empty string")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            "payload_base64 is invalid",
            original_exception=exc,
        ) from exc
    declared_length = require_positive_int(body["payload_length"], "payload_length")
    if declared_length != len(payload):
        raise PlasmaError(
            ErrorCode.PROTOCOL_INCOMPLETE,
            "payload_length does not match decoded Loopback payload",
            context={"declared": declared_length, "actual": len(payload)},
        )
    if declared_length > MAX_LOOPBACK_PAYLOAD_BYTES:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"Loopback payload exceeds the V1 transport limit of {MAX_LOOPBACK_PAYLOAD_BYTES} bytes",
        )
    declared_crc = require_crc32(body["tx_crc32"], "tx_crc32")
    actual_crc = crc32_hex(payload)
    if declared_crc != actual_crc:
        raise PlasmaError(
            ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
            "tx_crc32 does not match decoded Loopback payload",
            context={"expected": declared_crc, "actual": actual_crc},
        )
    return payload, actual_crc


async def execute_ps_loopback(
    body: dict[str, Any],
    client_factory: Callable[[], PlasmaClient],
) -> dict[str, Any]:
    """Bridge one Browser payload through the real Gateway -> Plasma Server path.

    This code deliberately has no Engineering Provider or Mock runtime fallback.
    If the local Plasma Server cannot execute the diagnostic exchange, the
    request fails instead of fabricating a PASS result.
    """
    _require_declared_keys(body)
    if body["endpoint"] != PS_LOOPBACK_ENDPOINT:
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            f"real-path loopback endpoint is not implemented: {body['endpoint']!r}",
        )
    test_id = require_test_id(body["test_id"])
    sequence = require_nonnegative_int(body["sequence"], "sequence")
    timeout_ms = _parse_timeout_ms(body["timeout_ms"])
    pattern = body["pattern"]
    seed = body["seed"]
    if not isinstance(pattern, str) or not pattern or len(pattern) > 128:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "pattern must be a non-empty string of at most 128 characters")
    if not isinstance(seed, str) or len(seed) > 128:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "seed must be a string of at most 128 characters")
    payload, tx_crc32 = _parse_payload(body)

    started_at = time.monotonic()
    response, returned = await client_factory().diagnostic_loopback(
        payload,
        test_id=test_id,
        sequence=sequence,
        endpoint=PS_LOOPBACK_ENDPOINT,
        pattern=pattern,
        seed=seed,
        response_timeout_s=timeout_ms / 1000.0,
    )
    ppu_rtt_ms = round((time.monotonic() - started_at) * 1000, 3)

    expected = {
        "message_type": DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
        "diagnostic_type": LOOPBACK_DIAGNOSTIC_TYPE,
        "diagnostic_version": DIAGNOSTIC_PROTOCOL_VERSION,
        "endpoint": PS_LOOPBACK_ENDPOINT,
        "source": PS_LOOPBACK_ENDPOINT,
        "test_id": test_id,
        "sequence": sequence,
        "transform": ECHO_TRANSFORM,
        "payload_length": len(payload),
        "tx_crc32": tx_crc32,
    }
    for field, value in expected.items():
        if response.get(field) != value:
            raise PlasmaError(
                ErrorCode.PROTOCOL_INCOMPLETE,
                f"Plasma Server diagnostic response has invalid {field}",
                context={"expected": value, "actual": response.get(field)},
            )

    if returned != payload:
        mismatch = next(
            (index for index, (expected_byte, actual_byte) in enumerate(zip(payload, returned)) if expected_byte != actual_byte),
            min(len(payload), len(returned)),
        )
        raise PlasmaError(
            ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
            "PS Loopback returned payload does not match transmitted payload",
            context={
                "first_mismatch": mismatch,
                "expected_length": len(payload),
                "actual_length": len(returned),
            },
        )
    rx_crc32 = crc32_hex(returned)
    if response.get("rx_crc32") != rx_crc32:
        raise PlasmaError(
            ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
            "Plasma Server rx_crc32 does not match returned Loopback payload",
            context={"declared": response.get("rx_crc32"), "actual": rx_crc32},
        )

    return {
        "ok": True,
        "diagnostic_protocol_version": DIAGNOSTIC_PROTOCOL_VERSION,
        "loopback": {
            "endpoint": PS_LOOPBACK_ENDPOINT,
            "source": PS_LOOPBACK_ENDPOINT,
            "test_id": test_id,
            "sequence": sequence,
            "transform": ECHO_TRANSFORM,
            "pattern": pattern,
            "seed": seed,
            "payload_length": len(payload),
            "tx_crc32": tx_crc32,
            "rx_crc32": rx_crc32,
            "ppu_rtt_ms": ppu_rtt_ms,
        },
        "payload_base64": base64.b64encode(returned).decode("ascii"),
    }
