"""Real host-only dual-Site MPE AXI/RTL transaction regression, no hardware."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_mpe_dual_site_axi_slv():
    run(
        simulator="icarus",
        verilog_sources=[str(PL / x) for x in (
            "rtl/mpe/plasma_mpe_swd_engine.sv",
            "rtl/mpe/plasma_mpe_dual_swd_core.sv",
            "rtl/mpe/plasma_mpe_swd_axi_lite.sv",
            "sim/IOBUF.sv",
            "sim/mpe_obuf_stub.sv",
        )],
        toplevel="plasma_mpe_swd_axi_lite",
        module="test_mpe_swd_axi",
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[str(PL / "verification/cocotb")],
        sim_build=str(PL / "build/mpe-dual-site/axi-sim"),
    )
