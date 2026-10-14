"""Cocotb/pytest front door for the first production PL modules.

Run: python3 -m pytest -v pl/verification/test_z2_swd_gpio_rtl.py
Requires Icarus Verilog, cocotb, cocotb-test, pytest.
"""
from __future__ import annotations

from pathlib import Path

from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]
SIM = PL / "sim"
RTL = PL / "rtl"
TB = PL / "verification" / "cocotb"
BUILD = PL / "build" / "z2-swd-gpio" / "sim"


def test_identity_axi_lite_cocotb():
    run(
        simulator="icarus",
        verilog_sources=[str(RTL / "bus/pl_identity_axi_lite.sv")],
        includes=[str(SIM / "identity_constants")],
        compile_args=["-g2012"],
        toplevel="pl_identity_axi_lite",
        module="test_pl_identity",
        python_search=[str(TB)],
        timescale="1ns/1ps",
        sim_build=str(BUILD / "identity"),
    )


def test_swd_emio_tristate_cocotb():
    run(
        simulator="icarus",
        verilog_sources=[
            str(SIM / "IOBUF.sv"),
            str(RTL / "site/swd_emio_bridge.sv"),
            str(SIM / "swd_emio_bridge_tb.sv"),
        ],
        compile_args=["-g2012"],
        toplevel="swd_emio_bridge_tb",
        module="test_swd_emio_bridge",
        python_search=[str(TB)],
        timescale="1ns/1ps",
        sim_build=str(BUILD / "swd-emio"),
    )
