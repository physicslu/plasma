"""Cocotb / Icarus verification for independent physical MPE SWD engines.

Does not open FPGA devices or qualify HIL. Run via
  pytest -q pl/verification/test_mpe_dual_swd_core_rtl.py
on a host with iverilog and cocotb_test available.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer


def init(d):
    d.rst_n.value = 0
    d.site_enable.value = 0
    d.cmd_valid.value = 0
    d.cmd_abort.value = 0
    d.cmd_op.value = 3  # line reset both Sites
    d.cmd_ap.value = 0
    d.cmd_read.value = 0
    d.cmd_addr.value = 0
    d.cmd_wdata.value = 0
    d.cmd_half_period.value = (7 << 16) | 3
    d.cmd_turnaround.value = (1 << 3) | 1
    d.cmd_idle_cycles.value = (8 << 8) | 8
    d.cmd_max_retries.value = 0
    d.cmd_error_data_phase.value = 0
    d.cmd_timeout_cycles.value = (30000 << 32) | 30000
    d.resp_ready.value = 0


async def start_pair(d):
    # Drive at falling edges to avoid driver/DUT races at posedge sampling.
    await FallingEdge(d.clk)
    d.rst_n.value = 1
    d.site_enable.value = 3
    await RisingEdge(d.clk)
    await Timer(1, units="ns")
    assert int(d.cmd_ready.value) == 3
    await FallingEdge(d.clk)
    d.cmd_valid.value = 3
    await FallingEdge(d.clk)
    d.cmd_valid.value = 0


@cocotb.test()
async def two_sites_clock_independently_with_distinct_dividers(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
    init(d)
    await Timer(1, units="ns")
    assert int(d.swclk_io.value) == 0
    await start_pair(d)

    count = [0, 0]
    prev = [0, 0]
    both_busy = False
    finished = False
    for _ in range(6000):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        clock = int(d.swclk_io.value)
        busy = int(d.busy.value)
        both_busy = both_busy or busy == 3
        for site in range(2):
            level = (clock >> site) & 1
            if level and not prev[site]:
                count[site] += 1
            prev[site] = level
        if int(d.resp_valid.value) == 3:
            finished = True
            break
    assert finished, "both hardware Sites must finish independently"
    assert both_busy, "both engines must physically run simultaneously"
    assert all(c >= 64 for c in count), f"missing independent clocks: {count}"
    # Same line-reset command, but separate half-periods -> different duration.
    assert int(d.resp_status.value) == 0
    assert int(d.link_state.value) == 0b0101  # each Site waiting for real DPIDR
    assert int(d.swclk_io.value) == 0

    await FallingEdge(d.clk)
    d.resp_ready.value = 3
    await RisingEdge(d.clk)
    await RisingEdge(d.clk)
    assert int(d.resp_valid.value) == 0


@cocotb.test()
async def disabling_one_site_does_not_abort_the_other(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
    init(d)
    await start_pair(d)
    for _ in range(40):
        await RisingEdge(d.clk)
    assert int(d.busy.value) == 3

    # Quiesce Site 1 after its line-reset start. Site 2 is unaffected.
    await FallingEdge(d.clk)
    d.site_enable.value = 2
    await RisingEdge(d.clk)
    await Timer(1, units="ns")
    assert int(d.swclk_io.value) & 1 == 0
    assert int(d.cmd_ready.value) & 1 == 0
    # Enforced abort is Site-local; Site 2 continues through the sequence.
    assert int(d.busy.value) & 2 == 2
    got_second = False
    for _ in range(6000):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        if int(d.resp_valid.value) & 2:
            got_second = True
            break
    assert got_second
    assert ((int(d.resp_status.value) >> 4) & 0xF) == 0
    assert int(d.swclk_io.value) & 2 == 0
