#!/usr/bin/env python3
"""Offline Phase 1 exact manufacturer MCP identity/provenance regression."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from microchip_phase1_information_v1 import DEFAULT_PATH
import microchip_phase1_mcp_identity_v1 as identity


def primary_fixture(missing=False, fuzzy=False):
    rows = [
        {"partNumber": "ATSAMD21G18A-MU", "basePartNumber": "ATSAMD21G18A",
         "lifecycleStatus": "Active", "productUrl": "https://www.microchip.com/en-us/product/ATSAMD21G18"},
        {"partNumber": "ATSAMD21G18A-MF", "basePartNumber": "ATSAMD21G18A",
         "lifecycleStatus": "Active", "productUrl": "https://www.microchip.com/en-us/product/ATSAMD21G18"},
    ]
    if missing:
        rows.pop()
    if fuzzy:
        rows.append({"partNumber": "EV75S95A", "lifecycleStatus": "Active"})
    total = len(rows)
    data = {
        "searchTerm": identity.QUERY,
        "pagination": {"total": total, "offset": 0, "limit": 20,
                       "hasMore": False},
        "products": rows,
    }
    rpc = {"jsonrpc": "2.0", "id": 3, "result": {
        "content": [{"type": "text", "text": json.dumps({
            "success": True, "data": data
        })}]
    }}
    return json.dumps(rpc).encode("utf-8")


class Phase1ExactManufacturerIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))

    def run_fixture(self, raw, reported_exact=2, **overrides):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "response-03.txt").write_bytes(raw)
            manifest = {"responses": [{
                "file": "response-03.txt",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "retrieved_at_utc": "2026-10-14T00:00:00+00:00",
                "request": {
                    "method": "tools/call", "id": 3,
                    "params": {"arguments": {"searchTerm": identity.QUERY,
                                            "limit": 20, "offset": 0}},
                },
            }]}
            if overrides.get("forged_hash"):
                manifest["responses"][0]["sha256"] = "0" * 64
            (path / "manifest.json").write_text(json.dumps(manifest))
            summary = {
                "exact_prefix_ordering_count": reported_exact,
                "independent_page_size_identity_and_lifecycle_match": True,
                "exact_query_ordering_parts": [
                    "ATSAMD21G18A-MU", "ATSAMD21G18A-MF"
                ],
                "fuzzy_foreign_ordering_count": 1 if overrides.get("fuzzy") else 0,
            }
            with patch.object(identity.paged, "replay", return_value=summary):
                return identity.replay_identity(path, self.dataset)

    def test_exact_two_rows_and_base_device_from_manufacturer_raw(self):
        outcome = self.run_fixture(primary_fixture())
        self.assertEqual(outcome["matched_exact_manufacturer_icpns"], 2)
        for row in outcome["exact_manufacturer_identity_evidence"]:
            self.assertEqual(row["manufacturer_base_part_number"],
                             "ATSAMD21G18A")
            self.assertEqual(row["identity_admission_state"], "NOT_ADMITTED")
            self.assertEqual(len(row["response_sha256"]), 64)
        self.assertFalse(outcome["all_records_internally_admitted"])
        self.assertFalse(outcome["programming_or_software_supported_claimed"])

    def test_missing_exact_variant_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambiguous or missing"):
            self.run_fixture(primary_fixture(missing=True))

    def test_response_hash_tampering_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.run_fixture(primary_fixture(), forged_hash=True)

    def test_fuzzy_foreign_result_not_admitted(self):
        outcome = self.run_fixture(primary_fixture(fuzzy=True), fuzzy=True)
        rows = outcome["exact_manufacturer_identity_evidence"]
        self.assertEqual({r["icpn"] for r in rows},
                         {"ATSAMD21G18A-MU", "ATSAMD21G18A-MF"})
        self.assertEqual(outcome["source_fuzzy_foreign_results_excluded"], 1)

    def test_identity_mismatch_with_reviewed_pilot_rejected(self):
        modified = deepcopy(self.dataset)
        modified["records"][0]["icpn"] = "ATSAMD21G18A-MUT"
        with tempfile.TemporaryDirectory() as td:
            with patch.object(identity, "check", return_value={}):
                with self.assertRaisesRegex(ValueError, "unreviewed exact pilot cohort"):
                    identity.replay_identity(td, modified)


if __name__ == "__main__":
    unittest.main()
