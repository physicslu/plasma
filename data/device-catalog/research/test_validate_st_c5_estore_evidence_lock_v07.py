"""Negative tests for immutable exact C5 source-bound research ledger."""
from __future__ import annotations
import copy
import json
import unittest

import validate_st_c5_estore_evidence_lock_v07 as gate


class EvidenceLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.codes = gate.CODES.read_text(encoding="utf-8")
        cls.report = json.loads(gate.REPORT.read_text(encoding="utf-8"))

    def rejected_codes(self, source):
        with self.assertRaises(ValueError):
            gate.validate_set(source)

    def test_full_frozen_st_baseline_and_c5_set(self):
        self.assertEqual(191, gate.validate()["combined_bounded_unpublished_minimum"])

    def test_loss_of_one_official_mpn(self):
        self.rejected_codes(self.codes.replace("STM32C531CBT6\n", "", 1))

    def test_duplicate(self):
        self.rejected_codes(self.codes + "STM32C531CBT6\n")

    def test_wildcard_must_not_generate_variants(self):
        self.rejected_codes(self.codes.replace("STM32C531CBT6\n", "STM32C531CBTx\n", 1))

    def test_distinct_tr_identity_cannot_be_collapsed(self):
        self.rejected_codes(self.codes.replace("STM32C531CBT3TR\n", "", 1))

    def test_lifecycle_promotion_disallowed(self):
        proposal = copy.deepcopy(self.report)
        proposal["production_write_authorized"] = True
        with self.assertRaises(ValueError):
            gate.validate(report=proposal, codes=self.codes)

    def test_manufacturer_full_portfolio_claim_blocked(self):
        proposal = copy.deepcopy(self.report)
        proposal["whole_st_actual_coverage_percent"] = 100
        with self.assertRaises(ValueError):
            gate.validate(report=proposal, codes=self.codes)

    def test_artifact_digest_is_immutable(self):
        proposal = copy.deepcopy(self.report)
        proposal["provenance"]["artifact_zip_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            gate.validate(report=proposal, codes=self.codes)


if __name__ == "__main__":
    unittest.main()
