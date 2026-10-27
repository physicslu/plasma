"""Host-only Cocotb RTL acceptance for physical dual-Site SWD core.

Requires a host with Icarus + cocotb_test. This standalone verification
does not touch Vivado, SWPC, Z2, LA2016, FPGA Manager or Blue Pill.
"""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_mpe_two_independent_site_swd_engines():
    run(
        simulator="icarus",
        verilog_sources=[str(PL / path) for path in (
            "rtl/site/swd_waveform_engine.sv",
            "rtl/site/swd_transaction_master.sv",
            "rtl/mpe/plasma_mpe_dual_swd_core.sv",
            "sim/IOBUF.sv",
            "sim/mpe_obuf_stub.sv",
        )],
        toplevel="plasma_mpe_dual_swd_core",
        module="test_mpe_dual_swd_core",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        sim_build=str(PL / "build/mpe-dual-site/sim"),
    )
