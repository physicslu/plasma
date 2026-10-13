#!/usr/bin/env python3
"""Source gate regression: no implicit new NXP Production admission."""
import json
import tempfile
import unittest
from pathlib import Path

from nxp_277_refresh_v7 import QUEUE_BLOB, SHARDS, blob, reconcile, selected, source_queue


class Bounded277SourceTests(unittest.TestCase):
    def test_frozen_source_queue(self):
        records = source_queue()
        self.assertEqual(len(records), 277)
        self.assertEqual(len(set(x["icpn"] for x in records)), 277)
        self.assertEqual(QUEUE_BLOB, blob(Path(__file__).parent /
                                           "nxp-277-manufacturer-gap-review-v6.csv"))
        self.assertEqual(sorted(sum([selected(records, i) for i in range(SHARDS)], []),
                                key=lambda x: x["icpn"]),
                         sorted(records, key=lambda x: x["icpn"]))

    def test_missing_all_source_shards_must_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises((ValueError, FileNotFoundError)):
                reconcile(Path(root), Path(root) / "out")

    def test_blocked_source_is_not_manufacturer_evidence(self):
        rows = source_queue()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for i in range(SHARDS):
                folder = root / f"nxp-277-refresh-shard-{i}"
                folder.mkdir()
                subset = selected(rows, i)
                statuses = [{
                    "icpn": r["icpn"],
                    "source_url": r["official_exact_part_url"],
                    "status": "blocked_source_or_schema",
                    "error_type": "TestBlocked",
                    "canonical_metadata_admission_authorized": False,
                } for r in subset]
                report = {
                    "schema_version": 7, "manufacturer": "NXP",
                    "queue_git_blob": QUEUE_BLOB, "shard": i,
                    "requested": len(subset),
                    "exact_skus": [r["icpn"] for r in subset],
                    "production_publication_authorized": False,
                    "programming_profile_qualified": False,
                    "results": statuses,
                }
                (folder / "shard.json").write_text(json.dumps(report), encoding="utf-8")
            output = root / "out"
            result = reconcile(root, output)
            self.assertEqual(result["refresh_states"], {"SOURCE_BLOCKED_OR_SCHEMA": 277})
            self.assertFalse(result["production_publication_authorized"])
            self.assertFalse(result["catalog_admission_qualified"])
            self.assertFalse(result["programming_profile_qualified"])

            # A forged 278th row or changed SKU cannot pass the batch proof.
            shard = root / "nxp-277-refresh-shard-0" / "shard.json"
            payload = json.loads(shard.read_text())
            payload["results"][0]["icpn"] = "FORGEDSKU"
            shard.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                reconcile(root, root / "reject")


if __name__ == "__main__":
    unittest.main()
