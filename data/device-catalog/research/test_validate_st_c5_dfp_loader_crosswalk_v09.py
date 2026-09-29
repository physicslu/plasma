"""Read-only regression tests for evidence-bound C5 DFP loader/source crosswalk."""
from __future__ import annotations

import copy
import csv
import io
import unittest

import validate_st_c5_dfp_loader_crosswalk_v09 as gate


class CrosswalkEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = gate.CROSSWALK.read_text(encoding="utf-8")
        cls.rows = gate.read_rows(cls.raw)

    def test_stability_and_production_isolation(self):
        result = gate.validate()
        self.assertEqual(172, result["observed_c5_exact_active_cohort"])
        self.assertEqual(139, result["official_DFP_exact_variant_observations"])
        self.assertEqual(33, result["parent_only_not_exact"])
        self.assertEqual(2683, result["production_unchanged"])
        self.assertFalse(result["catalog_admission_ready"])

    def test_three_fixed_loader_families(self):
        self.assertEqual({r["candidate_dev_id"] for r in self.rows},
                         {"0x44E", "0x44F", "0x45A"})
        self.assertEqual({r["candidate_xldr_path"] for r in self.rows},
                         set(gate.EXPECTED_LOADERS))

    def test_missing_33_exact_variants_have_no_exact_flash_size(self):
        missing = [r for r in self.rows
                   if r["dfp_evidence_state"] == "BASE_DEVICE_ONLY_NOT_EXACT"]
        self.assertEqual(33, len(missing))
        self.assertTrue(all(r["exact_variant_flash_bytes"] == "" and
                            r["plasma_route_ready"] == "false" for r in missing))

    def test_all_172_remain_nonexecutable_research(self):
        self.assertTrue(all(r["plasma_route_ready"] == "false"
                            for r in self.rows))

    def test_tr_suffix_is_not_deduplicated(self):
        ids = {r["icpn"] for r in self.rows}
        self.assertIn("STM32C531CBT3", ids)
        self.assertIn("STM32C531CBT3TR", ids)
        self.assertEqual(172, len(ids))

    def test_wrong_column_blocked(self):
        altered = self.raw.replace("dfp_evidence_state", "guessed_route", 1)
        with self.assertRaises(ValueError):
            gate.read_rows(altered)

    def test_excess_columns_blocked(self):
        malformed = self.raw + "STM32C5A3ZGT6,EXTRA\n"
        with self.assertRaises(ValueError):
            gate.read_rows(malformed)

    def test_nonpinned_vendor_pdsc_blocked(self):
        with self.assertRaises(ValueError):
            gate.build_from_pdsc(b"<package><name>untrusted</name></package>",
                                 ["STM32C531CBT6"])

    def test_source_git_blob_integrity(self):
        self.assertEqual("9240f423ccca0ba7c43a6a0ac800be8cd86e3470",
                         gate.git_blob(gate.prior.CODES.read_bytes()))


if __name__ == "__main__":
    unittest.main()
