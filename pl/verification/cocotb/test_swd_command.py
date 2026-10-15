"""Mandatory PL loopback gate: AXI -> reusable waveform -> dedicated responder."""
import random
import cocotb
from test_pl_identity import setup, cycle, value
from test_pl_control import write

BASE = 0x40002000
CMD, TX, COUNT, HALF, DRIVE, RX, STATUS, ERROR, MODE, PATTERN = range(4, 44, 4)


async def read(dut, offset, response=0, stall=0):
    assert value(dut.s_axi_arready) == 1
    dut.s_axi_araddr.value = BASE + offset
    dut.s_axi_arvalid.value = 1
    dut.s_axi_rready.value = 0
    await cycle(dut)
    dut.s_axi_arvalid.value = 0
    assert value(dut.s_axi_rvalid) == 1
    assert value(dut.s_axi_rresp) == response
    result = value(dut.s_axi_rdata)
    for _ in range(stall):
        await cycle(dut)
        assert value(dut.s_axi_rdata) == result
        assert value(dut.s_axi_rresp) == response
        assert value(dut.s_axi_arready) == 0
    dut.s_axi_rready.value = 1
    await cycle(dut)
    dut.s_axi_rready.value = 0
    return result


async def wr(dut, offset, data, **kwargs):
    await write(dut, BASE + offset, data, **kwargs)


async def configure(dut, tx, count, half, drive, mode=0, pattern=0):
    for offset, data in [(TX, tx), (COUNT, count), (HALF, half), (DRIVE, drive), (MODE, mode), (PATTERN, pattern)]:
        await wr(dut, offset, data)


async def finish(dut, count, half):
    for _ in range(2 * count * half + 4):
        await cycle(dut)
        if value(dut.core.done_sticky):
            assert not value(dut.core.active)
            return
    raise AssertionError('bounded completion failed')


@cocotb.test()
async def register_map_strobes_and_fail_closed(dut):
    await setup(dut)
    for offset, expected in [(0, 1), (CMD, 0), (TX, 0), (COUNT, 0), (HALF, 2), (DRIVE, 0), (RX, 0), (STATUS, 0), (ERROR, 0), (MODE, 0), (PATTERN, 0)]:
        assert await read(dut, offset, stall=2) == expected
    rng = random.Random(0x53574400)
    previous = 0
    for strobe in range(16):
        data = rng.getrandbits(32)
        await wr(dut, TX, data, strobe=strobe, order=['both', 'aw', 'w'][strobe % 3], stall=strobe % 4)
        for lane in range(4):
            if strobe & (1 << lane):
                previous = (previous & ~(255 << (8*lane))) | (data & (255 << (8*lane)))
        assert await read(dut, TX, stall=2) == previous
    for offset in [0, RX, STATUS, ERROR, 1, 0x2c, 0xffc, 0x1000, -4]:
        await wr(dut, offset, 0, response=2, stall=1)
        if offset in [1, 0x2c, 0xffc, 0x1000, -4]:
            assert await read(dut, offset, response=2, stall=1) == 0
    for offset, bad in [(COUNT, 0), (COUNT, 33), (COUNT, 64), (HALF, 0), (HALF, 1), (HALF, 65536), (DRIVE, 2), (MODE, 2)]:
        await wr(dut, offset, bad, response=2)
        assert await read(dut, ERROR) == 3
    await wr(dut, CMD, 2)
    assert await read(dut, ERROR) == 0
    for data, strobe in [(0, 15), (3, 15), (8, 15), (1, 1)]:
        await wr(dut, CMD, data, strobe=strobe, response=2)
        assert await read(dut, ERROR) == 1
        await wr(dut, CMD, 2)
    await wr(dut, CMD, 1, response=2)  # Reset count is invalid for START.
    assert await read(dut, ERROR) == 3
    await wr(dut, CMD, 4)
    assert await read(dut, STATUS) == 0
    await wr(dut, COUNT, 32, strobe=1)
    assert await read(dut, COUNT) == 32
    await wr(dut, COUNT, 0x100, strobe=2, response=2)
    assert await read(dut, COUNT) == 32


@cocotb.test()
async def independent_responder_lsb_and_clock_timing(dut):
    await setup(dut)
    for count, half, drive, mode, tx, pattern in [
        (1, 2, 1, 0, 1, 0), (8, 3, 1, 0, 0xA6, 0),
        (32, 2, 1, 1, 0x87654321, 0x5AC3960F),
        (7, 5, 0, 1, 0x55, 0x2D), (32, 4, 0, 0, 0, 0),
    ]:
        await configure(dut, tx, count, half, drive, mode, pattern)
        await wr(dut, CMD, 1)
        assert value(dut.core.engine_busy) == 1
        assert value(dut.core.error_sticky) == 0
        for bit in range(count):
            assert value(dut.core.swdio_out) == (tx >> bit) & 1
            assert value(dut.core.swdio_oe) == drive
            assert value(dut.core.swclk) == 0
            for tick in range(half):
                await cycle(dut)
                assert value(dut.core.swclk) == (1 if tick == half - 1 else 0)
                assert value(dut.core.swdio_oe) == drive
            for tick in range(half):
                await cycle(dut)
                assert value(dut.core.swclk) == (0 if tick == half - 1 else 1)
                if bit < count - 1 or tick < half - 1:
                    assert value(dut.core.swdio_oe) == drive
        assert value(dut.core.engine_done) == 1
        assert value(dut.core.swdio_oe) == 0
        await cycle(dut)  # AXI wrapper captures the one-cycle DONE.
        expected = pattern if mode else (tx if drive else 0xffffffff)
        expected &= (1 << count) - 1
        assert await read(dut, RX, stall=3) == expected
        assert (await read(dut, STATUS)) & 7 == 2
        for _ in range(5): await cycle(dut)
        assert value(dut.core.done_sticky) == 1
        await wr(dut, CMD, 2)
        assert (await read(dut, STATUS)) & 7 == 0
        assert await read(dut, RX) == expected  # CLEAR does not discard RX.


