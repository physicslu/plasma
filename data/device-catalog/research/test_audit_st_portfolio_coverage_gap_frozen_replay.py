#!/usr/bin/env python3
"""The 2026-09-29 ST coverage audit replays its frozen Production baseline from Git.

Historical evidence must stay reproducible while the live Production catalog
evolves; it is never re-validated against current Production data.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import audit_st_portfolio_coverage_gap as audit


class FrozenProductionBaselineReplay(unittest.TestCase):
    def test_replay_reproduces_stored_report_without_live_production(self):
        missing = HERE / "__no_live_production_manifest__.json"
        self.assertFalse(missing.exists())
        with patch.object(audit, "MANIFEST", missing):
            self.assertEqual(audit.render(), audit.load(audit.REPORT))

    def test_frozen_snapshot_and_report_artifacts_are_retained(self):
        snapshot = audit.load(audit.SOURCE)["production_baseline"]
        self.assertEqual(snapshot["manifest_git_blob_sha"], audit.EXPECTED_ST_MANIFEST_SHA)
        self.assertEqual(len(snapshot["frozen_st_sources"]), 23)

    def test_tampered_frozen_source_blob_fails_closed(self):
        original = audit.load(audit.SOURCE)
        tampered = copy.deepcopy(original)
        tampered["production_baseline"]["frozen_st_sources"][0]["git_blob_sha"] = "0" * 40
        with patch.object(audit, "load", side_effect=lambda p: tampered if p == audit.SOURCE
                          else json.loads(Path(p).read_text(encoding="utf-8"))):
            with self.assertRaises(RuntimeError):
                audit.render()

    def test_unknown_or_malformed_blob_fails_closed(self):
        for blob_id in ("0" * 40, "not-a-blob", "A" * 40):
            with self.subTest(blob_id=blob_id):
                with self.assertRaises(RuntimeError):
                    audit.frozen_git_blob(blob_id, "test")


if __name__ == "__main__":
    unittest.main()
