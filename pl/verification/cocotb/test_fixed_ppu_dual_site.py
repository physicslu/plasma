"""Two actual SWD RTL Site engines behind one unified AXI4-Lite router.

Both SWD targets are independent virtual fixtures; none are physical DUTs.
SIM-2 uses the unchanged production FixedABISWDController and the new
protocol-neutral FixedABIHardwareDriver, not a Cocotb-only command sequence.
"""
import cocotb
from cocotb.triggers import Timer

from test_fixed_fpga_swd_site_axi import Bench, OKAY, SLVERR
from virtual_swd_target import VirtualSWDTarget

from plasma_interfaces.fixed_abi_hardware_driver import FixedABIHardwareDriver
from plasma_interfaces.fixed_abi_swd import (
    FixedABISWDController, FixedABIStatus, FixedABIError,
)


PPU_BASE = 0x40000000
SITE1 = PPU_BASE + 0x4000
SITE2 = PPU_BASE + 0x5000
IMAGE = (0x11112222, 0x33334444, 0x55556666, 0x77778888)
BUILD = (0xABCDE001, 0xABCDE002, 0xABCDE003, 0xABCDE004)


class DualBench(Bench):
    def __init__(self, dut):
        super().__init__(dut)
        self.targets = (VirtualSWDTarget(), VirtualSWDTarget())
        self.target = self.targets[0]
        self.old_clocks = (0, 0)

    async def tick(self, n=1):
        d = self.dut
        for _ in range(n):
            d.s_axi_aclk.value = 0
            await Timer(5, units="ns")
            d.s_axi_aclk.value = 1
            await Timer(1, units="ns")
            clocks = int(d.swclk.value)
            enables = int(d.swdio_oe.value)
            outputs = int(d.swdio_out.value)
            inputs = 0
            for site in range(2):
                mask = 1 << site
                clock = bool(clocks & mask)
                oe, out = bool(enables & mask), bool(outputs & mask)
                target = self.targets[site]
                if clock and not self.old_clocks[site]:
                    target.rising(oe, out)
                assert not (oe and target.drive), "SWDIO contention at Site %d" % (site + 1)
                value = target.value if target.drive else out if oe else 1
                if value:
                    inputs |= mask
            d.swdio_in.value = inputs
            self.old_clocks = (bool(clocks & 1), bool(clocks & 2))
            await Timer(4, units="ns")

    async def init(self):
        d = self.dut
        for name, value in {
            "s_axi_aresetn": 0, "s_axi_awaddr": 0, "s_axi_awprot": 0,
            "s_axi_awvalid": 0, "s_axi_wdata": 0, "s_axi_wstrb": 0,
            "s_axi_wvalid": 0, "s_axi_bready": 0, "s_axi_araddr": 0,
            "s_axi_arprot": 0, "s_axi_arvalid": 0, "s_axi_rready": 0,
            "swdio_in": 3,
        }.items():
            getattr(d, name).value = value
        await self.tick(4)
        d.s_axi_aresetn.value = 1
        await self.tick(2)


def production_dual_abi_port(bench, *, bad_wstrb_site=None):
    """Blocking PS word port -> Cocotb AXI4-Lite BFM -> real dual RTL."""
    @cocotb.function
    async def read_word(address):
        if type(address) is not int or address & 3 or not PPU_BASE <= address < PPU_BASE + 0x10000:
            raise OSError("Out-of-range/unqualified AXI read")
        response, value = await bench.read(address - SITE1)
        if response != OKAY:
            raise OSError("AXI RRESP=%d" % response)
        return value

    @cocotb.function
    async def write_word(address, value):
        if (type(address) is not int or address & 3 or
                not SITE1 <= address < SITE2 + 0x1000 or
                type(value) is not int or not 0 <= value <= 0xFFFFFFFF):
            raise OSError("Out-of-range/unqualified AXI write")
        strb = 1 if (bad_wstrb_site is not None and
                     address == bad_wstrb_site + 0x24) else 15
        response = await bench.write(address - SITE1, value, strb=strb)
        if response != OKAY:
            raise OSError("AXI BRESP=%d" % response)

    class Port:
        def __init__(self):
            self.operations = []
            self.barriers = 0

        def read32(self, address):
            result = read_word(address)
            self.operations.append(("read", address, result))
            return result

        def write32(self, address, value):
            write_word(address, value)
            self.operations.append(("write", address, value))

        def write_barrier(self):
            # Models only BFM ordering; not a qualified ARMv7 memory barrier.
            self.operations.append(("barrier",))
            self.barriers += 1

    return Port()


