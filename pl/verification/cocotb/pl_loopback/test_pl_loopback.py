from __future__ import annotations

import zlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

REG_MAGIC = 0x000
REG_VERSION = 0x004
REG_CAPS = 0x008
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

MAGIC = 0x504C4C42
VERSION = 1
MAX_PAYLOAD = 64
COMMAND_ECHO = 1

STATUS_READY = 1 << 0
STATUS_BUSY = 1 << 1
STATUS_DONE = 1 << 2
STATUS_ERROR = 1 << 3

ERROR_UNSUPPORTED_COMMAND = 1
ERROR_INVALID_LENGTH = 2
ERROR_TX_CRC_MISMATCH = 3


def crc32(payload: bytes) -> int:
    return zlib.crc32(payload) & 0xFFFFFFFF


async def reset(dut) -> None:
    dut.s_axi_aresetn.value = 0
    dut.s_axi_awaddr.value = 0
    dut.s_axi_awprot.value = 0
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wdata.value = 0
    dut.s_axi_wstrb.value = 0
    dut.s_axi_wvalid.value = 0
    dut.s_axi_bready.value = 0
    dut.s_axi_araddr.value = 0
    dut.s_axi_arprot.value = 0
    dut.s_axi_arvalid.value = 0
    dut.s_axi_rready.value = 0
    for _ in range(4):
        await RisingEdge(dut.s_axi_aclk)
    dut.s_axi_aresetn.value = 1
    for _ in range(2):
        await RisingEdge(dut.s_axi_aclk)


async def send_aw(dut, address: int) -> None:
    dut.s_axi_awaddr.value = address
    dut.s_axi_awvalid.value = 1
    while True:
        await RisingEdge(dut.s_axi_aclk)
        if int(dut.s_axi_awready.value):
            break
    dut.s_axi_awvalid.value = 0


async def send_w(dut, value: int, strobe: int = 0xF) -> None:
    dut.s_axi_wdata.value = value
    dut.s_axi_wstrb.value = strobe
    dut.s_axi_wvalid.value = 1
    while True:
        await RisingEdge(dut.s_axi_aclk)
        if int(dut.s_axi_wready.value):
            break
    dut.s_axi_wvalid.value = 0


async def axi_write(dut, address: int, value: int, *, data_first: bool = False) -> None:
    dut.s_axi_bready.value = 0
    if data_first:
        await send_w(dut, value)
        await RisingEdge(dut.s_axi_aclk)
        await send_aw(dut, address)
    else:
        await send_aw(dut, address)
        await RisingEdge(dut.s_axi_aclk)
        await send_w(dut, value)

    while True:
        await RisingEdge(dut.s_axi_aclk)
        if int(dut.s_axi_bvalid.value):
            assert int(dut.s_axi_bresp.value) == 0
            break
    dut.s_axi_bready.value = 1
    await RisingEdge(dut.s_axi_aclk)
    dut.s_axi_bready.value = 0


async def axi_read(dut, address: int) -> int:
    dut.s_axi_rready.value = 0
    dut.s_axi_araddr.value = address
    dut.s_axi_arvalid.value = 1
    while True:
        await RisingEdge(dut.s_axi_aclk)
        if int(dut.s_axi_arready.value):
            break
    dut.s_axi_arvalid.value = 0

    while True:
        await RisingEdge(dut.s_axi_aclk)
        if int(dut.s_axi_rvalid.value):
            value = int(dut.s_axi_rdata.value)
            assert int(dut.s_axi_rresp.value) == 0
            break
    dut.s_axi_rready.value = 1
    await RisingEdge(dut.s_axi_aclk)
    dut.s_axi_rready.value = 0
    return value


