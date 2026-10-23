"""Host-only Icarus/Cocotb of independent Blue Pill SWD GPIO AXI-Lite IP."""
from pathlib import Path

from cocotb_test.simulator import run


PL = Path(__file__).resolve().parents[1]


def test_bluepill_remote_bitbang_axi_registers():
    run(
        simulator="icarus",
        verilog_sources=[str(PL / "rtl/bus/plasma_poc_swd_gpio_axi_lite.sv")],
        toplevel="plasma_poc_swd_gpio_axi_lite",
        module="test_bluepill_remote_bitbang_axi",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        sim_build=str(PL / "build/bluepill-bitbang-gate1"),
    )
