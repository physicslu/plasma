"""Production C FIFO core (OpenOCD plasma_swd adapter) on the real ABI-v5 RTL.

Every register access below is issued by software/native/swd/
plasma_swd_fifo_core.c through its injected read32/write32 interface; the
tests only choose the OpenOCD-level calls and the target behaviour, then
check results, the MMIO sequence and the wire. Host-only RTL transaction
simulation; NOT ARMv7/PS7 MMIO, Z2 or Blue Pill evidence.
"""
import cocotb
from ctypes import byref, c_uint32

from swd_c_core_bridge import (ACK_FAULT, AP0_R, AP0_W,
                               BAD_RESPONSE, Bench, DP_CTRL_R, DP_DPIDR_R,
                               DP_RDBUFF_R, NOT_READY, OK,
                               load_library, slot)

LIB = load_library()


async def bench(dut, **kw):
    b = Bench(dut, LIB)
    await b.start()
    await b.connect(**kw)
    return b


def completions(b, since):
    """(tag, status, ack) of every COMPLETION_META the C core read."""
    return [(v >> 16, v & 0xF, (v >> 4) & 7)
            for op, off, v, _ in b.log[since:] if op == "r" and off == 0x18]


async def queue_scratch_rounds(b, values, results):
    """AP0 write v, AP0 read (posted), DP RDBUFF read -> v, per value."""
    for i, value in enumerate(values):
        assert await b.call("plasma_swd_fifo_queue_write", AP0_W, value, 0) == OK
        assert await b.call("plasma_swd_fifo_queue_read", AP0_R, None, 0) == OK
        assert await b.call("plasma_swd_fifo_queue_read", DP_RDBUFF_R,
                            slot(results, i), 0) == OK


@cocotb.test()
async def admit_line_reset_dpidr_and_recover_off(dut):
    b = await bench(dut)
    assert b.target.resets == 1
    assert b.writes(0x38) == [1]
    assert b.writes(0x08) == [4]
    assert b.writes(0x68) == []  # no AP delay requested: register untouched
    assert await b.quiesce() == 1
    assert b.writes(0x38)[-1] == 0


@cocotb.test()
async def pipelined_batch_keeps_rtl_fifo_full_and_publishes_in_order(dut):
    b = await bench(dut)
    values = [0xA5000000 | (i * 0x01010101 & 0x00FFFFFF) for i in range(20)]
    results = (c_uint32 * len(values))()
    await queue_scratch_rounds(b, values, results)
    b.max_cmd_level = 0
    assert await b.call("plasma_swd_fifo_run") == OK
    assert list(results) == values
    assert b.max_cmd_level >= 8, b.max_cmd_level  # >1 outstanding in RTL
    writes = [v for ap, addr, v in b.target.writes if ap and addr == 0]
    assert writes == values
    await b.quiesce()


@cocotb.test()
async def full_software_queue_auto_flushes_through_the_rtl(dut):
    b = await bench(dut)
    n = 300  # > PLASMA_SWD_MAX_QUEUE (256): reserve() runs the first block
    results = (c_uint32 * n)()
    for i in range(n):
        assert await b.call("plasma_swd_fifo_queue_read", DP_DPIDR_R,
                            slot(results, i), 0) == OK
    assert b.fifo.count == n - 256
    assert await b.call("plasma_swd_fifo_run") == OK
    assert set(results) == {0x2BA01477}
    await b.quiesce()


@cocotb.test()
async def ap_delay_hint_programs_idle_cycles_only_on_change(dut):
    b = await bench(dut)
    mark = len(b.log)
    rdbuff = c_uint32(0)
    assert await b.call("plasma_swd_fifo_queue_write", AP0_W, 0x1234, 20) == OK
    assert await b.call("plasma_swd_fifo_queue_read", AP0_R, None, 300) == OK
    assert await b.call("plasma_swd_fifo_queue_read", DP_RDBUFF_R,
                        byref(rdbuff), 300) == OK  # DP: hint ignored
    assert await b.call("plasma_swd_fifo_run") == OK
    assert rdbuff.value == 0x1234
    assert b.writes(0x68, mark) == [20, 255, 8]
    _, idle = await b.read(0x68)
    assert idle == 8
    await b.quiesce()
    assert await b.read(0x68) == (0, 8)  # MODE OFF restores the default