def admitted_sites(port):
    broker = FixedABIHardwareDriver(
        port, ppu_base=PPU_BASE, image_id=IMAGE, build_id=BUILD,
        site_bitmap=0x03,
    )
    broker.admit()
    return broker, broker.open_site(1), broker.open_site(2)


@cocotb.test()
async def sim1_real_dual_site_presence_decoder_and_negative_windows(dut):
    b = DualBench(dut)
    await b.init()
    assert await b.read(-0x4000) == (OKAY, 0x4D534C50)
    assert await b.read(-0x4000 + 0x30) == (OKAY, 3)
    assert await b.read(-0x4000 + 0x34) == (OKAY, 3)
    assert await b.read(0x00) == (OKAY, 1)
    assert await b.read(0x1000) == (OKAY, 2)
    assert await b.read(0x1004) == (OKAY, 0x10000)
    for address in (-4, 0x2000, 0xB000, 0xC000, 0xFFFC, 0x10000):
        assert await b.read(address - 0x4000) == (SLVERR, 0), hex(address)
        assert await b.write(address - 0x4000, 123, first="w") == SLVERR
    assert await b.write(0x1024, 201, first="w") == OKAY
    assert await b.read(0x000C) == (OKAY, 1)
    assert await b.read(0x100C) == (OKAY, 1)
    assert await b.write(0x1024, 202, strb=1) == SLVERR
    assert await b.write(0x1025, 202) == SLVERR
    assert await b.write(0x1020, 3) == SLVERR  # unsupported SPI command
    assert await b.write(-0x4000 + 4, 0x10000) == SLVERR
    assert await b.read(-0x4000 + 4) == (OKAY, 0x10000)
    dut._log.info("SIM1_DUAL_REAL_SITE_DECODER_AND_NEGATIVE_PASS")


@cocotb.test()
async def sim1_overlapping_site_engines_then_independent_completion(dut):
    b = DualBench(dut)
    await b.init()
    for offset, sequence in ((0, 501), (0x1000, 502)):
        for register, word in ((0x24, sequence), (0x28, 1),
                               (0x30, 64), (0x34, 0), (0x38, 0),
                               (0x3C, 100000), (0x5C, 8)):
            assert await b.write(offset + register, word) == OKAY
    assert await b.write(0x20, 2) == OKAY
    assert await b.write(0x1020, 2, first="w") == OKAY
    states = [(await b.read(x))[1] for x in (0x0C, 0x100C)]
    assert states == [2, 2], states  # both physical engines simultaneously BUSY
    for _ in range(5000):
        if ((await b.read(0x0C))[1] == 4 and
                (await b.read(0x100C))[1] == 4):
            break
    else:
        raise AssertionError("Independent dual RTL Sites did not complete")
    assert b.targets[0].resets == 1 and b.targets[1].resets == 1
    assert await b.read(0x48) == (OKAY, 501)
    assert await b.read(0x1048) == (OKAY, 502)
    assert await b.write(0x64, 501) == OKAY
    assert await b.write(0x1064, 502) == OKAY
    assert await b.read(-0x4000 + 0x34) == (OKAY, 3)
    dut._log.info("SIM1_TWO_INDEPENDENT_RTL_ENGINES_OVERLAP_PASS")


@cocotb.test()
async def sim1_reset_discards_unpaired_site2_aw_and_stalled_global_read(dut):
    b = DualBench(dut)
    await b.init()
    d = dut
    d.s_axi_awaddr.value = SITE2 + 0x24
    d.s_axi_awvalid.value = 1
    await b.tick()
    d.s_axi_awvalid.value = 0
    assert int(d.s_axi_awready.value) == 0
    d.s_axi_araddr.value = PPU_BASE
    d.s_axi_arvalid.value = 1
    await b.tick()
    d.s_axi_arvalid.value = 0
    await b.tick(5)  # router forwards AR, Global generates held R
    assert int(d.s_axi_rvalid.value) == 1
    d.s_axi_aresetn.value = 0
    await b.tick(3)
    assert not int(d.s_axi_bvalid.value) and not int(d.s_axi_rvalid.value)
    d.s_axi_aresetn.value = 1
    await b.tick(3)
    assert await b.read(-0x4000) == (OKAY, 0x4D534C50)
    assert await b.read(-0x4000 + 0x30) == (OKAY, 3)
    assert await b.write(0x1024, 711, first="w") == OKAY
    assert await b.read(0x100C) == (OKAY, 1)
    assert await b.read(0x0C) == (OKAY, 1)
    dut._log.info("SIM1_DUAL_SITE_RESET_PENDING_AW_AR_CLEAN_PASS")


