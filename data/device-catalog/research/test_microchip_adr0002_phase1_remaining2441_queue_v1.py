#!/usr/bin/env python3
"""Microchip 2,441 remaining source queue: ADR-0002 boundaries and negative tests."""
from __future__ import annotations
from copy import deepcopy
from itertools import product
from unittest.mock import patch
import unittest

import microchip_adr0002_phase1_remaining2441_queue_v1 as q

SHA="a"*64
CFG="tcl/target/atsaml1x.cfg"
VAO=[
    "ATSAML10D16A-MZTVAO","ATSAML10E16A-MZTVAO",
    "ATSAML10E16A-MZVAO","ATSAML11E16A-MZTVAO",
]


def fixtures():
    variants=[]
    for series, group, density, package, grade, tail in product(
          ("10","11"),("D","E"),("14","15","16"),("M","A","U","Y"),("U","F"),("","T")):
        code=f"ATSAML{series}{group}{density}A-{package}{grade}{tail}"
        if q.official_pdf.ORDER.fullmatch(code):
            variants.append(code)
    variants=sorted(set(variants))[:122]
    assert len(variants)==122
    first_rows=[]
    for code in variants:
        first_rows.append({
            "icpn":code, "status":"MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR",
            "source_pdf_original_sha256":q.PDF_SHA,
            "software_supported_claimed":False,
            "production_write_authorized":False,
        })
    for code in VAO:
        first_rows.append({
            "icpn":code,"status":"MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED",
            "special_suffix_observed":"VAO",
            "source_pdf_original_sha256":q.PDF_SHA,
            "software_supported_claimed":False,
            "production_write_authorized":False,
        })
    records=[]
    frozen=[]
    for code in variants + VAO:
        base=code.split("-")[0]
        official={
            "icpn":code,"base_device":base,"ic_selector_visible":True,
            "phase1":{"identity_state":"IDENTIFIED",
                      "source_scope":"official_mcp_search_products_exact_partNumber_row",
                      "official_material_source_uri":"https://api.microchip.com/mcp/resources",
                      "source_observed_at_utc":"2026-10-15T00:00:00Z",
                      "original_manufacturer_sha256_refs":[SHA]},
            "phase2":{"programming_state":"UNKNOWN"},
            "phase3":{"compatibility_state":"NOT_TESTED"},
            "execution_authorized":False,
        }
        records.append(official)
        fields={}
        for field in q.PHASE_FIELDS:
            verified=field in ("manufacturer","icpn","base_device")
            fields[field]={
                "value":(code if field=="icpn" else
                         (base if field=="base_device" else "Microchip"))
                         if verified else None,
                "state":"VERIFIED" if verified else "UNKNOWN",
                "source_authority":"Microchip Technology official" if verified else None,
                "source_sha256_refs":[SHA] if verified else [],
                "notes":None,
            }
        frozen.append({
            "icpn":code,"base_device":base,"phase1_identity_status":"IDENTIFIED",
            "phase1_information_status":"INFORMATION_INCOMPLETE",
            "source_original_mcp_response_sha256_refs":[SHA],
            "openocd_target_cfg_research_only":CFG,
            "fields":fields,
        })
    return ({
        "policy":"ADR-0002",
        "phase1_identity_counts":{"IDENTIFIED":126},
        "phase2_programming_state_counts":{"SUPPORTED":0},
        "phase3_compatibility_state_counts":{"PASSED":0},
        "upstream_full_original_mcp_report_sha256":SHA,
        "records":records,
    },{
        "records":frozen,
    },{
        "schema_version":1,
        "p1_original_mcp_exact_icpn_count":126,
        "p1_base_device_count":12,
        "status_counts":{
            "MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR":122,
            "MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED":4,
        },
        "pdf_source_replay":{"original_pdf_sha256":q.PDF_SHA},
        "software_supported_icpns":0,
        "internal_admitted_icpns":0,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "records":first_rows,
    },variants)


class QueueTests(unittest.TestCase):
    def setUp(self):
        original, freeze, audit, names=fixtures()
        self.original,self.freeze,self.audit=original,freeze,audit
        mocks=[
            patch.object(q,"SOURCE",126),
            patch.object(q,"COHORT",126),
            patch.object(q,"REMAINING",4),
            patch.object(q,"REMAINING_BY_CFG",{CFG:4}),
            patch.object(q,"FIRST_CODES_SHA",q.digest_ids(names)),
            patch.object(q.target,"select_target",return_value={}),
        ]
        for m in mocks:
            m.start()
            self.addCleanup(m.stop)

    def test_four_vao_remain_phase1_identified_but_not_field_promoted(self):
        rows,summary=q.derive(self.original,self.freeze,self.audit)
        self.assertEqual(len(rows),4)
        self.assertEqual({r["icpn"] for r in rows},set(VAO))
        self.assertEqual(summary["remaining_special_vao_exact_icpns"],4)
        self.assertEqual(summary["phase1_field_coverage"]["working_vdd"]["UNKNOWN"],4)
        self.assertTrue(all(r["phase1_identity_status"]=="IDENTIFIED"
                            and not r["job_batch_execution_authorized"]
                            and r["phase2_programming_state"]=="UNKNOWN"
                            and r["phase3_compatibility_state"]=="NOT_TESTED"
                            and r["executable_openocd_target_cfg"] is None
                            for r in rows))

    def test_unverified_original_mcp_identity_join_fails_closed(self):
        original=deepcopy(self.original)
        original["records"][-1]["phase1"]["original_manufacturer_sha256_refs"]=["b"*64]
        with self.assertRaisesRegex(ValueError,"manufacturer evidence"):
            q.derive(original,self.freeze,self.audit)

    def test_cfg_does_not_authorize_phase2_or_hil(self):
        original=deepcopy(self.original)
        original["records"][-1]["phase2"]["programming_state"]="SUPPORTED"
        with self.assertRaisesRegex(ValueError,"Phase 2 or HIL"):
            q.derive(original,self.freeze,self.audit)

    def test_missing_source_provenance_not_guessed(self):
        frozen=deepcopy(self.freeze)
        last=frozen["records"][-1]["fields"]["icpn"]
        last["state"]="UNKNOWN"
        last["value"]=None
        last["source_sha256_refs"]=[]
        with self.assertRaisesRegex(ValueError,"identity not verified"):
            q.derive(self.original,frozen,self.audit)

    def test_first_batch_membership_must_match_original_material(self):
        audit=deepcopy(self.audit)
        audit["records"][0]["icpn"]="ATSAML11E16A-MUFABRICATED"
        with self.assertRaisesRegex(ValueError,"ordinary ordering variant"):
            q.derive(self.original,self.freeze,audit)

    def test_unknown_field_never_contains_fabricated_numeric_zero(self):
        frozen=deepcopy(self.freeze)
        frozen["records"][-1]["fields"]["working_vdd"]["value"]=0
        with self.assertRaisesRegex(ValueError,"unknown Phase 1 field"):
            q.derive(self.original,frozen,self.audit)

    def test_no_changes_to_openocd_qualifications(self):
        _,summary=q.derive(self.original,self.freeze,self.audit)
        self.assertFalse(summary["production_write_authorized"])
        self.assertFalse(summary["catalog_publication_authorized"])
        self.assertFalse(summary["programming_execution_authorized"])
        self.assertEqual(summary["phase2_supported"],0)
        self.assertEqual(summary["phase3_passed"],0)


if __name__=="__main__":
    unittest.main()
