"""Compile and run OPP C driver against synthetic host-only register bank."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "software/native/swd"


def test_opp_common_native_c_host_only(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("C compiler unavailable")
    exe = tmp_path / "opp_common_test"
    subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
         str(NATIVE / "plasma_opp_common.c"),
         str(NATIVE / "tests/test_plasma_opp_common.c"),
         "-o", str(exe)],
        check=True,
    )
    result = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
    assert "OPP common C host-only PASS" in result.stdout
