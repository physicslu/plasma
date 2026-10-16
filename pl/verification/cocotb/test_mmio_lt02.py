"""LT02 AXI4-Lite RTL tests and production Python word-port differential.

No physical MMIO / Z2. Invalid AXI addresses are probed in Cocotb only.
"""
import cocotb

from test_pl_identity import setup, cycle, read_reg, value
from test_pl_control import write

from plasma_interfaces.mmio_loop_test import LoopTestDriver

BASE = 0x40004000
DATA = BASE + 0x100
CAPACITY = 2048


@cocotb.test()
async def scratchpad_axi_channels_strobes_and_invalid_offsets(dut):
    await setup(dut)
    for off, value_expected in (
        (0x00, 0x4C543032), (0x04, 0x00010000),
        (0x08, 1), (0x0C, 2048), (0x14, 1),
        (0x18, 0), (0x1C, 0),
    ):
        await read_reg(dut, BASE + off, value_expected, stall=2)

    await write(dut, DATA, 0x11223344, order="w", stall=2)
    await read_reg(dut, DATA, 0x11223344, stall=2)
    await write(dut, DATA, 0xAABBCCDD, strobe=0b0101, order="aw", stall=1)
    await read_reg(dut, DATA, 0x11BB33DD)
    await write(dut, DATA, 0xFFFFFFFF, strobe=0)  # accepted no-op
    await read_reg(dut, DATA, 0x11BB33DD)
    await write(dut, DATA + 0x7FC, 0xC0FFEE12)
    await read_reg(dut, DATA + 0x7FC, 0xC0FFEE12)
    await read_reg(dut, BASE + 0x18, 4)
    await read_reg(dut, BASE + 0x1C, 4)

    # Invalid physical-bus transactions are simulated, NEVER issued on Z2.
    for addr in (BASE + 1, BASE + 0x0FC, BASE + 0x900, BASE + 0xFFC):
        await write(dut, addr, 1, response=2)
        await read_reg(dut, addr, 0, response=2)
    await write(dut, BASE + 0x14, 1, response=2)
    await write(dut, BASE + 0x10, 2, response=2)
    await write(dut, BASE + 0x10, 1, strobe=1, response=2)
    await read_reg(dut, BASE + 0x18, 4)
    await read_reg(dut, BASE + 0x1C, 4)

    # Counter clear deliberately does not clear memory.
    await write(dut, BASE + 0x10, 1)
    await read_reg(dut, BASE + 0x18, 0)
    await read_reg(dut, BASE + 0x1C, 0)
    await read_reg(dut, DATA, 0x11BB33DD)
    await read_reg(dut, BASE + 0x1C, 1)


@cocotb.test()
async def actual_python_looptest_driver_against_real_rtl(dut):
    await setup(dut)

    @cocotb.function
    async def read32(address):
        assert value(dut.s_axi_arready) == 1
        dut.s_axi_araddr.value = address
        dut.s_axi_arvalid.value = 1
        dut.s_axi_rready.value = 0
        await cycle(dut)
        dut.s_axi_arvalid.value = 0
        assert value(dut.s_axi_rvalid) == 1
        assert value(dut.s_axi_rresp) == 0, f"RTL RRESP on {address:#x}"
        result = value(dut.s_axi_rdata)
        dut.s_axi_rready.value = 1
        await cycle(dut)
        dut.s_axi_rready.value = 0
        return result

    @cocotb.function
    async def write32(address, word):
        await write(dut, address, word, order="both")

    class Bridge:
        def read32(self, address):
            return read32(address)
        def write32(self, address, word):
            write32(address, word)

    @cocotb.external
    def exercise():
        runner = LoopTestDriver(Bridge(), base=BASE)
        for length in (1, 1023, 1024, 1025, 2049):
            raw = bytes((index * 17 + length) & 0xFF for index in range(length))
            result = runner.echo(raw)
            assert result.payload == raw
            assert result.tx_crc32 == result.rx_crc32
            assert result.data_word_writes == result.data_word_reads
        return 5

    count = await exercise()
    assert count == 5
    dut._log.info("LT02_PRODUCTION_DRIVER_REAL_RTL_DIFFERENTIAL_PASS cases=%d", count)


@cocotb.test()
async def pending_response_reset_and_aw_w_channel_recovery(dut):
    await setup(dut)
    dut.s_axi_awaddr.value = DATA
    dut.s_axi_awvalid.value = 1
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    assert value(dut.s_axi_bvalid) == 0
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    dut.s_axi_wdata.value = 0xDEADBEEF
    dut.s_axi_wvalid.value = 1
    await cycle(dut)
    dut.s_axi_wvalid.value = 0
    assert value(dut.s_axi_bvalid) == 0
    dut.s_axi_awaddr.value = DATA
    dut.s_axi_awvalid.value = 1
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    assert value(dut.s_axi_bvalid) == 1
    dut.s_axi_bready.value = 1
    await cycle(dut)
    dut.s_axi_bready.value = 0
    await read_reg(dut, DATA, 0xDEADBEEF)
    dut.s_axi_araddr.value = DATA
    dut.s_axi_arvalid.value = 1
    dut.s_axi_rready.value = 0
    await cycle(dut)
    dut.s_axi_arvalid.value = 0
    assert value(dut.s_axi_rvalid) == 1
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    assert value(dut.s_axi_rvalid) == 0
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    await read_reg(dut, BASE, 0x4C543032)
