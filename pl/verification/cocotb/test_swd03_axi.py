"""SWD-03 AXI4-Lite register and handshake regression."""
import cocotb
from cocotb.triggers import Timer

BASE = 0x40003000
OKAY = 0
SLVERR = 2

REG_ABI = 0x00
REG_CONFIG = 0x08
REG_WDATA = 0x0C
REG_HALF = 0x10
REG_STATUS = 0x24


class AXIBench:
    def __init__(self, dut):
        self.d = dut

    async def tick(self, count=1):
        for _ in range(count):
            self.d.s_axi_aclk.value = 0
            await Timer(5, units="ns")
            self.d.s_axi_aclk.value = 1
            await Timer(5, units="ns")

    async def setup(self):
        d = self.d
        for name, value in {
            "s_axi_aresetn": 0,
            "s_axi_awaddr": 0,
            "s_axi_awprot": 0,
            "s_axi_awvalid": 0,
            "s_axi_wdata": 0,
            "s_axi_wstrb": 0,
            "s_axi_wvalid": 0,
            "s_axi_bready": 0,
            "s_axi_araddr": 0,
            "s_axi_arprot": 0,
            "s_axi_arvalid": 0,
            "s_axi_rready": 0,
            "swdio_in": 1,
        }.items():
            getattr(d, name).value = value

        await self.tick(4)
        d.s_axi_aresetn.value = 1
        await self.tick(2)

    async def write(self, offset, value, strb=15, order="aw"):
        d = self.d
        assert int(d.s_axi_bvalid.value) == 0

        async def address():
            assert int(d.s_axi_awready.value) == 1
            d.s_axi_awaddr.value = BASE + offset
            d.s_axi_awvalid.value = 1
            await self.tick()
            d.s_axi_awvalid.value = 0

        async def data():
            assert int(d.s_axi_wready.value) == 1
            d.s_axi_wdata.value = value
            d.s_axi_wstrb.value = strb
            d.s_axi_wvalid.value = 1
            await self.tick()
            d.s_axi_wvalid.value = 0

        if order == "aw":
            await address()
            await self.tick(2)
            await data()
        else:
            await data()
            await self.tick(2)
            await address()

        for _ in range(10):
            if int(d.s_axi_bvalid.value):
                break
            await self.tick()
        else:
            raise AssertionError("AXI BVALID timeout")

        response = int(d.s_axi_bresp.value)

        # BRESP must remain stable under backpressure.
        await self.tick(3)
        assert int(d.s_axi_bvalid.value) == 1
        assert int(d.s_axi_bresp.value) == response

        d.s_axi_bready.value = 1
        await self.tick()
        d.s_axi_bready.value = 0
        await self.tick()
        assert int(d.s_axi_bvalid.value) == 0

        return response

    async def read(self, offset):
        d = self.d
        assert int(d.s_axi_arready.value) == 1

        d.s_axi_araddr.value = BASE + offset
        d.s_axi_arvalid.value = 1
        await self.tick()
        d.s_axi_arvalid.value = 0

        for _ in range(10):
            if int(d.s_axi_rvalid.value):
                break
            await self.tick()
        else:
            raise AssertionError("AXI RVALID timeout")

        response = int(d.s_axi_rresp.value)
        data = int(d.s_axi_rdata.value)

        await self.tick(3)
        assert int(d.s_axi_rvalid.value) == 1
        assert int(d.s_axi_rresp.value) == response
        assert int(d.s_axi_rdata.value) == data

        d.s_axi_rready.value = 1
        await self.tick()
        d.s_axi_rready.value = 0
        await self.tick()

        return response, data


@cocotb.test()
async def axi_register_contract(dut):
    b = AXIBench(dut)
    await b.setup()

    # Reset values and fixed ABI.
    assert await b.read(REG_ABI) == (OKAY, 1)
    assert await b.read(REG_CONFIG) == (OKAY, 4)
    assert await b.read(REG_HALF) == (OKAY, 2)
    assert await b.read(REG_STATUS) == (OKAY, 2)

    # AW and W may arrive independently, in either order.
    assert await b.write(REG_WDATA, 0x11223344, order="aw") == OKAY
    assert await b.read(REG_WDATA) == (OKAY, 0x11223344)

    assert await b.write(
        REG_WDATA, 0xAABBCCDD, strb=0x5, order="w"
    ) == OKAY
    assert await b.read(REG_WDATA) == (OKAY, 0x11BB33DD)

    # Zero WSTRB must not modify configuration.
    assert await b.write(REG_WDATA, 0xFFFFFFFF, strb=0) == OKAY
    assert await b.read(REG_WDATA) == (OKAY, 0x11BB33DD)

    # Reserved bits are rejected, preserving old values.
    assert await b.write(REG_CONFIG, 0x100) == SLVERR
    assert await b.read(REG_CONFIG) == (OKAY, 4)

    assert await b.write(REG_HALF, 0x10000) == SLVERR
    assert await b.read(REG_HALF) == (OKAY, 2)

    # Undefined address and read-only register protection.
    assert await b.read(0x30) == (SLVERR, 0)
    assert await b.write(REG_STATUS, 123) == SLVERR

    dut._log.info("SWD03_AXI_REGISTER_CONTRACT_PASS")


