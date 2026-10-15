#!/usr/bin/env python3
"""Synthetic regression only; GitHub full original-MCP+PDF replay is authority."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import microchip_phase1_p1_ordering_crosswalk_v1 as xwalk
import microchip_phase1_p1_saml1x_pdf_custody_v1 as pdf

SHA="a"*64


def row(base, code):
    return {
        "icpn":code,"base_device":base,"dfp_name":base,
        "openocd_target_cfg_research_only":xwalk.CFG,
        "cfg_candidate_state":"P1_TARGET_ONLY_CFG_CANDIDATE",
        "internal_identity_admission":"NOT_ADMITTED",
        "software_supported_claimed":False,
        "production_write_authorized":False,
        "source_original_mcp_response_sha256_refs":[SHA],
        "fields":{k:{"status":"VERIFIED"} for k in (
            "manufacturer","icpn","base_device")} | {
            k:{"status":"PARTIAL"} for k in xwalk.GRAMMAR_FIELDS},
    }


def fixtures():
    bybase=[]
    for name in pdf.BASES:
        base="AT"+name+"A"
        family=xwalk.table1_family(base)
        packages="MY" if family["pin_count"]==24 else "AMU"
        codes=[]
        for p in packages:
            for grade in ("U","F","Z"):
                for carrier in ("","T"):
                    codes.append(base+"-"+p+grade+carrier)
        bybase.append([row(base,code) for code in codes])
    chosen=[rows[0] for rows in bybase]
    extra=[r for rows in bybase for r in rows[1:]]
    chosen += extra[:xwalk.COUNT-len(chosen)]
    assert len({r["icpn"] for r in chosen})==xwalk.COUNT
    return {
        "p1_target_only_icpn_count":126,
        "p1_unique_original_mcp_base_device_count":12,
        "source_replayed_p0_icpns_retained_separately":2437,
        "p1_openocd_target_cfg_research_only":xwalk.CFG,
        "upstream_original_manufacturer_bytes_replayed":True,
        "software_supported_icpn_count":0,
        "internal_identity_admitted_count":0,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase1_fully_verified_exact_icpns":0,
        "records":chosen,
    }


def original_pages(page):
    if page==14:
        table=[]
        for base in pdf.BASES:
            value=xwalk.table1_family("AT"+base+"A")
            table.append(f"{base} {value['flash_kib']}+2 {value['ram_kib']}")
        return "\n".join(table)
    return (
        "D = 24 Pins E = 32 Pins "
        "14 = 16 KB 15 = 32 KB 16 = 64 KB "
        "A = TQFP M = VQFN Y = SSOP U = WLCSP "
        "Optional KPH AEC-Q100"
    )


class Microchip126Test(unittest.TestCase):
    def setUp(self):
        self.original=fixtures()
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)/"p1.json"
        self.p.write_text(json.dumps(self.original),encoding="utf-8")

    def test_all_126_source_cohort_identity_read(self):
        data,digest=xwalk.read_source(self.p)
        self.assertEqual(len(data["records"]),126)
        self.assertEqual(digest,hashlib.sha256(self.p.read_bytes()).hexdigest())

    def test_family_sram_l10_l11_d14_not_same(self):
        self.assertEqual(xwalk.table1_family("ATSAML10D14A")["ram_kib"],4)
        self.assertEqual(xwalk.table1_family("ATSAML11D14A")["ram_kib"],8)
        self.assertEqual(xwalk.table1_family("ATSAML11E15A")["ram_kib"],8)
        self.assertEqual(xwalk.table1_family("ATSAML11E16A")["ram_kib"],16)
        self.assertEqual(xwalk.table1_family("ATSAML11E16A")["flash_kib"],64)
        self.assertEqual(xwalk.table1_family("ATSAML11E16A")["data_flash_kib"],2)

    def test_mcp_exact_commercial_code_does_not_mean_pdf_enumerated_sku(self):
        parsed=xwalk.interpret_one(row("ATSAML11E16A","ATSAML11E16A-MUT"))
        self.assertEqual(parsed["status"],
                         "MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR")
        self.assertEqual(parsed["derived_ordering_observations"]["package"],
                         "VQFN")
        self.assertEqual(parsed["derived_ordering_observations"]["temperature_max_c"],85)
        self.assertEqual(parsed["phase1_field_verified_promotions"],0)
        self.assertFalse(parsed["is_a_pdf_enumerated_exact_order_code"])
        self.assertFalse(parsed["software_supported_claimed"])

    def test_kph_and_aec_restrictions_fail_closed(self):
        for base,code in (
            ("ATSAML10E16A","ATSAML10E16A-MUTKPH"),
            ("ATSAML11E16A","ATSAML11E16A-UUTKPH"),
            ("ATSAML11D16A","ATSAML11D16A-YZT"),
            ("ATSAML10D16A","ATSAML10D16A-AUT"),
            ("ATSAML11E16A","ATSAML11E16A-YUT"),
        ):
            r=xwalk.interpret_one(row(base,code))
            self.assertEqual(r["status"],"ORDERING_PDF_RESTRICTION_CONFLICT",
                             code)
            self.assertEqual(r["derived_ordering_observations"],{})

    def test_kph_valid_l11_vqfn(self):
        record=xwalk.interpret_one(row("ATSAML11D14A",
                                    "ATSAML11D14A-MFTKPH"))
        self.assertEqual(record["status"],
                         "MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR")
        self.assertTrue(record["derived_ordering_observations"]
                        ["key_provisioning_suffix"])
        self.assertEqual(record["derived_ordering_observations"]
                         ["temperature_max_c"],125)

    def test_base_mismatch_and_unrecognized_codes_not_promoted(self):
        base="ATSAML11E16A"
        bad=xwalk.interpret_one(row(base,"ATSAML10E16A-MUT"))
        self.assertEqual(bad["status"],"BASE_PREFIX_IDENTITY_CONFLICT")
        other=xwalk.interpret_one(row(base,"ATSAML11E16A-MUXYZ"))
        self.assertEqual(other["status"],
                         "UNPARSED_ORIGINAL_MANUFACTURER_ORDER_CODE")
        self.assertFalse(other["production_write_authorized"])

    def test_original_pdf_row_validation_and_tamper(self):
        with patch.object(xwalk.original,"audit",return_value={
            "status":"SOURCE_BYTES_CAPTURED_AND_SEMANTICALLY_REPLAYED",
            "original_pdf_sha256":pdf.PINNED_ORIGINAL_SHA256}), \
            patch.object(xwalk.original,"pdftotext_pages",
                         side_effect=lambda path,n:original_pages(n)):
            proof=xwalk.replay_pdf_tables(self.tmp.name)
            self.assertTrue(proof["all_twelve_table_1_1_memory_rows_verified_in_original"])
        def bad_text(_path,n):
            return original_pages(n).replace("SAML11D14 16+2 8",
                                             "SAML11D14 16+2 4")
        with patch.object(xwalk.original,"audit",return_value={
            "status":"SOURCE_BYTES_CAPTURED_AND_SEMANTICALLY_REPLAYED",
            "original_pdf_sha256":pdf.PINNED_ORIGINAL_SHA256}), \
            patch.object(xwalk.original,"pdftotext_pages",
                         side_effect=bad_text):
            with self.assertRaisesRegex(ValueError,"SAML11D14"):
                xwalk.replay_pdf_tables(self.tmp.name)

    def test_no_126_cohort_tamper_admission_or_false_field_promotion(self):
        mutations=[
            lambda d:d["records"].pop(),
            lambda d:d["records"][0].update({"software_supported_claimed":True}),
            lambda d:d["records"][0]["fields"]["ram"].update({"status":"VERIFIED"}),
            lambda d:d.update({"source_replayed_p0_icpns_retained_separately":0}),
            lambda d:d.update({"production_write_authorized":True}),
        ]
        for change in mutations:
            t=copy.deepcopy(self.original)
            change(t)
            self.p.write_text(json.dumps(t))
            with self.assertRaises(ValueError):
                xwalk.read_source(self.p)
        self.p.write_text(json.dumps(self.original))

    def test_end_to_end_126_all_no_publication(self):
        with patch.object(xwalk,"replay_pdf_tables",return_value={
            "original_pdf_sha256":pdf.PINNED_ORIGINAL_SHA256,
            "all_twelve_table_1_1_memory_rows_verified_in_original":True}):
            report=xwalk.build(self.p,self.tmp.name)
        self.assertEqual(len(report["records"]),126)
        self.assertEqual(sum(report["status_counts"].values()),126)
        self.assertEqual(report["phase1_new_exact_icpn_field_verified_promotions"],0)
        self.assertEqual(report["software_supported_icpns"],0)
        self.assertFalse(report["production_write_authorized"])
        self.assertFalse(report["catalog_publication_authorized"])


if __name__=="__main__":
    unittest.main()