@cocotb.test()
async def sim2_production_broker_and_swd_controller_two_virtual_targets(dut):
    b = DualBench(dut)
    await b.init()
    raw = production_dual_abi_port(b)

    @cocotb.external
    def execute():
        broker, one, two = admitted_sites(raw)
        for sid, port, base in ((1, one, SITE1), (2, two, SITE2)):
            controller = FixedABISWDController(port, base=base, site_id=sid)
            reset = controller.transact(sequence=700 + sid, opcode=2, bit_count=64)
            data = controller.transact(sequence=710 + sid, opcode=1,
                                       bit_count=32, arg0=2)
            assert reset.status == data.status == FixedABIStatus.OK
            assert data.data == 0x2BA01477 and data.ack == 1 and data.data_valid
            assert not controller.poisoned
        assert raw.barriers == 4
        assert broker.expected_site_bitmap == 3
        for addr in (SITE1 + 0x20, SITE2 + 0x20):
            assert ("write", addr, 2) in raw.operations
            assert ("write", addr, 1) in raw.operations
        return len(raw.operations)

    count = await execute()
    assert count > 60
    assert b.targets[0].resets == b.targets[1].resets == 1
    assert await b.read(-0x4000 + 0x34) == (OKAY, 3)
    dut._log.info("SIM2_PRODUCTION_DRIVER_DUAL_RTL_DPIDR_PASS count=%d", count)


@cocotb.test()
async def sim2_site1_timeout_poison_does_not_poison_site2(dut):
    b = DualBench(dut)
    await b.init()
    raw = production_dual_abi_port(b)

    @cocotb.external
    def execute():
        _, one, two = admitted_sites(raw)
        failed = FixedABISWDController(one, base=SITE1, site_id=1)
        healthy = FixedABISWDController(two, base=SITE2, site_id=2)
        try:
            failed.transact(sequence=801, opcode=2, bit_count=64, timeout_ticks=1)
        except FixedABIError as exc:
            assert exc.result is not None
            assert exc.result.status == FixedABIStatus.TIMEOUT
            assert exc.uncertain_target_effects
        else:
            raise AssertionError("Real Site1 timeout not surfaced by production driver")
        assert failed.poisoned
        try:
            failed.transact(sequence=802, opcode=2, bit_count=64)
        except FixedABIError:
            pass
        else:
            raise AssertionError("Site1 unsafe silent retry")
        assert healthy.transact(sequence=901, opcode=2, bit_count=64).status == 0
        result = healthy.transact(sequence=902, opcode=1, bit_count=32, arg0=2)
        assert result.status == 0 and result.data == 0x2BA01477
        assert not healthy.poisoned

    await execute()
    assert await b.read(0x0C) == (OKAY, 8)
    assert await b.read(0x100C) == (OKAY, 1)
    assert await b.read(-0x4000 + 0x30) == (OKAY, 3)
    assert await b.read(-0x4000 + 0x34) == (OKAY, 2)
    assert await b.read(-0x4000 + 0x1004) == (OKAY, 1)
    dut._log.info("SIM2_PRODUCTION_DRIVER_SITE_FAULT_ISOLATION_PASS")


@cocotb.test()
async def sim2_bad_wstrb_site2_fail_closed_without_site1_mutation(dut):
    b = DualBench(dut)
    await b.init()
    raw = production_dual_abi_port(b, bad_wstrb_site=SITE2)

    @cocotb.external
    def execute():
        _, one, two = admitted_sites(raw)
        bad = FixedABISWDController(two, base=SITE2, site_id=2)
        try:
            bad.transact(sequence=1001, opcode=2, bit_count=64)
        except FixedABIError as exc:
            assert "AXI write uncertain" in str(exc) and exc.uncertain_target_effects
        else:
            raise AssertionError("Illegal WSTRB silently accepted")
        assert bad.poisoned and raw.barriers == 0
        assert not any(x[:2] == ("write", SITE2 + 0x20) for x in raw.operations)
        safe = FixedABISWDController(one, base=SITE1, site_id=1)
        assert safe.transact(sequence=1002, opcode=2, bit_count=64).status == 0

    await execute()
    assert await b.read(0x1068) == (OKAY, 0)
    assert await b.read(0x0C) == (OKAY, 1)
    dut._log.info("SIM2_PRODUCTION_DRIVER_SITE2_WSTRB_NEGATIVE_PASS")
