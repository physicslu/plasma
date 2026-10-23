"""Icarus pad simulation with idealized Xilinx vendor primitives only."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_bluepill_pmod_iobuf_turnaround():
    run(
        simulator="icarus",
        verilog_sources=[
            str(PL / "rtl/site/plasma_poc_swd_pmod.sv"),
            str(PL / "sim/bluepill_pmod_vendor_stub.sv"),
        ],
        toplevel="bluepill_pmod_tb",
        module="test_bluepill_pmod_cocotb",
        python_search=[str(PL / "verification/cocotb")],
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        sim_build=str(PL / "build/bluepill-pmod-host"),
    )
