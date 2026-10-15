"""SWD-06 RTL <-> SWD-05 Python driver co-simulation with real AXI bus.

Not a mock register backend: the Cocotb bridge executes actual AW/W/B and
AR/R handshakes in Icarus against the original SWD-03 SystemVerilog RTL.
Only test fixtures are connected; no Z2, physical SWD, or DUT.
"""
from pathlib import Path

from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]
SOURCES = [
    str(PL / "rtl/site/swd_waveform_engine.sv"),
    str(PL / "rtl/site/swd_transaction_master.sv"),
    str(PL / "rtl/bus/swd_transaction_axi_lite.sv"),
]


def _run(testcase: str, *, synth_fixture: bool) -> None:
    sources = list(SOURCES)
    if synth_fixture:
        sources += [
            str(PL / "rtl/site/swd03_dpidr_responder.sv"),
            str(PL / "sim/swd03_axi_fixture_tb.sv"),
        ]
    run(
        simulator="icarus",
        verilog_sources=sources,
        toplevel=("swd03_axi_fixture_tb" if synth_fixture
                  else "swd_transaction_axi_lite"),
        module="test_swd06_rtl_python",
        testcase=testcase,
        compile_args=["-g2012"],
        timescale="1ns/1ps",
        python_search=[
            str(PL / "verification/cocotb"),
            str(PL / "verification/models"),
        ],
        sim_build=str(PL / "build/swd06" / testcase),
    )


def test_driver_against_real_axi_and_synthesizable_fixture():
    _run("python_driver_against_synthesizable_dpidr_fixture", synth_fixture=True)


def test_driver_against_real_axi_and_virtual_wire_target():
    _run("python_driver_against_line_level_virtual_target", synth_fixture=False)


def test_driver_cancellation_against_real_axi():
    _run("python_driver_owner_thread_abort_against_real_axi", synth_fixture=True)
