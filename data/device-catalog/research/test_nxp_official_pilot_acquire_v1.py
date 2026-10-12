#!/usr/bin/env python3
"""Bounded source parser regression; does not simulate live acquisition."""
import importlib.util
import unittest
from pathlib import Path

SRC = Path(__file__).with_name("nxp_official_pilot_acquire_v1.py")
spec = importlib.util.spec_from_file_location("nxp_live_pilot", SRC)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class LivePilotParserTest(unittest.TestCase):
    def test_mcx_active_ordering_code(self):
        self.assertEqual(module.exact_code("MCXC041VFK\nPackage : HUQFN24\nMCXC041VFK", "MCXC"), "MCXC041VFK")
        self.assertEqual(module.lifecycle("MCXC041VFK (935463794557) Active Yes Yes"), "Active")
    def test_nxp_qualification_not_active(self):
        self.assertEqual(module.lifecycle("MCXN236VNLT Qualification Yes"), "Qualification")
        self.assertNotEqual(module.lifecycle("MCXN236VNLT Qualification Yes"), "Active")
    def test_kl25_exact_code(self):
        self.assertEqual(module.exact_code("MKL25Z128VLK4 Package LQFP80", "MKL25Z"), "MKL25Z128VLK4")
    def test_quality_rows_are_not_lifecycle(self):
        self.assertIsNone(module.lifecycle("MCXN236VNLT No 3 260 40 sec."))
    def test_bad_conflicting_status_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "contradictory"):
            module.lifecycle("MCXN236VNLT Active Qualification")
    def test_not_nxp_domains_are_rejected(self):
        self.assertFalse(module.official("https://www.nxp.com.evil.invalid/products"))
        self.assertFalse(module.official("http://www.nxp.com/products"))
        self.assertTrue(module.official("https://www.nxp.com/products/MCX-C04x"))
    def test_ambiguous_code_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            module.exact_code("MCXC041VFK MCXC041VFGR", "MCXC")

if __name__ == "__main__":
    unittest.main()
