"""LT02 exact synthesizable AXI scratchpad plus production Python driver."""
from pathlib import Path

from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_mmio_lt02_rtl_and_driver():
    run(
        simulator="icarus",
        verilog_sources=[str(PL / "rtl/bus/pl_mmio_loopback_axi_lite.sv")],
        toplevel="pl_mmio_loopback_axi_lite",
        module="test_mmio_lt02",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[
            str(PL.parent / "software/python"),
            str(PL / "verification/cocotb"),
        ],
        sim_build=str(PL / "build/mmio-lt02/sim"),
    )
