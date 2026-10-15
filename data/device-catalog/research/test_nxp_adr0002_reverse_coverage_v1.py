#!/usr/bin/env python3
"""Negative gates for bounded NXP reverse OpenOCD evidence, Phase1-safe."""
from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nxp_adr0002_reverse_coverage_v1 as audit


class NXPReverseCoverageTests(unittest.TestCase):
    def test_exact_population_and_report_replay(self):
        result = audit.build()
        self.assertEqual(result, audit.read_json(audit.OUTPUT))
        self.assertEqual(result["official_active_already_in_review"], 353)
        self.assertEqual(result["official_active_new_to_review"], 0)
        self.assertEqual(result["existing_nxp_exact_reviewed"], 501)
        self.assertEqual(result["review_priority_existing"], {"P0": 27, "P1": 38, "P2": 436})
        self.assertEqual(result["active_observed_priority"], {"P0": 12, "P1": 20, "P2": 321})
        self.assertEqual(result["not_observed_active_priority"], {"P0": 15, "P1": 18, "P2": 115})
        self.assertEqual(result["selected_filename_target_evidence_entries"], 48)
        self.assertEqual(result["new_p0_exact_attested_by_reverse_check"], 0)
        self.assertFalse(result["nxp_entire_active_portfolio_complete"])
        self.assertFalse(result["programming_or_hil_authorized"])

    def test_official_source_file_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "nxp.csv"
            tampered.write_bytes(audit.V10.read_bytes() + b"\n")
            altered = {tampered if p == audit.V10 else p: sha
                       for p, sha in audit.PINS.items()}
            with patch.object(audit, "V10", tampered), patch.object(audit, "PINS", altered):
                with self.assertRaisesRegex(ValueError, "immutable input drift"):
                    audit.build()

    def test_new_active_exact_must_not_be_silently_counted_as_reviewed(self):
        original = audit.read_json(audit.ACTIVE)
        old = original["reconciliation"]["observed_active_icpns"][0]
        original["reconciliation"]["observed_active_icpns"][0] = "MKL46Z128VLL4"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            pins = {path if p == audit.ACTIVE else p:
                    audit.blob(path.read_bytes()) if p == audit.ACTIVE else sha
                    for p, sha in audit.PINS.items()}
            with patch.object(audit, "ACTIVE", path), patch.object(audit, "PINS", pins):
                with self.assertRaisesRegex(ValueError, "new official Active exact ICPNs"):
                    audit.build()
        self.assertNotEqual(old, "MKL46Z128VLL4")

    def test_reprioritize_to_p0_without_review_is_rejected_even_if_resealed(self):
        with audit.V10.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            rows, columns = list(reader), reader.fieldnames
        self.assertIsNotNone(columns)
        source = next(r for r in rows if r["research_priority"] == "P2")
        source["research_priority"] = "P0"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "injected.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            pins = {path if p == audit.V10 else p:
                    audit.blob(path.read_bytes()) if p == audit.V10 else sha
                    for p, sha in audit.PINS.items()}
            with patch.object(audit, "V10", path), patch.object(audit, "PINS", pins):
                with self.assertRaisesRegex(ValueError, "historical priority baseline changed"):
                    audit.build()

    def test_source_target_sha_mismatch_rejected(self):
        source = audit.read_json(audit.SOURCE)
        source["target_files"] = [dict(e) for e in source["target_files"]]
        item = next(x for x in source["target_files"] if x["path"].endswith("k60.cfg"))
        item["git_blob"] = "0" * 40
        previous = audit.read_json(audit.PREVIOUS)
        with self.assertRaisesRegex(ValueError, "source anchor drift"):
            audit.confirm_target_index(source, previous, None)

    def test_imx6_target_cannot_be_relabelled_mimxrt(self):
        source = audit.read_json(audit.SOURCE)
        source["target_files"] = [dict(e) for e in source["target_files"]]
        item = next(x for x in source["target_files"] if x["path"].endswith("imx6.cfg"))
        item["review_class"] = "previously_reviewed_chain"
        with self.assertRaisesRegex(ValueError, "evidence class drift"):
            audit.confirm_target_index(source, audit.read_json(audit.PREVIOUS), None)

    def test_no_additional_p0_sku_in_legacy_family_config_prefixes(self):
        with audit.V10.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        matches = [x["icpn"] for x in rows if x["icpn"].startswith(
            audit.UNSAMPLED_LEGACY_PREFIXES)]
        self.assertEqual(matches, [])
        self.assertNotIn("MKL46Z128VLL4", {r["icpn"] for r in rows})
        self.assertNotIn("LPC1768FBD100", {r["icpn"] for r in rows})


if __name__ == "__main__":
    unittest.main()