@cocotb.test()
async def busy_commands_preserve_transfer_and_first_error(dut):
    await setup(dut)
    await configure(dut, 0xA55A1234, 32, 20, 1, 1, 0x0F1E2D3C)
    await wr(dut, CMD, 1)
    assert (await read(dut, STATUS, stall=3)) & 1
    for offset, data in [(CMD, 1), (CMD, 2), (TX, 0), (COUNT, 1), (HALF, 2), (DRIVE, 0), (MODE, 0), (PATTERN, 0)]:
        await wr(dut, offset, data, order='w', response=2)
        assert await read(dut, ERROR) == 2
    await wr(dut, CMD, 3, response=2)  # First error remains BUSY.
    assert await read(dut, ERROR) == 2
    await wr(dut, TX, 0, strobe=0)
    await wr(dut, CMD, 0xffffffff, strobe=0)
    assert await read(dut, TX) == 0xA55A1234
    assert await read(dut, PATTERN) == 0x0F1E2D3C
    assert await read(dut, RX) == 0  # Partial samples must not leak into RX result.
    await finish(dut, 32, 20)
    assert await read(dut, RX) == 0x0F1E2D3C
    assert (await read(dut, STATUS)) & 7 == 6  # Truthful DONE plus rejected-command ERROR.
    await wr(dut, CMD, 2)
    assert await read(dut, ERROR) == 0
    await wr(dut, CMD, 1)  # Back-to-back accepted command, no external reset.
    assert value(dut.core.done_sticky) == 0
    assert await read(dut, RX) == 0x0F1E2D3C  # Last result remains while active.
    await finish(dut, 32, 20)
    assert (await read(dut, STATUS)) & 7 == 2


@cocotb.test()
async def reset_active_and_response_backpressure(dut):
    await setup(dut)
    await configure(dut, 0xffffffff, 32, 8, 1, 1, 0x12345678)
    await wr(dut, CMD, 1)
    dut.s_axi_araddr.value = BASE + STATUS
    dut.s_axi_arvalid.value = 1
    await cycle(dut)
    dut.s_axi_arvalid.value = 0
    held = value(dut.s_axi_rdata)
    assert held & 1
    await wr(dut, CMD, 4, order='aw', stall=3)
    assert value(dut.s_axi_rvalid) == 1
    assert value(dut.s_axi_rdata) == held
    assert value(dut.core.engine_busy) == value(dut.core.swclk) == value(dut.core.swdio_oe) == 0
    dut.s_axi_rready.value = 1
    await cycle(dut)
    dut.s_axi_rready.value = 0
    for offset, expected in [(COUNT, 0), (HALF, 2), (RX, 0), (ERROR, 0), (STATUS, 0)]:
        assert await read(dut, offset) == expected
    await configure(dut, 3, 32, 8, 1)
    await wr(dut, CMD, 1)
    dut.s_axi_awvalid.value = 1  # Reset an unfinished AW and active waveform.
    dut.s_axi_awaddr.value = BASE + TX
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    dut.s_axi_aresetn.value = 0
    await cycle(dut)
    assert value(dut.s_axi_bvalid) == value(dut.s_axi_rvalid) == 0
    assert value(dut.core.engine_busy) == value(dut.core.swdio_oe) == 0
    dut.s_axi_aresetn.value = 1
    await cycle(dut)
    dut.s_axi_wvalid.value = 1
    dut.s_axi_wdata.value = 0xFEDCBA98
    await cycle(dut)
    dut.s_axi_wvalid.value = 0
    for _ in range(3):
        await cycle(dut)
        assert value(dut.s_axi_bvalid) == 0
    dut.s_axi_awaddr.value = BASE + TX
    dut.s_axi_awvalid.value = 1
    await cycle(dut)
    dut.s_axi_awvalid.value = 0
    assert value(dut.s_axi_bvalid) == 1
    dut.s_axi_bready.value = 1
    await cycle(dut)
    dut.s_axi_bready.value = 0
    assert await read(dut, TX) == 0xFEDCBA98
    await configure(dut, 0, 1, 2, 0, 1, 1)
    await wr(dut, CMD, 1)
    await finish(dut, 1, 2)
    assert await read(dut, RX) == 1


@cocotb.test()
async def maximum_divider_boundary(dut):
    await setup(dut)
    await configure(dut, 1, 1, 65535, 1, 1, 0)
    await wr(dut, CMD, 1)
    for _ in range(65534):
        await cycle(dut)
        assert value(dut.core.swclk) == 0
    await cycle(dut)
    assert value(dut.core.swclk) == 1
    for _ in range(65534):
        await cycle(dut)
        assert value(dut.core.swclk) == 1
    await cycle(dut)
    assert value(dut.core.swclk) == 0
    await cycle(dut)
    assert await read(dut, RX) == 0
    assert (await read(dut, STATUS)) & 7 == 2
