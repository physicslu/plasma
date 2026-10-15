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
