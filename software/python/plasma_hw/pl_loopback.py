from __future__ import annotations

import mmap
import os
import struct
import threading
import time
import zlib
from pathlib import Path
from typing import Protocol

from plasma_core.errors import ErrorCode, PlasmaError


PL_LOOPBACK_MAGIC = 0x504C4C42
PL_LOOPBACK_VERSION = 1
PL_LOOPBACK_COMMAND_ECHO = 1
PL_LOOPBACK_CAP_CRC32 = 1 << 16
PL_LOOPBACK_CAP_ECHO = 1 << 17
PL_LOOPBACK_MAX_PAYLOAD_BYTES = 64
PL_LOOPBACK_REGISTER_WINDOW_BYTES = 0x1000

REG_MAGIC = 0x000
REG_VERSION = 0x004
REG_CAPABILITIES = 0x008
REG_CONTROL = 0x00C
REG_STATUS = 0x010
REG_COMMAND = 0x014
REG_SEQUENCE = 0x018
REG_LENGTH = 0x01C
REG_TX_CRC32 = 0x020
REG_RX_SEQUENCE = 0x024
REG_RX_LENGTH = 0x028
REG_RX_CRC32 = 0x02C
REG_ERROR_CODE = 0x030
REG_TX_DATA = 0x040
REG_RX_DATA = 0x080

CONTROL_START = 1 << 0
CONTROL_CLEAR = 1 << 1
STATUS_READY = 1 << 0
STATUS_BUSY = 1 << 1
STATUS_DONE = 1 << 2
STATUS_ERROR = 1 << 3

HW_ERROR_NONE = 0
HW_ERROR_UNSUPPORTED_COMMAND = 1
HW_ERROR_INVALID_LENGTH = 2
HW_ERROR_TX_CRC_MISMATCH = 3


class RegisterIO(Protocol):
    def read32(self, offset: int) -> int: ...

    def write32(self, offset: int, value: int) -> None: ...

    def close(self) -> None: ...


class UIORegisterIO:
    """Map one OS-owned UIO resource without exposing physical addresses upstream."""

    def __init__(
        self,
        path: str | Path,
        *,
        map_size: int = PL_LOOPBACK_REGISTER_WINDOW_BYTES,
    ) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "PL Loopback UIO path must be absolute")
        if map_size < PL_LOOPBACK_REGISTER_WINDOW_BYTES or map_size % mmap.PAGESIZE != 0:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"PL Loopback UIO map_size must be page-aligned and at least {PL_LOOPBACK_REGISTER_WINDOW_BYTES}",
            )
        try:
            self._fd = os.open(self.path, os.O_RDWR | os.O_SYNC)
            self._map = mmap.mmap(
                self._fd,
                map_size,
                flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
            )
        except OSError as exc:
            if hasattr(self, "_fd"):
                os.close(self._fd)
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                f"cannot map PL Loopback UIO resource: {self.path}",
                recoverable=True,
                original_exception=exc,
            ) from exc

    def read32(self, offset: int) -> int:
        try:
            return struct.unpack_from("<I", self._map, offset)[0]
        except (ValueError, struct.error) as exc:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                f"invalid PL Loopback register read at 0x{offset:03x}",
                original_exception=exc,
            ) from exc

    def write32(self, offset: int, value: int) -> None:
        try:
            struct.pack_into("<I", self._map, offset, value & 0xFFFFFFFF)
        except (ValueError, struct.error) as exc:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                f"invalid PL Loopback register write at 0x{offset:03x}",
                original_exception=exc,
            ) from exc

    def close(self) -> None:
        self._map.close()
        os.close(self._fd)


