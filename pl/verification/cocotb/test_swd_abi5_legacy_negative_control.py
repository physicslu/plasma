"""Negative control against the *real* archived ST-LINK ACK waveform.

This test is ONLY run on an intentionally mutated copy of the ABI-v5 RTL,
restoring the old SWCLK-HIGH-end sample point. It must produce the observed
ACK=0b100/FAULT from a known-good 0b001/OK physical response. The normal
(unmutated) ABI-v5 test independently requires ACK OK and the exact DPIDR.
"""
import cocotb

from stlink_golden_trace import extract_reference
from test_swd_abi5_edge_phase import EdgeBench


@cocotb.test()
async def old_high_end_sampling_reproduces_spurious_fault(dut):
    golden = extract_reference()
    frame = golden["dpidr"][0]
    assert frame["data"] == 0x1BA01477

    bench = EdgeBench(dut)
    await bench.setup()
    reset = await bench.command(sequence=True)
    assert reset["status"] == 0 and reset["link"] == 1

    bench.begin_target(ack=1)
    bench.target_bits = list(frame["response_bits"])
    observed = await bench.command()
    # The old RTL consumed ACK[0] during turnaround and sampled ACK[1],
    # ACK[2] and DPIDR bit0, thereby returning FAULT=0b100.
    assert observed["ack"] == 0b100, observed
    assert observed["status"] == 4, observed
    assert not observed["valid"], observed
