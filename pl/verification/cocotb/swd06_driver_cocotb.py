"""SWD-06: real SWD-05 driver -> cocotb AXI4-Lite BFM -> SWD-03 RTL.

The synchronous production driver executes on cocotb's external worker thread.
The only MMIO backend is a cocotb.function bridge: every driver read32/write32
causes a real simulated AXI4-Lite transaction with BRESP/RRESP checks and
B/R channel backpressure. This is NOT the SWD-05 FakeAXI state machine.
No Z2, Vivado, /dev/mem, runtime service or physical IC is accessed.
"""
from __future__ import annotations

import cocotb
from cocotb.triggers import Timer

from plasma_interfaces.swd_transaction import (
    SWDAck, SWDDriverError, SWDLink, SWDStatus, SWDTiming,
    SWDTransactionDriver,
)
from test_swd03_axi import AXIBench, SWDWireBench, BASE, OKAY

DPIDR = 0x2BA01477


def simulated_mmio(bench):
    """Bridge that can ONLY be called from a cocotb.external thread.

    The cocotb.function decorator schedules a coroutine back in the simulator
    thread and waits for actual AXI bus completion before returning.
    """
    @cocotb.function
    async def axi_read32(addr):
        if type(addr) is not int or addr & 3 or not BASE <= addr < BASE + 0x30:
            raise OSError("SWD06 BFM rejected out-of-range read")
        resp, data = await bench.read(addr - BASE)
        if resp != OKAY:
            raise OSError(f"AXI read RRESP={resp} at 0x{addr:08X}")
        return data

    @cocotb.function
    async def axi_write32(addr, data):
        if (type(addr) is not int or addr & 3 or not BASE <= addr < BASE + 0x30
                or type(data) is not int or not 0 <= data <= 0xFFFFFFFF):
            raise OSError("SWD06 BFM rejected out-of-range/value write")
        resp = await bench.write(addr - BASE, data)
        if resp != OKAY:
            raise OSError(f"AXI write BRESP={resp} at 0x{addr:08X}")

    class Bridge:
        def __init__(self):
            self.trace = []
            self.abort_on_busy = False
            self.cancel_driver = None

        def read32(self, addr):
            value = axi_read32(addr)
            self.trace.append(("r", addr, value))
            if (self.abort_on_busy and addr == BASE + 0x24 and
                    value & 1 and self.cancel_driver is not None):
                self.abort_on_busy = False
                assert self.cancel_driver.request_abort()
            return value

        def write32(self, addr, data):
            axi_write32(addr, data)
            self.trace.append(("w", addr, data))

    return Bridge()


def make_driver(bridge, *, timing=None):
    return SWDTransactionDriver(
        bridge, timing=timing, poll_budget=12000, poll_interval_s=0,
        max_poll_seconds=45.0,
    )


def started(bridge):
    return [v for typ, addr, v in bridge.trace
            if typ == "w" and addr == BASE + 4 and v == 1]


def acked(bridge):
    return [v for typ, addr, v in bridge.trace
            if typ == "w" and addr == BASE + 4 and v == 4]


@cocotb.test()
async def python_driver_against_synthesizable_dpidr_fixture(dut):
    """Actual RTL and synthesizable PL fixture, not a behavioral FakeAXI."""
    bench = AXIBench(dut)
    await bench.setup()
    bridge = simulated_mmio(bench)

    @cocotb.external
    def exercise():
        d = make_driver(bridge)
        assert bridge.trace == [("r", BASE, 1)]
        try:
            d.read_dp(0)
        except SWDDriverError as exc:
            assert "line_reset" in str(exc)
        else:
            raise AssertionError("read_dp allowed before line reset")
        assert started(bridge) == []

        reset = d.line_reset()
        assert reset.status == SWDStatus.OK
        assert reset.link_state == SWDLink.DPIDR_REQUIRED
        assert reset.attempts == 0
        assert d.read_dp(0) == DPIDR
        assert d.read_dp(0) == DPIDR  # response ACK really freed the RTL
        assert not d.poisoned

        # Synthesizable DPIDR fixture rejects all unsupported DP/AP operations.
        before = len(started(bridge))
        try:
            d.read_dp(4)  # non-DPIDR read gives RTL FAULT; no read data
        except SWDDriverError as exc:
            assert exc.response is not None
            assert exc.response.status == SWDStatus.FAULT
            assert exc.response.ack == SWDAck.FAULT
            assert not exc.response.data_valid
            assert exc.response.attempts == 1
        else:
            raise AssertionError("Unsupported read returned success")
        assert len(started(bridge)) == before + 1
        assert d.read_dp(0) == DPIDR

        before = len(started(bridge))
        try:
            d.write_dp(0, 0xDEADBEEF)
        except SWDDriverError as exc:
            assert exc.response is not None
            assert exc.response.status == SWDStatus.FAULT
            assert not exc.uncertain_target_effects
        else:
            raise AssertionError("Fixture accepted unsupported DP write")
        assert len(started(bridge)) == before + 1

        # All five transactions reached physical RTL START exactly once each.
        assert len(started(bridge)) == 6
        assert len(acked(bridge)) == len(started(bridge))
        assert not d.poisoned
        return len(bridge.trace)

    count = await exercise()
    assert count > 50
    dut._log.info("SWD06_SYNTH_RTL_PYTHON_DIFFERENTIAL_PASS mmio_words=%d", count)


