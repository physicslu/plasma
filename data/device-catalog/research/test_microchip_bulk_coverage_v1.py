#!/usr/bin/env python3
"""Regression tests for the research-only Microchip coverage contract."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("microchip_bulk", HERE / "microchip_bulk_coverage_v1.py")
assert spec and spec.loader
microchip_bulk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(microchip_bulk)


class MicrochipBulkCoverageTest(unittest.TestCase):
    def test_registry_keeps_five_lanes_and_no_global_denominator(self):
        result = microchip_bulk.summarize()
        self.assertEqual(len(result["segments"]), 5)
        self.assertIsNone(result["complete_global_active_denominator"])
        self.assertIsNone(result["global_active_identity_coverage"])
        self.assertFalse(result["claims"]["production_write_authorized"])

    @staticmethod
    def sample(segment="8bit", status="Active", complete=False):
        return {
            "manufacturer": "Microchip",
            "segment": segment,
            "source_url": "https://www.microchip.com/en-us/products/microcontrollers/8-bit-mcus",
            "source_population_complete": complete,
            "official_count": 1 if complete else None,
            "source_content_sha256": "a" * 64 if complete else None,
            "rows": [{
                "icpn": "PIC16F18855-I/SS",
                "lifecycle": status,
                "source_url": "https://www.microchip.com/en-us/product/PIC16F18855-I/SS",
                "evidence_sha256": "b" * 64,
            }],
        }

    def run_snapshot(self, value):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "8bit.json").write_text(json.dumps(value), encoding="utf-8")
            return microchip_bulk.summarize(Path(temp))

    def test_partial_snapshot_is_observed_not_global_coverage(self):
        result = self.run_snapshot(self.sample())
        self.assertEqual(result["observed_active_exact"], 1)
        self.assertIsNone(result["complete_global_active_denominator"])

    def test_source_count_alone_cannot_forge_global_completeness(self):
        result = self.run_snapshot(self.sample(complete=True))
        self.assertEqual(result["segments"][0]["state"], "verified_snapshot")
        self.assertIsNone(result["complete_global_active_denominator"])

    def test_unreviewed_lifecycle_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "lifecycle"):
            self.run_snapshot(self.sample(status="EOL soon"))

    def test_missing_row_evidence_is_rejected(self):
        value = self.sample()
        del value["rows"][0]["evidence_sha256"]
        with self.assertRaisesRegex(ValueError, "row evidence"):
            self.run_snapshot(value)

    def test_untrusted_row_source_is_rejected(self):
        value = self.sample()
        value["rows"][0]["source_url"] = "https://microchip.com.evil.invalid/product"
        with self.assertRaisesRegex(ValueError, "not Microchip"):
            self.run_snapshot(value)

    def test_duplicate_exact_identity_in_one_lane_is_rejected(self):
        value = self.sample()
        value["rows"].append(dict(value["rows"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate exact"):
            self.run_snapshot(value)

    def test_conflicting_cross_lane_lifecycle_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "8bit.json").write_text(json.dumps(self.sample()), encoding="utf-8")
            other = self.sample(segment="wireless", status="NRND")
            (root / "wireless.json").write_text(json.dumps(other), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "conflicting"):
                microchip_bulk.summarize(root)


if __name__ == "__main__":
    unittest.main()
