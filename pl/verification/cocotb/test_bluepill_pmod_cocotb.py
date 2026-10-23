"""Host-only digital PMODB Hi-Z/turnaround; not physical electrical proof."""
import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def swdio_oe_releases_wire_to_target(dut):
    dut.swclk.value = 0
    dut.swdio_out.value = 1
    dut.swdio_oe.value = 0
    dut.target_oe.value = 1
    dut.target_out.value = 0
    await Timer(2, units="ns")
    assert int(dut.sample_swdio.value) == 0
    assert int(dut.sample_swclk.value) == 0

    dut.target_out.value = 1
    await Timer(2, units="ns")
    assert int(dut.sample_swdio.value) == 1

    dut.target_oe.value = 0
    dut.swdio_oe.value = 1
    dut.swdio_out.value = 0
    dut.swclk.value = 1
    await Timer(2, units="ns")
    assert int(dut.sample_swdio.value) == 0
    assert int(dut.sample_swclk.value) == 1

    dut.swdio_out.value = 1
    await Timer(2, units="ns")
    assert int(dut.sample_swdio.value) == 1

    dut.swdio_oe.value = 0
    dut.target_out.value = 0
    dut.target_oe.value = 1
    await Timer(2, units="ns")
    assert int(dut.sample_swdio.value) == 0
