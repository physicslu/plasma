"""Offline PSPL-02 and SWD-00 Cocotb regression entry point."""
from pathlib import Path

from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]
RTL = PL / "rtl"
TESTS = PL / "verification" / "cocotb"
BUILD = PL / "build" / "pspl02-swd00" / "sim"


def test_pspl02_axi_control():
    run(
        simulator="icarus",
        verilog_sources=[str(RTL / "bus/pl_control_axi_lite.sv")],
        compile_args=["-g2012"],
        toplevel="pl_control_axi_lite",
        module="test_pl_control",
        python_search=[str(TESTS)],
        timescale="1ns/1ps",
        sim_build=str(BUILD / "control"),
    )


def test_swd00_waveform_engine():
    run(
        simulator="icarus",
        verilog_sources=[str(RTL / "site/swd_waveform_engine.sv")],
        compile_args=["-g2012"],
        toplevel="swd_waveform_engine",
        module="test_swd_waveform",
        python_search=[str(TESTS)],
        timescale="1ns/1ps",
        sim_build=str(BUILD / "waveform"),
    )
