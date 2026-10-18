"""Host-only 64KiB unified AXI+Identity+SWD Site1 Cocotb integration tests.

Router is the only external AXI slave. No real physical address probing,
kernel memory, GPIO, RTL FPGA image synthesis, or board electrical evidence.
"""
import cocotb

from test_fixed_fpga_swd_site_axi import Bench, OKAY, SLVERR
from fixed_swd_site_driver import FixedSWDSiteSimDriver

SITE_BASE = 0x40004000
IDENT_OFF = -0x4000  # Bench base is SITE_BASE; negative offset addresses Global.


async def global_read(b, offset):
    return await b.read(IDENT_OFF + offset)


async def global_write(b, offset, val, *, first="aw"):
    return await b.write(IDENT_OFF + offset, val, first=first)


@cocotb.test()
async def unified_64k_address_decode_and_site_presence(dut):
    b = Bench(dut)
    await b.init()
    assert await global_read(b, 0x0000) == (OKAY, 0x4D534C50)
    assert await global_read(b, 0x0004) == (OKAY, 0x00010000)
    assert await global_read(b, 0x0028) == (OKAY, 1)   # SWD-only
    assert await global_read(b, 0x0030) == (OKAY, 1)   # Site 1 only
    assert await global_read(b, 0x0034) == (OKAY, 1)   # Site1 RTL genuinely IDLE
    assert await global_read(b, 0x0038) == (OKAY, 1)
    assert await global_read(b, 0x1000) == (OKAY, 1)
    assert await b.read(0x0000) == (OKAY, 1)  # Site ID at +0x4000
    assert await b.read(0x0004) == (OKAY, 0x00010000)
    assert await b.read(0x0008) == (OKAY, 1)
    assert await b.read(0x000C) == (OKAY, 1)
    dut._log.info("PPU_UNIFIED_AXI_ADDRESS_IDENTITY_PASS")


@cocotb.test()
async def unified_protected_decode_and_split_axi_aw_w(dut):
    b = Bench(dut)
    await b.init()
    # These intentionally invalid addresses MUST remain Cocotb-only.
    for off in (0x0001, 0x0002, 0x0054, 0x0FFC, 0x1010,
                0x2000, 0x3000, 0x5000, 0xB000, 0xC000, 0xFFFC,
                0x10000, -4):
        assert await global_read(b, off) == (SLVERR, 0), hex(off)
    # Global is readonly. Supply W before AW and do NOT forward it to Site1.
    assert await global_write(b, 0x0004, 0xA55A, first="w") == SLVERR
    assert await global_read(b, 0x0004) == (OKAY, 0x00010000)
    assert await b.read(0x000C) == (OKAY, 1)
    # Valid Site1 write uses the very same bus, with AW/W in either order.
    assert await b.write(0x24, 0x4321, first="w") == OKAY
    assert await b.write(0x5C, 2, first="aw") == OKAY
    assert await b.write(0x24, 0, first="aw") == SLVERR
    # AW in missing Site2 window + W must not mutate Site1.
    assert await global_write(b, 0x5000 + 0x24, 0x4322, first="w") == SLVERR
    assert await b.read(0x000C) == (OKAY, 1)
    assert await global_read(b, 0x0030) == (OKAY, 1)
    dut._log.info("PPU_UNIFIED_AXI_SPLIT_AW_W_SAFE_DECODE_PASS")


@cocotb.test()
async def unified_identity_then_driver_reset_and_virtual_dpidr(dut):
    b = Bench(dut)
    await b.init()
    assert await global_read(b, 0x0000) == (OKAY, 0x4D534C50)
    assert await global_read(b, 0x0030) == (OKAY, 1)
    assert await global_read(b, 0x0034) == (OKAY, 1)
    driver = FixedSWDSiteSimDriver(b)
    reset = await driver.transact(sequence=300, opcode=2, bit_count=64)
    assert reset.status == 0
    assert b.target.resets == 1
    dp = await driver.transact(sequence=301, opcode=1, bit_count=32, arg0=2)
    assert dp.status == 0 and dp.data == 0x2BA01477
    assert dp.ack == 1 and dp.data_valid
    assert (dp.attempts, dp.link_state, dp.raw_status) == (1, 2, 0)
    assert not driver.poisoned
    assert await global_read(b, 0x0034) == (OKAY, 1)
    assert await global_read(b, 0x1004) == (OKAY, 0)
    dut._log.info("PPU_UNIFIED_AXI_IDENTITY_DRIVER_DPIDR_PASS")


