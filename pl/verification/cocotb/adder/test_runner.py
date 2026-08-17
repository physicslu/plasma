from pathlib import Path

from cocotb_tools.runner import get_runner


def test_adder(monkeypatch):
    test_source_dir = Path(__file__).resolve().parent
    pl_dir = Path(__file__).resolve().parents[3]
    rtl_source = pl_dir / "rtl" / "examples" / "adder.sv"
    build_dir = pl_dir / "build" / "cocotb" / "adder"

    # cocotb runs the simulator in test_dir and writes wave/results files there.
    # Keep the Python test module importable while running the simulator entirely
    # from the disposable build tree so generated artifacts never pollute source.
    monkeypatch.syspath_prepend(str(test_source_dir))

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
        test_dir=build_dir,
        waves=True,
    )
