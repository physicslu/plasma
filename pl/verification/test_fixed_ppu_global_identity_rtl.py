"""Icarus/Cocotb-only PPU Global Identity candidate; no bitstream or real UIO."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_fixed_ppu_global_identity_axi_rtl():
    run(
        simulator="icarus",
        verilog_sources=[
            str(PL / "rtl/bus/fixed_fpga_ppu_global_identity_axi_lite.sv"),
        ],
        toplevel="fixed_fpga_ppu_global_identity_axi_lite",
        module="test_fixed_ppu_global_identity",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        sim_build=str(PL / "build/fixed-ppu-identity-v1/global-identity-sim"),
    )
