from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import struct
from dataclasses import dataclass, field
from typing import Any

from .errors import ErrorCode, PlasmaError

PROTOCOL_VERSION = "3.3"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({PROTOCOL_VERSION})
MAGIC = b"PLASMA33"
HEADER = struct.Struct("!8sIII")


@dataclass(frozen=True, slots=True)
class ProtocolLimits:
    metadata: int = 65_536
    map_data: int = 1_048_576
    binary: int = 67_108_864


@dataclass(slots=True)
class Frame:
    metadata: dict[str, Any]
    map_data: dict[str, Any] = field(default_factory=dict)
    binary: bytes = b""


def _json_bytes(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlasmaError(
            ErrorCode.PROTOCOL_JSON_INVALID,
            "frame contains non-JSON data",
            original_exception=exc,
        ) from exc


def encode_frame(frame: Frame, limits: ProtocolLimits = ProtocolLimits()) -> bytes:
    metadata = dict(frame.metadata)
    metadata.setdefault("protocol_version", PROTOCOL_VERSION)
    version = metadata.get("protocol_version")
    if version != PROTOCOL_VERSION:
        raise PlasmaError(
            ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
            f"unsupported protocol version: {version!r}",
        )
    metadata_bytes = _json_bytes(metadata)
    map_bytes = _json_bytes(frame.map_data) if frame.map_data else b""
    lengths = (len(metadata_bytes), len(map_bytes), len(frame.binary))
    _validate_lengths(lengths, limits)
    return HEADER.pack(MAGIC, *lengths) + metadata_bytes + map_bytes + frame.binary


def _validate_lengths(lengths: tuple[int, int, int], limits: ProtocolLimits) -> None:
    names = ("metadata", "map", "binary")
    maxima = (limits.metadata, limits.map_data, limits.binary)
    for name, size, maximum in zip(names, lengths, maxima, strict=True):
        if size > maximum:
            raise PlasmaError(
                ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE,
                f"{name} payload is {size} bytes; limit is {maximum}",
                context={"payload": name, "size": size, "limit": maximum},
            )


def _decode_json(data: bytes, label: str) -> dict[str, Any]:
    if not data:
        return {}
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlasmaError(
            ErrorCode.PROTOCOL_JSON_INVALID,
            f"invalid {label} JSON",
            original_exception=exc,
        ) from exc
    if not isinstance(value, dict):
        raise PlasmaError(ErrorCode.PROTOCOL_JSON_INVALID, f"{label} JSON must be an object")
    return value


def decode_frame_bytes(data: bytes, limits: ProtocolLimits = ProtocolLimits()) -> Frame:
    if len(data) < HEADER.size:
        raise PlasmaError(ErrorCode.PROTOCOL_INCOMPLETE, "incomplete protocol header")
    magic, metadata_len, map_len, binary_len = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise PlasmaError(ErrorCode.PROTOCOL_HEADER_INVALID, "invalid protocol magic")
    lengths = (metadata_len, map_len, binary_len)
    _validate_lengths(lengths, limits)
    expected = HEADER.size + sum(lengths)
    if len(data) != expected:
        raise PlasmaError(
            ErrorCode.PROTOCOL_INCOMPLETE,
            f"frame length mismatch: expected {expected}, received {len(data)}",
        )
    cursor = HEADER.size
    metadata_raw = data[cursor : cursor + metadata_len]
    cursor += metadata_len
    map_raw = data[cursor : cursor + map_len]
    cursor += map_len
    frame = Frame(
        metadata=_decode_json(metadata_raw, "metadata"),
        map_data=_decode_json(map_raw, "map"),
        binary=data[cursor : cursor + binary_len],
    )
    _validate_frame(frame)
    return frame


async def read_frame(
    reader: asyncio.StreamReader,
    limits: ProtocolLimits = ProtocolLimits(),
) -> Frame:
    try:
        header = await reader.readexactly(HEADER.size)
    except asyncio.IncompleteReadError as exc:
        raise PlasmaError(
            ErrorCode.PROTOCOL_INCOMPLETE,
            "connection ended before the protocol header was complete",
            original_exception=exc,
        ) from exc
    magic, metadata_len, map_len, binary_len = HEADER.unpack(header)
    if magic != MAGIC:
        raise PlasmaError(ErrorCode.PROTOCOL_HEADER_INVALID, "invalid protocol magic")
    lengths = (metadata_len, map_len, binary_len)
    _validate_lengths(lengths, limits)
    try:
        metadata_raw = await reader.readexactly(metadata_len)
        map_raw = await reader.readexactly(map_len)
        binary = await reader.readexactly(binary_len)
    except asyncio.IncompleteReadError as exc:
        raise PlasmaError(
            ErrorCode.PROTOCOL_INCOMPLETE,
            "connection ended before the frame payload was complete",
            original_exception=exc,
        ) from exc
    frame = Frame(
        metadata=_decode_json(metadata_raw, "metadata"),
        map_data=_decode_json(map_raw, "map"),
        binary=binary,
    )
    _validate_frame(frame)
    return frame


def _validate_frame(frame: Frame) -> None:
    version = frame.metadata.get("protocol_version")
    if version != PROTOCOL_VERSION:
        raise PlasmaError(
            ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
            f"unsupported protocol version: {version!r}",
        )
    expected_size = frame.metadata.get("image_size")
    if expected_size is not None:
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
            raise PlasmaError(ErrorCode.PROTOCOL_HEADER_INVALID, "image_size must be a non-negative integer")
        if expected_size != len(frame.binary):
            raise PlasmaError(
                ErrorCode.PROTOCOL_INCOMPLETE,
                "image_size does not match BINLEN",
                context={"image_size": expected_size, "binlen": len(frame.binary)},
            )
    expected_hash = frame.metadata.get("image_sha256")
    if expected_hash is not None:
        if (
            not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in expected_hash)
        ):
            raise PlasmaError(
                ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
                "image_sha256 must be a 64-digit hexadecimal SHA-256 value",
            )
        actual_hash = hashlib.sha256(frame.binary).hexdigest()
        if not hmac.compare_digest(expected_hash.lower(), actual_hash):
            raise PlasmaError(
                ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
                "image SHA-256 does not match metadata",
                context={"expected": expected_hash, "actual": actual_hash},
            )