@cocotb.test()
async def python_driver_against_line_level_virtual_target(dut):
    """SWD-03 AXI + SWD Master real RTL, independent edge-level target."""
    bench = SWDWireBench(dut)
    await bench.setup()
    bridge = simulated_mmio(bench)

    @cocotb.external
    def exercise():
        d = make_driver(bridge, timing=SWDTiming(max_wait_retries=2))
        assert d.line_reset().status == SWDStatus.OK
        assert d.read_dp(0) == DPIDR

        # Hardware owns bounded WAIT replay; the Python driver issues 1 START.
        bench.target.ack_script.extend([2, 2, 1])
        before = len(started(bridge))
        assert d.read_dp(0) == DPIDR
        assert len(started(bridge)) == before + 1
        bench.target.ack_script.extend([2, 2, 2])
        before = len(started(bridge))
        try:
            d.read_dp(0)
        except SWDDriverError as exc:
            assert exc.response is not None
            assert exc.response.status == SWDStatus.WAIT_LIMIT
            assert exc.response.ack == SWDAck.WAIT
            assert exc.response.attempts == 3
        else:
            raise AssertionError("WAIT limit did not surface to PS driver")
        assert len(started(bridge)) == before + 1

        bench.target.ack_script.append(4)
        try:
            d.read_dp(0)
        except SWDDriverError as exc:
            assert exc.response is not None
            assert exc.response.status == SWDStatus.FAULT
            assert exc.response.ack == SWDAck.FAULT
        else:
            raise AssertionError("Target FAULT not surfaced")

        bench.target.parity_fault = True
        try:
            d.read_dp(0)
        except SWDDriverError as exc:
            assert exc.response is not None
            assert exc.response.status == SWDStatus.PARITY
            assert exc.response.data_valid is False
            assert exc.response.link_state == SWDLink.RESET_REQUIRED
        else:
            raise AssertionError("Bad data parity not surfaced")
        try:
            d.read_dp(0)
        except SWDDriverError as exc:
            assert "line_reset" in str(exc)
        else:
            raise AssertionError("Driver read after parity loss of sync")
        assert d.line_reset().status == SWDStatus.OK
        assert d.read_dp(0) == DPIDR

        # The virtual target implements DP writes. The RTL transfer must
        # preserve the data exactly and complete with no read data_valid.
        r = d.write_dp(8, 0x11223344)
        assert r.status == SWDStatus.OK
        assert not r.data_valid and r.ack == SWDAck.OK
        assert bench.target.writes[-1] == (False, 8, 0x11223344)
        assert not d.poisoned
        return len(started(bridge)), len(bench.target.headers)

    transactions, headers = await exercise()
    assert transactions > 7 and headers >= transactions - 2
    dut._log.info("SWD06_WIRE_RTL_PYTHON_DIFFERENTIAL_PASS starts=%d headers=%d",
                  transactions, headers)


@cocotb.test()
async def python_driver_owner_thread_abort_against_real_axi(dut):
    """Cancellation signal goes to the driver; driver writes actual RTL ABORT."""
    bench = AXIBench(dut)
    await bench.setup()
    bridge = simulated_mmio(bench)

    @cocotb.external
    def exercise():
        d = make_driver(bridge, timing=SWDTiming(half_period_cycles=9))
        d.line_reset()
        assert d.read_dp(0) == DPIDR
        bridge.cancel_driver = d
        bridge.abort_on_busy = True
        before = len(started(bridge))
        try:
            d.write_dp(0, 0xA55A5AA5)
        except SWDDriverError as exc:
            assert exc.response is not None
            assert exc.response.status == SWDStatus.ABORTED
            assert exc.uncertain_target_effects is True
            assert exc.response.link_state == SWDLink.RESET_REQUIRED
        else:
            raise AssertionError("Owner thread failed to abort active RTL")
        assert len(started(bridge)) == before + 1
        commands = [v for typ, addr, v in bridge.trace
                    if typ == "w" and addr == BASE + 4]
        assert commands[-3:] == [1, 2, 4]
        assert not d.poisoned  # valid ABORTED response was consumed
        assert d.line_reset().status == SWDStatus.OK
        assert d.read_dp(0) == DPIDR

    await exercise()
    dut._log.info("SWD06_RTL_DRIVER_ABORT_AND_RECOVERY_PASS")


@cocotb.test()
async def python_driver_rtl_timeout_and_explicit_recovery(dut):
    """SWD Master internal FCLK timeout surfaced through real AXI to Python."""
    bench = AXIBench(dut)
    await bench.setup()
    bridge = simulated_mmio(bench)

    @cocotb.external
    def exercise():
        # 20 FCLK cycles are deliberately insufficient for the 64+64+8
        # SWCLK line reset: SWD-03 hardware, not Python polling, times out.
        driver = make_driver(bridge, timing=SWDTiming(timeout_cycles=20))
        before = len(started(bridge))
        try:
            driver.line_reset()
        except SWDDriverError as exc:
            assert exc.response is not None
            assert exc.response.status == SWDStatus.TIMEOUT
            assert exc.response.link_state == SWDLink.RESET_REQUIRED
        else:
            raise AssertionError("RTL timeout never propagated to SWD-05")
        assert len(started(bridge)) == before + 1
        assert len(acked(bridge)) == len(started(bridge))
        assert not driver.poisoned

        # No retry is performed automatically. Explicit caller decision
        # to recover and update transport timing must precede another START.
        driver.timing = SWDTiming(timeout_cycles=1_000_000)
        assert driver.line_reset().status == SWDStatus.OK
        assert driver.read_dp(0) == DPIDR
        assert len(started(bridge)) == before + 3

        # RTL rejects writes to read-only STATUS; the bridge must propagate
        # B channel SLVERR, not silently translate it to a successful write.
        try:
            bridge.write32(BASE + 0x24, 1)
        except OSError as exc:
            assert "BRESP=2" in str(exc)
        else:
            raise AssertionError("Real RTL AXI SLVERR was swallowed")

    await exercise()
    dut._log.info("SWD06_RTL_TIMEOUT_EXPLICIT_RECOVERY_AND_AXI_SLVERR_PASS")
