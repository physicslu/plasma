"""Host-only real RTL AXI-Lite SWD bitbang register and negative tests."""
import cocotb
from cocotb.triggers import Timer

from plasma_interfaces.bluepill_remote_bitbang import RemoteBitbangSWD


BASE = 0x40008000
OKAY, SLVERR = 0, 2


class Bench:
    def __init__(self, dut):
        self.d = dut

    async def tick(self, n=1):
        for _ in range(n):
            self.d.s_axi_aclk.value = 0
            await Timer(5, units="ns")
            self.d.s_axi_aclk.value = 1
            await Timer(5, units="ns")

    async def reset(self):
        d = self.d
        for k, v in {
            "s_axi_aresetn": 0,
            "s_axi_awaddr": 0, "s_axi_awprot": 0, "s_axi_awvalid": 0,
            "s_axi_wdata": 0, "s_axi_wstrb": 0, "s_axi_wvalid": 0,
            "s_axi_bready": 0, "s_axi_araddr": 0,
            "s_axi_arprot": 0, "s_axi_arvalid": 0,
            "s_axi_rready": 0, "swdio_in": 1,
        }.items():
            getattr(d, k).value = v
        await self.tick(3)
        d.s_axi_aresetn.value = 1
        await self.tick()

    async def write(self, addr, value, *, strb=15, split=False):
        d = self.d
        d.s_axi_awaddr.value = addr
        d.s_axi_awvalid.value = 1
        d.s_axi_wdata.value = value
        d.s_axi_wstrb.value = strb
        if split:
            d.s_axi_wvalid.value = 0
            await self.tick()
            d.s_axi_awvalid.value = 0
            await self.tick()
            d.s_axi_wvalid.value = 1
        else:
            d.s_axi_wvalid.value = 1
        await self.tick()
        d.s_axi_awvalid.value = 0
        d.s_axi_wvalid.value = 0
        assert int(d.s_axi_bvalid.value) == 1
        result = int(d.s_axi_bresp.value)
        d.s_axi_bready.value = 1
        await self.tick()
        d.s_axi_bready.value = 0
        return result

    async def read(self, addr):
        d = self.d
        d.s_axi_araddr.value = addr
        d.s_axi_arvalid.value = 1
        await self.tick()
        d.s_axi_arvalid.value = 0
        assert int(d.s_axi_rvalid.value) == 1
        data = int(d.s_axi_rdata.value)
        response = int(d.s_axi_rresp.value)
        d.s_axi_rready.value = 1
        await self.tick()
        d.s_axi_rready.value = 0
        return response, data


@cocotb.test()
async def single_site_gpio_bitbang_register_lifecycle(dut):
    bench = Bench(dut)
    await bench.reset()
    assert (int(dut.swclk.value), int(dut.swdio_out.value),
            int(dut.swdio_oe.value)) == (0, 1, 0)
    assert await bench.read(BASE) == (OKAY, 0x50425357)
    assert await bench.read(BASE + 4) == (OKAY, 0x00010000)
    assert await bench.read(BASE + 12) == (OKAY, 0x09)
    assert await bench.write(BASE + 8, 7) == OKAY
    assert (int(dut.swclk.value), int(dut.swdio_out.value),
            int(dut.swdio_oe.value)) == (1, 1, 1)
    assert await bench.read(BASE + 12) == (OKAY, 0x0F)
    dut.swdio_in.value = 0
    assert await bench.read(BASE + 12) == (OKAY, 0x0E)
    # Split AW/W must commit precisely one whole word.
    assert await bench.write(BASE + 8, 0, split=True) == OKAY
    assert await bench.read(BASE + 12) == (OKAY, 0x00)
    assert await bench.write(BASE + 8, 2) == OKAY
    assert await bench.read(BASE + 12) == (OKAY, 0x08)


@cocotb.test()
async def rejects_register_escape_partial_strobe_reserved_bits_and_reset(dut):
    bench = Bench(dut)
    await bench.reset()
    assert await bench.write(BASE + 8, 2) == OKAY
    for addr, value, strobe in (
        (BASE + 4, 7, 15),  # ID/ABI read-only
        (BASE + 12, 7, 15),  # SAMPLE read-only
        (BASE + 8, 7, 1),  # partial AXI strobe
        (BASE + 8, 8, 15),  # reserved bit
        (BASE + 9, 0, 15),  # unaligned address
        (BASE + 0x1008, 7, 15),  # other Site aperture
    ):
        assert await bench.write(addr, value, strb=strobe) == SLVERR
        assert (int(dut.swclk.value), int(dut.swdio_out.value),
                int(dut.swdio_oe.value)) == (0, 1, 0)
    assert await bench.read(BASE + 0x1008) == (SLVERR, 0)
    assert await bench.read(BASE + 8) == (SLVERR, 0)
    assert await bench.write(BASE + 8, 7) == OKAY
    dut.s_axi_aresetn.value = 0
    await bench.tick(2)
    assert (int(dut.swclk.value), int(dut.swdio_out.value),
            int(dut.swdio_oe.value)) == (0, 1, 0)


@cocotb.test()
async def production_bridge_controls_actual_gpio_rtl(dut):
    """Real Python PS word-port -> Cocotb AXI BFM -> real PL candidate."""
    bench = Bench(dut)
    await bench.reset()

    @cocotb.function
    async def read_word(address):
        response, value = await bench.read(address)
        if response != OKAY:
            raise OSError("AXI read refused")
        return value

    @cocotb.function
    async def write_word(address, value):
        response = await bench.write(address, value)
        if response != OKAY:
            raise OSError("AXI write refused")

    class Port:
        def __init__(self):
            self.barriers = 0

        def read32(self, address):
            return read_word(address)

        def write32(self, address, value):
            write_word(address, value)

        def write_barrier(self):
            # Only host BFM ordering, not a native ARMv7 DMB proof.
            self.barriers += 1

    # RemoteBitbangSWD deliberately exposes a synchronous MMIO protocol.
    # Cocotb 1.9.x requires it to execute in an @external worker thread;
    # the @function wrappers then safely schedule AXI BFM coroutines.
    # Calling a @function from the simulator thread raises:
    # "queue_function called from unrecognized thread".
    @cocotb.external
    def exercise_bridge():
        port = Port()
        bridge = RemoteBitbangSWD(port, base=BASE)
        bridge.admit()
        assert bridge.exchange(b"Odefgc") == b"1"
        assert port.read32(BASE + 12) == 0x0F
        assert bridge.exchange(b"oQ") == b""
        assert port.read32(BASE + 12) == 0x09
        return port.barriers

    barriers = await exercise_bridge()
    assert (int(dut.swclk.value), int(dut.swdio_out.value),
            int(dut.swdio_oe.value)) == (0, 1, 0)
    assert barriers >= 7
