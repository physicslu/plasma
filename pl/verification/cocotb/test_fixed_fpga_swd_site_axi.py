"""Simulation-only AXI-Lite / Fixed ABI Site-1 / reused SWD master smoke tests.

Uses a virtual SWD target; never opens /dev/uio*, /dev/mem or drives pins.
"""
import cocotb
from cocotb.triggers import Timer
from virtual_swd_target import VirtualSWDTarget

BASE = 0x40004000
OKAY = 0
SLVERR = 2


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.target = VirtualSWDTarget()
        self.old_clock = 0

    async def tick(self, n=1):
        d = self.dut
        for _ in range(n):
            d.s_axi_aclk.value = 0
            await Timer(5, units="ns")
            d.s_axi_aclk.value = 1
            await Timer(1, units="ns")
            swclk = int(d.swclk.value)
            oe, out = int(d.swdio_oe.value), int(d.swdio_out.value)
            if swclk and not self.old_clock:
                self.target.rising(oe, out)
            assert not (oe and self.target.drive), "SWDIO contention"
            d.swdio_in.value = (self.target.value if self.target.drive
                                else out if oe else 1)
            self.old_clock = swclk
            await Timer(4, units="ns")

    async def init(self):
        d = self.dut
        for name, val in {
            "s_axi_aresetn": 0, "s_axi_awaddr": 0, "s_axi_awprot": 0,
            "s_axi_awvalid": 0, "s_axi_wdata": 0, "s_axi_wstrb": 0,
            "s_axi_wvalid": 0, "s_axi_bready": 0, "s_axi_araddr": 0,
            "s_axi_arprot": 0, "s_axi_arvalid": 0, "s_axi_rready": 0,
            "swdio_in": 1,
        }.items():
            getattr(d, name).value = val
        await self.tick(4)
        d.s_axi_aresetn.value = 1
        await self.tick(2)

    async def write(self, off, value, strb=15, first="aw"):
        d = self.dut
        async def aw():
            for _ in range(20):
                if int(d.s_axi_awready.value): break
                await self.tick()
            else: raise AssertionError("AWREADY stalled")
            d.s_axi_awaddr.value = BASE + off
            d.s_axi_awvalid.value = 1
            await self.tick()
            d.s_axi_awvalid.value = 0

        async def wd():
            for _ in range(20):
                if int(d.s_axi_wready.value): break
                await self.tick()
            else: raise AssertionError("WREADY stalled")
            d.s_axi_wdata.value = value
            d.s_axi_wstrb.value = strb
            d.s_axi_wvalid.value = 1
            await self.tick()
            d.s_axi_wvalid.value = 0

        if first == "aw":
            await aw(); await self.tick(); await wd()
        else:
            await wd(); await self.tick(); await aw()
        for _ in range(20):
            if int(d.s_axi_bvalid.value): break
            await self.tick()
        else: raise AssertionError("BVALID stalled")
        resp = int(d.s_axi_bresp.value)
        await self.tick(2)
        assert int(d.s_axi_bvalid.value) and int(d.s_axi_bresp.value) == resp
        d.s_axi_bready.value = 1
        await self.tick()
        d.s_axi_bready.value = 0
        await self.tick()
        assert int(d.s_axi_bvalid.value) == 0
        return resp

    async def read(self, off):
        d = self.dut
        for _ in range(20):
            if int(d.s_axi_arready.value): break
            await self.tick()
        else: raise AssertionError("ARREADY stalled")
        d.s_axi_araddr.value = BASE + off
        d.s_axi_arvalid.value = 1
        await self.tick()
        d.s_axi_arvalid.value = 0
        for _ in range(20):
            if int(d.s_axi_rvalid.value): break
            await self.tick()
        else: raise AssertionError("RVALID stalled")
        resp = int(d.s_axi_rresp.value)
        data = int(d.s_axi_rdata.value)
        await self.tick(2)
        assert int(d.s_axi_rvalid.value) and int(d.s_axi_rdata.value) == data
        d.s_axi_rready.value = 1
        await self.tick()
        d.s_axi_rready.value = 0
        await self.tick()
        return resp, data

    async def wait_done(self, limit=30000):
        for _ in range(limit):
            state = (await self.read(0x0c))[1]
            if state in (4, 8):
                return state
        raise AssertionError("No bounded SWD completion")


