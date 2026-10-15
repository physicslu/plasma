#!/usr/bin/env python3
"""Fail-closed Phase 1 exact-SKU identity and S1 completeness regression."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import microchip_phase1_s1_exact_identity_funnel_v1 as funnel
from microchip_phase1_information_v1 import FIELDS

SHA="a"*64
AT="2026-10-13T12:30:44+00:00"


def item(icpn,base,mapping):
    return {
        "icpn":icpn,"base_device":base,"mapping_state":mapping,
        "original_mcp_response_sha256_refs":[SHA],
        "manufacturer_base_identity_evidence":
            "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND",
        "manufacturer_raw_lifecycle_status":"Active",
        "manufacturer_exact_material_source_observations":[{
            "manufacturer_official_source_uri":funnel.OFFICIAL_URI,
            "source_scope":funnel.MATERIAL_SCOPE,
            "exact_icpn":icpn,
            "manufacturer_base_part_number":base,
            "source_query":base,
            "original_response_sha256":SHA,
            "original_observed_at_utc":AT,
            "original_product_uri":None,
            "original_evidence_file":"BATCH/BASE/response-03.txt",
        }]
    }


def data():
    rows=[
        item("ATSAMD21G18A-MU","ATSAMD21G18",
             "EXACT_DFP_NAME_CFG_CANDIDATE"),
        item("ATSAML11D14A-MUT","ATSAML11D14A",
             "P1_TARGET_ONLY_CFG_CANDIDATE"),
        item("PIC32CM1216MC00024-I/SS","PIC32CM1216MC00024",
             "NO_DFP_NAME_CFG_CROSSWALK"),
        item("PIC18F452-I/SP","PIC18F452",
             "NO_DFP_NAME_CFG_CROSSWALK"),
    ]
    return rows


def ledger(rows,selected):
    return {
        "schema_version":1,"manufacturer":"Microchip",
        "original_cfg_reverse_source_report_sha256":SHA,
        "source_replayed_research_icpn_denominator":4,
        "phase1_field_contract":list(FIELDS),
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_compatibility_authorized":False,
        "records":[{
            "icpn":row["icpn"],
            "base_device":row["base_device"],
            "source_original_mcp_response_sha256_refs":[SHA],
            "software_supported_claimed":False,
            "production_write_authorized":False,
            "internal_identity_admission":"NOT_ADMITTED",
            "fields":{
                field:{"status":("VERIFIED" if field in
                        ("manufacturer","icpn","base_device") else "UNKNOWN"),
                       "value":None if field not in
                           ("manufacturer","icpn","base_device") else
                           (row["icpn"] if field=="icpn" else
                            (row["base_device"] if field=="base_device" else
                             "Microchip")),
                       "source_locator":("original manufacturer MCP exact material"
                                         if field in ("manufacturer","icpn",
                                                      "base_device") else None),
                       "evidence_scope":("exact_mcp_response_row" if field in
                           ("manufacturer","icpn","base_device") else None),
                       "original_response_sha256_refs":([SHA] if field in
                           ("manufacturer","icpn","base_device") else None)}
                for field in FIELDS},
        } for row in rows if row["icpn"] in selected],
    }


class Phase1S1IdentityTest(unittest.TestCase):
    def setUp(self):
        self.rows=data()
        self.source={"fake":"upstream"}
        self.p0=ledger(self.rows,{self.rows[0]["icpn"]})
        self.p1=ledger(self.rows,{self.rows[1]["icpn"]})
        for key,value in (("EXPECTED",4),("P0",1),("P1",1),("P2",2)):
            patcher=patch.object(funnel,key,value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher=patch.object(funnel.p0,"verify_upstream",
                             side_effect=lambda s:self.rows)
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self):
        return funnel.create(self.source,self.p0,self.p1,SHA)

    def test_vendor_exact_icpn_is_phase1_identified_independent_of_cfg(self):
        out=self.build()
        self.assertEqual(out["phase1_s1_identified"],4)
        self.assertEqual(out["phase1_s1_complete"],0)
        self.assertEqual(out["legacy_research_priority_counts_separate_from_phases"],
                         {"P0":1,"P1":1,"P2":2})
        self.assertEqual(out["phase1_information_coverage_all_source_observed_icpns"]
                         ["flash"]["UNKNOWN"],4)
        self.assertEqual(out["records"][2]["phase1_identity_status"],"IDENTIFIED")
        self.assertEqual(out["records"][2]["research_priority_separate_from_phase"],"P2")
        self.assertFalse(out["production_write_authorized"])

    def test_missing_original_capture_time_keeps_research_only(self):
        self.rows[2]["manufacturer_exact_material_source_observations"][0][
            "original_observed_at_utc"]=None
        out=self.build()
        self.assertEqual(out["phase1_s1_identified"],3)
        self.assertEqual(out["phase1_research_only_source_gaps"],1)
        self.assertEqual(out["phase1_s1_complete"],0)

    def test_replay_generated_timestamp_is_not_allowed(self):
        src=self.rows[2]["manufacturer_exact_material_source_observations"][0]
        src["original_observed_at_utc"]="2026-10-15T12:00:00"  # naive local
        self.assertEqual(self.build()["phase1_s1_identified"],3)

    def test_unofficial_source_is_not_phase1_accepted(self):
        self.rows[2]["manufacturer_exact_material_source_observations"][0][
            "manufacturer_official_source_uri"]="https://example.org/unknown"
        self.assertEqual(self.build()["phase1_s1_identified"],3)

    def test_conflicting_vendor_base_is_disputed(self):
        self.rows[3]["manufacturer_exact_material_source_observations"][0][
            "manufacturer_base_part_number"]="FABRICATED"
        out=self.build()
        self.assertEqual(out["phase1_identity_disputed"],1)
        self.assertEqual(out["phase1_s1_identified"],3)

    def test_unbound_original_sha_keeps_research_only(self):
        self.rows[3]["manufacturer_exact_material_source_observations"][0][
            "original_response_sha256"]="b"*64
        out=self.build()
        self.assertEqual(out["phase1_s1_identified"],3)

    def test_priority_is_not_used_to_exclude_verified_p2_identity(self):
        self.rows[2]["mapping_state"]="NO_DFP_NAME_CFG_CROSSWALK"
        self.assertEqual(self.build()["phase1_s1_identified"],4)

    def test_information_partial_not_s1_complete(self):
        self.p0["records"][0]["fields"]["flash"]={
            "status":"PARTIAL","value":64,
            "source_locator":"official original chart TR 123 col Flash",
            "evidence_scope":"official_family_parametric_chart",
            "original_response_sha256_refs":[SHA]}
        result=self.build()
        self.assertEqual(result["phase1_s1_complete"],0)
        self.assertEqual(result["phase1_information_coverage_all_source_observed_icpns"]
                         ["flash"]["PARTIAL"],1)

    def test_unsupported_verified_spec_evidence_rejected(self):
        self.p0["records"][0]["fields"]["flash"]={
            "status":"VERIFIED","value":64,
            "source_locator":None,
            "evidence_scope":"guessed",
            "original_response_sha256_refs":None}
        with self.assertRaisesRegex(ValueError,"evidence"):
            self.build()

    def test_sourced_not_applicable_does_not_imply_full_completion(self):
        self.p0["records"][0]["fields"]["vdda"]={
            "status":"NOT_APPLICABLE","value":None,
            "source_locator":"official original datasheet p.10 supply table",
            "evidence_scope":"official_exact_icpn_applicability",
            "original_response_sha256_refs":[SHA]}
        report=self.build()
        self.assertEqual(report["phase1_s1_complete"],0)
        self.assertEqual(
            report["phase1_information_coverage_all_source_observed_icpns"]
                  ["vdda"]["NOT_APPLICABLE"],1)

    def test_wrong_p0_ledger_fails(self):
        self.p0["records"][0]["base_device"]="WRONG"
        with self.assertRaisesRegex(ValueError,"diverges"):
            self.build()

    def test_cross_ledger_duplicate_and_source_sha_rejected(self):
        self.p1["records"][0]["icpn"]=self.p0["records"][0]["icpn"]
        with self.assertRaisesRegex(ValueError,"overlapping"):
            self.build()
        self.p1=ledger(self.rows,{self.rows[1]["icpn"]})
        self.p0["original_cfg_reverse_source_report_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"untrusted"):
            self.build()

    def test_duplicate_exact_commercial_identity_rejected(self):
        self.rows[3]["icpn"]=self.rows[2]["icpn"]
        with self.assertRaisesRegex(ValueError,"duplicated"):
            self.build()


if __name__=="__main__":
    unittest.main()
