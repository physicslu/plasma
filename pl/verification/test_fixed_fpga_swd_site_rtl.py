"""Run the isolated fixed-image SWD Site-1 AXI-Lite vertical slice in simulation.

No Vivado project, FPGA bitstream, physical pins, /dev/mem or real UIO.
"""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_fixed_fpga_swd_site1_abi_and_virtual_dpidr():
    run(
        simulator="icarus",
        verilog_sources=[
            str(PL / "rtl/site/swd_waveform_engine.sv"),
            str(PL / "rtl/site/swd_transaction_master.sv"),
            str(PL / "rtl/bus/fixed_fpga_swd_site_axi_lite.sv"),
        ],
        toplevel="fixed_fpga_swd_site_axi_lite",
        module="test_fixed_fpga_swd_site_axi",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb"),
                       str(PL / "verification/models")],
        sim_build=str(PL / "build/fixed-swd-v1/site1-sim"),
    )
