"""Identity-only strict physical aperture, no SWD capability."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_identity_only_axi_lite_cocotb():
    run(simulator="icarus",
        verilog_sources=[str(PL / "rtl/bus/pl_identity_axi_lite.sv")],
        includes=[str(PL / "sim/identity_constants")],
        parameters={"CAPABILITY_FLAGS": 0, "STRICT_ADDRESS": 1,
                    "AXI_BASE_ADDRESS": 0x40000000},
        compile_args=["-g2012"], toplevel="pl_identity_axi_lite",
        module="test_pl_identity_only",
        python_search=[str(PL / "verification/cocotb")],
        timescale="1ns/1ps", sim_build=str(PL / "build/z2-identity/sim"))