@cocotb.test()
async def mid_pipeline_fault_reports_and_site_stays_usable(dut):
    b = await bench(dut)
    values = list(range(1, 9))
    results = (c_uint32 * len(values))()
    await queue_scratch_rounds(b, values, results)
    # 7th transfer (AP write of value 3) gets FAULT; nothing is latched.
    b.target.ack_script.extend([1] * 6 + [4])
    assert await b.call("plasma_swd_fifo_run") == ACK_FAULT
    assert not b.fifo.blocked and b.fifo.admitted
    assert list(results) == [0] * len(values)  # nothing published
    assert await b.read(0x2C) == (0, 0)       # no RTL fault latch
    assert await b.read(0x24) == (0, 0)       # all completions popped
    assert await b.reconnect() == 0x2BA01477  # OpenOCD-style reconnect
    await b.quiesce()


@cocotb.test()
async def mid_pipeline_parity_latches_discards_and_clears(dut):
    b = await bench(dut)
    values = list(range(0x10, 0x18))
    results = (c_uint32 * len(values))()
    await queue_scratch_rounds(b, values, results)
    headers_before = len(b.target.headers)
    # Corrupt the parity of the 3rd OK read = round 2 AP0 read = 5th op.
    original, reads = b.target._read_value, [0]

    def read_value():
        reads[0] += 1
        b.target.parity_fault = reads[0] == 3
        return original()
    b.target._read_value = read_value
    mark = len(b.log)
    assert await b.call("plasma_swd_fifo_run") == BAD_RESPONSE
    done = completions(b, mark)
    assert [st for _, st, _ in done] == [0, 0, 0, 0, 6], done  # ST_PARITY
    pushed = len(b.writes(0x14, mark))
    assert pushed > 5, pushed  # later commands were already in the RTL FIFO
    assert len(b.target.headers) - headers_before == 5  # ...never executed
    w = [(off, v) for op, off, v, _ in b.log[mark:] if op == "w"]
    assert w.index((0x28, 4)) < w.index((0x2C, 1))  # discard, then RW1C
    assert list(results) == [0] * len(values)
    assert not b.fifo.blocked and b.fifo.admitted
    assert await b.read(0x2C) == (0, 0)
    assert await b.read(0x24) == (0, 0)
    assert await b.reconnect() == 0x2BA01477
    await b.quiesce()


@cocotb.test()
async def rtl_timeout_latches_and_is_cleared(dut):
    b = await bench(dut)
    # Harness configuration, not C logic: a 20-FCLK budget expires inside
    # the 8-bit request (HALF_PERIOD 4 = 8 FCLK per bit), before the target
    # drives SWDIO. The production budget (1,000,000 FCLK = 10 ms) cannot
    # expire this way because the RTL generates SWCLK itself.
    assert await b.write(0x0C, 20) == 0
    dpidr = c_uint32(0)
    assert await b.call("plasma_swd_fifo_queue_read", DP_DPIDR_R,
                        byref(dpidr), 0) == OK
    assert await b.call("plasma_swd_fifo_queue_read", DP_CTRL_R, None, 0) == OK
    mark = len(b.log)
    assert await b.call("plasma_swd_fifo_run") == BAD_RESPONSE
    assert [st for _, st, _ in completions(b, mark)] == [7]  # ST_TIMEOUT
    assert len(b.writes(0x14, mark)) == 2  # CTRL read pushed, discarded
    assert await b.read(0x2C) == (0, 0)
    assert await b.read(0x24) == (0, 0)
    assert await b.write(0x0C, 1000000) == 0
    # The abandoned request leaves the link at NEED_RESET: reconnect.
    assert await b.reconnect() == 0x2BA01477
    await b.quiesce()


