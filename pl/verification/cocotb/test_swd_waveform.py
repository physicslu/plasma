"""SWD-00 digital waveform primitive, no physical pins or target IC."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def cycle(dut):
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")


def val(signal):
    return int(signal.value)


async def init(dut):
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.tx_data.value = 0
    dut.bit_count.value = 0
    dut.half_period_cycles.value = 0
    dut.drive_enable.value = 0
    dut.swdio_in.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await cycle(dut)
    await cycle(dut)
    assert val(dut.swdio_oe) == 0
    assert val(dut.swclk) == 0
    dut.rst_n.value = 1
    await cycle(dut)


async def launch(dut, tx, count, half, drive):
    dut.tx_data.value = tx
    dut.bit_count.value = count
    dut.half_period_cycles.value = half
    dut.drive_enable.value = drive
    dut.start.value = 1
    await cycle(dut)
    dut.start.value = 0


@cocotb.test()
async def tx_lsb_first_and_sample_rising_phase(dut):
    await init(dut)
    tx = 0xA6
    rx = 0xC9
    await launch(dut, tx, 8, 3, 1)
    assert val(dut.busy) == 1
    assert val(dut.swdio_oe) == 1
    for i in range(8):
        assert val(dut.swdio_out) == ((tx >> i) & 1)
        for tick in range(3):
            await cycle(dut)
            assert val(dut.swclk) == (1 if tick == 2 else 0)
        dut.swdio_in.value = (rx >> i) & 1
        for tick in range(3):
            await cycle(dut)
            assert val(dut.swclk) == (0 if tick == 2 else 1)
    assert val(dut.done) == 1
    assert val(dut.busy) == 0
    assert val(dut.error) == 0
    assert val(dut.rx_data) == rx
    assert val(dut.swdio_oe) == 0
    await cycle(dut)
    assert val(dut.done) == 0


@cocotb.test()
async def read_hi_z_and_invalid_commands(dut):
    await init(dut)
    for count, half in ((0, 3), (33, 3), (8, 1)):
        await launch(dut, 0, count, half, 0)
        assert val(dut.busy) == 0
        assert val(dut.done) == 1
        assert val(dut.error) == 1
        assert val(dut.swdio_oe) == 0
        await cycle(dut)
    dut.swdio_in.value = 1
    await launch(dut, 0xFFFFFFFF, 2, 2, 0)
    assert val(dut.swdio_oe) == 0
    for _ in range(8):
        await cycle(dut)
    assert val(dut.rx_data) == 3
    assert val(dut.done) == 1
    assert val(dut.error) == 0
    assert val(dut.swdio_oe) == 0


@cocotb.test()
async def abort_on_reset_and_reject_busy_start(dut):
    await init(dut)
    await launch(dut, 0xFFFFFFFF, 32, 5, 1)
    dut.start.value = 1
    await cycle(dut)
    dut.start.value = 0
    assert val(dut.error) == 1
    assert val(dut.busy) == 1
    dut.rst_n.value = 0
    await cycle(dut)
    assert val(dut.busy) == 0
    assert val(dut.swclk) == 0
    assert val(dut.swdio_oe) == 0
    assert val(dut.done) == 0
    dut.rst_n.value = 1
    await cycle(dut)
    await launch(dut, 1, 1, 2, 1)
    for _ in range(4):
        await cycle(dut)
    assert val(dut.done) == 1
    assert val(dut.error) == 0