async def write_payload(dut, payload: bytes) -> None:
    padded = payload + bytes((-len(payload)) % 4)
    for offset in range(0, len(padded), 4):
        await axi_write(
            dut,
            REG_TX_DATA + offset,
            int.from_bytes(padded[offset : offset + 4], "little"),
            data_first=(offset // 4) % 2 == 1,
        )


async def read_payload(dut, length: int) -> bytes:
    returned = bytearray()
    for offset in range(0, length, 4):
        returned.extend((await axi_read(dut, REG_RX_DATA + offset)).to_bytes(4, "little"))
    return bytes(returned[:length])


async def launch(
    dut,
    payload: bytes,
    sequence: int,
    *,
    command: int = COMMAND_ECHO,
    declared_length: int | None = None,
    declared_crc: int | None = None,
) -> tuple[int, int]:
    await axi_write(dut, REG_CONTROL, 0x2)
    await axi_write(dut, REG_COMMAND, command, data_first=True)
    await axi_write(dut, REG_SEQUENCE, sequence)
    await axi_write(dut, REG_LENGTH, len(payload) if declared_length is None else declared_length)
    await axi_write(dut, REG_TX_CRC32, crc32(payload) if declared_crc is None else declared_crc)
    if payload:
        await write_payload(dut, payload[:MAX_PAYLOAD])
    await axi_write(dut, REG_CONTROL, 0x1, data_first=True)

    for _ in range(400):
        status = await axi_read(dut, REG_STATUS)
        if status & STATUS_DONE:
            return status, await axi_read(dut, REG_ERROR_CODE)
    raise AssertionError("PL loopback transaction did not complete within bounded simulation time")


@cocotb.test()
async def identity_and_capabilities_are_stable(dut) -> None:
    cocotb.start_soon(Clock(dut.s_axi_aclk, 10, units="ns").start())
    await reset(dut)

    assert await axi_read(dut, REG_MAGIC) == MAGIC
    assert await axi_read(dut, REG_VERSION) == VERSION
    capabilities = await axi_read(dut, REG_CAPS)
    assert capabilities & 0xFFFF == MAX_PAYLOAD
    assert capabilities & (1 << 16)
    assert capabilities & (1 << 17)
    assert await axi_read(dut, REG_STATUS) == STATUS_READY


@cocotb.test()
async def deterministic_payloads_round_trip_through_pl(dut) -> None:
    cocotb.start_soon(Clock(dut.s_axi_aclk, 10, units="ns").start())
    await reset(dut)

    payloads = [
        b"\x00",
        bytes([0xAA]) * 63,
        bytes(range(64)),
        bytes((1 << (index % 8)) for index in range(64)),
    ]
    for sequence, payload in enumerate(payloads, start=100):
        status, error = await launch(dut, payload, sequence)
        assert status & STATUS_DONE
        assert not status & STATUS_BUSY
        assert not status & STATUS_ERROR
        assert error == 0
        assert await axi_read(dut, REG_RX_SEQUENCE) == sequence
        assert await axi_read(dut, REG_RX_LENGTH) == len(payload)
        assert await axi_read(dut, REG_RX_CRC32) == crc32(payload)
        assert await read_payload(dut, len(payload)) == payload


@cocotb.test()
async def invalid_command_length_and_crc_fail_closed(dut) -> None:
    cocotb.start_soon(Clock(dut.s_axi_aclk, 10, units="ns").start())
    await reset(dut)

    status, error = await launch(dut, b"command", 1, command=0xDEADBEEF)
    assert status & STATUS_ERROR
    assert error == ERROR_UNSUPPORTED_COMMAND

    status, error = await launch(dut, b"", 2, declared_length=65, declared_crc=0)
    assert status & STATUS_ERROR
    assert error == ERROR_INVALID_LENGTH

    payload = b"crc-mismatch"
    status, error = await launch(dut, payload, 3, declared_crc=crc32(payload) ^ 1)
    assert status & STATUS_ERROR
    assert error == ERROR_TX_CRC_MISMATCH
    assert await axi_read(dut, REG_RX_CRC32) == crc32(payload)


@cocotb.test()
async def back_to_back_transactions_do_not_reuse_stale_response_state(dut) -> None:
    cocotb.start_soon(Clock(dut.s_axi_aclk, 10, units="ns").start())
    await reset(dut)

    first = bytes([0x55]) * 17
    second = bytes([0xFF - index for index in range(32)])
    for sequence, payload in ((0x12345678, first), (0x12345679, second)):
        status, error = await launch(dut, payload, sequence)
        assert status & STATUS_DONE
        assert not status & STATUS_ERROR
        assert error == 0
        assert await axi_read(dut, REG_RX_SEQUENCE) == sequence
        assert await axi_read(dut, REG_RX_LENGTH) == len(payload)
        assert await read_payload(dut, len(payload)) == payload
