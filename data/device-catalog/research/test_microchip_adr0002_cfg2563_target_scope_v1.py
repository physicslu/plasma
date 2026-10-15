#!/usr/bin/env python3
"""No 23,276-vs-2,563 Phase 1 target confusion; source identity is not CFG gate."""
from copy import deepcopy
from unittest.mock import patch
import unittest

import microchip_adr0002_cfg2563_target_scope_v1 as m

SHA="a"*64


def fixtures():
    codes=[("CHIP-A","BASE-A","tcl/target/cfg-a.cfg"),
           ("CHIP-B","BASE-B","tcl/target/cfg-b.cfg")]
    full=[]
    frozen=[]
    for code,base,cfg in codes:
        full.append({
            "icpn":code,"base_device":base,
            "phase1":{"identity_state":"IDENTIFIED",
                      "original_manufacturer_sha256_refs":[SHA]},
            "phase2":{"programming_state":"UNKNOWN"},
            "phase3":{"compatibility_state":"NOT_TESTED"},
            "ic_selector_visible":True,
            "execution_authorized":False,
        })
        frozen.append({
            "icpn":code,"base_device":base,"phase1_identity_status":"IDENTIFIED",
            "source_original_mcp_response_sha256_refs":[SHA],
            "openocd_target_cfg_research_only":cfg,
        })
    return (
        {"policy":"ADR-0002","manufacturer":"Microchip",
         "phase1_exact_icpn_observed":2,
         "selector_visible_identified_count":2,
         "production_write_authorized":False,"records":full},
        {"adr":"ADR-0002","manufacturer":"Microchip",
         "scope":"frozen_5cfg_2563_exact_original_manufacturer_icpns",
         "record_count":2,"s1_identified":2,
         "cfg_identity_freeze_sha256":m.CFG_SHA,
         "cfg_counts":{"tcl/target/cfg-a.cfg":1,"tcl/target/cfg-b.cfg":1},
         "production_write_authorized":False,
         "phase2_programming_authorized":False,
         "phase3_hil_authorized":False,
         "records":frozen},
    )


class CFGFirstTargetScopeContract(unittest.TestCase):
    def setUp(self):
        for key,value in (
            ("TARGET",2),("SOURCE",2),
            ("CFG_COUNTS",{"tcl/target/cfg-a.cfg":1,
                           "tcl/target/cfg-b.cfg":1}),
        ):
            p=patch.object(m,key,value)
            p.start()
            self.addCleanup(p.stop)

    def test_target_scope_does_not_imply_software_qualification(self):
        out=m.select_target(*fixtures())
        self.assertEqual(out["phase1_delivery_target_exact_icpns"],2)
        self.assertEqual(out["phase2_target_supported"],0)
        self.assertEqual(out["phase3_target_passed"],0)
        self.assertFalse(out["job_batch_execution_authorized"])
        self.assertTrue(out["all_identified_material_visibility_semantics_unchanged"])
        self.assertEqual(out["target_identity_freeze_sha256"],m.CFG_SHA)

    def test_official_identity_without_cfg_qualification_is_not_accepted_in_cohort(self):
        canonical,cfg=fixtures()
        cfg["records"][0]["icpn"]="FABRICATED-A"
        with self.assertRaisesRegex(ValueError,"original-MCP"):
            m.select_target(canonical,cfg)

    def test_cfg_membership_never_licenses_phase2(self):
        canonical,cfg=fixtures()
        canonical["records"][0]["phase2"]["programming_state"]="SUPPORTED"
        with self.assertRaisesRegex(ValueError,"CFG membership"):
            m.select_target(canonical,cfg)

    def test_original_mcp_hash_join_must_match(self):
        canonical,cfg=fixtures()
        cfg["records"][0]["source_original_mcp_response_sha256_refs"]=["b"*64]
        with self.assertRaisesRegex(ValueError,"exact identity"):
            m.select_target(canonical,cfg)

    def test_visibility_must_not_be_cfg_filtered(self):
        canonical,cfg=fixtures()
        canonical["records"][0]["ic_selector_visible"]=False
        with self.assertRaisesRegex(ValueError,"exact identity"):
            m.select_target(canonical,cfg)

    def test_freeze_digest_is_locked_independently_of_counts(self):
        canonical,cfg=fixtures()
        cfg["cfg_identity_freeze_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"five-CFG"):
            m.select_target(canonical,cfg)

    def test_target_must_be_subset_no_duplicate(self):
        canonical,cfg=fixtures()
        cfg["records"][1]=deepcopy(cfg["records"][0])
        with self.assertRaisesRegex(ValueError,"CFG target"):
            m.select_target(canonical,cfg)


if __name__=="__main__":
    unittest.main()
