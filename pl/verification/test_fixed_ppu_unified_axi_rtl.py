"""Icarus + Cocotb Host-only 64 KiB PPU Unified AXI/Identity/SWD Site1."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_fixed_ppu_unified_axi_site1_identity_and_virtual_swd():
    run(
        simulator="icarus",
        verilog_sources=[
            str(PL / "rtl/site/swd_waveform_engine.sv"),
            str(PL / "rtl/site/swd_transaction_master.sv"),
            str(PL / "rtl/bus/fixed_fpga_ppu_global_identity_axi_lite.sv"),
            str(PL / "rtl/bus/fixed_fpga_swd_site_axi_lite.sv"),
            str(PL / "rtl/bus/fixed_ppu_unified_axi_site1.sv"),
        ],
        toplevel="fixed_ppu_unified_axi_site1",
        module="test_fixed_ppu_unified_axi",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb"),
                       str(PL / "verification/models")],
        sim_build=str(PL / "build/fixed-ppu-unified-v1/axi-site1-sim"),
    )
