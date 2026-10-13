#!/usr/bin/env python3
"""Offline NXP exact commercial /part/ field extraction regressions."""
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nxp_meta", HERE / "nxp_bulk_part_metadata_v1.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BODY = """MCXA156VFT
Active

Package

H-PQFN48: H-PQFN48, thermal enhanced - plastic quad flat non-lead; 48 terminals; 7 mm x 7 mm body

Buy Options

Operating Features
"""
TABLE = [
    ["Flash (kB)", "1024"],
    ["Ambient Operating Temperature (Min to Max) (℃)", "-40 to 125"],
]


class NxpBulkPartMetadataContracts(unittest.TestCase):
    def test_freeze_all_341_metadata_gaps(self):
        values = mod.rows()
        self.assertEqual(len(values), 341)
        self.assertEqual(len(set(values)), 341)
        self.assertNotIn("MKL25Z128VLK4", values)
        for i in range(8):
            selected = [v for j, v in enumerate(values) if j % 8 == i]
            self.assertIn(len(selected), (42, 43))
        self.assertFalse(mod.official("https://www.nxp.com.evil.invalid/part/MCXA156VFT"))

    def test_exact_official_part_has_package_flash_and_ambient(self):
        row = mod.parse_official_part(BODY, TABLE, "MCXA156VFT", ["MCXA156VFT"])
        self.assertEqual(row["package_raw"], "H-PQFN48")
        self.assertEqual(row["package_terminals"], 48)
        self.assertEqual(row["flash_kb_raw"], 1024)
        self.assertEqual(row["ambient_temperature_raw"], "-40 to 125")
        self.assertEqual(row["manufacturer_metadata_fields_observed"], 4)
        self.assertFalse(row["canonical_metadata_admission_authorized"])
        self.assertFalse(row["programming_backend_qualified"])

    def test_redirect_to_family_or_parent_does_not_inherit_metadata(self):
        with self.assertRaisesRegex(ValueError, "heading"):
            mod.parse_official_part(BODY, TABLE, "MCXA156VFTR", ["MCXA156VFT"])

    def test_missing_flash_is_unknown_not_zero(self):
        row = mod.parse_official_part(BODY, TABLE[1:], "MCXA156VFT", ["MCXA156VFT"])
        self.assertIsNone(row["flash_kb_raw"])
        self.assertEqual(row["manufacturer_metadata_fields_observed"], 3)

    def test_contradictory_manufacturer_flash_is_not_silently_chosen(self):
        with self.assertRaisesRegex(ValueError, "contradictory"):
            mod.parse_official_part(BODY, TABLE + [["Flash (kB)", "512"]],
                                    "MCXA156VFT", ["MCXA156VFT"])

    def test_package_name_pin_number_disagreement_blocks(self):
        with self.assertRaisesRegex(ValueError, "terminal count disagreement"):
            mod.parse_official_part(BODY.replace("48 terminals", "64 terminals"),
                                    TABLE, "MCXA156VFT", ["MCXA156VFT"])


if __name__ == "__main__":
    unittest.main()
