#!/usr/bin/env python3
"""Negative source-bound NXP Active→OpenOCD research discovery gates."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nxp_validate_source_first_active_v2 as audit


class SourceFirstReverseTests(unittest.TestCase):
    def setUp(self):
        self.rows = audit.read_json(audit.CANDIDATES)

    def test_base_27_candidates_are_not_product_support(self):
        summary = audit.validate()
        self.assertEqual(summary["reviewed_original"], 501)
        self.assertEqual(summary["new_discovery_candidates"], 27)
        self.assertEqual(summary["new_software_qualified"], 0)
        self.assertEqual(summary["new_production_admissions"], 0)
        self.assertEqual(summary["pages"], 9)
        self.assertEqual(summary["openocd_source_paths"], 13)
        self.assertIsNone(summary["nxp_global_portfolio_coverage"])
        self.assertFalse(summary["official_original_html_sha256_pinned"])

    def test_deny_synthetic_supported_admission(self):
        self.rows["records"][0]["openocd_software_supported"] = True
        with self.assertRaisesRegex(ValueError, "silently promoted"):
            audit.validate(original=self.rows)

    def test_deny_synthetic_production_admission(self):
        self.rows["records"][0]["production_admission"] = True
        with self.assertRaisesRegex(ValueError, "silently promoted"):
            audit.validate(original=self.rows)

    def test_deny_forged_html_byte_provenance(self):
        self.rows["manufacturer_page_bytes_archived"] = True
        with self.assertRaisesRegex(ValueError, "archived original"):
            audit.validate(original=self.rows)

    def test_deny_remapping_to_different_flash_driver(self):
        self.rows["records"][0]["openocd_flash_driver"] = "kinetis"
        with self.assertRaisesRegex(ValueError, "source route drift"):
            audit.validate(original=self.rows)

    def test_deny_using_imx_application_processor_config_for_mimxrt(self):
        self.rows["records"][0]["openocd_target"] = "tcl/target/imx6.cfg"
        with self.assertRaisesRegex(ValueError, "source route drift"):
            audit.validate(original=self.rows)

    def test_deny_unknown_vendor_webpage(self):
        self.rows["records"][0]["manufacturer_url"] = "https://random.example/fake"
        with self.assertRaisesRegex(ValueError, "unreviewed official page"):
            audit.validate(original=self.rows)

    def test_deny_unreviewed_new_icpn(self):
        # Every new source-first candidate must be independently reviewed.
        self.rows["records"].append(copy.deepcopy(self.rows["records"][-1]))
        self.rows["records"][-1]["icpn"] = "MKL46Z999VLL4"
        with self.assertRaisesRegex(ValueError, "candidate list count changed"):
            audit.validate(original=self.rows)

    def test_deny_resealed_upstream_git_blob(self):
        self.rows["source_entries_sha1_git_blob"]["tcl/target/k40.cfg"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "source Git blob"):
            audit.validate(original=self.rows)

    def test_deny_invented_whole_vendor_complete(self):
        self.rows["manufacturer_coverage"] = "NXP_COMPLETE"
        with self.assertRaisesRegex(ValueError, "whole-vendor"):
            audit.validate(original=self.rows)

    def test_deny_prior_501_overlap(self):
        self.rows["records"][-1]["icpn"] = "MKL25Z128VLL4"
        self.rows["records"].sort(key=lambda x: x["icpn"])
        with self.assertRaisesRegex(ValueError, "candidate overlaps"):
            audit.validate(original=self.rows)

    def test_deny_variant_to_other_product_page(self):
        row = next(r for r in self.rows["records"] if r["icpn"] == "LPC4357JBD208E")
        row["manufacturer_url"] = "https://www.nxp.com/products/LPC4357FET256?tab=Package_Quality_Tab"
        with self.assertRaisesRegex(ValueError, "product-page ambiguity"):
            audit.validate(original=self.rows)


if __name__ == "__main__":
    unittest.main()