@cocotb.test()
async def unified_fault_flows_to_global_and_stays_sticky(dut):
    b = Bench(dut)
    await b.init()
    assert await b.write(0x24, 450) == OKAY
    assert await b.write(0x30, 64) == OKAY
    assert await b.write(0x34, 0) == OKAY
    assert await b.write(0x38, 0) == OKAY
    assert await b.write(0x3C, 1) == OKAY
    assert await b.write(0x20, 2) == OKAY
    assert await b.wait_done(3000) == 8
    assert await global_read(b, 0x0030) == (OKAY, 1)
    assert await global_read(b, 0x0034) == (OKAY, 0)
    assert await global_read(b, 0x0038) == (OKAY, 3)
    assert await global_read(b, 0x1004) == (OKAY, 1)
    assert await global_read(b, 0x1008) == (OKAY, 1)
    assert await b.read(0x0048) == (OKAY, 450)
    assert await b.read(0x004C) == (OKAY, 5)
    assert await b.write(0x64, 450) == OKAY
    assert await b.read(0x000C) == (OKAY, 8)
    assert await global_read(b, 0x0034) == (OKAY, 0)
    assert await global_read(b, 0x1004) == (OKAY, 1)
    assert await b.write(0x24, 451) == SLVERR
    # Read-only Identity unaffected by fatal Site1 transaction.
    assert await global_read(b, 0x0000) == (OKAY, 0x4D534C50)
    dut._log.info("PPU_UNIFIED_AXI_FAULT_ISOLATION_PASS")


@cocotb.test()
async def unified_reset_forgets_partial_aw_and_pending_read(dut):
    b = Bench(dut)
    await b.init()
    # Half-arrived Site1 AW must not be paired with new post-reset W.
    dut.s_axi_awaddr.value = SITE_BASE + 0x24
    dut.s_axi_awvalid.value = 1
    await b.tick()
    dut.s_axi_awvalid.value = 0
    assert int(dut.s_axi_awready.value) == 0
    # Start an Identity read, deliberately leave response unconsumed.
    dut.s_axi_araddr.value = 0x40000000
    dut.s_axi_arvalid.value = 1
    await b.tick()
    dut.s_axi_arvalid.value = 0
    dut.s_axi_aresetn.value = 0
    await b.tick(3)
    assert int(dut.s_axi_bvalid.value) == 0
    assert int(dut.s_axi_rvalid.value) == 0
    dut.s_axi_aresetn.value = 1
    await b.tick(3)
    assert await global_read(b, 0x0000) == (OKAY, 0x4D534C50)
    assert await b.read(0x000C) == (OKAY, 1)
    assert await global_write(b, 0x0004, 99, first="w") == SLVERR
    assert await b.write(0x24, 777, first="w") == OKAY
    assert await global_read(b, 0x0030) == (OKAY, 1)
    dut._log.info("PPU_UNIFIED_AXI_RESET_PARTIAL_TRANSACTION_PASS")


@cocotb.test()
async def unified_production_fixed_abi_controller_dpidr(dut):
    """Real PS control implementation -> unified router -> Site1 RTL -> virtual DUT.

    Only the Cocotb backend is simulated. No ARM device stores or real MMIO.
    """
    from test_fixed_fpga_swd_site_axi import production_fixed_abi_port
    from plasma_interfaces.fixed_abi_swd import FixedABISWDController, FixedABIStatus

    b = Bench(dut)
    await b.init()
    assert await global_read(b, 0x0000) == (OKAY, 0x4D534C50)
    assert await global_read(b, 0x0030) == (OKAY, 1)
    assert await global_read(b, 0x0034) == (OKAY, 1)
    assert await global_read(b, 0x0038) == (OKAY, 1)
    port = production_fixed_abi_port(b)

    @cocotb.external
    def execute_production_control():
        controller = FixedABISWDController(port, base=SITE_BASE, site_id=1)
        assert port.operations == []  # constructor does not touch AXI
        reset = controller.transact(sequence=801, opcode=2, bit_count=64)
        assert reset.status == FixedABIStatus.OK
        assert reset.link_state == 1 and not reset.data_valid
        dpidr = controller.transact(
            sequence=802, opcode=1, bit_count=32, arg0=2,
        )
        assert dpidr.status == FixedABIStatus.OK
        assert dpidr.data == 0x2BA01477
        assert (dpidr.ack, dpidr.data_valid, dpidr.attempts,
                dpidr.link_state, dpidr.raw_status) == (1, True, 1, 2, 0)
        assert not controller.poisoned
        assert port.barriers == 2
        for seq, opcode in ((801, 2), (802, 1)):
            start_idx = port.operations.index(("write", SITE_BASE + 0x20, opcode))
            ack_idx = port.operations.index(("write", SITE_BASE + 0x64, seq))
            assert port.operations[start_idx - 1] == ("barrier",)
            assert start_idx < ack_idx
        assert all(
            SITE_BASE <= op[1] < SITE_BASE + 0x100
            for op in port.operations if op[0] in ("read", "write")
        )
        return len(port.operations)

    operations = await execute_production_control()
    assert operations > 20 and b.target.resets == 1
    assert await b.read(0x000C) == (OKAY, 1)
    assert await global_read(b, 0x0034) == (OKAY, 1)
    assert await global_read(b, 0x1004) == (OKAY, 0)
    dut._log.info("SIM2_PRODUCTION_CONTROL_UNIFIED_AXI_DPIDR_PASS operations=%d",
                  operations)


