"""AXI4-Lite ABI v1: read registers, independent write channels and reset."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def cycle(dut):
    await RisingEdge(dut.s_axi_aclk)
    # Sample registered outputs after NBA update (avoid race with simulator).
    await Timer(1, units="ns")


def value(signal):
    return int(signal.value)


async def setup(dut):
    dut.s_axi_aresetn.value = 0
    dut.s_axi_awaddr.value = 0
    dut.s_axi_awprot.value = 0
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wdata.value = 0
    dut.s_axi_wstrb.value = 15
    dut.s_axi_wvalid.value = 0
    dut.s_axi_bready.value = 0
    dut.s_axi_araddr.value = 0
    dut.s_axi_arprot.value = 0
    dut.s_axi_arvalid.value = 0
    dut.s_axi_rready.value = 0
    cocotb.start_soon(Clock(dut.s_axi_aclk, 10, units="ns").start())
    await cycle(dut)
    await cycle(dut)
    assert value(dut.s_axi_bvalid) == 0
    assert value(dut.s_axi_rvalid) == 0
    dut.s_axi_aresetn.value = 1
    await cycle(dut)


async def read_reg(dut, address, expectation, response=0, stall=0):
    assert value(dut.s_axi_arready) == 1
    dut.s_axi_araddr.value = address
    dut.s_axi_arvalid.value = 1
    dut.s_axi_rready.value = 0
    await cycle(dut)
    dut.s_axi_arvalid.value = 0
    assert value(dut.s_axi_rvalid) == 1, f"missing RVALID at {address:#x}"
    assert value(dut.s_axi_rresp) == response, f"bad RRESP at {address:#x}"
    assert value(dut.s_axi_rdata) == expectation, f"bad RDATA at {address:#x}"
    assert value(dut.s_axi_arready) == 0
    for _ in range(stall):
        await cycle(dut)
        assert value(dut.s_axi_rvalid) == 1, "lost pending response"
        assert value(dut.s_axi_rdata) == expectation, "RDATA changed under backpressure"
        assert value(dut.s_axi_arready) == 0
    dut.s_axi_rready.value = 1
    await cycle(dut)
    assert value(dut.s_axi_rvalid) == 0
    dut.s_axi_rready.value = 0


async def write_reg(dut, aw_first=True, stall=0, concurrent=False):
    # AXI4-Lite AW and W are independent channels, order must not matter.
    assert value(dut.s_axi_awready) == 1
    assert value(dut.s_axi_wready) == 1
    dut.s_axi_awaddr.value = 0x43C00004
    dut.s_axi_wdata.value = 0xFFFFFFFF
    dut.s_axi_bready.value = 0
    if concurrent:
        dut.s_axi_awvalid.value = 1
        dut.s_axi_wvalid.value = 1
        await cycle(dut)
        dut.s_axi_awvalid.value = 0
        dut.s_axi_wvalid.value = 0
    else:
        first = dut.s_axi_awvalid if aw_first else dut.s_axi_wvalid
        second = dut.s_axi_wvalid if aw_first else dut.s_axi_awvalid
        first.value = 1
        await cycle(dut)
        first.value = 0
        assert value(dut.s_axi_bvalid) == 0
        second.value = 1
        await cycle(dut)
        second.value = 0
    assert value(dut.s_axi_bvalid) == 1, "missing write response"
    assert value(dut.s_axi_bresp) == 2, "write must return SLVERR"
    assert value(dut.s_axi_awready) == 0
    assert value(dut.s_axi_wready) == 0
    for _ in range(stall):
        await cycle(dut)
        assert value(dut.s_axi_bvalid) == 1
        assert value(dut.s_axi_bresp) == 2
    dut.s_axi_bready.value = 1
    await cycle(dut)
    assert value(dut.s_axi_bvalid) == 0
    dut.s_axi_bready.value = 0


@cocotb.test()
async def identity_register_read_and_offset_decode(dut):
    await setup(dut)
    base = 0x43C00000  # representative mapped PS physical address
    expected = [
        0x504C534D, 0x00000100, 1, 1,
        0x01234567, 0x89ABCDEF, 0xFEDCBA98, 0x76543210,
    ]
    for offset, word in enumerate(expected):
        await read_reg(dut, base + offset * 4, word, stall=offset % 3)
    # Window beyond 0x1f, and unaligned offsets, must return SLVERR.
    for offset in (0x20, 0x3C, 0x100, 0xFFC, 0x01, 0x1F):
        await read_reg(dut, base + offset, 0, response=2, stall=2)
    # Repeat the same identity read with a second upper mapped base:
    # the AXI interconnect owns aperture/address decoding.
    await read_reg(dut, 0x40000000, expected[0])


@cocotb.test()
async def write_is_rejected_and_does_not_change_identity(dut):
    await setup(dut)
    rng = random.Random(0x504C534D)
    for i in range(32):
        await write_reg(
            dut, aw_first=bool(i % 2), stall=rng.randrange(4),
            concurrent=i % 3 == 0,
        )
        if i % 4 == 0:
            await read_reg(dut, 0x43C00004, 0x00000100, stall=1)


@cocotb.test()
async def read_backpressure_and_reset_recovery(dut):
    await setup(dut)
    # Hold a read response, then reset it while the master is stalled.
    dut.s_axi_araddr.value = 0x43C00000
    dut.s_axi_arvalid.value = 1
    await cycle(dut)
    dut.s_axi_arvalid.value = 0
    assert value(dut.s_axi_rvalid) == 1
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    assert value(dut.s_axi_rvalid) == 0
    assert value(dut.s_axi_bvalid) == 0
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    await read_reg(dut, 0x43C00000, 0x504C534D)
    # Reset a half-arrived AW; subsequent W must not fabricate BVALID.
    dut.s_axi_awvalid.value = 1
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    dut.s_axi_wvalid.value = 1
    await cycle(dut)
    dut.s_axi_wvalid.value = 0
    for _ in range(4):
        await cycle(dut)
        assert value(dut.s_axi_bvalid) == 0
    # Complete the half-pending W with a new AW transaction.
    dut.s_axi_awvalid.value = 1
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    assert value(dut.s_axi_bvalid) == 1
    dut.s_axi_bready.value = 1
    await cycle(dut)
    dut.s_axi_bready.value = 0
    assert value(dut.s_axi_bvalid) == 0
