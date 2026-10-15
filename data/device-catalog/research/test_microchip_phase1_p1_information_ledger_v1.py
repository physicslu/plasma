"""P1 source-bound exact-ICPN/Chart regression; mock fixtures are not vendor evidence."""
import copy
import unittest
from unittest.mock import patch

import microchip_phase1_p0_information_ledger_v1 as p0
import microchip_phase1_p1_information_ledger_v1 as phase1
from test_microchip_phase1_p0_information_ledger_v1 import synthetic_upstream

HASH="b"*64
BASES=tuple(f"ATSAML21{letter}{n}A" for letter in ("E","G","J") for n in
            ("15","16","17","18"))
P1_BEGIN=p0.EXPECTED_P0


def valid_research():
    source=synthetic_upstream()
    relevant=[x for x in source["icpn_rows"]
              if x["mapping_state"]==phase1.P1_STATE]
    assert len(relevant)==126
    for index,row in enumerate(relevant):
        base=BASES[index % len(BASES)]
        row["base_device"]=base
        row["dfp_device_name"]=base
        row["openocd_target_cfg"]=phase1.P1_CFG
    source["cfg_group_rows"]=[
        {"priority":"P0","openocd_target_cfg":f"unused-{n}","dfp_device_names":[]}
        for n in range(9)
    ]+[
        {"priority":"P1","openocd_target_cfg":phase1.P1_CFG,
         "dfp_device_name_count":12,"dfp_device_names":list(BASES)},
        {"priority":"P1","openocd_target_cfg":"tcl/target/avr32.cfg",
         "dfp_device_name_count":0,"dfp_device_names":[]},
    ]
    return source


