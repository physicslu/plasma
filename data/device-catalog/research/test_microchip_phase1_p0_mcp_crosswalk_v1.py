"""Synthetic-only tests for source-verified Microchip chart P0 <-> MCP crosswalk."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import microchip_phase1_p0_mcp_crosswalk_v1 as xwalk


def synthetic_chart():
    rows = []
    bases = ["ATSAMD21G18"] + [f"ATSAMD21X{i:04d}" for i in range(340)]
    for i, base in enumerate(bases):
        fields = {key: {"status": "UNKNOWN"} for key in
                  ("flash", "ram", "vdd", "io_supply", "vdda")}
        fields["flash"]["status"] = "PARTIAL"
        rows.append({
            "base_device_chart_observation": base,
            "source_lead_id": "sam-d-c-r-l0",
            "source_tr_ordinal": 100 + i,
            "fields_family_scope_only": fields,
        })
    return {
        "policy": "ADR-0002 Phase 1 - IC Information",
        "manufacturer": "Microchip",
        "chart_scope": "microchipdirect_chart_branchID_21_mid_3_only",
        "source_url": "https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3",
        "source_original_sha256": "a" * 64,
        "pinned_openocd_commit": xwalk.chart.EXPECTED_OPENOCD_COMMIT,
        "all_records_research_only": True,
        "production_write_authorized": False,
        "chart_records": {"observed_chart_base_devices": 341,
                          "P0_source_leads": 341,
                          "P1_deferred": 0, "P2_archive_only": 0},
        "p0_family_records": rows,
    }


def source_row(icpn, base="ATSAMD21G18"):
    return {
        "source_part_number": icpn, "source_base_part_number": base,
        "raw_lifecycle_not_admission": "Active",
        "source_mcp_product_url": "https://www.microchip.com/en-us/product/ATSAMD21G18",
        "source_file": "response-03.txt",
        "source_sha256": "b" * 64,
        "source_locator": "products[0]",
        "query": "ATSAMD21G18A",
        "request_limit": 20, "request_offset": 0,
    }


def stub_mcp():
    values = [
        source_row("ATSAMD21G18A-MU"),
        source_row("ATSAMD21G18A-MF"),
        source_row("ATSAMD21G18A-SYNTHETIC"),
        source_row("ATSAMD21G18A-T/BOGUS", "WRONG_BASE"),
        source_row("ATSAMD21G18A", "ATSAMD21G18"),
        source_row("EV75S95A", "FOREIGN"),
    ]
    return ({ "reported_total": len(values), "exact_prefix_ordering_count": 5,
              "fuzzy_foreign_ordering_count": 1,
              "independent_page_size_identity_and_lifecycle_match": True },
            {v["source_part_number"].upper(): v for v in values})


def verified_pilot():
    return {"matched_exact_manufacturer_icpns": 2,
            "original_mcp_pagination_replayed": True,
            "exact_manufacturer_identity_evidence": [
                {"icpn": "ATSAMD21G18A-MU"},
                {"icpn": "ATSAMD21G18A-MF"},
            ]}


class CrosswalkTest(unittest.TestCase):
    def test_without_capture_341_unqueried_not_false_zero(self):
        report = xwalk.crosswalk_from_evidence(synthetic_chart())
        self.assertEqual(report["total_p0_chart_base_devices"], 341)
        self.assertEqual(report["mcp_source_state_by_chart_base_device"],
                         {"MCP_ORIGINAL_IDENTITY_REPLAYED": 0,
                          "MCP_SOURCE_NOT_AVAILABLE": 0, "NOT_QUERIED": 341})
        self.assertIsNone(report["unqueried_source_exact_icpn_count"])
        self.assertIsNone(report["p0_chart_to_mcp_matrix"][0][
            "manufacturer_exact_icpns_observed"])
        self.assertFalse(report["mcp_global_or_family_sku_census_complete"])
        self.assertFalse(report["production_write_authorized"])
        self.assertEqual(report["total_exact_icpn_admissions"], 0)

    def test_source_failure_is_not_zero_coverage(self):
        report = xwalk.crosswalk_from_evidence(
            synthetic_chart(), capture_outcome="SOURCE_NOT_AVAILABLE")
        self.assertEqual(report["mcp_source_state_by_chart_base_device"],
                         {"MCP_ORIGINAL_IDENTITY_REPLAYED": 0,
                          "MCP_SOURCE_NOT_AVAILABLE": 1, "NOT_QUERIED": 340})
        selected = next(v for v in report["p0_chart_to_mcp_matrix"]
                        if v["chart_base_device"] == "ATSAMD21G18")
        self.assertIsNone(selected["manufacturer_exact_icpns_observed"])

    def test_hashed_source_candidate_and_quarantine_not_admitted(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            xwalk, "original_primary_mcp_records", return_value=stub_mcp()
        ), patch.object(xwalk.pilot_identity, "replay_identity",
                        return_value=verified_pilot()):
            Path(temp, "manifest.json").write_text(
                json.dumps({"responses": ["init", "status", "tools", "page1"]}))
            report = xwalk.crosswalk_from_evidence(
                synthetic_chart(), mcp_root=temp, capture_outcome="REPLAYED")
        self.assertEqual(report["mcp_source_state_by_chart_base_device"],
                         {"MCP_ORIGINAL_IDENTITY_REPLAYED": 1,
                          "MCP_SOURCE_NOT_AVAILABLE": 0, "NOT_QUERIED": 340})
        self.assertEqual(len(report["commercial_icpn_original_rows_observed_not_admitted"]), 3)
        self.assertEqual(set(report["replayed_exact_pilot_icpns"]),
                         {"ATSAMD21G18A-MU", "ATSAMD21G18A-MF"})
        self.assertEqual(len(report["quarantined_mcp_exact_prefix_rows"]), 2)
        reasons = {r["quarantine_reason"] for r in
                   report["quarantined_mcp_exact_prefix_rows"]}
        self.assertEqual(reasons, {"BARE_QUERY_NOT_PROVEN_COMMERCIAL_ORDER_CODE",
                                   "MANUFACTURER_BASE_DEVICE_MISMATCH"})
        for row in report["commercial_icpn_original_rows_observed_not_admitted"]:
            self.assertEqual(row["internal_admission_state"], "NOT_ADMITTED")
            self.assertFalse(row["software_supported_claimed"])
            self.assertEqual(len(row["source_sha256"]), 64)

    def test_unexpected_base_schema_and_admission_fail_closed(self):
        altered = synthetic_chart()
        altered["p0_family_records"][0]["fields_family_scope_only"]["flash"][
            "status"] = "VERIFIED"
        with self.assertRaisesRegex(ValueError, "promoted"):
            xwalk.crosswalk_from_evidence(altered)
        changed = synthetic_chart()
        changed["chart_records"]["P0_source_leads"] = 342
        with self.assertRaisesRegex(ValueError, "denominator"):
            xwalk.crosswalk_from_evidence(changed)

    def test_cannot_claim_replay_without_original_bytes(self):
        with self.assertRaisesRegex(ValueError, "source bytes and acquisition"):
            xwalk.crosswalk_from_evidence(
                synthetic_chart(), mcp_root=None, capture_outcome="REPLAYED")
        with self.assertRaisesRegex(ValueError, "source bytes and acquisition"):
            xwalk.crosswalk_from_evidence(
                synthetic_chart(), mcp_root="/tmp/forged", capture_outcome="NOT_RUN")

    def test_primary_original_bytes_hash_and_identity_drift(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            products = [
                {"partNumber": "ATSAMD21G18A-MU",
                 "basePartNumber": "ATSAMD21G18",
                 "lifecycleStatus": "Active"},
                {"partNumber": "ATSAMD21G18A-MF",
                 "basePartNumber": "ATSAMD21G18",
                 "lifecycleStatus": "Active"},
            ]
            response = {"jsonrpc": "2.0", "id": 3,
                        "result": {"content": [{"type": "text",
                           "text": json.dumps({"success": True, "data": {
                               "searchTerm": "ATSAMD21G18A",
                               "pagination": {"total": 2, "offset": 0,
                                              "limit": 20, "hasMore": False},
                               "products": products,
                           }})}]}}
            raw = json.dumps(response).encode()
            (folder / "response-03.txt").write_bytes(raw)
            event = {"file": "response-03.txt", "sha256": hashlib.sha256(raw).hexdigest(),
                     "request": {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                 "params": {"arguments": {
                                     "searchTerm": "ATSAMD21G18A",
                                     "limit": 20, "offset": 0}}}}
            (folder / "manifest.json").write_text(json.dumps({
                "query": "ATSAMD21G18A", "endpoint": xwalk.mcp.ENDPOINT,
                "responses": [event]
            }))
            mock = {"reported_total": 2, "ordering_parts": [
                "ATSAMD21G18A-MU", "ATSAMD21G18A-MF"],
                "independent_page_size_identity_and_lifecycle_match": True}
            with patch.object(xwalk.paged, "replay", return_value=mock):
                _summary, rows = xwalk.original_primary_mcp_records(
                    folder, "ATSAMD21G18A")
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows["ATSAMD21G18A-MU"]["source_base_part_number"],
                                 "ATSAMD21G18")
                (folder / "response-03.txt").write_bytes(raw+b"\n")
                with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                    xwalk.original_primary_mcp_records(folder, "ATSAMD21G18A")


if __name__ == "__main__":
    unittest.main()
