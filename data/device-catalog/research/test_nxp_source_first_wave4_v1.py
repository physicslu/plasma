#!/usr/bin/env python3
"""Negative admission/authority tests for NXP OpenOCD Wave4 research."""
import copy
import csv
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nxp_validate_source_first_wave4_v1 as audit


class NXPWave4ResearchTests(unittest.TestCase):
    def setUp(self):
        self.doc = audit.load(audit.LEDGER)

    def test_replay_and_scope(self):
        report = audit.validate()
        self.assertEqual(report["new_exact_observation_strings"], 20)
        self.assertEqual(report["p0_source_backed_discovery"], 18)
        self.assertEqual(report["p1_bounded_driver_id_gap"], 2)
        self.assertEqual(report["excluded_no_longer_manufactured"], 1)
        self.assertEqual(report["new_software_supported"], 0)
        self.assertEqual(report["new_production_admission"], 0)
        self.assertFalse(report["original_manufacturer_source_bytes_captured"])
        self.assertFalse(report["entire_nxp_vendor_complete"])

    def test_reject_new_support_admission(self):
        self.doc["records"][0]["flash_programming_qualified"] = True
        with self.assertRaisesRegex(ValueError, "qualification improperly promoted"):
            audit.validate(self.doc)

    def test_reject_production_admission(self):
        self.doc["records"][0]["production_admitted"] = True
        with self.assertRaisesRegex(ValueError, "qualification improperly promoted"):
            audit.validate(self.doc)

    def test_reject_fake_hil(self):
        self.doc["records"][0]["physical_hil_verified"] = True
        with self.assertRaisesRegex(ValueError, "qualification improperly promoted"):
            audit.validate(self.doc)

    def test_reject_fabricated_original_html(self):
        self.doc["official_page_original_html_byte_custody"] = True
        with self.assertRaisesRegex(ValueError, "source custody"):
            audit.validate(self.doc)

    def test_reject_false_lpc1769_material_observation(self):
        item = next(x for x in self.doc["records"] if x["family"] == "LPC1769")
        item["manufacturer_evidence_scope"] = "MATERIAL_ACTIVE"
        with self.assertRaisesRegex(ValueError, "manufacturer evidence"):
            audit.validate(self.doc)

    def test_reject_promoting_lpc832_to_p0_without_flash_id(self):
        item = next(x for x in self.doc["records"] if x["family"] == "LPC832")
        item["priority"] = "P0_DISCOVERY_CANDIDATE_ONLY"
        with self.assertRaisesRegex(ValueError, "priority changed"):
            audit.validate(self.doc)

    def test_reject_invented_lpc832_part_id(self):
        item = next(x for x in self.doc["records"] if x["family"] == "LPC832")
        item["openocd_driver_part_id_cases"] = ["LPC832_101"]
        with self.assertRaisesRegex(ValueError, "Driver Part-ID"):
            audit.validate(self.doc)

    def test_reject_no_longer_manufactured_promoted_to_active(self):
        self.doc["excluded"][0]["manufacturer_observed_lifecycle"] = "Active"
        with self.assertRaisesRegex(ValueError, "No Longer Manufactured"):
            audit.validate(self.doc)

    def test_reject_source_sha_drift(self):
        self.doc["openocd_source_git_blobs"]["src/flash/nor/lpc2000.c"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "original Git blob SHA"):
            audit.validate(self.doc)

    def test_reject_unreviewed_official_url(self):
        self.doc["records"][0]["manufacturer_url"] = "https://notnxp.example.invalid"
        with self.assertRaisesRegex(ValueError, "source URL mismatch"):
            audit.validate(self.doc)

    def test_reject_unreviewed_new_sku(self):
        item = copy.deepcopy(self.doc["records"][-1])
        item["icpn"] = "LPC834M101FHI33FAKE"
        self.doc["records"].append(item)
        with self.assertRaisesRegex(ValueError, "candidate count"):
            audit.validate(self.doc)

    def test_reject_overlap_with_existing_501(self):
        with audit.ORIGINAL.open(encoding="utf-8", newline="") as f:
            old = {x["icpn"] for x in csv.DictReader(f)}
        self.assertEqual(len(old), 501)
        old.remove(next(iter(old)))
        old.add(self.doc["records"][0]["icpn"])
        with self.assertRaisesRegex(ValueError, "duplicated by new candidates"):
            audit.validate(self.doc, baseline=old)

    def test_reject_relabelled_flash_target(self):
        item = next(x for x in self.doc["records"] if x["family"] == "LPC11U68")
        item["openocd_target"] = "tcl/target/lpc84x.cfg"
        with self.assertRaisesRegex(ValueError, "Target/Helper/Driver"):
            audit.validate(self.doc)


if __name__ == "__main__":
    unittest.main()
