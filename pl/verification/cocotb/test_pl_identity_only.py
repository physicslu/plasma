"""Directed AXI checks for the Identity-only build parameters."""
import cocotb
from test_pl_identity import setup, cycle, read_reg, write_reg, value

BASE = 0x40000000
WORDS = [0x504C534D, 0x100, 1, 0, 0x01234567, 0x89ABCDEF, 0xFEDCBA98, 0x76543210]


@cocotb.test()
async def strict_aperture_and_write_rejection(dut):
    await setup(dut)
    for i, word in enumerate(WORDS):
        await read_reg(dut, BASE + 4 * i, word, stall=i % 4)
    for offset in [1, 2, 3, 0x1F, 0x20, 0x100, 0xFFC, 0x1000, 0x10000, 0x3FFFFFFC]:
        await read_reg(dut, BASE + offset, 0, response=2, stall=3)
    for addr in [0, BASE - 4, 0x43C00000, 0x80000000, 0xFFFFFFFF]:
        await read_reg(dut, addr, 0, response=2)
    for aw_first, concurrent in [(True, False), (False, False), (True, True)]:
        await write_reg(dut, aw_first=aw_first, concurrent=concurrent, stall=4)
        for i, word in enumerate(WORDS):
            await read_reg(dut, BASE + 4 * i, word)


@cocotb.test()
async def reset_drops_pending_responses_and_half_writes(dut):
    await setup(dut)
    # Simultaneous read and rejected write; hold both responses until reset.
    dut.s_axi_araddr.value = BASE
    dut.s_axi_arvalid.value = 1
    dut.s_axi_awaddr.value = BASE
    dut.s_axi_awvalid.value = 1
    dut.s_axi_wvalid.value = 1
    await cycle(dut)
    dut.s_axi_arvalid.value = 0
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wvalid.value = 0
    for _ in range(3):
        await cycle(dut)
        assert value(dut.s_axi_rvalid) == value(dut.s_axi_bvalid) == 1
        assert value(dut.s_axi_rresp) == 0
        assert value(dut.s_axi_bresp) == 2
        assert value(dut.s_axi_rdata) == WORDS[0]
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    assert value(dut.s_axi_rvalid) == value(dut.s_axi_bvalid) == 0
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    for first in [dut.s_axi_awvalid, dut.s_axi_wvalid]:
        first.value = 1
        await cycle(dut)
        first.value = 0
        dut.s_axi_aresetn.value = 0
        await cycle(dut)
        dut.s_axi_aresetn.value = 1
        await cycle(dut)
        assert value(dut.s_axi_bvalid) == 0
        await write_reg(dut, concurrent=True)
    await read_reg(dut, BASE, WORDS[0], stall=3)
