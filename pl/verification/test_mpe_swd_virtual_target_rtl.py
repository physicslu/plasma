"""MPE SWD transaction/virtual Blue Pill target, digital simulation only."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_mpe_swd_virtual_dpidr():
    run(
        simulator="icarus",
        verilog_sources=[str(PL / "rtl/mpe/plasma_mpe_swd_engine.sv")],
        toplevel="plasma_mpe_swd_engine",
        module="test_mpe_swd_virtual_target",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        sim_build=str(PL / "build/mpe-dual-site/virtual-target-sim"),
    )
