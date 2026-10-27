"""Real Icarus/Cocotb bus-level test of two independent MPE AXI Sites.

Driver deliberately owns independent AXI AW, W, AR channels. No fake
successful bus access, no ARM/Linux MMIO/HIL, no target attached.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


BASE = 0x43C00000
SITE1 = BASE + 0x1000
SITE2 = BASE + 0x2000


def initialize(d):
    d.s_axi_aresetn.value = 0
    d.s_axi_awaddr.value = 0
    d.s_axi_awprot.value = 0
    d.s_axi_awvalid.value = 0
    d.s_axi_wdata.value = 0
    d.s_axi_wstrb.value = 0
    d.s_axi_wvalid.value = 0
    d.s_axi_bready.value = 0
    d.s_axi_araddr.value = 0
    d.s_axi_arprot.value = 0
    d.s_axi_arvalid.value = 0
    d.s_axi_rready.value = 0


async def start(d):
    cocotb.start_soon(Clock(d.s_axi_aclk, 10, units="ns").start())
    initialize(d)
    for _ in range(4):
        await FallingEdge(d.s_axi_aclk)
    d.s_axi_aresetn.value = 1
    await FallingEdge(d.s_axi_aclk)


async def sender(d, channel, address=None, data=None, strb=15, delay=0):
    for _ in range(delay):
        await FallingEdge(d.s_axi_aclk)
    await FallingEdge(d.s_axi_aclk)
    if channel == "aw":
        d.s_axi_awaddr.value = address
        d.s_axi_awvalid.value = 1
        ready = d.s_axi_awready
        valid = d.s_axi_awvalid
    elif channel == "w":
        d.s_axi_wdata.value = data
        d.s_axi_wstrb.value = strb
        d.s_axi_wvalid.value = 1
        ready = d.s_axi_wready
        valid = d.s_axi_wvalid
    else:
        raise AssertionError(channel)
    for _ in range(40):
        await Timer(1, units="ns")
        if int(ready.value):
            await RisingEdge(d.s_axi_aclk)
            await FallingEdge(d.s_axi_aclk)
            valid.value = 0
            return
        await FallingEdge(d.s_axi_aclk)
    raise AssertionError("AXI handshake timed out " + channel)


async def write(d, addr, data, *, strb=15, w_delay=0, aw_delay=0, delay_b=2):
    aw = cocotb.start_soon(sender(d, "aw", address=addr, delay=aw_delay))
    ww = cocotb.start_soon(sender(d, "w", data=data, strb=strb, delay=w_delay))
    await aw
    await ww
    for _ in range(40):
        await FallingEdge(d.s_axi_aclk)
        await Timer(1, units="ns")
        if int(d.s_axi_bvalid.value):
            value = int(d.s_axi_bresp.value)
            for _ in range(delay_b):
                await FallingEdge(d.s_axi_aclk)
                assert int(d.s_axi_bvalid.value)
                assert int(d.s_axi_bresp.value) == value
            d.s_axi_bready.value = 1
            await RisingEdge(d.s_axi_aclk)
            await FallingEdge(d.s_axi_aclk)
            d.s_axi_bready.value = 0
            return value
    raise AssertionError("No BRESP from AXI slave")


async def read(d, addr, *, delay_r=2):
    await FallingEdge(d.s_axi_aclk)
    d.s_axi_araddr.value = addr
    d.s_axi_arvalid.value = 1
    for _ in range(40):
        await Timer(1, units="ns")
        if int(d.s_axi_arready.value):
            await RisingEdge(d.s_axi_aclk)
            await FallingEdge(d.s_axi_aclk)
            d.s_axi_arvalid.value = 0
            break
        await FallingEdge(d.s_axi_aclk)
    else:
        raise AssertionError("AXI read address timeout")
    for _ in range(40):
        await FallingEdge(d.s_axi_aclk)
        await Timer(1, units="ns")
        if int(d.s_axi_rvalid.value):
            data = int(d.s_axi_rdata.value)
            response = int(d.s_axi_rresp.value)
            for _ in range(delay_r):
                await FallingEdge(d.s_axi_aclk)
                assert int(d.s_axi_rvalid.value)
                assert int(d.s_axi_rdata.value) == data
            d.s_axi_rready.value = 1
            await RisingEdge(d.s_axi_aclk)
            await FallingEdge(d.s_axi_aclk)
            d.s_axi_rready.value = 0
            return response, data
    raise AssertionError("No RRESP from AXI slave")


async def expect_read(d, addr, expected):
    code, val = await read(d, addr)
    assert code == 0 and val == expected, (
        f"bad read {addr:#x}: status={code}, value={val:#x}; expected={expected:#x}"
    )


async def wait_both(d, limit=3000):
    count = [0, 0]
    prev = [0, 0]
    both_busy = False
    for _ in range(limit):
        await RisingEdge(d.s_axi_aclk)
        await Timer(1, units="ns")
        busy = int(d.u_mpe.busy.value)
        both_busy = both_busy or busy == 3
        wires = int(d.swclk_io.value)
        for n in range(2):
            level = (wires >> n) & 1
            if level and not prev[n]:
                count[n] += 1
            prev[n] = level
        if int(d.u_mpe.resp_valid.value) == 3:
            return count, both_busy
    raise AssertionError("two-Site completion exceeded test budget")


@cocotb.test()
async def axi_site_banks_and_parallel_physical_reset(d):
    await start(d)
    await expect_read(d, BASE, 0x4D504531)
    await expect_read(d, BASE + 4, 0x10000)
    await expect_read(d, BASE + 8, 3)
    await expect_read(d, SITE1, 0x10001)
    await expect_read(d, SITE2, 0x10002)
    assert (await read(d, SITE2 + 0x40))[0] == 2  # strict register decode
    assert (await read(d, BASE + 0x3000))[0] == 2
    assert (await read(d, SITE1 + 1))[0] == 2
    assert await write(d, SITE1 + 8, 3, strb=0x1) == 2
    await expect_read(d, SITE1 + 8, 500)  # rejected partial update

    # AW and W independently arrive; separate Site registers must not alias.
    assert await write(d, SITE1 + 8, 3, w_delay=4) == 0
    assert await write(d, SITE2 + 8, 7, aw_delay=4) == 0
    await expect_read(d, SITE1 + 8, 3)
    await expect_read(d, SITE2 + 8, 7)

    for base in (SITE1, SITE2):
        assert await write(d, base + 0x28, 1) == 0  # enable
    assert await write(d, SITE1 + 0x14, (1 << 16) | 0x100) == 0
    assert await write(d, SITE2 + 0x14, (2 << 16) | 0x100) == 0
    count, concurrent = await wait_both(d)
    assert concurrent and min(count) >= 64, count
    assert abs(count[0] - count[1]) <= 1, count
    assert int(d.swclk_io.value) == 0
    for base, tag in ((SITE1, 1), (SITE2, 2)):
        code, status = await read(d, base + 4)
        assert code == 0 and status & 4
        code, meta = await read(d, base + 0x18)
        assert code == 0 and meta >> 16 == tag and meta & 0xF == 0
        assert await write(d, base + 0x20, tag + 4) == 2  # wrong tag
        assert await write(d, base + 0x14, (tag + 8) << 16 | 0x100) == 2  # busy until pop
        assert await write(d, base + 0x20, tag) == 0
    await FallingEdge(d.s_axi_aclk)
    await expect_read(d, SITE1 + 0x24, 0)
    await expect_read(d, SITE2 + 0x24, 0)


@cocotb.test()
async def abort_site1_no_site2_effect(d):
    await start(d)
    for base in (SITE1, SITE2):
        assert await write(d, base + 8, 5) == 0
        assert await write(d, base + 0x28, 1) == 0
    assert await write(d, SITE1 + 0x14, (17 << 16) | 0x100) == 0
    assert await write(d, SITE2 + 0x14, (18 << 16) | 0x100) == 0
    for _ in range(20):
        await RisingEdge(d.s_axi_aclk)
    assert int(d.u_mpe.busy.value) == 3
    assert await write(d, SITE1 + 0x28, 0) == 0  # disable aborts only 1
    assert (int(d.swclk_io.value) & 1) == 0
    assert int(d.u_mpe.busy.value) & 2
    for _ in range(1800):
        await RisingEdge(d.s_axi_aclk)
        await Timer(1, units="ns")
        if int(d.u_mpe.resp_valid.value) == 3:
            break
    else:
        raise AssertionError("independent abort test timed out")
    s1 = (await read(d, SITE1 + 0x18))[1]
    s2 = (await read(d, SITE2 + 0x18))[1]
    assert s1 >> 16 == 17 and (s1 & 15) == 8, hex(s1)
    assert s2 >> 16 == 18 and (s2 & 15) == 0, hex(s2)
    assert (await read(d, SITE1 + 0x2c))[1] == 1
    assert (await read(d, SITE2 + 0x2c))[1] == 0
    assert await write(d, SITE1 + 0x28, 1) == 0
    assert await write(d, SITE1 + 0x20, 17) == 0
    assert await write(d, SITE1 + 0x14, (19 << 16) | 0x100) == 2  # sticky fault
    assert await write(d, SITE2 + 0x20, 18) == 0
