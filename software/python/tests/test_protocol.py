from __future__ import annotations

import asyncio
import hashlib
import struct
import unittest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.protocol import (
    HEADER,
    MAGIC,
    Frame,
    ProtocolLimits,
    decode_frame_bytes,
    encode_frame,
    read_frame,
)


class ProtocolTests(unittest.TestCase):
    def test_round_trip_with_map_and_binary(self) -> None:
        binary = bytes(range(64))
        frame = Frame(
            metadata={
                "protocol_version": "3.1",
                "operation": "program",
                "firmware_sha256": hashlib.sha256(binary).hexdigest(),
            },
            map_data={"sections": [{"address": 0, "length": 64}]},
            binary=binary,
        )
        decoded = decode_frame_bytes(encode_frame(frame))
        self.assertEqual(decoded.binary, binary)
        self.assertEqual(decoded.map_data, frame.map_data)
        self.assertEqual(decoded.metadata["operation"], "program")

    def test_invalid_magic(self) -> None:
        data = bytearray(encode_frame(Frame(metadata={"protocol_version": "3.1"})))
        data[:8] = b"NOTMAGIC"
        with self.assertRaises(PlasmaError) as caught:
            decode_frame_bytes(bytes(data))
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_HEADER_INVALID)

    def test_incomplete_payload(self) -> None:
        data = encode_frame(Frame(metadata={"protocol_version": "3.1"}, binary=b"abc"))
        with self.assertRaises(PlasmaError) as caught:
            decode_frame_bytes(data[:-1])
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_INCOMPLETE)

    def test_payload_limit(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            encode_frame(
                Frame(metadata={"protocol_version": "3.1"}, binary=b"1234"),
                ProtocolLimits(binary=3),
            )
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE)

    def test_version_rejected(self) -> None:
        data = encode_frame(Frame(metadata={"protocol_version": "2.0"}))
        with self.assertRaises(PlasmaError) as caught:
            decode_frame_bytes(data)
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_VERSION_UNSUPPORTED)

    def test_checksum_mismatch(self) -> None:
        data = encode_frame(
            Frame(
                metadata={"protocol_version": "3.1", "firmware_sha256": "0" * 64},
                binary=b"payload",
            )
        )
        with self.assertRaises(PlasmaError) as caught:
            decode_frame_bytes(data)
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_CHECKSUM_MISMATCH)

    def test_malformed_checksum_is_rejected(self) -> None:
        data = encode_frame(
            Frame(
                metadata={"protocol_version": "3.1", "firmware_sha256": "not-a-sha256"},
                binary=b"payload",
            )
        )
        with self.assertRaises(PlasmaError) as caught:
            decode_frame_bytes(data)
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_CHECKSUM_MISMATCH)

    def test_firmware_size_must_match_binary_length(self) -> None:
        data = encode_frame(
            Frame(
                metadata={"protocol_version": "3.1", "firmware_size": 99},
                binary=b"payload",
            )
        )
        with self.assertRaises(PlasmaError) as caught:
            decode_frame_bytes(data)
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_INCOMPLETE)

    def test_invalid_json(self) -> None:
        metadata = b"{not-json}"
        data = HEADER.pack(MAGIC, len(metadata), 0, 0) + metadata
        with self.assertRaises(PlasmaError) as caught:
            decode_frame_bytes(data)
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_JSON_INVALID)


class AsyncProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_async_read(self) -> None:
        encoded = encode_frame(Frame(metadata={"protocol_version": "3.1", "operation": "status"}))
        reader = asyncio.StreamReader()

        async def feed() -> None:
            for offset in range(0, len(encoded), 3):
                reader.feed_data(encoded[offset : offset + 3])
                await asyncio.sleep(0)
            reader.feed_eof()

        feeder = asyncio.create_task(feed())
        frame = await read_frame(reader)
        await feeder
        self.assertEqual(frame.metadata["operation"], "status")

    async def test_async_incomplete_header(self) -> None:
        reader = asyncio.StreamReader()
        reader.feed_data(b"PLAS")
        reader.feed_eof()
        with self.assertRaises(PlasmaError) as caught:
            await read_frame(reader)
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_INCOMPLETE)
