from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "verification" / "cocotb" / "pl_loopback" / "Makefile"


def test_pl_loopback_axi_lite_cocotb_regression() -> None:
    if shutil.which("iverilog") is None or shutil.which("cocotb-config") is None:
        pytest.skip("PL Loopback RTL regression requires Icarus Verilog and cocotb")
    if importlib.util.find_spec("cocotb") is None:
        pytest.skip("PL Loopback RTL regression requires cocotb")

    completed = subprocess.run(
        ["make", "-f", str(MAKEFILE), "SIM=icarus"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout
