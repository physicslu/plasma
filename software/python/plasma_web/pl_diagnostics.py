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
    PL_LOOPBACK_ENDPOINT,
    crc32_hex,
    require_nonnegative_int,
    require_test_id,
)
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_hw.pl_loopback import PL_LOOPBACK_MAX_PAYLOAD_BYTES

from .diagnostics import _parse_payload, _parse_timeout_ms, _require_declared_keys


async def execute_pl_loopback(
    body: dict[str, Any],
    client_factory: Callable[[], PlasmaClient],
) -> dict[str, Any]:
    """Bridge one browser payload through Gateway -> Plasma Server -> real PL.

    This qualification endpoint deliberately has no PS echo or Mock fallback.
    A PASS response must identify both endpoint and source as PL.
    """
    _require_declared_keys(body)
    if body["endpoint"] != PL_LOOPBACK_ENDPOINT:
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            f"PL qualification endpoint requires endpoint='pl': {body['endpoint']!r}",
        )
    test_id = require_test_id(body["test_id"])
    sequence = require_nonnegative_int(body["sequence"], "sequence")
    if sequence > 0xFFFFFFFF:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PL loopback sequence must fit uint32")
    timeout_ms = _parse_timeout_ms(body["timeout_ms"])
    pattern = body["pattern"]
    seed = body["seed"]
    if not isinstance(pattern, str) or not pattern or len(pattern) > 128:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "pattern must be a non-empty string of at most 128 characters")
    if not isinstance(seed, str) or len(seed) > 128:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "seed must be a string of at most 128 characters")
    payload, tx_crc32 = _parse_payload(body)
    if len(payload) > PL_LOOPBACK_MAX_PAYLOAD_BYTES:
        raise PlasmaError(
            ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE,
            f"PL Loopback qualification payload is limited to {PL_LOOPBACK_MAX_PAYLOAD_BYTES} bytes",
        )

    started_at = time.monotonic()
    response, returned = await client_factory().diagnostic_loopback(
        payload,
        test_id=test_id,
        sequence=sequence,
        endpoint=PL_LOOPBACK_ENDPOINT,
        pattern=pattern,
        seed=seed,
        response_timeout_s=timeout_ms / 1000.0,
    )
    ppu_rtt_ms = round((time.monotonic() - started_at) * 1000, 3)

    expected = {
        "message_type": DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
        "diagnostic_type": LOOPBACK_DIAGNOSTIC_TYPE,
        "diagnostic_version": DIAGNOSTIC_PROTOCOL_VERSION,
        "endpoint": PL_LOOPBACK_ENDPOINT,
        "source": PL_LOOPBACK_ENDPOINT,
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
                f"Plasma Server PL diagnostic response has invalid {field}",
                context={"expected": value, "actual": response.get(field)},
            )

    if returned != payload:
        mismatch = next(
            (
                index
                for index, (expected_byte, actual_byte) in enumerate(zip(payload, returned))
                if expected_byte != actual_byte
            ),
            min(len(payload), len(returned)),
        )
        raise PlasmaError(
            ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
            "PL Loopback returned payload does not match transmitted payload",
            context={
                "first_mismatch": mismatch,
                "expected_length": len(payload),
                "actual_length": len(returned),
            },
        )
    rx_crc32 = crc32_hex(returned)
    if response.get("rx_crc32") != rx_crc32 or rx_crc32 != tx_crc32:
        raise PlasmaError(
            ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
            "PL Loopback response CRC32 does not match returned payload",
            context={"declared": response.get("rx_crc32"), "actual": rx_crc32},
        )

    return {
        "ok": True,
        "diagnostic_protocol_version": DIAGNOSTIC_PROTOCOL_VERSION,
        "loopback": {
            "endpoint": PL_LOOPBACK_ENDPOINT,
            "source": PL_LOOPBACK_ENDPOINT,
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
