from pathlib import Path

from cocotb_tools.runner import get_runner


def test_adder():
    test_dir = Path(__file__).resolve().parent
    pl_dir = Path(__file__).resolve().parents[3]
    rtl_source = pl_dir / "rtl" / "examples" / "adder.sv"
    build_dir = pl_dir / "build" / "cocotb" / "adder"

    runner = get_runner("verilator")

    runner.build(
        sources=[rtl_source],
        hdl_toplevel="adder",
        build_dir=build_dir,
        waves=True,
    )

    runner.test(
        hdl_toplevel="adder",
        test_module="test_adder",
        build_dir=build_dir,
        test_dir=test_dir,
        waves=True,
    )
