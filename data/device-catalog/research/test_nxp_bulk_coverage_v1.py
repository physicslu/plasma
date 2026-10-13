#!/usr/bin/env python3
"""Unit gates for research-only NXP bulk coverage contract."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nxp_bulk", HERE / "nxp_bulk_coverage_v1.py")
assert spec and spec.loader
nxp_bulk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nxp_bulk)


class BulkCoverageTest(unittest.TestCase):
    def test_registry_and_retained_kl25(self):
        result = nxp_bulk.summarize(None)
        self.assertEqual(result["locked_kl25_pilot_exact"], 12)
        self.assertEqual(len(result["segments"]), 6)
        self.assertEqual(result["observed_active_exact"], 0)
        self.assertIsNone(result["complete_global_active_denominator"])
        self.assertIsNone(result["global_active_identity_coverage"])

    @staticmethod
    def sample(mpn="MKL25Z128VLK4", status="Active", complete=False):
        return {"manufacturer": "NXP", "segment": "kinetis",
                "source_url": "https://www.nxp.com/products/KL2x?tab=Package_Quality_Tab",
                "source_population_complete": complete,
                "rows": [{"icpn": mpn, "lifecycle": status,
                          "source_url": "https://www.nxp.com/products/KL2x",
                          "evidence_sha256": "a" * 64}]}

    def run_sample(self, value):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "kinetis.json").write_text(json.dumps(value), encoding="utf-8")
            return nxp_bulk.summarize(Path(d))

    def test_partial_snapshot_never_claims_whole_vendor(self):
        result = self.run_sample(self.sample())
        self.assertEqual(result["observed_active_exact"], 1)
        self.assertEqual(result["active_missing_from_production"], 1)
        self.assertIsNone(result["complete_global_active_denominator"])
        self.assertEqual(result["segments"][1]["state"], "partial_snapshot")

    def test_forged_full_coverage_is_rejected_without_independent_count(self):
        with self.assertRaisesRegex(ValueError, "manufacturer count facet"):
            self.run_sample(self.sample(complete=True))

    def test_unknown_lifecycle_is_not_active(self):
        result = self.run_sample(self.sample(status="Unknown"))
        self.assertEqual(result["observed_active_exact"], 0)
        self.assertEqual(result["observed_unknown_lifecycle_exact"], 1)

    def test_missing_evidence_is_rejected(self):
        x = self.sample()
        del x["rows"][0]["evidence_sha256"]
        with self.assertRaisesRegex(ValueError, "row evidence"):
            self.run_sample(x)

    def test_manufacturer_source_required(self):
        x = self.sample()
        x["rows"][0]["source_url"] = "https://other.example.com/unverified"
        with self.assertRaisesRegex(ValueError, "row evidence not NXP"):
            self.run_sample(x)


if __name__ == "__main__":
    unittest.main()
