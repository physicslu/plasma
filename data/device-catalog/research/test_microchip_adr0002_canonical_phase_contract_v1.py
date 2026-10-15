#!/usr/bin/env python3
"""ADR-0002 Microchip canonical phase separation and negative tests."""
from copy import deepcopy
from unittest.mock import patch
import unittest

import microchip_adr0002_canonical_phase_contract_v1 as a

SHA="a"*64
AT="2026-10-15T00:00:00+00:00"


def source_record(code,*,identity="IDENTIFIED",cfg_priority="P2"):
    statuses={
        key:("VERIFIED" if key in
             ("manufacturer","icpn","base_device") else "UNKNOWN")
        for key in a.FIELD_MAP
    }
    return {
        "manufacturer":"Microchip",
        "icpn":code,
        "base_device":code.split("-")[0],
        "phase1_identity_status":identity,
        "phase1_information_status":"INFORMATION_INCOMPLETE",
        "material_official_source_uri":a.OFFICIAL_URI,
        "source_scope":a.MATERIAL_SCOPE,
        "observed_at_utc_from_original_responses":[AT],
        "original_mcp_response_sha256_refs":[SHA],
        "internal_identity_admitted":False,
        "openocd_software_supported_asserted":False,
        "physical_hil_passed_asserted":False,
        "research_priority_separate_from_phase":cfg_priority,
        "information_field_statuses":statuses,
    }


def source():
    rows=[source_record("PART-A",cfg_priority="P0"),
          source_record("PART-B",cfg_priority="P1"),
          source_record("PART-C",cfg_priority="P2")]
    return {
        "schema_version":1,
        "policy":"ADR-0002 Phase 1 Original Manufacturer Exact ICPN Funnel",
        "manufacturer":"Microchip",
        "official_mcp_source_uri":a.OFFICIAL_URI,
        "source_subset_observed_distinct_commercial_icpns":3,
        "source_scope_not_global_manufacturer_census":True,
        "upstream_full_original_mcp_report_sha256":SHA,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_compatibility_authorized":False,
        "phase1_s1_identified":3,
        "phase1_s1_complete":0,
        "phase1_research_only_source_gaps":0,
        "phase1_identity_disputed":0,
        "legacy_research_priority_counts_separate_from_phases":{
            "P0":1,"P1":1,"P2":1},
        "records":rows,
    }


class ADR0002CanonicalMicrochipTests(unittest.TestCase):
    def setUp(self):
        p=patch.object(a,"EXACT_SNAPSHOT_COUNT",3)
        p.start()
        self.addCleanup(p.stop)

    def test_all_original_exact_identified_visible_irrespective_of_cfg(self):
        out=a.canonical_projection(source())
        self.assertEqual(out["phase1_identity_counts"]["IDENTIFIED"],3)
        self.assertEqual(out["selector_visible_identified_count"],3)
        self.assertEqual(out["phase2_programming_state_counts"]["SUPPORTED"],0)
        self.assertEqual(out["phase3_compatibility_state_counts"]["PASSED"],0)
        self.assertEqual(out["phase1_information_complete_count"],0)
        for rec in out["records"]:
            self.assertTrue(rec["ic_selector_visible"])
            self.assertFalse(rec["execution_authorized"])
            self.assertEqual(rec["phase2"]["programming_state"],"UNKNOWN")
            self.assertEqual(rec["phase3"]["compatibility_state"],"NOT_TESTED")
            self.assertEqual(rec["phase1"]["field_states"]["working_vdd"],"UNKNOWN")
            self.assertNotIn("research_priority",rec)
            self.assertNotIn("P0",str(rec))
            self.assertNotIn("P1",str(rec))
            self.assertNotIn("P2",str(rec))

    def test_identity_without_cfg_is_not_excluded(self):
        x=source()
        del x["legacy_research_priority_counts_separate_from_phases"]
        for rec in x["records"]:
            rec.pop("research_priority_separate_from_phase")
        self.assertEqual(a.canonical_projection(x)["selector_visible_identified_count"],3)

    def test_disputed_material_is_hidden_without_deleting_source(self):
        x=source()
        x["records"][0]["phase1_identity_status"]="IDENTITY_DISPUTED"
        x["phase1_s1_identified"]=2
        x["phase1_identity_disputed"]=1
        out=a.canonical_projection(x)
        self.assertEqual(out["selector_visible_identified_count"],2)
        self.assertEqual(len(out["records"]),3)
        self.assertFalse(out["records"][0]["ic_selector_visible"])

    def test_source_bytes_hash_missing_rejected(self):
        x=source()
        x["records"][0]["original_mcp_response_sha256_refs"]=[]
        with self.assertRaisesRegex(ValueError,"original official"):
            a.canonical_projection(x)

    def test_no_unsupported_phase2_support_promotion(self):
        x=source()
        x["records"][0]["openocd_software_supported_asserted"]=True
        with self.assertRaisesRegex(ValueError,"no-qualification"):
            a.canonical_projection(x)

    def test_unverified_field_cannot_claim_information_complete(self):
        x=source()
        x["records"][1]["phase1_information_status"]="INFORMATION_COMPLETE"
        with self.assertRaisesRegex(ValueError,"INFORMATION_COMPLETE"):
            a.canonical_projection(x)

    def test_duplicated_exact_vendor_material_fails(self):
        x=source()
        x["records"][1]["icpn"]=x["records"][0]["icpn"]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            a.canonical_projection(x)

    def test_not_applicable_requires_actual_upstream_evidence_and_remains_distinct(self):
        x=source()
        x["records"][0]["information_field_statuses"]["vdda"]="NOT_APPLICABLE"
        out=a.canonical_projection(x)
        self.assertEqual(out["field_coverage"]["vdda"]["NOT_APPLICABLE"],1)
        self.assertEqual(out["phase1_information_complete_count"],0)
        # This status projection never manufactures a value or a supply proof.
        self.assertNotIn("vdda_voltage",out["records"][0]["phase1"])

    def test_unknown_cannot_become_numeric_zero_or_mapped_route(self):
        x=source()
        x["records"][0]["information_field_statuses"]["vdd"]="zero"
        with self.assertRaisesRegex(ValueError,"invalid ADR-0002"):
            a.canonical_projection(x)

    def test_production_write_not_permitted_by_phase1_report(self):
        x=source()
        x["production_write_authorized"]=True
        with self.assertRaisesRegex(ValueError,"untrusted"):
            a.canonical_projection(x)


if __name__=="__main__":
    unittest.main()