class P1Phase1InformationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=valid_research()

    def test_126_p1_icpns_identity_source_only_and_all_spec_unknown(self):
        out=phase1.build(self.source,HASH)
        self.assertEqual(out["p1_target_only_icpn_count"],126)
        self.assertEqual(len(out["records"]),126)
        self.assertEqual(out["p1_unique_original_mcp_base_device_count"],12)
        self.assertEqual(sum(out["p1_distinct_base_icpn_counts"].values()),126)
        self.assertEqual(out["p1_openocd_target_cfg_research_only"],
                         "tcl/target/atsaml1x.cfg")
        for k in ("manufacturer","icpn","base_device"):
            self.assertEqual(out["per_field_coverage"][k]["VERIFIED"],126)
        for k in phase1.UNRESOLVED:
            self.assertEqual(out["per_field_coverage"][k]["UNKNOWN"],126)
            self.assertEqual(out["per_field_coverage"][k]["VERIFIED"],0)
        self.assertTrue(out["p1_target_only_not_software_supported"])
        self.assertFalse(out["catalog_publication_authorized"])
        self.assertFalse(out["production_write_authorized"])
        self.assertFalse(out["original_manufacturer_bytes_replayed_by_this_projection"])
        self.assertEqual(out["phase1_fully_verified_exact_icpns"],0)
        self.assertEqual(out["internal_identity_admitted_count"],0)
        self.assertEqual(out["software_supported_icpn_count"],0)
        self.assertTrue(all(r["cfg_candidate_state"]==phase1.P1_STATE
                            and r["target_cfg_is_flash_software_support"] is False
                            for r in out["records"]))

    def test_tampered_source_and_unknown_unreviewed_base_rejected(self):
        for key,value in (("production_write_authorized",True),
                          ("phase2_programming_authorized",True),
                          ("all_icpn_original_bytes_replayed_in_this_command",False),
                          ("icpn_denominator_joined_in_this_run",120)):
            with self.subTest(key=key):
                changed=copy.deepcopy(self.source)
                changed[key]=value
                with self.assertRaises(ValueError):
                    phase1.build(changed,HASH)
        bad=copy.deepcopy(self.source)
        row=next(x for x in bad["icpn_rows"] if
                 x["mapping_state"]==phase1.P1_STATE)
        row["base_device"]="UNLISTED-SILICON"
        with self.assertRaisesRegex(ValueError,"exact DFP name"):
            phase1.build(bad,HASH)
        bad=copy.deepcopy(self.source)
        row=next(x for x in bad["icpn_rows"] if
                 x["mapping_state"]==phase1.P1_STATE)
        row["original_mcp_response_sha256_refs"]=["BAD"]
        with self.assertRaisesRegex(ValueError,"source SHA"):
            phase1.build(bad,HASH)

    def test_no_crosswalk_from_openocd_target_to_verified_info(self):
        bad=copy.deepcopy(self.source)
        row=next(x for x in bad["icpn_rows"] if
                 x["mapping_state"]==phase1.P1_STATE)
        row["cfg_applicability_reviewed"]=True
        with self.assertRaisesRegex(ValueError,"eligibility"):
            phase1.build(bad,HASH)
        bad=copy.deepcopy(self.source)
        row=next(x for x in bad["icpn_rows"] if
                 x["mapping_state"]==phase1.P1_STATE)
        row["openocd_target_cfg"]="tcl/target/pic32mx.cfg"
        with self.assertRaisesRegex(ValueError,"Target-only"):
            phase1.build(bad,HASH)
        bad=copy.deepcopy(self.source)
        bad["cfg_group_rows"][-2]["dfp_device_name_count"]=13
        with self.assertRaisesRegex(ValueError,"pinned DFP"):
            phase1.build(bad,HASH)

    def test_duplicate_identity_rejected(self):
        bad=copy.deepcopy(self.source)
        p1=[r for r in bad["icpn_rows"] if r["mapping_state"]==phase1.P1_STATE]
        p1[1]["icpn"]=p1[0]["icpn"]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            phase1.build(bad,HASH)

    def test_chart_partial_join_exact_base_only_no_support_promotion(self):
        matched_base=BASES[0]
        # This fixture bypasses original-byte parsing intentionally. CI must
        # still cold-replay the REAL manufacturer HTML before mapping.
        fields={}
        for num,field in enumerate(phase1.FAMILY_FIELDS):
            fields[field]={
                "status":"PARTIAL", "value":64,
                "original_raw_value":"64", "original_header":field,
                "original_unit":"KB" if field in ("flash","ram") else None,
                "source_tr_ordinal":44,
                "source_column_number_1based":num+1,
                "source_original_sha256":HASH,
                "evidence_scope":"official_base_device_chart_not_exact_icpn",
            }
        checked={
            "chart_records":{"P1_deferred":1},
            "exact_icpn_fields_verified_from_chart":0,
            "source_original_sha256":HASH,
            "chart_scope":"microchipdirect_chart_branchID_21_mid_3_only",
            "source_url":"https://www.microchipdirect.com/chart.aspx?branchID=21&mid=3",
        }
        rows={matched_base:{"fields":fields,"original_tr":44}}
        with patch.object(phase1,"chart_p1_fields",return_value=(checked,rows)):
            out=phase1.build(self.source,HASH,chart_root="/mock/original-chart")
        expected=sum(r["base_device"]==matched_base for r in out["records"])
        self.assertGreater(expected,0)
        detail=out["p1_official_chart_evidence"]
        self.assertEqual(detail["p1_icpns_exact_base_joined_to_chart"],expected)
        self.assertEqual(detail["p1_icpns_no_chart_base_match"],126-expected)
        for field in phase1.FAMILY_FIELDS:
            self.assertEqual(out["per_field_coverage"][field]["PARTIAL"],expected)
            self.assertEqual(out["per_field_coverage"][field]["VERIFIED"],0)
        for field in ("io_supply","vdda","core_architecture"):
            self.assertEqual(out["per_field_coverage"][field]["UNKNOWN"],126)
        self.assertEqual(out["phase1_fully_verified_exact_icpns"],0)
        self.assertFalse(out["catalog_publication_authorized"])
        rows_bad=copy.deepcopy(rows)
        rows_bad[matched_base]["fields"]["flash"]["source_original_sha256"]="0"*64
        with patch.object(phase1,"chart_p1_fields",
                          return_value=(checked,rows_bad)):
            with self.assertRaisesRegex(ValueError,"provenance"):
                phase1.build(self.source,HASH,chart_root="/mock/original-chart")


if __name__=="__main__":
    unittest.main()
