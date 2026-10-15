"""SWD-03 AXI4-Lite RTL regression."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_swd03_axi_register_contract():
    run(
        simulator="icarus",
        verilog_sources=[
            str(PL / "rtl/site/swd_waveform_engine.sv"),
            str(PL / "rtl/site/swd_transaction_master.sv"),
            str(PL / "rtl/bus/swd_transaction_axi_lite.sv"),
        ],
        toplevel="swd_transaction_axi_lite",
        module="test_swd03_axi",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        sim_build=str(PL / "build/swd03/axi-sim"),
    )
