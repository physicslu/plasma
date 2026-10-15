"""PSPL-02 AXI-Lite read/write, independent channels, strobes and response stalls."""
import cocotb
from test_pl_identity import setup, cycle, read_reg, value

BASE = 0x40001000
MASK = 0xA5A55A5A


async def write(dut, address, data, strobe=15, order="both", stall=0, response=0):
    assert value(dut.s_axi_awready) == 1
    assert value(dut.s_axi_wready) == 1
    dut.s_axi_awaddr.value = address
    dut.s_axi_wdata.value = data
    dut.s_axi_wstrb.value = strobe
    dut.s_axi_bready.value = 0
    if order == "both":
        dut.s_axi_awvalid.value = 1
        dut.s_axi_wvalid.value = 1
        await cycle(dut)
        dut.s_axi_awvalid.value = 0
        dut.s_axi_wvalid.value = 0
    else:
        first, second = (
            (dut.s_axi_awvalid, dut.s_axi_wvalid) if order == "aw"
            else (dut.s_axi_wvalid, dut.s_axi_awvalid)
        )
        first.value = 1
        await cycle(dut)
        first.value = 0
        assert value(dut.s_axi_bvalid) == 0
        for _ in range(2):
            await cycle(dut)
            assert value(dut.s_axi_bvalid) == 0
        second.value = 1
        await cycle(dut)
        second.value = 0
    assert value(dut.s_axi_bvalid) == 1
    assert value(dut.s_axi_bresp) == response
    for _ in range(stall):
        await cycle(dut)
        assert value(dut.s_axi_bvalid) == 1
        assert value(dut.s_axi_bresp) == response
        assert value(dut.s_axi_awready) == 0
        assert value(dut.s_axi_wready) == 0
    dut.s_axi_bready.value = 1
    await cycle(dut)
    dut.s_axi_bready.value = 0
    assert value(dut.s_axi_bvalid) == 0


@cocotb.test()
async def loopback_and_strobes(dut):
    await setup(dut)
    await read_reg(dut, BASE, 0)
    await read_reg(dut, BASE + 4, MASK)
    await write(dut, BASE, 0x12345678, order="w", stall=3)
    await read_reg(dut, BASE, 0x12345678, stall=3)
    await read_reg(dut, BASE + 4, 0x12345678 ^ MASK)
    assert value(dut.control_value) == 0x12345678
    await write(dut, BASE, 0xAABBCCDD, strobe=0b0101, order="aw")
    await read_reg(dut, BASE, 0x12BB56DD)
    await write(dut, BASE, 0xFFFFFFFF, strobe=0, order="both")
    await read_reg(dut, BASE, 0x12BB56DD)
    await write(dut, BASE, 0x00000000, strobe=15)
    await read_reg(dut, BASE, 0)


@cocotb.test()
async def rejected_writes_and_invalid_reads(dut):
    await setup(dut)
    await write(dut, BASE, 0xDEADBEEF)
    for addr in (BASE + 1, BASE + 4, BASE + 8, BASE + 0xFFC,
                 BASE + 0x1000, BASE - 4, 0x43C00000):
        await write(dut, addr, 0, order="aw", response=2, stall=1)
        await read_reg(dut, addr, 0, response=2)
    await read_reg(dut, BASE, 0xDEADBEEF)
    await read_reg(dut, BASE + 4, 0xDEADBEEF ^ MASK)


@cocotb.test()
async def response_reset_and_half_write_reset(dut):
    await setup(dut)
    dut.s_axi_awaddr.value = BASE
    dut.s_axi_wdata.value = 0xFEEDCAFE
    dut.s_axi_awvalid.value = 1
    dut.s_axi_wvalid.value = 1
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wvalid.value = 0
    assert value(dut.s_axi_bvalid) == 1
    await read_reg(dut, BASE, 0xFEEDCAFE)
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    assert value(dut.s_axi_bvalid) == 0
    assert value(dut.control_value) == 0
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    dut.s_axi_awaddr.value = BASE
    dut.s_axi_awvalid.value = 1
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    dut.s_axi_wdata.value = 0xAAAA5555
    dut.s_axi_wvalid.value = 1
    await cycle(dut)
    dut.s_axi_wvalid.value = 0
    for _ in range(4):
        await cycle(dut)
        assert value(dut.s_axi_bvalid) == 0
    dut.s_axi_awvalid.value = 1
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    assert value(dut.s_axi_bvalid) == 1
    dut.s_axi_bready.value = 1
    await cycle(dut)
    dut.s_axi_bready.value = 0
    await read_reg(dut, BASE, 0xAAAA5555)
