from __future__ import annotations

import zlib

import pytest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_hw.pl_loopback import (
    CONTROL_CLEAR,
    CONTROL_START,
    HW_ERROR_TX_CRC_MISMATCH,
    PL_LOOPBACK_CAP_CRC32,
    PL_LOOPBACK_CAP_ECHO,
    PL_LOOPBACK_MAGIC,
    PL_LOOPBACK_MAX_PAYLOAD_BYTES,
    PL_LOOPBACK_VERSION,
    REG_CAPABILITIES,
    REG_COMMAND,
    REG_CONTROL,
    REG_ERROR_CODE,
    REG_LENGTH,
    REG_MAGIC,
    REG_RX_CRC32,
    REG_RX_DATA,
    REG_RX_LENGTH,
    REG_RX_SEQUENCE,
    REG_SEQUENCE,
    REG_STATUS,
    REG_TX_CRC32,
    REG_TX_DATA,
    REG_VERSION,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_READY,
    PLLoopbackDevice,
)


class FakeRegisters:
    def __init__(self, *, never_complete: bool = False, corrupt_sequence: bool = False) -> None:
        self.values = {
            REG_MAGIC: PL_LOOPBACK_MAGIC,
            REG_VERSION: PL_LOOPBACK_VERSION,
            REG_CAPABILITIES: PL_LOOPBACK_MAX_PAYLOAD_BYTES | PL_LOOPBACK_CAP_CRC32 | PL_LOOPBACK_CAP_ECHO,
            REG_STATUS: STATUS_READY,
        }
        self.never_complete = never_complete
        self.corrupt_sequence = corrupt_sequence
        self.closed = False

    def read32(self, offset: int) -> int:
        return self.values.get(offset, 0)

    def write32(self, offset: int, value: int) -> None:
        value &= 0xFFFFFFFF
        self.values[offset] = value
        if offset != REG_CONTROL:
            return
        if value & CONTROL_CLEAR:
            self.values[REG_STATUS] = STATUS_READY
            self.values[REG_ERROR_CODE] = 0
        if not value & CONTROL_START:
            return
        if self.never_complete:
            self.values[REG_STATUS] = 0x2
            return

        length = self.values[REG_LENGTH]
        payload = bytearray()
        for data_offset in range(0, length, 4):
            payload.extend(self.values.get(REG_TX_DATA + data_offset, 0).to_bytes(4, "little"))
        payload = payload[:length]
        actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
        self.values[REG_RX_SEQUENCE] = self.values[REG_SEQUENCE] + (1 if self.corrupt_sequence else 0)
        self.values[REG_RX_LENGTH] = length
        self.values[REG_RX_CRC32] = actual_crc
        for data_offset in range(0, length, 4):
            chunk = payload[data_offset : data_offset + 4]
            self.values[REG_RX_DATA + data_offset] = int.from_bytes(chunk + bytes(4 - len(chunk)), "little")
        if actual_crc != self.values[REG_TX_CRC32]:
            self.values[REG_ERROR_CODE] = HW_ERROR_TX_CRC_MISMATCH
            self.values[REG_STATUS] = STATUS_READY | STATUS_DONE | STATUS_ERROR
        else:
            self.values[REG_ERROR_CODE] = 0
            self.values[REG_STATUS] = STATUS_READY | STATUS_DONE

    def close(self) -> None:
        self.closed = True


def test_semantic_device_round_trips_boundary_payloads() -> None:
    registers = FakeRegisters()
    device = PLLoopbackDevice(registers)
    for sequence, payload in (
        (1, b"\x00"),
        (2, bytes([0xAA]) * 63),
        (3, bytes(range(64))),
    ):
        assert device.exchange(payload, sequence=sequence) == payload
    device.close()
    assert registers.closed


def test_probe_rejects_wrong_hardware_identity() -> None:
    registers = FakeRegisters()
    registers.values[REG_MAGIC] ^= 1
    with pytest.raises(PlasmaError) as caught:
        PLLoopbackDevice(registers)
    assert caught.value.code is ErrorCode.INTERFACE_FAILURE


def test_timeout_is_typed_and_recoverable() -> None:
    device = PLLoopbackDevice(
        FakeRegisters(never_complete=True),
        transaction_timeout_s=0.002,
        poll_interval_s=0.0001,
    )
    with pytest.raises(PlasmaError) as caught:
        device.exchange(b"timeout", sequence=7)
    assert caught.value.code is ErrorCode.OPERATION_TIMEOUT
    assert caught.value.recoverable is True


def test_sequence_mismatch_cannot_pass() -> None:
    device = PLLoopbackDevice(FakeRegisters(corrupt_sequence=True))
    with pytest.raises(PlasmaError) as caught:
        device.exchange(b"sequence", sequence=9)
    assert caught.value.code is ErrorCode.PROTOCOL_INCOMPLETE


def test_payload_above_hardware_boundary_is_rejected_before_start() -> None:
    device = PLLoopbackDevice(FakeRegisters())
    with pytest.raises(PlasmaError) as caught:
        device.exchange(bytes(PL_LOOPBACK_MAX_PAYLOAD_BYTES + 1), sequence=1)
    assert caught.value.code is ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE
