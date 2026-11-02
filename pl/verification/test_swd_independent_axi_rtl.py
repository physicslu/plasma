"""Real Icarus/Cocotb dual AXI-slave per-Site SWD RTL, HOST-ONLY.

Two Site registers/pads are separately instantiated. The eventual Vivado
AXI Interconnect, ARMv7 MMIO and OpenOCD Bridge still require qualification.
"""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


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
