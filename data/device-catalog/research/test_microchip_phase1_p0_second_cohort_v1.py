#!/usr/bin/env python3
"""Synthetic read-only second-cohort P0 manufacturer MCP gates."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import microchip_phase1_p0_second_cohort_v1 as second


def fixture():
    devs = [("ATSAMD21G18", "sam-d-c-r-l0"),
            ("ATSAME54P20A", "sam-e5-d5"),
            ("PIC32MX170F256B", "pic32mx")]
    devs += [(f"ATSAMD21TEST{i:04d}", "sam-d-c-r-l0") for i in range(338)]
    assert len(devs) == 341
    return {
        "policy": "ADR-0002 Phase 1 - IC Information",
        "manufacturer": "Microchip",
        "chart_scope": "microchipdirect_chart_branchID_21_mid_3_only",
        "pinned_openocd_commit": second.chart.EXPECTED_OPENOCD_COMMIT,
        "source_original_sha256": "a" * 64,
        "source_url": "https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3",
        "all_records_research_only": True, "production_write_authorized": False,
        "chart_records": {"P0_source_leads": 341},
        "p0_family_records": [
            {"base_device_chart_observation": name, "source_lead_id": lead,
             "source_tr_ordinal": i+100}
            for i,(name,lead) in enumerate(devs)],
    }


def row(icpn, base):
    return {"source_part_number": icpn, "source_base_part_number": base,
            "raw_lifecycle_not_admission": "Active",
            "source_file": "response-03.txt", "source_sha256": "b"*64,
            "source_locator": "products[0]", "query": base,
            "request_limit": 20, "request_offset": 0}


def fake_source(path, query):
    if query == "ATSAME54P20A":
        values = [
            row("ATSAME54P20A-AU", query),
            row("ATSAME54P20A-MU", "UNEXPECTED_BASE"),
            row("ATSAME54P20A", query),
            row("SOME_EVAL_BOARD", "OTHER"),
        ]
    elif query == "PIC32MX170F256B":
        values = [row("PIC32MX170F256B-50I/SP", query)]
    else:
        raise AssertionError("unexpected exploratory source query")
    (Path(path)/"manifest.json").write_text(json.dumps({
        "responses": ["initialize", "initialized", "tools", "product"],
    }))
    return (
        {"reported_total": len(values),
         "exact_prefix_ordering_count": len(values)-int(query=="ATSAME54P20A"),
         "fuzzy_foreign_ordering_count": int(query=="ATSAME54P20A"),
         "independent_page_size_identity_and_lifecycle_match": True},
        {x["source_part_number"].upper(): x for x in values})


class SecondCohort(unittest.TestCase):
    def test_two_source_chart_names_no_suffix_inference(self):
        plan = second.cohort(fixture())
        self.assertEqual([(r["lead_id"],r["mcp_search_term"]) for r in plan],
                         [("sam-e5-d5","ATSAME54P20A"),
                          ("pic32mx","PIC32MX170F256B")])
        self.assertTrue(all(r["query_intent"].startswith("EXPLORATORY_") for r in plan))
        self.assertTrue(all(r["exact_icpn_admission_authorized"] is False for r in plan))

    def test_baseline_fully_unknown_except_historical_separately(self):
        out=second.report(fixture(), {})
        self.assertEqual(out["mcp_state_counts"], {
            "CURRENT_REPLAYED_MATCH": 0, "CURRENT_REPLAYED_NO_EXACT_MATCH": 0,
            "SOURCE_NOT_AVAILABLE": 0, "PREVIOUS_REPLAYED_NOT_RECHECKED": 1,
            "NOT_QUERIED": 340})
        self.assertEqual(len(out["p0_chart_coverage_matrix"]),341)
        self.assertIsNone(out["known_unqueried_family_exact_icpn_count"])
        self.assertEqual(out["current_exact_icpn_admissions"],0)
        self.assertFalse(out["openocd_software_supported_claimed"])
        self.assertFalse(out["original_bytes_durable_archive_verified"])

    def test_mcp_query_failure_is_not_zero_manufacturer_icpns(self):
        out=second.report(fixture(),{"sam-e5-d5":("SOURCE_NOT_AVAILABLE",None)})
        self.assertEqual(out["mcp_state_counts"]["SOURCE_NOT_AVAILABLE"],1)
        value=next(q for q in out["query_results"] if q["lead_id"]=="sam-e5-d5")
        self.assertIsNone(value["source_exact_ordering_candidates_not_admitted"])
        self.assertFalse(value["source_independent_pagination_replayed"])

    def test_replayed_source_conflicts_bare_query_and_fuzzy_are_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            first=root/"e5"; second_root=root/"pic32"
            first.mkdir();second_root.mkdir()
            with patch.object(second.existing, "original_primary_mcp_records",
                              side_effect=fake_source):
                out=second.report(fixture(), {
                    "sam-e5-d5":("REPLAYED",first),
                    "pic32mx":("REPLAYED",second_root),
                })
        self.assertEqual(out["mcp_state_counts"],{
            "CURRENT_REPLAYED_MATCH":2, "CURRENT_REPLAYED_NO_EXACT_MATCH":0,
            "SOURCE_NOT_AVAILABLE":0,"PREVIOUS_REPLAYED_NOT_RECHECKED":1,
            "NOT_QUERIED":338})
        self.assertEqual(
            {r["source_part_number"] for r in out["exact_mcp_source_observed_not_admitted"]},
            {"ATSAME54P20A-AU","PIC32MX170F256B-50I/SP"})
        self.assertEqual({x["quarantine_reason"] for x in out["quarantined_identity_rows"]},
                         {"MANUFACTURER_BASE_DEVICE_MISMATCH",
                          "BARE_CHART_NAME_NOT_PROVEN_ORDERABLE"})
        self.assertTrue(all(x["internal_admission_state"]=="NOT_ADMITTED"
                            for x in out["exact_mcp_source_observed_not_admitted"]))
        self.assertEqual(out["current_exact_icpn_admissions"],0)
        self.assertEqual(out["phase1_exact_icpn_specifications_verified"],0)

    def test_missing_family_and_wrong_source_fail_closed(self):
        bad=deepcopy(fixture())
        bad["p0_family_records"]=[
            x for x in bad["p0_family_records"] if x["source_lead_id"]!="pic32mx"]
        bad["chart_records"]["P0_source_leads"]=340
        with self.assertRaisesRegex(ValueError,"untrusted original P0"):
            second.cohort(bad)
        with self.assertRaisesRegex(ValueError,"source data/outcome mismatch"):
            second.report(fixture(),{"sam-e5-d5":("REPLAYED",None)})
        with self.assertRaisesRegex(ValueError,"unapproved"):
            second.report(fixture(),{"unknown-lead":("NOT_RUN",None)})

    def test_duplicate_chart_base_rejected(self):
        duplicate=deepcopy(fixture())
        duplicate["p0_family_records"][2]["base_device_chart_observation"]="ATSAME54P20A"
        with self.assertRaisesRegex(ValueError,"duplicate P0"):
            second.cohort(duplicate)


if __name__=="__main__":
    unittest.main()