@cocotb.test()
async def site1_register_map_and_strict_axi_errors(dut):
    b = Bench(dut)
    await b.init()
    assert await b.read(0x00) == (OKAY, 1)
    assert await b.read(0x04) == (OKAY, 0x10000)
    assert await b.read(0x08) == (OKAY, 1)
    assert await b.read(0x0c) == (OKAY, 1)
    assert await b.read(0x58) == (OKAY, 0)  # no SPI FIFO
    assert await b.read(0x18) == (OKAY, 0)
    assert await b.read(0x20) == (SLVERR, 0)  # WO command is not readable
    assert await b.read(0x0700) == (SLVERR, 0)  # Reserved Site offset
    assert await b.read(0x1000) == (SLVERR, 0)  # No alias to Site 2
    assert await b.write(0x20, 1, strb=1) == SLVERR
    assert await b.write(0x21, 1, strb=15) == SLVERR
    assert await b.write(0x08, 0xFFFFFFFF) == SLVERR
    assert await b.write(0x28, 2) == SLVERR   # SPI unsupported
    assert await b.write(0x64, 1) == SLVERR   # No DONE result
    assert await b.write(0x24, 1, first="w") == OKAY
    assert await b.write(0x34, 0) == OKAY
    assert await b.write(0x20, 1) == OKAY    # before reset: NEED_RESET result
    assert await b.wait_done() == 4
    assert await b.read(0x48) == (OKAY, 1)
    assert await b.read(0x4c) == (OKAY, 10)  # NEED_RESET distinct
    assert await b.write(0x64, 2) == SLVERR # Exact sequence binding
    assert await b.write(0x64, 1) == OKAY
    assert await b.read(0x0c) == (OKAY, 1)
    dut._log.info("FIXED_ABI_SWDSITE_AXI_REGISTER_PASS")


@cocotb.test()
async def site1_reset_then_virtual_dpidr(dut):
    b = Bench(dut)
    await b.init()
    assert await b.write(0x24, 7) == OKAY
    assert await b.write(0x28, 1) == OKAY
    assert await b.write(0x30, 64) == OKAY
    assert await b.write(0x34, 0) == OKAY
    assert await b.write(0x38, 0) == OKAY
    assert await b.write(0x3c, 1000000) == OKAY
    assert await b.write(0x5c, 2) == OKAY
    assert await b.write(0x20, 2) == OKAY  # SWD_LINE_RESET, fixed 64-clock slice
    assert await b.write(0x20, 2) == SLVERR
    assert await b.write(0x24, 8) == SLVERR
    assert await b.wait_done() == 4
    assert (await b.read(0x48))[1] == 7
    assert (await b.read(0x4c))[1] == 0
    assert (await b.read(0x60))[1] == 0
    assert b.target.resets == 1
    assert await b.write(0x64, 7) == OKAY
    assert await b.write(0x24, 8) == OKAY
    assert await b.write(0x30, 32) == OKAY
    assert await b.write(0x34, 2) == OKAY  # DP read, addr=0
    assert await b.write(0x20, 1) == OKAY
    assert await b.wait_done() == 4
    assert await b.read(0x48) == (OKAY, 8)
    assert await b.read(0x4c) == (OKAY, 0)
    assert await b.read(0x60) == (OKAY, 0x2BA01477)
    assert await b.read(0x50) == (OKAY, 1)
    meta = (await b.read(0x6c))[1]
    assert meta & 7 == 1
    assert meta & 8
    assert ((meta >> 4) & 0x1FF) == 1
    assert ((meta >> 13) & 3) == 2
    assert await b.read(0x70) == (OKAY, 0)
    assert await b.write(0x64, 8) == OKAY
    assert await b.read(0x68) == (OKAY, 2)
    dut._log.info("FIXED_ABI_SWDSITE_DPIDR_PASS")


@cocotb.test()
async def injected_sim_driver_through_axi_to_virtual_swd_target(dut):
    """Pure Python driver -> real AXI-Lite RTL -> legacy SWD master -> virtual target."""
    from fixed_swd_site_driver import FixedSWDSiteSimDriver

    b = Bench(dut)
    await b.init()
    driver = FixedSWDSiteSimDriver(b, site_id=1)
    reset = await driver.transact(sequence=100, opcode=2, bit_count=64)
    assert reset.sequence == 100 and reset.status == 0
    assert b.target.resets == 1
    dpidr = await driver.transact(sequence=101, opcode=1, bit_count=32, arg0=2)
    assert dpidr.sequence == 101 and dpidr.status == 0
    assert dpidr.data == 0x2BA01477
    assert (dpidr.ack, dpidr.data_valid, dpidr.attempts, dpidr.link_state, dpidr.raw_status) == (1, True, 1, 2, 0)
    assert not driver.poisoned
    dut._log.info("FIXED_ABI_DRIVER_AXILITE_SWD_VIRTUAL_TARGET_PASS")
