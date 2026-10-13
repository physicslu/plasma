#!/usr/bin/env python3
"""Single NXP 353-SKU research batch: positive + negative fail-closed tests."""
from __future__ import annotations

import importlib.util
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nxp_bulk_admission",
    HERE / "nxp_bulk_admission_matrix_v1.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Full353AdmissionPreflight(unittest.TestCase):
    def test_all_353_exact_identifiers_in_one_transaction(self):
        rows, report = mod.build()
        self.assertEqual(len(rows), 353)
        self.assertEqual(report["active_candidates_exact"], 353)
        self.assertEqual(report["active_metadata_reviewed_kl25"], 12)
        self.assertEqual(report["active_metadata_missing"], 341)
        self.assertEqual(report["non_active_excluded_exact"], 15)
        self.assertEqual(report["active_missing_from_production"], 353)
        self.assertEqual(
            mod.exact_set_hash({x["icpn"] for x in rows}), mod.ACTIVE_HASH)
        self.assertEqual(sum(report["candidate_counts_by_research_segment"].values()), 353)
        self.assertEqual(
            set(report["candidate_counts_by_research_segment"]),
            {"mcx", "kinetis", "lpc", "k32", "imx-rt", "wireless"})
        self.assertEqual(rows, sorted(rows, key=lambda r: r["icpn"]))
        self.assertTrue(all(r["production_publication_authorized"] == "false"
                            and r["programming_backend_qualified"] == "false"
                            and r["lifecycle"] == "Active" for r in rows))
        self.assertTrue(all(
            r["identity_evidence_level"] == "frozen_official_exact_set_only"
            and r["source_row_sha256s"] == "" and r["official_product_pages"] == ""
            for r in rows))
        self.assertIsNone(report["full_portfolio_active_denominator"])
        self.assertIsNone(report["full_portfolio_active_coverage"])

    def test_frozen_353_csv_replays_the_single_generator(self):
        expected, _ = mod.build()
        path = HERE / "nxp-active-353-bulk-candidates-v1.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, mod.FIELDS)
            stored = list(reader)
        self.assertEqual(stored, expected)
        self.assertEqual(len(stored), 353)

    def test_metadata_never_guessed_for_other_341(self):
        rows, report = mod.build()
        missing = [x for x in rows if x["metadata_gate"] ==
                   "manufacturer_metadata_missing"]
        ready = [x for x in rows if x["metadata_gate"] ==
                 "manufacturer_metadata_reviewed_KL25"]
        self.assertEqual(len(missing), 341)
        self.assertEqual(len(ready), 12)
        self.assertTrue(all(not x["package"] and not x["pin_count"]
                            and not x["flash_size"] and not x["temperature_grade"]
                            for x in missing))
        self.assertTrue(all(x["package"] and x["pin_count"] and x["flash_size"]
                            and x["temperature_grade"] for x in ready))
        self.assertFalse(report["catalog_automatic_admission_authorized"])
        self.assertFalse(report["production_write_authorized"])

    def test_exact_code_classification_rejects_unsupported_prefix(self):
        self.assertEqual(mod.segment_for("MCXW727DMFTBR"), "mcx")
        self.assertEqual(mod.segment_for("MIMXRT106ADVL6A"), "imx-rt")
        with self.assertRaisesRegex(ValueError, "unclassified"):
            mod.segment_for("S32K123123")

    def test_forged_full_vendor_denominator_fails_closed(self):
        s = mod.read(mod.SNAPSHOT)
        s["scope_limits"]["global_nxp_active_denominator"] = 353
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tampered.json"
            path.write_text(json.dumps(s), encoding="utf-8")
            with patch.object(mod, "SNAPSHOT", path):
                with self.assertRaisesRegex(ValueError, "bounded research"):
                    mod.build()

    def test_one_missing_active_identity_breaks_frozen_sha(self):
        s = mod.read(mod.SNAPSHOT)
        s["reconciliation"]["observed_active_icpns"].pop()
        s["reconciliation"]["observed_active_exact"] -= 1
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tampered.json"
            path.write_text(json.dumps(s), encoding="utf-8")
            with patch.object(mod, "SNAPSHOT", path):
                with self.assertRaisesRegex(ValueError, "353 exact Active"):
                    mod.build()

    def test_missing_live_acquisition_is_never_accepted_as_full_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises((ValueError, FileNotFoundError)):
                mod.build(Path(root))

    def test_identity_can_be_qualified_without_backend(self):
        rows, summary = mod.build()
        self.assertEqual(summary["status"],
                         "DRY_RUN_METADATA_INCOMPLETE_OWNER_APPROVAL_NOT_YET_REQUESTED")
        self.assertFalse(summary["programming_backend_qualified"])
        self.assertFalse(summary["physical_validation_claimed"])
        self.assertFalse(summary["per_sku_raw_source_evidence_locked"])


if __name__ == "__main__":
    unittest.main()
