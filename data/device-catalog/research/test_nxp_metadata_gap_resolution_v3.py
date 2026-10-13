#!/usr/bin/env python3
"""Research-only BGA bump qualification from exact manufacturer HTML evidence."""
from __future__ import annotations
import importlib.util
import json
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("bga_v3", HERE/"nxp_metadata_gap_resolution_v3.py")
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SKU="MCXA145VMP"
HTML=(
    "<html><body><h1>MCXA145VMP</h1><div>Package</div>"
    "<div>LFBGA64: LFBGA64, plastic low profile fine-pitch ball grid array; "
    "64 bumps; 0.5 mm pitch; 5 mm x 5 mm body</div>"
    "<div>Buy Options</div><table><tr><td>Flash (kB)</td><td>512</td>"
    "</tr></table></body></html>"
).encode()


class ManufacturerBumpSourceTests(unittest.TestCase):
    def test_exact_sku_raw_bumps_source(self):
        self.assertEqual(mod.read_bga_contacts(SKU,HTML,"LFBGA64"),64)

    def test_official_sku_mismatch_blocks(self):
        with self.assertRaisesRegex(ValueError,"SKU H1"):
            mod.read_bga_contacts("MCXA145VMPR",HTML,"LFBGA64")

    def test_missing_bumps_cannot_be_guessed_from_package_suffix(self):
        with self.assertRaisesRegex(ValueError,"ambiguous or missing"):
            mod.read_bga_contacts(SKU,HTML.replace(b"64 bumps",b"contacts"),"LFBGA64")

    def test_package_count_contradiction_blocks(self):
        with self.assertRaisesRegex(ValueError,"disagree"):
            mod.read_bga_contacts(SKU,HTML.replace(b"64 bumps",b"48 bumps"),"LFBGA64")

    def test_package_name_mismatch_blocks(self):
        with self.assertRaisesRegex(ValueError,"package name mismatch"):
            mod.read_bga_contacts(SKU,HTML,"LFBGA48")

    def test_duplicate_contradictory_bump_values_block(self):
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            mod.read_bga_contacts(SKU,HTML.replace(b"64 bumps",b"64 bumps and 48 bumps"),"LFBGA64")

    def test_frozen_partial_exact_set_is_eleven(self):
        x=json.loads(mod.GATE.read_text())
        self.assertEqual(len(x["original_missing_bump_exact_skus"]),11)
        self.assertEqual(len(set(x["original_missing_bump_exact_skus"])),11)
        self.assertTrue(all(x["production_write_authorized"] is False
                            for _ in x["original_missing_bump_exact_skus"]))


if __name__=="__main__":
    unittest.main()
