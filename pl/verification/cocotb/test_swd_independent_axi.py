"""Host-only independent SWD IP simulation: two AXI slaves, two pad owners.

Icarus/Cocotb executes real per-Site RTL, not an emulated MMIO success stub.
This does NOT validate the eventual Vivado AXI Interconnect/HWH or PS ARMv7.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

BASE = [0x43C01000, 0x43C02000]


def field(handle, site, width):
    return (int(handle.value) >> (site * width)) & ((1 << width) - 1)


def put(handle, site, width, value):
    old = int(handle.value)
    mask = ((1 << width) - 1) << (site * width)
    handle.value = (old & ~mask) | ((value << (site * width)) & mask)


def init(d):
    d.rst_n.value = 0
    for h in (d.awaddr, d.awprot, d.awvalid, d.wdata, d.wstrb,
              d.wvalid, d.bready, d.araddr, d.arprot, d.arvalid, d.rready):
        h.value = 0


async def start(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
    init(d)
    for _ in range(4):
        await FallingEdge(d.clk)
    d.rst_n.value = 1
    await FallingEdge(d.clk)


async def sender(d, site, kind, address=None, data=None, strb=15, delay=0):
    for _ in range(delay):
        await FallingEdge(d.clk)
    await FallingEdge(d.clk)
    if kind == "aw":
        put(d.awaddr, site, 32, address)
        put(d.awvalid, site, 1, 1)
        valid = d.awvalid
        ready = d.awready
    else:
        put(d.wdata, site, 32, data)
        put(d.wstrb, site, 4, strb)
        put(d.wvalid, site, 1, 1)
        valid = d.wvalid
        ready = d.wready
    for _ in range(60):
        await Timer(1, units="ns")
        if field(ready, site, 1):
            await RisingEdge(d.clk)
            await FallingEdge(d.clk)
            put(valid, site, 1, 0)
            return
        await FallingEdge(d.clk)
    raise AssertionError("AXI address/data handshake timeout")


async def write(d, site, offset, data, *, strb=15, aw_delay=0, w_delay=0):
    addr = BASE[site] + offset
    aw = cocotb.start_soon(sender(d, site, "aw", address=addr, delay=aw_delay))
    ww = cocotb.start_soon(sender(d, site, "w", data=data, strb=strb,
                                 delay=w_delay))
    await aw
    await ww
    for _ in range(70):
        await FallingEdge(d.clk)
        await Timer(1, units="ns")
        if field(d.bvalid, site, 1):
            answer = field(d.bresp, site, 2)
            for _ in range(2):
                await FallingEdge(d.clk)
                assert field(d.bvalid, site, 1) == 1
                assert field(d.bresp, site, 2) == answer
            put(d.bready, site, 1, 1)
            await RisingEdge(d.clk)
            await FallingEdge(d.clk)
            put(d.bready, site, 1, 0)
            return answer
    raise AssertionError("AXI B response timeout")


async def read(d, site, offset, *, address=None):
    await FallingEdge(d.clk)
    put(d.araddr, site, 32, BASE[site] + offset if address is None else address)
    put(d.arvalid, site, 1, 1)
    for _ in range(60):
        await Timer(1, units="ns")
        if field(d.arready, site, 1):
            await RisingEdge(d.clk)
            await FallingEdge(d.clk)
            put(d.arvalid, site, 1, 0)
            break
        await FallingEdge(d.clk)
    else:
        raise AssertionError("AXI AR timeout")
    for _ in range(60):
        await FallingEdge(d.clk)
        await Timer(1, units="ns")
        if field(d.rvalid, site, 1):
            val = field(d.rdata, site, 32)
            status = field(d.rresp, site, 2)
            for _ in range(2):
                await FallingEdge(d.clk)
                assert field(d.rvalid, site, 1)
                assert field(d.rdata, site, 32) == val
            put(d.rready, site, 1, 1)
            await RisingEdge(d.clk)
            await FallingEdge(d.clk)
            put(d.rready, site, 1, 0)
            return status, val
    raise AssertionError("AXI R timeout")


async def expect(d, site, off, value):
    assert await read(d, site, off) == (0, value)


@cocotb.test()
async def independent_mode_admission_and_bitbang_pads(d):
    await start(d)
    for s in (0, 1):
        await expect(d, s, 0, 0x20001 + s)
        await expect(d, s, 0x38, 0)
        assert await write(d, s, 0x3C, 7) == 2   # DEBUG locked off
        assert await write(d, s, 0x14, (3 << 16) | 0x100) == 2
    assert await write(d, 0, 0x38, 3) == 2        # reserved mode
    assert await write(d, 0, 0x38, 2, strb=1) == 2
    assert await write(d, 0, 0x38, 2) == 0
    await expect(d, 0, 0x38, 2)
    assert await write(d, 0, 0x14, (4 << 16) | 0x100) == 2
    assert await write(d, 0, 0x3C, 8) == 2      # unknown debug bits
    assert await write(d, 0, 0x3C, 6) == 0      # DATA/OE settle at clock low
    assert await write(d, 0, 0x3C, 7) == 0      # then CLK high
    await expect(d, 0, 0x3C, 7)
    assert (await read(d, 0, 0x40)) == (0, 1)   # sampled data bit, 0x40 valid
    assert int(d.swclk_io.value) & 1
    assert d.swdio_io.value.binstr[-1] == "1"
    assert await write(d, 0, 0x3C, 1) == 2     # cannot change direction high
    assert await write(d, 0, 0x38, 1) == 2     # driven pads cannot change owner
    assert await write(d, 0, 0x3C, 6) == 0     # lower CLK without changing data
    assert await write(d, 0, 0x3C, 0) == 0     # release SWDIO at low CLK
    await FallingEdge(d.clk)
    assert (int(d.swclk_io.value) & 1) == 0
    assert await write(d, 0, 0x38, 1) == 0
    await expect(d, 0, 0x38, 1)
    assert await write(d, 0, 0x3C, 7) == 2    # debug writes now forbidden
    await expect(d, 1, 0x38, 0)               # Site 2 untouched
    assert (await read(d, 0, 0x40))[0] == 2   # sample debug-only
    assert (await read(d, 0, 0x44))[0] == 2   # reserved offset
    assert (await read(d, 0, 0, address=BASE[1]))[0] == 2
    assert (await read(d, 1, 0, address=BASE[0]))[0] == 2


@cocotb.test()
async def two_independent_normal_engines_and_immutable_responses(d):
    await start(d)
    for s, half in ((0, 50), (1, 60)):
        assert await write(d, s, 0x38, 1) == 0
        assert await write(d, s, 0x08, 2) == 2  # old 25MHz denied
        assert await write(d, s, 0x08, 49) == 2  # >1MHz denied
        await expect(d, s, 0x08, 500)           # no mutation on reject
        assert await write(d, s, 0x08, half) == 0
        assert await write(d, s, 0x28, 1) == 0
    for s in (0, 1):
        assert await write(d, s, 0x14, ((s + 1) << 16) | 0x100) == 0
    both_running = False
    edges = [0, 0]
    last = [0, 0]
    for _ in range(13500):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        clock = int(d.swclk_io.value)
        busy0 = int(d.g_sites[0].u_site.busy.value)
        busy1 = int(d.g_sites[1].u_site.busy.value)
        both_running = both_running or (busy0 and busy1)
        for s in (0, 1):
            level = (clock >> s) & 1
            if level and not last[s]:
                edges[s] += 1
            last[s] = level
        if int(d.g_sites[0].u_site.resp_valid.value) and int(
                d.g_sites[1].u_site.resp_valid.value):
            break
    else:
        raise AssertionError("both independent normal SWD commands timed out")
    assert both_running and min(edges) >= 64, edges
    assert int(d.swclk_io.value) == 0
    for s in (0, 1):
        await expect(d, s, 0x24, 2)
        meta = (await read(d, s, 0x18))[1]
        assert (meta >> 16) == s + 1 and (meta & 0xF) == 0
        assert await write(d, s, 0x38, 2) == 2   # response still owned
        assert await write(d, s, 0x20, s + 100) == 2  # wrong tagged POP
        assert await write(d, s, 0x20, s + 1) == 0
        await FallingEdge(d.clk)
        await expect(d, s, 0x24, 0)
        assert await write(d, s, 0x28, 0) == 0
        assert await write(d, s, 0x38, 0) == 0
    assert int(d.swclk_io.value) == 0


@cocotb.test()
async def debug_site_one_does_not_stop_normal_site_two(d):
    await start(d)
    assert await write(d, 0, 0x38, 2) == 0  # debug Site 1
    assert await write(d, 1, 0x38, 1) == 0  # normal Site 2
    assert await write(d, 1, 0x08, 50) == 0
    assert await write(d, 1, 0x28, 1) == 0
    assert await write(d, 1, 0x14, (9 << 16) | 0x100) == 0
    for _ in range(20):
        await RisingEdge(d.clk)
    assert int(d.g_sites[1].u_site.busy.value)
    assert await write(d, 0, 0x3C, 1) == 0   # Site 1 debug clock high
    assert int(d.swclk_io.value) & 1
    assert await write(d, 0, 0x3C, 0) == 0   # independent debug clock low
    assert await write(d, 0, 0x38, 0) == 0
    assert int(d.g_sites[1].u_site.busy.value), "Site 2 must not be cancelled"
    for _ in range(9500):
        await RisingEdge(d.clk)
        if int(d.g_sites[1].u_site.resp_valid.value):
            break
    else:
        raise AssertionError("Site 2 normal transaction stalled by Site 1")
    code, meta = await read(d, 1, 0x18)
    assert code == 0 and meta >> 16 == 9 and (meta & 0xF) == 0
    await expect(d, 0, 0x38, 0)
