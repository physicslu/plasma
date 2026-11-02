"""Independent edge-timed SWD PHY test against the real ABI-v5 RTL.

The target updates SWDIO *after* each SWCLK rising edge; OpenOCD bitbang
samples SWDIO in the LOW window before the next rising edge. Unlike the
historical SWD VirtualSWDTarget, ACK[0] becomes available on the turnaround
rising edge. A HIGH-end SWDIO sampler therefore observes the following bit.

Host-only timing/logic qualification; not electrical timing or real Z2 HIL.
"""
import cocotb
from cocotb.triggers import Timer
from stlink_golden_trace import extract_reference

BLUEPILL_DPIDR = 0x1BA01477


def bits(value, width):
    return [(value >> i) & 1 for i in range(width)]


class EdgeBench:
    def __init__(self, dut):
        self.d = dut
        self.previous_swclk = 0
        self.transfer_edges = None
        self.target_bits = []
        self.rising_edges = 0
        self.transmitted_request = []

    async def tick(self, count=1):
        d = self.d
        for _ in range(count):
            d.clk.value = 0
            await Timer(5, units="ns")
            d.clk.value = 1
            await Timer(1, units="ns")
            clock = int(d.swclk.value)
            if clock and not self.previous_swclk and self.transfer_edges is not None:
                idx = self.transfer_edges
                self.rising_edges += 1
                if idx < 8:
                    # Eight outgoing SWD request bits; target not driving yet.
                    assert int(d.swdio_oe.value) == 1, ("request OE", idx)
                    self.transmitted_request.append(int(d.swdio_out.value))
                else:
                    # First incoming bit begins at the turnaround rising edge.
                    rx_idx = idx - 8
                    # Only the target-driven turnaround/ACK/read response is
                    # Hi-Z on the host side; subsequent IDLE is host-owned.
                    if rx_idx < len(self.target_bits):
                        assert int(d.swdio_oe.value) == 0, ("target OE contention", idx)
                    d.swdio_in.value = (self.target_bits[rx_idx]
                                        if rx_idx < len(self.target_bits) else 1)
                self.transfer_edges += 1
            self.previous_swclk = clock
            await Timer(4, units="ns")

    async def setup(self):
        d = self.d
        d.clk.value = 0
        defaults = dict(rst_n=0, cmd_abort=0, cmd_valid=0,
                        cmd_op=0, cmd_sequence_bits=0, cmd_sequence_data=0,
                        cmd_ap=0, cmd_read=1, cmd_addr=0, cmd_wdata=0,
                        cmd_half_period=4, cmd_turnaround=1, cmd_idle_cycles=8,
                        cmd_max_retries=0, cmd_error_data_phase=0,
                        cmd_timeout_cycles=1000000, resp_ready=0, swdio_in=1)
        for name, value in defaults.items():
            getattr(d, name).value = value
        await self.tick(4)
        d.rst_n.value = 1
        await self.tick(2)

    async def command(self, *, sequence=False, half=4):
        d = self.d
        assert int(d.cmd_ready.value) == 1, "transaction engine not ready"
        d.cmd_half_period.value = half
        d.cmd_op.value = int(sequence)
        d.cmd_sequence_bits.value = 0
        d.cmd_valid.value = 1
        await self.tick()
        d.cmd_valid.value = 0
        for _ in range(20000):
            await self.tick()
            if int(d.resp_valid.value):
                break
        else:
            raise AssertionError("RTL transaction timed out")
        result = dict(status=int(d.resp_status.value),
                      ack=int(d.resp_ack.value),
                      data=int(d.resp_rdata.value),
                      valid=int(d.resp_data_valid.value),
                      link=int(d.link_state.value))
        d.resp_ready.value = 1
        await self.tick()
        d.resp_ready.value = 0
        await self.tick()
        assert int(d.swclk.value) == 0
        return result

    def begin_target(self, *, ack=1, data=BLUEPILL_DPIDR, parity_fault=False):
        # On each rising SWCLK: request[0..7], then turnaround emits ACK[0].
        # The ACK edge is *not* deferred until the following ACK phase.
        self.transfer_edges = 0
        self.transmitted_request = []
        self.target_bits = bits(ack, 3)
        if ack == 1:
            self.target_bits += bits(data, 32)
            self.target_bits.append((data.bit_count() & 1) ^ int(parity_fault))
        # Remaining idle/turnaround has no actively driven target value.
        self.d.swdio_in.value = 1


