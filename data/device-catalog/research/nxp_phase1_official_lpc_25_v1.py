#!/usr/bin/env python3
"""ADR-0002 NXP Phase1: 11 NXP Product/Package pages -> 25 official materials.

Incremental *identity-only* review. The NXP original HTML bytes are NOT
archived; only this PLASMA transcription is Git-blob-locked. Do not infer
software programming support, Production admission, IC Selector, or HIL.
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from pathlib import Path

import nxp_phase1_funnel_audit_v1 as root_audit
import nxp_phase1_lpc11u_lpc83x_11_v1 as prior_audit

HERE = Path(__file__).resolve().parent
CSV = "nxp-25-lpc-exact-material-12nc-phase1-v1.csv"
GIT_BLOB = "31d3fd024c01ff21db0534a5522fc0fbedf88890"
SOURCE_SCOPE = "OFFICIAL_NXP_EXACT_MATERIAL_12NC_PRODUCT_FAMILY_PAGE_NOT_SOFTWARE_QUALIFIED"
FAMILY_SCOPE = "OFFICIAL_NXP_PRODUCT_ID_PLUS_FAMILY_BREADCRUMB_NOT_DATASHEET_VERIFIED"
PRODUCTS = {
    "LPC1758FBD80": ("LPC1758","LPC1700","LQFP80",80,"Cortex-M3"),
    "LPC1768FBD100": ("LPC1768","LPC1700","LQFP100",100,"Cortex-M3"),
    "LPC1769FBD100": ("LPC1769","LPC1700","LQFP100",100,"Cortex-M3"),
    "LPC1778FBD208": ("LPC1778","LPC1700","LQFP208",208,"Cortex-M3"),
    "LPC1788FBD208": ("LPC1788","LPC1700","LQFP208",208,"Cortex-M3"),
    "LPC4088FBD208": ("LPC4088","LPC4000","LQFP208",208,"Cortex-M4"),
    "LPC4078FBD208": ("LPC4078","LPC4000","LQFP208",208,"Cortex-M4"),
    "LPC4357FET256": ("LPC4357","LPC4300","LBGA256",256,"Cortex-M4/M0"),
    "LPC4357JBD208": ("LPC4357","LPC4300","LQFP208",208,"Cortex-M4/M0"),
    "LPC1549JBD100": ("LPC1549","LPC1500","LQFP100",100,"Cortex-M3"),
    "LPC2378FBD144": ("LPC2378","LPC2000","LQFP144",144,"Arm7TDMI-S"),
}
# Exact NXP Package/Quality > Material Declaration crosswalks. Parenthesized
# 12NC is NXP's manufacturer material number. Unadorned commercial product
# material is sometimes shown as '<product>,551': preserve BOTH representations.
EXPECTED = {
 "LPC1758FBD80":("935288607551","LPC1758FBD80","LPC1758FBD80,551"),
 "LPC1758FBD80K":("935288607557","LPC1758FBD80","LPC1758FBD80K"),
 "LPC1758FBD80/P1K":("935430326557","LPC1758FBD80","LPC1758FBD80/P1K"),
 "LPC1758FBD80Y":("935288607518","LPC1758FBD80","LPC1758FBD80Y"),
 "LPC1768FBD100":("935288608551","LPC1768FBD100","LPC1768FBD100,551"),
 "LPC1768FBD100K":("935288608557","LPC1768FBD100","LPC1768FBD100K"),
 "LPC1768FBD100Y":("935288608518","LPC1768FBD100","LPC1768FBD100Y"),
 "LPC1769FBD100":("935290522551","LPC1769FBD100","LPC1769FBD100,551"),
 "LPC1769FBD100K":("935290522557","LPC1769FBD100","LPC1769FBD100K"),
 "LPC1769FBD100/P1K":("935430318557","LPC1769FBD100","LPC1769FBD100/P1K"),
 "LPC1778FBD208":("935291594551","LPC1778FBD208","LPC1778FBD208,551"),
 "LPC1778FBD208K":("935291594557","LPC1778FBD208","LPC1778FBD208K"),
 "LPC1788FBD208":("935291861551","LPC1788FBD208","LPC1788FBD208,551"),
 "LPC1788FBD208K":("935291861557","LPC1788FBD208","LPC1788FBD208K"),
 "LPC4088FBD208":("935297086551","LPC4088FBD208","LPC4088FBD208,551"),
 "LPC4088FBD208K":("935297086557","LPC4088FBD208","LPC4088FBD208K"),
 "LPC4078FBD208":("935297092551","LPC4078FBD208","LPC4078FBD208,551"),
 "LPC4357FET256":("935297131551","LPC4357FET256","LPC4357FET256,551"),
 "LPC4357FET256K":("935297131557","LPC4357FET256","LPC4357FET256K"),
 "LPC4357JBD208E":("935299642551","LPC4357JBD208","LPC4357JBD208E"),
 "LPC4357JBD208K":("935299642557","LPC4357JBD208","LPC4357JBD208K"),
 "LPC1549JBD100E":("935302466551","LPC1549JBD100","LPC1549JBD100E"),
 "LPC1549JBD100K":("935302466557","LPC1549JBD100","LPC1549JBD100K"),
 "LPC2378FBD144":("935282458551","LPC2378FBD144","LPC2378FBD144,551"),
 "LPC2378FBD144K":("935282458557","LPC2378FBD144","LPC2378FBD144K"),
}
NEW_RELATED = frozenset((
 "LPC1758FBD80/P1K","LPC1758FBD80Y",
 "LPC1768FBD100Y","LPC1769FBD100K","LPC1769FBD100/P1K"
))
ARM7_URL = ("https://www.nxp.com/products/processors-and-microcontrollers/"
 "arm-microcontrollers/general-purpose-mcus/lpc2000-arm7/"
 "arm7-with-512kb-flash-58-kb-sram-ethernet-usb-2-0-device-can-and-10-bit-adc:"
 "LPC2378FBD144?tab=Package_Quality_Tab")

def need(yes, message):
    if not yes:
        raise ValueError("NXP LPC official material S1: "+message)

def load():
    raw = (HERE / CSV).read_bytes()
    need(root_audit.git_blob(raw) == GIT_BLOB,
         "transcribed research source Git blob drift")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    need(rows and not any(None in x for x in rows),
         "malformed NXP material CSV")
    return rows

def validate(rows, reverse_names, already_identified):
    need(len(rows)==25 and len(EXPECTED)==25,"unexpected reviewed material count")
    by_id={r["icpn"]:r for r in rows}
    need(len(by_id)==25 and set(by_id)==set(EXPECTED),
         "missing, duplicate or unreviewed exact material name")
    need(len({r["manufacturer_12nc"] for r in rows}) == 25,
         "manufacturer 12NC collision")
    for part,row in by_id.items():
        nc,product,material = EXPECTED[part]
        model,family,package,pins,core = PRODUCTS[product]
        expected_url=ARM7_URL if product=="LPC2378FBD144" else (
            "https://www.nxp.com/products/"+product+"?tab=Package_Quality_Tab"
        )
        observed=(row["manufacturer_12nc"],row["official_product_id"],
                  row["material_declaration_display"],row["manufacturer_model_lead"],
                  row["manufacturer_family"],row["package"],
                  row["pin_count"],row["core_model"],row["official_package_quality_url"])
        expected=(nc,product,material,model,family,package,str(pins),core,expected_url)
        need(observed == expected,
             "NXP product/base/package/12NC/source mismatch: "+part)
        need(row["manufacturer"] == "NXP"
             and row["material_lifecycle_observed"] == "Active"
             and row["model_family_evidence_scope"] == FAMILY_SCOPE
             and row["source_locator"].startswith("NXP Product > Package/Quality")
             and row["source_observed_date"] == "2026-10-15"
             and row["phase1_identity_evidence_kind"] == SOURCE_SCOPE
             and row["raw_original_official_html_archived"] == "false"
             and row["official_page_original_bytes_sha256"] == ""
             and all(row[key] == "false" for key in
                    ("phase2_software_supported","production_admitted",
                     "physical_hil_passed")),
             "false original-document custody, phase qualification or source scope")
        need(part not in already_identified,
             "material duplicates already identified S1")
        if part in NEW_RELATED:
            need(row["original_reverse_wave_icpn"]=="false"
                 and part not in reverse_names,
                 "new official family variant mislabeled as old reverse lead")
        else:
            need(row["original_reverse_wave_icpn"]=="true"
                 and part in reverse_names,
                 "original reverse lead not traceable")
    need(len(NEW_RELATED)==5, "unexpected additional official-family variant count")
    need(len(set(EXPECTED)-NEW_RELATED)==20,
         "unexpected old 38 reverse leads crosswalk count")
    return set(EXPECTED)

def build():
    # Already accepted NXP 240+11 Phase 1 source validation remains unchanged.
    prior = prior_audit.build()
    need(prior["phase1_identified_s1"]==251
         and prior["phase1_identity_review_backlog"]==315
         and prior["historical_research_universe"]==566,
         "approved historical NXP Phase1 251 snapshot drift")
    originals=root_audit.read("legacy")
    reverse=root_audit.read("reverse")
    earlier={r["icpn"] for r in originals if r["identity_state"]=="ADMITTED"}
    earlier|={r["icpn"] for r in root_audit.read("lpc81x")}
    earlier|={r["icpn"] for r in root_audit.read("lpc82x")}
    earlier|={r["icpn"] for r in prior_audit.load()}
    need(len(earlier)==251,"previous Phase1 identities overlap")
    rev={r["icpn_observation"] for r in reverse}
    added=validate(load(),rev,earlier)
    remain=rev - earlier - added
    need(len(remain)==18,"source-discovered uncleared reverse candidates changed")
    added_outside=added-rev
    need(added_outside == NEW_RELATED,
         "new related variants are not limited to official manufacturer evidence")
    s1=earlier|added
    universe={r["icpn"] for r in originals}|rev|added_outside
    backlog=universe-s1
    need(len(s1)==276 and len(universe)==571
         and len(backlog)==295 and len(backlog)==277+18,
         "subset identity, universe or backlog invariant mismatch")
    need(len(s1)<=len(universe),"S1 exceeds exact manufacturer inventory")
    return {
        "policy":"ADR-0002_NXP_PHASE1_MANUFACTURER_IDENTIFIED",
        "manufacturer":"NXP",
        "previous_source_locked_s1":251,
        "new_official_exact_icpns":25,
        "new_reverse_wave_crosswalk":20,
        "new_official_family_variants_outside_566":5,
        "new_source_git_blob":GIT_BLOB,
        "official_manufacturer_html_bytes_archived":False,
        "source_universe_unique_icpns":len(universe),
        "phase1_identified_s1":len(s1),
        "phase1_information_complete_s1_complete":0,
        "phase1_identity_review_backlog":len(backlog),
        "backlog_components":{
            "legacy_partial_exact_html_base_unknown":70,
            "legacy_source_blocked_or_schema":207,
            "remaining_reverse_wave_icpns":len(remain)
        },
        "remaining_reverse_wave_icpns": sorted(remain),
        "phase2_supported_s2":None,
        "phase3_hil_passed_s3":None,
        "production_catalog_selector_changes":False,
        "reference_source_kind":"official NXP Package/Quality material and 12NC pages; original HTML not archived"
    }

if __name__ == "__main__":
    out=build()
    print("NXP_PHASE1_OFFICIAL_LPC_25_PASS universe=571 S1=276 new=25 "
          "reversed=20 additional_family_variants=5 S1_complete=0 "
          "backlog=295 reverse_remain=18 S2=NOT_AUDITED S3=NOT_AUDITED")
    print(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True))
