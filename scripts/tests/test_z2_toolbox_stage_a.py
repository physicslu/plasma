"""Stage A host guards and sigrok artifact interpretation."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "z2-toolbox.py"
SPEC = importlib.util.spec_from_file_location("z2_toolbox", SCRIPT)
assert SPEC and SPEC.loader
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class StageATest(unittest.TestCase):
    def test_no_attestation_stops_before_devices(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "stage-a"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Blue Pill", result.stderr)

    def test_wave_edges_and_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            wave = Path(directory) / "test.sr"
            with zipfile.ZipFile(wave, "w") as archive:
                archive.writestr("metadata", "[device 1]\nsamplerate=1 MHz\nunitsize=2\n"
                                 "probe1=CH0\nprobe2=CH1\nprobe3=CH2\nprobe4=CH3\n")
                states = bytes([4, 0]) * 10 + bytes([15, 0]) * 10 + bytes([4, 0]) * 10
                archive.writestr("logic-1-1", states)
            previous = tool.SAMPLES
            try:
                tool.SAMPLES = 30
                result = tool.analyze_wave(wave)
            finally:
                tool.SAMPLES = previous
            self.assertTrue(result["reference_ch2_high"])
            self.assertTrue(result["clock_ch0_edges"])
            self.assertTrue(result["dio_ch1_edges"])
            self.assertTrue(result["clock_ch3_edges"])
            self.assertEqual(result["sample_count"], 30)


if __name__ == "__main__":
    unittest.main()
