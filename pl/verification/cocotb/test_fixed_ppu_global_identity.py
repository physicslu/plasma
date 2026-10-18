"""Standalone PPU Global Identity AXI4-Lite Cocotb: no real FPGA/MMIO."""
import cocotb
from test_pl_identity import setup, cycle, read_reg, write_reg, value

BASE = 0x40000000

WORDS = {
    0x000: 0x4D534C50, 0x004: 0x00010000,
    0x008: 0x11112222, 0x00c: 0x33334444,
    0x010: 0x55556666, 0x014: 0x77778888,
    0x018: 0xABCDE001, 0x01c: 0xABCDE002,
    0x020: 0xABCDE003, 0x024: 0xABCDE004,
    0x028: 1, 0x02c: 0, 0x030: 1,
    0x034: 1, 0x038: 1, 0x03c: 1,
    0x040: 0, 0x044: 1, 0x048: 4096,
    0x04c: 64, 0x050: 0, 0x1000: 1,
    0x1004: 0, 0x1008: 0, 0x100c: 0,
}


async def init(dut):
    dut.site_ready_i.value = 1
    dut.site_fault_i.value = 0
    dut.pl_ready_i.value = 1
    await setup(dut)


@cocotb.test()
async def global_identity_abi_v1_exact_register_readback(dut):
    await init(dut)
    for off, expected in WORDS.items():
        await read_reg(dut, BASE + off, expected, stall=3)
    dut._log.info("GLOBAL_IDENTITY_ABI_V1_EXACT_PASS")


@cocotb.test()
async def reject_legacy_wrong_address_width_and_reserved_sites(dut):
    await init(dut)
    # These are virtual AXI test vectors, NEVER real MMIO probes.
    for address in (
        BASE + 1, BASE + 2, BASE + 3,
        BASE + 0x0054, BASE + 0x00FC,
        BASE + 0x1010, BASE + 0x2000, BASE + 0x3000,
        BASE + 0x4000, BASE + 0xB000, BASE + 0xC000,
        BASE + 0xFFFC, BASE - 4, BASE + 0x10000,
        0x43C00000,
    ):
        await read_reg(dut, address, 0, response=2, stall=2)
    for aw_first, concurrent in ((True, False), (False, False), (True, True)):
        await write_reg(dut, aw_first=aw_first, concurrent=concurrent, stall=3)
    for off in (0x000, 0x028, 0x030, 0x1000):
        await read_reg(dut, BASE + off, WORDS[off])
    dut._log.info("GLOBAL_IDENTITY_AXI_DENY_PASS")


@cocotb.test()
async def ready_fault_masks_and_registered_rdata_backpressure(dut):
    await init(dut)
    # PL-ready alone is insufficient; faulted Site is masked out of ready.
    dut.site_ready_i.value = 1
    dut.site_fault_i.value = 1
    await cycle(dut)
    await read_reg(dut, BASE + 0x030, 1)
    await read_reg(dut, BASE + 0x034, 0)
    await read_reg(dut, BASE + 0x038, 3)
    await read_reg(dut, BASE + 0x040, 1)
    await read_reg(dut, BASE + 0x1004, 1)
    await read_reg(dut, BASE + 0x1008, 1)
    # Site1 fault is not a global image readiness decision; Host policy
    # separately refuses admission while any global fault is indicated.
    dut.site_fault_i.value = 0
    dut.site_ready_i.value = 0
    dut.pl_ready_i.value = 0
    await cycle(dut)
    await read_reg(dut, BASE + 0x034, 0)
    await read_reg(dut, BASE + 0x038, 0)
    await read_reg(dut, BASE + 0x1000, 0)
    dut._log.info("GLOBAL_IDENTITY_DYNAMIC_STATUS_PASS")


@cocotb.test()
async def async_reset_drops_pending_read_and_half_write(dut):
    await init(dut)
    dut.s_axi_araddr.value = BASE + 0x000
    dut.s_axi_arvalid.value = 1
    await cycle(dut)
    dut.s_axi_arvalid.value = 0
    assert value(dut.s_axi_rvalid) == 1
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    assert value(dut.s_axi_rvalid) == 0
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    await read_reg(dut, BASE, WORDS[0x000])
    dut._log.info("GLOBAL_IDENTITY_AXI_RESET_PASS")
