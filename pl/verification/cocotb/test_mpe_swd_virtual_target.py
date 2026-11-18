"""Host-only line-level virtual SWD target, separate from MPE RTL.

This is a *real* Icarus execution with a Python protocol-bit responder; it is
NOT an external Blue Pill/DPIDR attestation. The target waveform comes from
SWD bit positions, NOT from the RTL implementation's internal phase.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer


DPIDR = 0x1BA01477
REQUEST_DPIDR = 0xA5  # LSB-first 8-bit SWD read DP addr 0 header


def configure(d):
    d.rst_n.value = 0
    d.cmd_valid.value = 0
    d.cmd_abort.value = 0
    d.cmd_op.value = 0
    d.cmd_ap.value = 0
    d.cmd_read.value = 1
    d.cmd_addr.value = 0
    d.cmd_wdata.value = 0
    d.cmd_half_period.value = 4
    d.cmd_turnaround.value = 1
    d.cmd_idle_cycles.value = 8
    d.cmd_max_retries.value = 0
    d.cmd_error_data_phase.value = 0
    d.cmd_timeout_cycles.value = 20000
    d.resp_ready.value = 0
    d.swdio_in.value = 1


async def reset(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
    configure(d)
    for _ in range(3):
        await FallingEdge(d.clk)
    d.rst_n.value = 1
    for _ in range(2):
        await FallingEdge(d.clk)


async def transact(d, *, line_reset):
    await FallingEdge(d.clk)
    d.cmd_op.value = 1 if line_reset else 0
    assert int(d.cmd_ready.value)
    d.cmd_valid.value = 1
    await FallingEdge(d.clk)
    d.cmd_valid.value = 0


async def complete(d, maxclocks=6000):
    for _ in range(maxclocks):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        if int(d.resp_valid.value):
            return
    raise AssertionError("SWD transaction had no bounded completion")


async def consume(d):
    await FallingEdge(d.clk)
    d.resp_ready.value = 1
    await FallingEdge(d.clk)
    d.resp_ready.value = 0
    await FallingEdge(d.clk)
    assert not int(d.resp_valid.value)


async def line_reset(d):
    await transact(d, line_reset=True)
    await complete(d)
    assert int(d.resp_status.value) == 0
    assert int(d.link_state.value) == 1
    assert int(d.swdio_oe.value) == 0
    assert int(d.swclk.value) == 0
    await consume(d)


async def virtual_swd_target(d, *, ack=1, data=DPIDR, parity_error=False):
    # Exactly the SWD on-wire sequence for an SWD DP_READ:
    # 8 request, 1 turnaround, 3 ACK, optional 32 data + 1 parity,
    # 1 turnaround, >=8 idle.
    # Sampling is performed at the end of the SWCLK high half-cycle.
    prev = 0
    clock_idx = 0
    header_bits = []
    saw_target_window = 0
    for _ in range(6000):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        clock = int(d.swclk.value)
        if clock and not prev:
            index = clock_idx
            clock_idx += 1
            if index < 8:
                header_bits.append((int(d.swdio_out.value), int(d.swdio_oe.value)))
            if 9 <= index <= 11:
                d.swdio_in.value = (ack >> (index - 9)) & 1
                assert int(d.swdio_oe.value) == 0, f"ACK contention at {index}"
                saw_target_window += 1
            elif ack == 1 and 12 <= index <= 43:
                d.swdio_in.value = (data >> (index - 12)) & 1
                assert int(d.swdio_oe.value) == 0, f"DATA contention at {index}"
                saw_target_window += 1
            elif ack == 1 and index == 44:
                d.swdio_in.value = (bin(data).count("1") & 1) ^ int(parity_error)
                assert int(d.swdio_oe.value) == 0
                saw_target_window += 1
            else:
                d.swdio_in.value = 1
        prev = clock
        if int(d.resp_valid.value):
            assert clock_idx >= (54 if ack == 1 else 20), clock_idx
            assert saw_target_window >= (36 if ack == 1 else 3)
            expected = [(REQUEST_DPIDR >> i) & 1 for i in range(8)]
            assert [v for v, oe in header_bits] == expected, header_bits
            assert all(oe == 1 for _, oe in header_bits)
            return clock_idx
    raise AssertionError("Target simulator timed out")


@cocotb.test()
async def virtual_bluepill_dpidr_ack_and_parity(d):
    await reset(d)
    await line_reset(d)
    await transact(d, line_reset=False)
    clocks = await virtual_swd_target(d)
    assert clocks >= 54
    assert int(d.resp_status.value) == 0
    assert int(d.resp_ack.value) == 1
    assert int(d.resp_data_valid.value) == 1
    assert int(d.resp_rdata.value) == DPIDR
    assert int(d.link_state.value) == 2
    await consume(d)


@cocotb.test()
async def virtual_dpidr_bad_parity_must_reject_data(d):
    await reset(d)
    await line_reset(d)
    await transact(d, line_reset=False)
    await virtual_swd_target(d, parity_error=True)
    assert int(d.resp_status.value) == 6
    assert int(d.resp_ack.value) == 1
    assert int(d.resp_data_valid.value) == 0
    assert int(d.resp_rdata.value) == 0
    assert int(d.link_state.value) == 0


@cocotb.test()
async def virtual_wait_not_replayed_and_no_data(d):
    await reset(d)
    await line_reset(d)
    await transact(d, line_reset=False)
    clocks = await virtual_swd_target(d, ack=2)
    assert clocks < 32, f"WAIT response unexpectedly clocked target data: {clocks}"
    assert int(d.resp_status.value) == 3
    assert int(d.resp_ack.value) == 2
    assert int(d.resp_data_valid.value) == 0
    assert int(d.resp_rdata.value) == 0
    assert int(d.resp_attempts.value) == 1