# Wire-level fixture: the target only observes SWCLK edges, OE and SWDIO.
# It has no knowledge of AXI register writes or the master's internal state.
from virtual_swd_target import VirtualSWDTarget

REG_COMMAND = 0x04
REG_TURN = 0x14
REG_IDLE = 0x18
REG_RETRIES = 0x1C
REG_TIMEOUT = 0x20
REG_META = 0x28
REG_RDATA = 0x2C
STATUS_BUSY = 1 << 0
STATUS_READY = 1 << 1
STATUS_RESP_VALID = 1 << 2
DPIDR = 0x2BA01477


class SWDWireBench(AXIBench):
    def __init__(self, dut):
        super().__init__(dut)
        self.target = VirtualSWDTarget()
        self.old_swclk = 0
        self.edge_count = 0

    async def tick(self, count=1):
        for _ in range(count):
            self.d.s_axi_aclk.value = 0
            await Timer(5, units="ns")
            self.d.s_axi_aclk.value = 1
            await Timer(1, units="ns")
            clk = int(self.d.swclk.value)
            oe = int(self.d.swdio_oe.value)
            value = int(self.d.swdio_out.value)
            if clk and not self.old_swclk:
                self.target.rising(oe, value)
                self.edge_count += 1
            assert not (self.target.drive and oe), "SWDIO ownership collision"
            self.d.swdio_in.value = (
                self.target.value if self.target.drive
                else value if oe else 1
            )
            self.old_swclk = clk
            await Timer(4, units="ns")

    async def wait_response(self, limit=20000):
        for _ in range(limit):
            valid = int(self.d.master_resp_valid.value)
            if valid:
                assert int(self.d.master_busy.value) == 0
                return
            await self.tick()
        raise AssertionError("SWD master response timed out")

    async def complete(self):
        await self.wait_response()
        meta = await self.read(REG_META)
        data = await self.read(REG_RDATA)
        assert meta[0] == OKAY and data[0] == OKAY
        status = (await self.read(REG_STATUS))[1]
        assert status & STATUS_RESP_VALID
        assert not status & STATUS_READY
        # Result must be preserved while the host is not acknowledging it.
        for _ in range(15):
            assert (await self.read(REG_META))[1] == meta[1]
            assert (await self.read(REG_RDATA))[1] == data[1]
        return meta[1], data[1]

    async def acknowledge(self):
        assert await self.write(REG_COMMAND, 4) == OKAY
        state = (await self.read(REG_STATUS))[1]
        assert not (state & STATUS_RESP_VALID)
        assert state & STATUS_READY


@cocotb.test()
async def axi_to_virtual_swd_dpidr(dut):
    b = SWDWireBench(dut)
    await b.setup()
    assert await b.read(REG_STATUS) == (OKAY, STATUS_READY)

    # A transfer before line initialization returns NEED_RESET (2).
    assert await b.write(REG_COMMAND, 1) == OKAY
    meta, data = await b.complete()
    assert meta & 0xF == 2
    assert data == 0
    await b.acknowledge()

    # SWD line recovery: 64 released + 64 high + 8 low clocks.
    assert await b.write(REG_CONFIG, 0x05) == OKAY
    assert await b.write(REG_COMMAND, 1) == OKAY
    assert (await b.write(REG_COMMAND, 1)) == SLVERR
    assert (await b.write(REG_CONFIG, 0x04)) == SLVERR
    meta, data = await b.complete()
    assert meta & 0xF == 0 and data == 0
    assert b.target.resets == 1
    assert b.edge_count >= 136
    assert (await b.write(REG_CONFIG, 0x04)) == SLVERR
    await b.acknowledge()

    # Read DP DPIDR via AXI: request, turnaround, ACK, data and parity.
    assert await b.write(REG_CONFIG, 0x04) == OKAY
    assert await b.write(REG_COMMAND, 1) == OKAY
    meta, data = await b.complete()
    assert (meta & 0xF) == 0
    assert ((meta >> 4) & 7) == 1
    assert ((meta >> 7) & 1) == 1
    assert ((meta >> 8) & 0x1FF) == 1
    assert data == DPIDR
    assert b.target.headers[-1] == 0xA5
    await b.acknowledge()

    # Input configuration violations are reported by the transaction master,
    # not silently coerced by the AXI adapter.
    assert await b.write(REG_HALF, 1) == OKAY
    assert await b.write(REG_COMMAND, 1) == OKAY
    meta, data = await b.complete()
    assert (meta & 0xF) == 1 and data == 0
    await b.acknowledge()
    assert await b.write(REG_HALF, 2) == OKAY

    # A running write must be interrupted without automatic retry.
    assert await b.write(REG_CONFIG, 0x00) == OKAY  # DP write ABORT
    assert await b.write(REG_HALF, 9) == OKAY
    assert await b.write(REG_COMMAND, 1) == OKAY
    assert ((await b.read(REG_STATUS))[1] & STATUS_BUSY) != 0
    assert await b.write(REG_WDATA, 0xDEADBEEF) == SLVERR
    assert await b.write(REG_COMMAND, 2) == OKAY
    meta, _ = await b.complete()
    assert (meta & 0xF) == 8  # ABORTED; target effects are uncertain
    await b.acknowledge()

    dut._log.info("SWD03_AXI_TO_VIRTUAL_TARGET_PASS")
