"""GitHub-hosted Icarus/Cocotb SIM-1/SIM-2 dual real Site RTL regression."""
from pathlib import Path

from cocotb_test.simulator import run


PL = Path(__file__).resolve().parents[1]


def test_fixed_ppu_dual_site_abi_and_production_driver():
    run(
        simulator="icarus",
        verilog_sources=[
            str(PL / "rtl/site/swd_waveform_engine.sv"),
            str(PL / "rtl/site/swd_transaction_master.sv"),
            str(PL / "rtl/bus/fixed_fpga_ppu_global_identity_axi_lite.sv"),
            str(PL / "rtl/bus/fixed_fpga_swd_site_axi_lite.sv"),
            str(PL / "rtl/bus/fixed_ppu_unified_axi_dual_site.sv"),
        ],
        toplevel="fixed_ppu_unified_axi_dual_site",
        module="test_fixed_ppu_dual_site",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb"),
                       str(PL / "verification/models")],
        sim_build=str(PL / "build/fixed-ppu-unified-v1/axi-dual-site-sim"),
    )
