"""Source-only policy regressions; no ARM executable or hardware required."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "bluepill_armhf", Path(__file__).resolve().parents[1] / "check-openocd-bluepill-armhf.py"
)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class ArmhfPolicyTest(unittest.TestCase):
    def test_reject_new_glibc(self):
        for version in ("2.36", "2.38", "2.40"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "> 2.35"):
                CHECK.required_glibc(f"Version needs section '.gnu.version_r'\nName: GLIBC_{version}")

    def test_only_required_versions_count(self):
        self.assertEqual(CHECK.required_glibc("Version definition section\nName: GLIBC_2.40\nVersion needs section\nName: GLIBC_2.35\nName: GLIBC_2.4"), (2, 35))

    def test_reject_missing_swd_adapter(self):
        for text in ("", "remote_bitbang { jtag }", "dummy { swd }"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "missing"):
                CHECK.check_adapter(text)

    def test_accept_swd_adapter(self):
        CHECK.check_adapter("remote_bitbang { jtag swd }\n")

    def test_private_interface_only_for_libc_loader_pair(self):
        text = "Version needs section\nName: GLIBC_PRIVATE\nName: GLIBC_2.4"
        with self.assertRaises(ValueError):
            CHECK.required_glibc(text)
        self.assertEqual(CHECK.required_glibc(text, libc_loader_pair=True), (2, 4))

    def test_reject_soft_float(self):
        with self.assertRaises(ValueError):
            CHECK.check_armhf("Class: ELF32\nData: little endian\nMachine: ARM\nFlags: Version5 EABI, soft-float ABI")


if __name__ == "__main__":
    unittest.main()