@cocotb.test()
async def silent_target_is_bad_ack_not_a_latched_fault(dut):
    b = await bench(dut)
    b.target.silent = True
    results = (c_uint32 * 4)()
    for i in range(4):
        assert await b.call("plasma_swd_fifo_queue_read", DP_DPIDR_R,
                            slot(results, i), 0) == OK
    mark = len(b.log)
    assert await b.call("plasma_swd_fifo_run") == BAD_RESPONSE
    done = completions(b, mark)
    # No ACK (pulled-up 111) -> BAD_ACK; the engine then refuses the rest
    # with NEED_RESET instead of clocking a desynchronised target.
    assert done == [(done[0][0], 5, 7)] + [(t, 2, 0) for t, _, _ in done[1:]]
    assert len(done) == 4
    assert not b.fifo.blocked
    assert await b.read(0x2C) == (0, 0)
    assert await b.read(0x24) == (0, 0)
    b.target.silent = False
    assert await b.reconnect() == 0x2BA01477
    await b.quiesce()


@cocotb.test()
async def mid_pipeline_wait_without_orundetect_is_reported_not_replayed(dut):
    b = await bench(dut)  # CTRL/STAT without ORUNDETECT
    values = [0x51, 0x52, 0x53]
    results = (c_uint32 * len(values))()
    await queue_scratch_rounds(b, values, results)
    b.target.ack_script.extend([1, 1, 1, 2])  # round 2 AP write: WAIT
    writes_before = len(b.target.writes)
    assert await b.call("plasma_swd_fifo_run") == BAD_RESPONSE
    # Later transfers already ran on the wire (no ORUNDETECT); C must not
    # replay the waited write after them.
    later = b.target.writes[writes_before:]
    assert (True, 0, 0x52) not in later
    assert not b.fifo.blocked
    assert await b.read(0x24) == (0, 0)
    await b.quiesce()


@cocotb.test()
async def wrong_site_window_bus_error_blocks_admission(dut):
    b = Bench(dut, LIB)
    await b.start()
    rc = LIB.plasma_swd_fifo_init(byref(b.fifo), byref(b.io), 1, 1000)
    assert rc == OK
    # read32 failed (SLVERR): admit reports the Site as not this ABI.
    assert await b.call("plasma_swd_fifo_admit") == BAD_RESPONSE
    assert b.log[-1][:2] == ("r", 0x43C01000 - 0x43C02000) and b.log[-1][3] == 2
    assert b.fifo.blocked
    assert await b.call("plasma_swd_fifo_run") == NOT_READY
    assert await b.read(0x38) == (0, 0)  # the real Site was never touched


@cocotb.test()
async def wait_with_orundetect_has_no_data_phase_and_desynchronises(dut):
    """CHARACTERISATION of a known RTL gap (2026-11-04), not desired behaviour.

    OpenOCD's dap_dp_init sets CTRL/STAT.ORUNDETECT. ADIv5 then requires a
    33-clock data phase after every WAIT/FAULT, but the engine hard-wires
    cmd_error_data_phase=0. The target consumes the following idle clocks
    and request as write data (WDATAERR), the next transfer sees no ACK
    (BAD_ACK) and the rest of the batch is refused with NEED_RESET. The C
    WAIT -> ABORT -> re-push path is therefore not reached; the batch fails
    without replay and an OpenOCD-style reconnect recovers. Update this test
    when the RTL gains the ORUNDETECT data phase.
    """
    b = await bench(dut, ctrl=0x50000001)
    values = [0x61, 0x62, 0x63]
    results = (c_uint32 * len(values))()
    await queue_scratch_rounds(b, values, results)
    b.target.ack_script.extend([1, 1, 1, 2])  # round 2 AP write: WAIT
    writes_before = len(b.target.writes)
    mark = len(b.log)
    assert await b.call("plasma_swd_fifo_run") == BAD_RESPONSE
    done = [(st, ack) for _, st, ack in completions(b, mark)]
    assert done[:5] == [(0, 1), (0, 1), (0, 1), (3, 2), (5, 7)], done
    assert all(d == (2, 0) for d in done[5:]) and len(done) == 10, done
    assert b.target.control & 0x82 == 0x82  # WDATAERR + STICKYORUN
    assert b.target.writes[writes_before:] == [(True, 0, 0x61)]  # no replay
    assert list(results) == [0] * len(values)
    assert not b.fifo.blocked
    assert await b.reconnect(ctrl=0x50000001) == 0x2BA01477
    assert b.target.control & 0xB2 == 0  # ABORT cleared the sticky flags
    await b.quiesce()
