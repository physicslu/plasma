"""Host-only actual SWD-04 transaction/recovery functions vs SWD-03 RTL."""
from pathlib import Path
from cocotb_test.simulator import run

PL = Path(__file__).resolve().parents[1]


def test_swd04_exact_hil_functions_against_rtl():
    run(
        simulator='icarus',
        verilog_sources=[str(PL / name) for name in (
            'rtl/site/swd_waveform_engine.sv',
            'rtl/site/swd_transaction_master.sv',
            'rtl/bus/swd_transaction_axi_lite.sv',
            'rtl/site/swd03_dpidr_responder.sv',
            'sim/swd03_axi_fixture_tb.sv',
        )],
        toplevel='swd03_axi_fixture_tb', module='swd04_hil_cocotb',
        compile_args=['-g2012'], timescale='1ns/1ps',
        python_search=[str(PL.parent), str(PL.parent/'software/python'),
                       str(PL/'verification/cocotb'), str(PL/'verification/models')],
        sim_build=str(PL/'build/swd04-staging/hil-rtl'),
    )
