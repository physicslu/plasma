#!/usr/bin/env python3
"""Research-only synthetic tests; original 23,276-row CI replay is authority."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import microchip_phase1_p1_dfp_discovery_v1 as discovery

SHA="a"*64
P0="EXACT_DFP_NAME_CFG_CANDIDATE"
P1="P1_TARGET_ONLY_CFG_CANDIDATE"
UNMAPPED="NO_DFP_NAME_CFG_CROSSWALK"


def row(icpn,base,state):
    return {"icpn":icpn,"base_device":base,"mapping_state":state,
            "original_mcp_response_sha256_refs":[SHA],
            "dfp_device_name":None if state==UNMAPPED else base,
            "openocd_target_cfg":None if state==UNMAPPED else "tcl/target/any.cfg",
            "manufacturer_base_identity_evidence":
                "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND",
            "software_supported_claimed":False,
            "production_write_authorized":False}


def inventory():
    packs=[]
    for pack,lane,devices in (
        ("PIC32MZ_DFP","32bit-pic-sam",["PIC32MZ1024EFH064"]),
        ("SAM-L21_DFP","32bit-pic-sam",["ATSAML21J18A"]),
        ("PIC18F_DFP","8bit",["PIC18F452"]),
        ("SAMA5D2_DFP","excluded_mpu_candidate",["ATSAMA5D21"]),
    ):
        packs.append({"pack_name":pack,"pack_version":"v1.0.0",
                      "discovery_lane":lane,"device_names":devices})
    return {"source_bytes_sha256":discovery.gates.PINNED_DFP_SOURCE,
            "manufacturer":"Microchip",
            "observed_distinct_device_support_names":4,
            "device_support_list_is_complete_commercial_sku_inventory":False,
            "population_boundary_validated":False,
            "production_write_authorized":False,
            "device_packs":packs}


def input_fixture():
    rows=[
        row("ATSAMD21G18A-MU","ATSAMD21G18",P0),
        row("ATSAML11E16A-MUT","ATSAML11E16A",P1),
        row("PIC32MZ1024EFH064-I/PT","PIC32MZ1024EFH064",UNMAPPED),
        row("PIC18F452-I/PT","PIC18F452",UNMAPPED),
        row("ATSAMA5D21-I/XX","ATSAMA5D21",UNMAPPED),
    ]
    upstream={"icpn_denominator_joined_in_this_run":5,
              "all_icpn_original_bytes_replayed_in_this_command":True,
              "original_dfp_index_sha256_required":
                  discovery.gates.PINNED_DFP_SOURCE,
              "production_write_authorized":False,
              "cfg_software_supported_claimed":False}
    return upstream,rows


class P1DFPDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.original,self.rows=input_fixture()
        for name,val in (("SOURCE_SUBSET",5),("P0_BASELINE",1),
                         ("P1_TARGET_BASELINE",1),("DFP_SUPPORTED_NAMES",4)):
            p=patch.object(discovery,name,val)
            p.start()
            self.addCleanup(p.stop)
        p=patch.object(discovery,"verify_upstream",
                       side_effect=lambda src:self.rows)
        p.start()
        self.addCleanup(p.stop)

    def test_exact_mcp_and_dfp_32bit_only(self):
        report=discovery.classify(self.original,inventory())
        self.assertEqual(report["p1_discovery_exact_icpn_candidates"],1)
        self.assertEqual(report["p1_expanded_research_queue_total"],2)
        self.assertEqual(report["baseline_p0_p1_records_reclassified"],0)
        self.assertEqual(report["records"][0]["icpn"],
                         "PIC32MZ1024EFH064-I/PT")
        self.assertEqual(report["records"][0]["openocd_target_cfg"],None)
        self.assertEqual(report["records"][0]["p1_research_state"],
                         discovery.STATE)
        self.assertEqual(report["new_phase1_fields_verified"],0)
        self.assertFalse(report["production_write_authorized"])
        self.assertFalse(report["phase2_programming_authorized"])

    def test_no_upgraded_support_or_false_production(self):
        for mutation in (
            lambda src:src.update({"production_write_authorized":True}),
            lambda src:src.update({"all_icpn_original_bytes_replayed_in_this_command":False}),
            lambda src:src.update({"cfg_software_supported_claimed":True}),
            lambda src:src.update({"icpn_denominator_joined_in_this_run":999}),
        ):
            t=copy.deepcopy(self.original)
            mutation(t)
            with self.assertRaises(ValueError):
                discovery.classify(t,inventory())

    def test_missing_original_mcp_sha_rejected(self):
        self.rows[2]["original_mcp_response_sha256_refs"]=[]
        with self.assertRaisesRegex(ValueError,"hashes"):
            discovery.classify(self.original,inventory())

    def test_fake_opencd_cfg_for_dfp_discovery_rejected(self):
        self.rows[2]["openocd_target_cfg"]="tcl/target/fake.cfg"
        with self.assertRaisesRegex(ValueError,"qualification"):
            discovery.classify(self.original,inventory())

    def test_mpu_and_8bit_not_promoted(self):
        report=discovery.classify(self.original,inventory())
        self.assertEqual(len(report["records"]),1)
        self.assertEqual(report["not_selected_mapping_gap_reasons"]
                         ["no_exact_eligible_32bit_dfp_base"],2)

    def test_duplicate_original_mcp_rejected(self):
        self.rows[3]["icpn"]=self.rows[2]["icpn"]
        with self.assertRaisesRegex(ValueError,"duplicated"):
            discovery.classify(self.original,inventory())

    def test_unknown_dfp_source_sha_rejected(self):
        t=inventory()
        t["source_bytes_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"invalid"):
            discovery.classify(self.original,t)

    def test_ambiguous_case_insensitive_dfp_rejected(self):
        t=inventory()
        t["device_packs"][1]["device_names"]=["pic32mz1024efh064"]
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            discovery.classify(self.original,t)


if __name__=="__main__":
    unittest.main()
