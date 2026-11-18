"""Collect the standalone Host-only PPU Doctor unittest suite in Python PS CI.

The GitHub Python PS job invokes pytest only for software/python/tests.
Keep the existing Doctor negative regressions executable by that job without
duplicating tests or adding hardware/network execution.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST_SCRIPT = ROOT / "scripts/tests/test_plasma_ppu.py"
SPEC = importlib.util.spec_from_file_location("ppu_doctor_hostonly_regression", TEST_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# pytest collects this unittest.TestCase alias and every test_* method.
TestPPUDoctor = MODULE.DoctorTests


def test_retired_z2_doctor_entrypoints_are_absent():
    assert not (ROOT / "scripts/plasma_z2.py").exists()
    assert not (ROOT / "scripts/tests/test_plasma_z2.py").exists()
