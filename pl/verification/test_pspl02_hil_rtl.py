"""Exact PSPL-02 HIL functions vs actual RTL, independent of Z2."""
from pathlib import Path
import pytest
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("variant", ["control", "waveform"])
def test_pspl02_hil_functions_against_rtl(variant):
    sources = ["rtl/bus/pl_control_axi_lite.sv"] if variant == "control" else [
        "rtl/bus/swd_command_axi_lite.sv", "rtl/site/swd_waveform_engine.sv",
        "rtl/site/pl_loopback_responder.sv", "verification/sva/pl_axi_waveform_checks.sv",
        "sim/swd_command_axi_tb.sv",
    ]
    run(simulator="icarus", verilog_sources=[str(PL/p) for p in sources],
        toplevel="pl_control_axi_lite" if variant == "control" else "swd_command_axi_tb",
        module="pspl02_hil_cocotb", compile_args=["-g2012"], timescale="1ns/1ps",
        extra_env={"PSPL02_HIL_VARIANT": variant},
        python_search=[str(PL.parent), str(PL/"verification/cocotb")],
        sim_build=str(PL/"build/pspl02-hil"/variant))