@cocotb.test()
async def unified_production_fixed_abi_controller_timeout_sticky_fault(dut):
    """The production controller sees a fatal Site1 RTL fault via the router."""
    from test_fixed_fpga_swd_site_axi import production_fixed_abi_port
    from plasma_interfaces.fixed_abi_swd import (
        FixedABISWDController, FixedABIError, FixedABIStatus,
    )

    b = Bench(dut)
    await b.init()
    assert await global_read(b, 0x0034) == (OKAY, 1)
    port = production_fixed_abi_port(b)

    @cocotb.external
    def execute_timeout():
        controller = FixedABISWDController(port, base=SITE_BASE, site_id=1)
        try:
            controller.transact(
                sequence=811, opcode=2, bit_count=64, timeout_ticks=1,
            )
        except FixedABIError as exc:
            assert exc.result is not None
            assert (exc.result.sequence, exc.result.status) == (
                811, FixedABIStatus.TIMEOUT,
            )
            assert exc.uncertain_target_effects
        else:
            raise AssertionError("Production controller missed the actual RTL timeout")
        assert controller.poisoned
        assert port.barriers == 1
        try:
            controller.transact(sequence=812, opcode=2, bit_count=64)
        except FixedABIError as exc:
            assert "poisoned" in str(exc)
        else:
            raise AssertionError("Poisoned production controller attempted a retry")
        assert not any(op[:2] == ("write", SITE_BASE + 0x24) and
                       op[2] == 812 for op in port.operations)
        return len(port.operations)

    count = await execute_timeout()
    assert count > 10
    assert await b.read(0x000C) == (OKAY, 8)
    assert await b.read(0x0010) == (OKAY, 5)
    assert await b.read(0x0068) == (OKAY, 1)
    assert await global_read(b, 0x0030) == (OKAY, 1)
    assert await global_read(b, 0x0034) == (OKAY, 0)
    assert await global_read(b, 0x0038) == (OKAY, 3)
    assert await global_read(b, 0x1004) == (OKAY, 1)
    assert await global_read(b, 0x1008) == (OKAY, 1)
    assert await global_read(b, 0x0000) == (OKAY, 0x4D534C50)
    dut._log.info("SIM2_PRODUCTION_CONTROL_UNIFIED_AXI_STICKY_FAULT_PASS")


@cocotb.test()
async def unified_production_fixed_abi_controller_rejects_partial_wstrb(dut):
    """Bad WSTRB produces real AXI SLVERR without executing Site1 START."""
    from test_fixed_fpga_swd_site_axi import production_fixed_abi_port
    from plasma_interfaces.fixed_abi_swd import FixedABISWDController, FixedABIError

    b = Bench(dut)
    await b.init()
    port = production_fixed_abi_port(b, partial_sequence=True)

    @cocotb.external
    def execute_bad_wstrb():
        controller = FixedABISWDController(port, base=SITE_BASE, site_id=1)
        try:
            controller.transact(sequence=821, opcode=2, bit_count=64)
        except FixedABIError as exc:
            assert "AXI write uncertain" in str(exc)
            assert exc.uncertain_target_effects
        else:
            raise AssertionError("RTL/router accepted unsupported partial WSTRB")
        assert controller.poisoned
        assert port.barriers == 0
        assert not any(op[:2] == ("write", SITE_BASE + 0x20)
                       for op in port.operations)

    await execute_bad_wstrb()
    assert await b.read(0x000C) == (OKAY, 1)
    assert await b.read(0x0048) == (OKAY, 0)
    assert await b.read(0x0068) == (OKAY, 0)
    assert await global_read(b, 0x0034) == (OKAY, 1)
    assert await global_read(b, 0x1004) == (OKAY, 0)
    dut._log.info("SIM2_PRODUCTION_CONTROL_UNIFIED_AXI_WSTRB_FAIL_CLOSED_PASS")
