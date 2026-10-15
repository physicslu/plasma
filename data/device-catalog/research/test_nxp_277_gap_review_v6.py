#!/usr/bin/env python3
"""277 manufacturer-only Exact Active NXP data gaps, no backend admission."""
import csv
import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "software/python"))

from plasma_web.device_catalog import DeviceCatalog

QUEUE = HERE / "nxp-277-manufacturer-gap-review-v6.csv"
SUMMARY = HERE / "nxp-277-gap-summary-v6.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
SOURCE_129 = HERE / "nxp-353-metadata-gap-review-queue-v3.csv"
SOURCE_148 = HERE / "nxp-148-new-official-metadata-review-v5.csv"
SOURCE_212 = HERE / "nxp-212-manufacturer-device-evidence-v5.csv"


def blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def csvrows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class Nxp277GapReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue = csvrows(QUEUE)
        cls.summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        cls.catalog = DeviceCatalog.from_manifest(MANIFEST)

    def test_all_bounded_277_exact_active_have_one_review_decision(self):
        self.assertEqual(len(self.queue), 277)
        self.assertEqual(len({r["icpn"] for r in self.queue}), 277)
        self.assertEqual(Counter(r["discovery_cohort"] for r in self.queue), {
            "original_353_active": 129, "expanded_148_active": 148
        })
        original = {r["icpn"] for r in csvrows(SOURCE_129)}
        extra = {r["icpn"] for r in csvrows(SOURCE_148)}
        self.assertEqual({r["icpn"] for r in self.queue}, original | extra)
        self.assertEqual(len(original & extra), 0)
        self.assertEqual(self.catalog.size, 4975)
        self.assertEqual(sum(x.vendor == "NXP" for x in self.catalog.records), 224)
        self.assertTrue(all(self.catalog.resolve("NXP",r["icpn"]) is None
                            for r in self.queue))

    def test_exact_source_lock_for_all_reviewed_sources(self):
        expected = {
            "original_129": SOURCE_129,
            "new_148": SOURCE_148,
            "admitted_212": SOURCE_212,
            "production_manifest": MANIFEST,
        }
        for label, path in expected.items():
            self.assertEqual(blob(path),
                             self.summary["source_git_blobs"][label], label)
        self.assertIsNone(self.summary["manufacturer_global_denominator"])
        self.assertEqual(self.summary["bounded_active_exact_501"], 501)
        self.assertEqual(self.summary["pending_active_exact"], 277)
        self.assertFalse(self.summary["production_catalog_authorized"])
        self.assertFalse(self.summary["physical_programming_qualified"])

    def test_new_148_status_partition_and_no_false_zeros(self):
        recent = [x for x in self.queue if x["discovery_cohort"] == "expanded_148_active"]
        self.assertEqual(Counter(x["source_state"] for x in recent), {
            "FOUR_BASIC_FIELDS_OBSERVED_REVIEW_REQUIRED": 3,
            "PARTIAL_EXACT_PAGE_FIELDS_REVIEW_REQUIRED": 31,
            "OFFICIAL_EXACT_PART_PAGE_BLOCKED": 114,
        })
        four = [x for x in recent if x["source_state"] == "FOUR_BASIC_FIELDS_OBSERVED_REVIEW_REQUIRED"]
        self.assertEqual({x["icpn"] for x in four}, {
            "LPC5502JHI48", "LPC5504JHI48", "LPC5506JHI48",
        })
        self.assertEqual({x["observed_flash_kb"] for x in four},
                         {"64", "128", "256"})
        self.assertTrue(all(not x["observed_ram_kb"] and
                            "ram" in x["missing_evidence"] and
                            x["official_html_sha256"] and
                            x["official_exact_part_url"].endswith(x["icpn"])
                            for x in four))
        for x in self.queue:
            self.assertEqual(x["production_catalog_authorized"], "false")
            self.assertEqual(x["programming_profile_qualified"], "false")
            self.assertEqual(x["official_exact_part_url"],
                             "https://www.nxp.com/part/" + x["icpn"])


if __name__ == "__main__":
    unittest.main()
