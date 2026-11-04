"""Real Icarus/Cocotb dual AXI-slave per-Site SWD RTL, HOST-ONLY.

Two Site registers/pads are separately instantiated. The eventual Vivado
AXI Interconnect, ARMv7 MMIO and OpenOCD Bridge still require qualification.
"""
from pathlib import Path
import subprocess
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]
NATIVE_SWD = PL.parent / "software/native/swd"


def test_two_independent_swd_axi_ips_normal_and_debug():
    run(
        simulator="icarus",
        verilog_sources=[str(PL / x) for x in (
            "rtl/swd/plasma_swd_transaction_engine.sv",
            "rtl/swd/plasma_swd_site_axi_lite.sv",
            "sim/swd_two_site_axi_tb.sv",
            "sim/IOBUF.sv",
            "sim/mpe_obuf_stub.sv",
        )],
        toplevel="swd_two_site_axi_tb",
        module="test_swd_independent_axi",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb"),
                       str(PL.parent / "software/python")],
        sim_build=str(PL / "build/swd-independent-two-site/axi-sim"),
    )


def test_production_c_fifo_core_drives_site_rtl():
    """pl/AGENTS.md 4A: the OpenOCD adapter's C FIFO core, compiled
    unmodified, issues every MMIO access through an AXI BFM to the RTL."""
    build = PL / "build/swd-independent-c-core"
    build.mkdir(parents=True, exist_ok=True)
    library = build / "libplasma_swd_fifo_core.so"
    subprocess.run([
        "gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-O1", "-fPIC", "-shared", f"-I{NATIVE_SWD}",
        str(NATIVE_SWD / "plasma_swd_fifo_core.c"),
        str(PL / "verification/cocotb/swd_c_core_abi.c"),
        "-o", str(library),
    ], check=True)
    run(
        simulator="icarus",
        verilog_sources=[str(PL / x) for x in (
            "rtl/swd/plasma_swd_transaction_engine.sv",
            "rtl/swd/plasma_swd_site_axi_lite.sv",
            "sim/swd_c_core_site_tb.sv",
            "sim/IOBUF.sv",
            "sim/mpe_obuf_stub.sv",
        )],
        toplevel="swd_c_core_site_tb",
        module="test_swd_c_fifo_core",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        extra_env={"PLASMA_SWD_C_CORE_SO": str(library)},
        sim_build=str(build / "axi-sim"),
    )


def test_abi5_swd_edge_phase_against_independent_target():
    """Bitbang timing control: target changes on SWCLK rise, host samples LOW.

    Unlike the existing virtual target, ACK[0] is put on the wire by the
    turnaround rising edge. This case must fail for the old HIGH-end sampler.
    """
    run(
        simulator="icarus",
        verilog_sources=[str(PL / "rtl/swd/plasma_swd_transaction_engine.sv")],
        toplevel="plasma_swd_transaction_engine",
        module="test_swd_abi5_edge_phase",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        sim_build=str(PL / "build/swd-independent-edge-phase/rtl-sim"),
    )


def test_abi5_stlink_legacy_sampling_negative_control(tmp_path):
    """Prove the ST-LINK trace detects the original HIGH-end ACK phase bug.

    Restore only the old sampling edge in an isolated *temporary* RTL copy;
    never modify the production RTL or bitstream to run the control.
    """
    source = (PL / "rtl/swd/plasma_swd_transaction_engine.sv").read_text()
    low_capture = (
        "                    if (phase == PH_ACK)\n"
        "                        ack_shift[bit_index[1:0]] <= swdio_in;\n"
        "                    if (phase == PH_DATA && read_direction_q)\n"
        "                        read_q[bit_index[4:0]] <= swdio_in;\n"
        "                    if (phase == PH_PARITY && read_direction_q)\n"
        "                        parity_sample_q <= swdio_in;\n"
    )
    low_anchor = low_capture + "                    swclk <= 1'b1;"
    high_anchor = (
        "                    swclk <= 1'b0;\n"
        "                    timer <= half_q - 16'd1;\n"
        "                    if (bit_index + 9'd1 < phase_bits) begin"
    )
    if source.count(low_anchor) != 1 or source.count(high_anchor) != 1:
        raise AssertionError("P0 SWD sample structure changed: re-review negative control")
    mutated = source.replace(
        low_anchor, "                    swclk <= 1'b1;", 1
    ).replace(
        high_anchor,
        "                    swclk <= 1'b0;\n"
        "                    timer <= half_q - 16'd1;\n"
        + low_capture
        + "                    if (bit_index + 9'd1 < phase_bits) begin",
        1,
    )
    # Legacy RTL used the *live* SWDIO value for the third ACK bit and
    # read parity because the clock-high sampling FF updates nonblocking
    # on exactly the same FCLK edge as phase completion. Restore this too:
    # reverting the sampling edge alone fabricates a different 000/BAD_ACK
    # regression, not the observed 100/FAULT failure.
    new_ack = "wire [2:0] complete_ack = ack_shift;"
    old_ack = "wire [2:0] complete_ack = {swdio_in,ack_shift[1:0]};"
    new_parity = "wire parity_read_mismatch = ((^read_q) != parity_sample_q);"
    old_parity = "wire parity_read_mismatch = ((^read_q) != swdio_in);"
    assert mutated.count(new_ack) == 1 and mutated.count(new_parity) == 1
    mutated = mutated.replace(new_ack, old_ack, 1)
    mutated = mutated.replace(new_parity, old_parity, 1)
    assert mutated != source
    fixture = tmp_path / "abi5-old-high-end-sampling.sv"
    fixture.write_text(mutated)
    run(
        simulator="icarus",
        verilog_sources=[str(fixture)],
        toplevel="plasma_swd_transaction_engine",
        module="test_swd_abi5_legacy_negative_control",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        sim_build=str(tmp_path / "mutated-sim"),
    )