@cocotb.test()
async def abi5_swd_sample_before_rising_agrees_with_bitbang(d):
    """Old RTL incorrectly maps ACK OK + DPIDR bit0=1 to ACK FAULT."""
    for ack, data, parity_fault, half, expected in [
        (1, BLUEPILL_DPIDR, False, 4, 0),
        (1, BLUEPILL_DPIDR, False, 10, 0),
        (1, 0x12345678, False, 4, 0),
        (2, 0, False, 4, 3),
        (4, 0, False, 4, 4),
        (1, BLUEPILL_DPIDR, True, 4, 6),
        (7, 0, False, 4, 5),
    ]:
        b = EdgeBench(d)
        await b.setup()
        reset = await b.command(sequence=True, half=half)
        assert reset["status"] == 0 and reset["link"] == 1, reset
        b.begin_target(ack=ack, data=data, parity_fault=parity_fault)
        out = await b.command(half=half)
        assert out["status"] == expected, (ack, data, half, out)
        assert out["ack"] == ack, (ack, out)
        if expected == 0:
            assert out["valid"] == 1 and out["data"] == data, (data, out)
        else:
            assert out["valid"] == 0, out
        assert b.rising_edges > 8, b.rising_edges
        b.transfer_edges = None


@cocotb.test()
async def abi5_replay_real_stlink_verify_capture(d):
    """Use *recorded* STLINK-V3SET Target response bits, not fixture-generated ACK.

    The SHA-pinned LA2016 sample stream is decoded independently of RTL; only
    the bounded DP IDCODE/ACK and AP WAIT response windows are re-timed to the
    RTL's SWCLK. OE/clock source cannot be taken from the passive capture.
    """
    reference = extract_reference()
    assert reference["sha256"] and len(reference["dpidr"]) >= 2
    assert len(reference["wait"]) >= 1

    for frame in reference["dpidr"][:2]:
        b = EdgeBench(d)
        await b.setup()
        reset = await b.command(sequence=True)
        assert reset["status"] == 0 and reset["link"] == 1, reset
        b.begin_target(ack=1)
        b.target_bits = list(frame["response_bits"])  # Exact ST-LINK LA bits
        out = await b.command()
        assert out["status"] == 0 and out["ack"] == 1, (reference["name"], out)
        assert out["data"] == frame["data"] == BLUEPILL_DPIDR and out["valid"]
        assert tuple(b.transmitted_request) == tuple(frame["header"])

    # The saved WAIT was returned to a real request (not an invented response).
    # First establish a connected DP by replaying the measured DPIDR response.
    b = EdgeBench(d)
    await b.setup()
    reset = await b.command(sequence=True)
    assert reset["status"] == 0 and reset["link"] == 1
    b.begin_target(ack=1)
    b.target_bits = list(reference["dpidr"][0]["response_bits"])
    assert (await b.command())["status"] == 0
    wait = reference["wait"][0]
    request = wait["header"]
    d.cmd_ap.value = request[1]
    d.cmd_read.value = request[2]
    d.cmd_addr.value = request[3] * 4 + request[4] * 8
    b.begin_target(ack=2)
    b.target_bits = list(wait["response_bits"])
    out = await b.command()
    assert out["status"] == 3 and out["ack"] == 2, out
    assert tuple(b.transmitted_request) == tuple(request)