class PLLoopbackDevice:
    """Semantic PS/PL loopback boundary above UIO/MMIO register mechanics."""

    def __init__(
        self,
        registers: RegisterIO,
        *,
        transaction_timeout_s: float = 0.25,
        poll_interval_s: float = 0.0005,
    ) -> None:
        if transaction_timeout_s <= 0:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "PL Loopback transaction timeout must be positive")
        if poll_interval_s <= 0:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "PL Loopback poll interval must be positive")
        self.registers = registers
        self.transaction_timeout_s = transaction_timeout_s
        self.poll_interval_s = poll_interval_s
        self._lock = threading.Lock()
        self.max_payload_bytes = 0
        self.probe()

    @staticmethod
    def _crc32(payload: bytes) -> int:
        return zlib.crc32(payload) & 0xFFFFFFFF

    def probe(self) -> None:
        magic = self.registers.read32(REG_MAGIC)
        version = self.registers.read32(REG_VERSION)
        capabilities = self.registers.read32(REG_CAPABILITIES)
        if magic != PL_LOOPBACK_MAGIC:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "PL Loopback hardware identity mismatch",
                context={"expected": f"0x{PL_LOOPBACK_MAGIC:08x}", "actual": f"0x{magic:08x}"},
            )
        if version != PL_LOOPBACK_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported PL Loopback hardware version: {version}",
            )
        if capabilities & (PL_LOOPBACK_CAP_CRC32 | PL_LOOPBACK_CAP_ECHO) != (
            PL_LOOPBACK_CAP_CRC32 | PL_LOOPBACK_CAP_ECHO
        ):
            raise PlasmaError(ErrorCode.INTERFACE_FAILURE, "PL Loopback required capabilities are missing")
        maximum = capabilities & 0xFFFF
        if maximum <= 0 or maximum > PL_LOOPBACK_MAX_PAYLOAD_BYTES:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                f"invalid PL Loopback hardware payload capability: {maximum}",
            )
        self.max_payload_bytes = maximum

    def _write_payload(self, payload: bytes) -> None:
        padded = payload + bytes((-len(payload)) % 4)
        for offset in range(0, len(padded), 4):
            self.registers.write32(
                REG_TX_DATA + offset,
                int.from_bytes(padded[offset : offset + 4], "little"),
            )

    def _read_payload(self, length: int) -> bytes:
        returned = bytearray()
        for offset in range(0, length, 4):
            returned.extend(self.registers.read32(REG_RX_DATA + offset).to_bytes(4, "little"))
        return bytes(returned[:length])

    def _raise_hardware_error(self, code: int, *, actual_crc32: int) -> None:
        if code == HW_ERROR_UNSUPPORTED_COMMAND:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PL Loopback rejected unsupported command")
        if code == HW_ERROR_INVALID_LENGTH:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PL Loopback rejected payload length")
        if code == HW_ERROR_TX_CRC_MISMATCH:
            raise PlasmaError(
                ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
                "PL Loopback detected TX CRC32 mismatch",
                context={"pl_rx_crc32": f"{actual_crc32:08x}"},
            )
        raise PlasmaError(
            ErrorCode.INTERFACE_FAILURE,
            f"PL Loopback returned unknown hardware error code: {code}",
        )

    def exchange(self, payload: bytes, *, sequence: int) -> bytes:
        if not isinstance(payload, bytes) or not payload:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PL Loopback payload must be non-empty bytes")
        if len(payload) > self.max_payload_bytes:
            raise PlasmaError(
                ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE,
                f"PL Loopback payload exceeds hardware limit of {self.max_payload_bytes} bytes",
            )
        if isinstance(sequence, bool) or not isinstance(sequence, int) or not 0 <= sequence <= 0xFFFFFFFF:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PL Loopback sequence must fit uint32")

        expected_crc = self._crc32(payload)
        with self._lock:
            self.registers.write32(REG_CONTROL, CONTROL_CLEAR)
            self.registers.write32(REG_COMMAND, PL_LOOPBACK_COMMAND_ECHO)
            self.registers.write32(REG_SEQUENCE, sequence)
            self.registers.write32(REG_LENGTH, len(payload))
            self.registers.write32(REG_TX_CRC32, expected_crc)
            self._write_payload(payload)
            self.registers.write32(REG_CONTROL, CONTROL_START)

            deadline = time.monotonic() + self.transaction_timeout_s
            while True:
                status = self.registers.read32(REG_STATUS)
                if status & STATUS_DONE:
                    break
                if time.monotonic() >= deadline:
                    raise PlasmaError(
                        ErrorCode.OPERATION_TIMEOUT,
                        "PL Loopback hardware did not complete before timeout",
                        recoverable=True,
                        context={"sequence": sequence, "timeout_s": self.transaction_timeout_s},
                    )
                time.sleep(self.poll_interval_s)

            rx_crc32 = self.registers.read32(REG_RX_CRC32)
            if status & STATUS_ERROR:
                self._raise_hardware_error(
                    self.registers.read32(REG_ERROR_CODE),
                    actual_crc32=rx_crc32,
                )
            if status & STATUS_BUSY or not status & STATUS_READY:
                raise PlasmaError(ErrorCode.INTERFACE_FAILURE, "PL Loopback terminal status is inconsistent")

            rx_sequence = self.registers.read32(REG_RX_SEQUENCE)
            rx_length = self.registers.read32(REG_RX_LENGTH)
            if rx_sequence != sequence:
                raise PlasmaError(
                    ErrorCode.PROTOCOL_INCOMPLETE,
                    "PL Loopback response sequence mismatch",
                    context={"expected": sequence, "actual": rx_sequence},
                )
            if rx_length != len(payload):
                raise PlasmaError(
                    ErrorCode.PROTOCOL_INCOMPLETE,
                    "PL Loopback response length mismatch",
                    context={"expected": len(payload), "actual": rx_length},
                )
            returned = self._read_payload(rx_length)
            actual_crc = self._crc32(returned)
            if rx_crc32 != actual_crc or actual_crc != expected_crc:
                raise PlasmaError(
                    ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
                    "PL Loopback response CRC32 mismatch",
                    context={
                        "expected": f"{expected_crc:08x}",
                        "declared": f"{rx_crc32:08x}",
                        "actual": f"{actual_crc:08x}",
                    },
                )
            if returned != payload:
                raise PlasmaError(ErrorCode.PROTOCOL_CHECKSUM_MISMATCH, "PL Loopback payload mismatch")
            return returned

    def close(self) -> None:
        self.registers.close()
