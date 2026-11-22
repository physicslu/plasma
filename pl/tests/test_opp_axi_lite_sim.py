"""OPP AXI4-Lite behavioral simulation; host-only, never loads FPGA."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_opp_axi_lite_behavior(tmp_path):
    compiler = shutil.which("iverilog")
    runner = shutil.which("vvp")
    if not compiler or not runner:
        pytest.skip("Icarus Verilog unavailable")
    executable = tmp_path / "opp_axi_sim"
    subprocess.run(
        [compiler, "-g2012", "-s", "tb", "-o", str(executable),
         str(ROOT / "pl/rtl/bus/opp_common_axi_lite_v1.sv"),
         str(ROOT / "pl/sim/tb_opp_common_axi_lite_v1.sv")],
        check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        [runner, str(executable)], check=True, capture_output=True, text=True,
        timeout=30,
    )
    assert "OPP AXI4-Lite simulation PASS" in result.stdout
