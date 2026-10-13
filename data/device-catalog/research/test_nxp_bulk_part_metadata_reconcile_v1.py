#!/usr/bin/env python3
"""Synthetic eight-shard manufacturer metadata proofs; no network or Production."""
import csv
import gzip
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nxp_bulk_meta_reconcile", HERE / "nxp_bulk_part_metadata_reconcile_v1.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class NxpMetadataEightShardTest(unittest.TestCase):
    def make_shards(self, root: Path, observed: bool = False):
        with mod.CANDIDATES.open(encoding="utf-8", newline="") as stream:
            candidates = list(csv.DictReader(stream))
        missing = [x["icpn"] for x in candidates
                   if x["metadata_gate"] == "manufacturer_metadata_missing"]
        self.assertEqual(len(missing), 341)
        for shard in range(8):
            directory = root / f"nxp-part-metadata-shard-{shard}"
            directory.mkdir()
            names = [value for i, value in enumerate(missing) if i % 8 == shard]
            data = []
            for name in names:
                row = {
                    "icpn": name, "status": "blocked_source_or_schema",
                    "source_url": f"https://www.nxp.com/part/{name}",
                    "canonical_metadata_admission_authorized": False,
                }
                if observed and name == missing[0]:
                    raw = ("<html><h1>" + name + "</h1></html>").encode()
                    digest = hashlib.sha256(raw).hexdigest()
                    with gzip.open(directory / f"{name}.html.gz", "wb") as f:
                        f.write(raw)
                    row = {
                        "icpn": name, "status": "official_nxp_part_metadata_observed",
                        "source_url": f"https://www.nxp.com/part/{name}",
                        "canonical_metadata_admission_authorized": False,
                        "source_sha256": digest,
                        "heading_matches_exact_sku": True,
                        "programming_backend_qualified": False,
                        "package_raw": "LQFP64",
                        "package_terminals": 64,
                        "flash_kb_raw": 512,
                        "ambient_temperature_raw": "-40 to 105",
                        "junction_temperature_raw": None,
                    }
                data.append(row)
            doc = {
                "manufacturer": "NXP",
                "shard": shard, "shard_count": 8,
                "production_write_authorized": False,
                "requested": len(data),
                "observed": sum(x["status"] == "official_nxp_part_metadata_observed"
                                for x in data),
                "blocked": sum(x["status"] == "blocked_source_or_schema"
                               for x in data),
                "results": data,
            }
            (directory / "metadata-shard.json").write_text(json.dumps(doc))

    def test_complete_341_partition_even_if_all_vendor_pages_block(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            self.make_shards(root)
            rows, report = mod.normalized(root)
            self.assertEqual(len(rows), 353)
            self.assertEqual(report["prior_reviewed_KL25"], 12)
            self.assertEqual(report["blocked_exact_part_pages"], 341)
            self.assertEqual(report["acquired_official_part_metadata"], 0)
            self.assertFalse(report["production_write_authorized"])
            self.assertFalse(report["automatic_canonical_metadata_admission_authorized"])

    def test_original_vendor_html_sha_and_fields_are_proven(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            self.make_shards(root, observed=True)
            rows, report = mod.normalized(root)
            self.assertEqual(len(rows), 353)
            self.assertEqual(report["blocked_exact_part_pages"], 340)
            self.assertEqual(report["source_fields_complete_but_review_required"], 1)
            self.assertEqual(report["acquired_official_part_metadata"], 1)
            self.assertEqual(report["field_observed_counts"]["flash_kb_raw"], 13)

    def test_missing_html_evidence_cannot_pass_vendor_metadata_gate(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            self.make_shards(root, observed=True)
            first = next(root.glob("nxp-part-metadata-shard-0/*.html.gz"))
            first.write_bytes(gzip.compress(b"<unexpected>"))
            with self.assertRaisesRegex(ValueError, "manufacturer HTML changed"):
                mod.normalized(root)


if __name__ == "__main__":
    unittest.main()
