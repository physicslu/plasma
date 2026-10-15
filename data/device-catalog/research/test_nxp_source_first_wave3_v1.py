#!/usr/bin/env python3
"""Negative proof that source-first NXP wave3 remains research-only."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nxp_validate_source_first_wave3_v1 as scope


class NXPWave3Tests(unittest.TestCase):
    def setUp(self):
        self.doc = scope.load(scope.LEDGER)

    def test_replay_no_software_promotion(self):
        result = scope.validate()
        self.assertEqual(result["new_official_source_observations"], 18)
        self.assertEqual(result["p0_discovery_candidates"], 15)
        self.assertEqual(result["p1_candidates"], 3)
        self.assertEqual(result["new_software_supported"], 0)
        self.assertEqual(result["new_production_admitted"], 0)
        self.assertFalse(result["official_original_html_sha256_present"])

    def test_reject_invented_nxp_original_byte_custody(self):
        self.doc["manufacturer_original_html_archived"] = True
        with self.assertRaisesRegex(ValueError, "false source custody"):
            scope.validate(self.doc)

    def test_reject_claiming_all_vendor_active_coverage(self):
        self.doc["whole_vendor_active_denominator"] = 18
        with self.assertRaisesRegex(ValueError, "false source custody"):
            scope.validate(self.doc)

    def test_reject_p1_driver_only_promoted_to_p0(self):
        item = next(x for x in self.doc["records"] if x["family"] == "LPC1549")
        item["candidate_class"] = "P0_DISCOVERY_CANDIDATE"
        with self.assertRaisesRegex(ValueError, "silently promoted"):
            scope.validate(self.doc)

    def test_reject_mixed_lifecycle_promoted_to_active(self):
        item = next(x for x in self.doc["records"] if x["family"] == "LPC2148")
        item["manufacturer_status"] = "Active"
        with self.assertRaisesRegex(ValueError, "mixed lifecycle"):
            scope.validate(self.doc)

    def test_reject_jtag_and_nrnd_suppression(self):
        item = next(x for x in self.doc["records"] if x["family"] == "LPC2378")
        item["qualifying_gap"] = "SWD-ready"
        with self.assertRaisesRegex(ValueError, "JTAG/NRND restriction lost"):
            scope.validate(self.doc)

    def test_reject_mislabelled_flash_driver(self):
        self.doc["records"][0]["pinned_flash_driver"] = "kinetis.c"
        with self.assertRaisesRegex(ValueError, "Target/Helper/Driver"):
            scope.validate(self.doc)

    def test_reject_synthetic_programming_support(self):
        self.doc["records"][0]["software_supported"] = True
        with self.assertRaisesRegex(ValueError, "silently promoted"):
            scope.validate(self.doc)

    def test_reject_synthetic_hil_evidence(self):
        self.doc["records"][0]["hardware_validated"] = True
        with self.assertRaisesRegex(ValueError, "silently promoted"):
            scope.validate(self.doc)

    def test_reject_candidate_inflation(self):
        item = copy.deepcopy(self.doc["records"][-1])
        item["icpn"] = "LPC1788FBD100FAKE"
        self.doc["records"].append(item)
        self.doc["records"].sort(key=lambda x: x["icpn"])
        with self.assertRaisesRegex(ValueError, "exact candidate additions"):
            scope.validate(self.doc)

    def test_reject_source_hash_forgery(self):
        self.doc["target_driver_git_blob_sha1"]["tcl/target/lpc8xx.cfg"] = "0"*40
        with self.assertRaisesRegex(ValueError, "Git blob"):
            scope.validate(self.doc)


if __name__ == "__main__":
    unittest.main()
