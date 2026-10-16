#!/usr/bin/env python3
"""NXP ADR-0002 Phase1: official K40/K60/KL46 plus same KL4x family materials.

This is a reproducible PLASMA-transcription audit, NOT manufacturer-original
HTML archival; source SHA pins the checked-in CSV, NOT the vendor web bytes.
No Phase 2 software qualification, Production/Selector, or physical HIL.
"""
from __future__ import annotations
import csv
import io
import json
from collections import Counter
from pathlib import Path

import nxp_phase1_funnel_audit_v1 as root
import nxp_phase1_lpc11u_lpc83x_11_v1 as prior_11
import nxp_phase1_official_lpc_25_v1 as prior_25

HERE=Path(__file__).resolve().parent
FILENAME="nxp-21-k40-k60-kl4x-official-materials-phase1-v1.csv"
SOURCE_GIT_BLOB="d11788fb5b210bd3b3ed06807f922c3ac1e2f8a0"
OFFICIAL={
    "K40": "https://www.nxp.com/products/K40_100?tab=Package_Quality_Tab",
    "K60": "https://www.nxp.com/products/K60_100?tab=Package_Quality_Tab",
    "KL46": "https://www.nxp.com/products/KL4x?tab=Package_Quality_Tab",
    "KL43": "https://www.nxp.com/products/KL4x?tab=Package_Quality_Tab",
}
# Fixed manufacturer transcribed exact material 12NC and physical package.
# Do not produce these suffixes from family string arithmetic.
MATERIALS={
 "MK40DN512VLK10":("K40","MK40DN512","935319887557","LQFP80",80,512,128),
 "MK40DN512VLL10":("K40","MK40DN512","935319895557","LQFP100",100,512,128),
 "MK40DN512VLQ10":("K40","MK40DN512","935323263557","LQFP144",144,512,128),
 "MK40DN512VMD10":("K40","MK40DN512","935324567557","LBGA144",144,512,128),
 "MK60DN512VLL10":("K60","MK60DN512","935323339557","LQFP100",100,512,128),
 "MK60DN512VLQ10":("K60","MK60DN512","935321729557","LQFP144",144,512,128),
 "MK60DN512VMC10":("K60","MK60DN512","935313053557","LFBGA121",121,512,128),
 "MK60DN512VMC10R":("K60","MK60DN512","935313053518","LFBGA121",121,512,128),
 "MK60DN512VMD10":("K60","MK60DN512","935311025557","LBGA144",144,512,128),
 "MK60DN512VLL10R":("K60","MK60DN512","935323339528","LQFP100",100,512,128),
 "MKL46Z128VLH4":("KL46","MKL46Z128","935323348557","LQFP64",64,128,16),
 "MKL46Z128VLL4":("KL46","MKL46Z128","935321829557","LQFP100",100,128,16),
 "MKL46Z128VMC4":("KL46","MKL46Z128","935323351557","LFBGA121",121,128,16),
 "MKL46Z256VLH4":("KL46","MKL46Z256","935325758557","LQFP64",64,256,32),
 "MKL46Z256VLL4":("KL46","MKL46Z256","935320037557","LQFP100",100,256,32),
 "MKL46Z256VMC4":("KL46","MKL46Z256","935320083557","LFBGA121",121,256,32),
 "MKL46Z256VMP4":("KL46","MKL46Z256","935311622557","LFBGA64",64,256,32),
 "MKL43Z128VLH4":("KL43","MKL43Z128","935320579557","LQFP64",64,128,16),
 "MKL43Z128VMP4":("KL43","MKL43Z128","935312295557","LFBGA64",64,128,16),
 "MKL43Z256VLH4":("KL43","MKL43Z256","935318116557","LQFP64",64,256,32),
 "MKL43Z256VMP4":("KL43","MKL43Z256","935324856557","LFBGA64",64,256,32),
}
EXTRA=frozenset(["MK60DN512VLL10R","MKL43Z128VLH4","MKL43Z128VMP4",
                 "MKL43Z256VLH4","MKL43Z256VMP4"])
DENY_FLAGS=("original_official_html_archived","original_official_pdf_archived",
            "phase1_information_complete","phase2_programming_supported",
            "production_admitted","phase3_hil_passed")

def need(yes,why):
    if not yes:
        raise ValueError("NXP Kinetis Phase1: "+why)

def load():
    raw=(HERE/FILENAME).read_bytes()
    need(root.git_blob(raw)==SOURCE_GIT_BLOB,"transcribed source Git blob drift")
    rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    need(len(rows)==21 and not any(None in r for r in rows),
         "CSV count/shape invalid")
    return rows

def verify_materials(rows,seen_prior,reverse_names):
    need(len(rows)==len(MATERIALS)==21,"material count not 21")
    actual={r["icpn"] for r in rows}
    need(actual==set(MATERIALS) and len(actual)==len(rows),
         "commercial exact ICPNs missing, duplicated or fabricated")
    need(len({r["manufacturer_12nc"] for r in rows})==len(rows),
         "manufacturer material 12NC duplicated")
    need(not (actual&seen_prior),
         "new NXP material overlaps approved prior S1")
    for r in rows:
        part=r["icpn"]
        group,base,nc,pkg,pins,flash,ram=MATERIALS[part]
        got=(r["source_batch"],r["manufacturer_family"],r["base_device"],
             r["manufacturer_12nc"],r["package"],
             r["package_terminal_count"],r["flash_kb"],r["ram_kb"],
             r["core_model"],r["working_vdd_min_v"],r["working_vdd_max_v"],
             r["temperature_min_c"],r["temperature_max_c"])
        expected=(group,group,base,nc,pkg,str(pins),str(flash),str(ram),
                  "Cortex-M0+" if group.startswith("KL") else "Cortex-M4",
                  "1.71","3.6","-40","105")
        need(got==expected,"official exact material/base/12NC/field mismatch: "+part)
        need(r["manufacturer"]=="NXP"
             and r["manufacturer_material_status"]=="Active"
             and r["source_observed_date"]=="2026-10-15"
             and r["official_material_product_url"]==OFFICIAL[group]
             and r["official_product_parametric_url"]==OFFICIAL[group].replace(
                 "Package_Quality_Tab","Buy_Parametric_Tab")
             and r["exact_material_identity_evidence"]==
                 "OFFICIAL_NXP_EXACT_COMMERCIAL_ORDER_CODE_AND_12NC"
             and r["base_family_evidence"]==
                 "NXP_OFFICIAL_PRODUCT_FAMILY_AND_DATASHEET_SUPPORTED_PARTS; BASE_LINK_NOT_SILICON_ID"
             and r["official_material_locator"].startswith("NXP Package/Quality")
             and r["phase1_identified"]=="true",
             "manufacturer official material identity/provenance invalid")
        need(all(r[k]=="false" for k in DENY_FLAGS),
             "source bytes archive or software/Production/HIL falsely promoted")
        if part in EXTRA:
            need(r["prior_reverse_wave_member"]=="false"
                 and part not in reverse_names,
                 "additional official family material falsely counted as old candidate")
        else:
            need(r["prior_reverse_wave_member"]=="true"
                 and part in reverse_names,
                 "reverse family observation not traced to official identity")
    need(len(actual-EXTRA)==16 and len(EXTRA)==5,
         "16 original plus 5 extra exact identities unexpectedly changed")
    return actual

def build():
    # Never retroactively mutate or broaden approved historical NXP datasets.
    prev=prior_25.build()
    need(prev["phase1_identified_s1"]==276
         and prev["source_universe_unique_icpns"]==571
         and prev["phase1_identity_review_backlog"]==295,
         "prior merged NXP S1=276 evidence baseline drift")
    legacy=root.read("legacy")
    reverse=root.read("reverse")
    existing={r["icpn"] for r in legacy if r["identity_state"]=="ADMITTED"}
    existing|={r["icpn"] for r in root.read("lpc81x")}
    existing|={r["icpn"] for r in root.read("lpc82x")}
    existing|={r["icpn"] for r in prior_11.load()}
    existing|={r["icpn"] for r in prior_25.load()}
    need(len(existing)==276,"historical Phase1 identities not unique")
    rev={r["icpn_observation"] for r in reverse}
    added=verify_materials(load(),existing,rev)
    remaining=rev - existing - added
    need(remaining=={"LPC1114FBD48/333J","LPC2148FBD64"},
         "two deliberately unresolved legacy reverse identities changed")
    source_universe={r["icpn"] for r in legacy}|rev
    source_universe|={r["icpn"] for r in prior_25.load()}-rev
    source_universe|=added-rev
    s1=existing|added
    backlog=source_universe-s1
    need(len(source_universe)==576 and len(s1)==297
         and len(backlog)==279,
         "S1/identity-backlog/source-universe count invariant changed")
    return {
        "manufacturer":"NXP",
        "policy":"ADR-0002_PHASE1_IDENTIFIED_EXACT_COMMERCIAL_ICPN",
        "baseline_s1":276,
        "new_official_kinetis_exact_materials":21,
        "new_from_previous_cfg_reverse_leads":16,
        "new_from_same_official_family_products":5,
        "source_transcription_git_blob":SOURCE_GIT_BLOB,
        "source_original_nxp_html_pdf_bytes_archived":False,
        "unique_source_observed_or_candidate_icpns":len(source_universe),
        "phase1_identified_s1":len(s1),
        "phase1_information_complete_s1_complete":0,
        "phase1_identity_review_backlog":len(backlog),
        "phase1_backlog_components":{
            "legacy_partial_exact_html_unknown_base":70,
            "legacy_source_blocked_schema":207,
            "reverse_order_code_ambiguity_lpc1114_lpc2148":2,
        },
        "pending_original_cfg_reverse_icpns":sorted(remaining),
        "phase2_openocd_supported_s2":None,
        "phase3_hil_s3":None,
        "production_catalog_ic_selector_changes":False,
    }

if __name__=="__main__":
    result=build()
    print("NXP_KINETIS_PHASE1_21_PASS universe=576 S1=297 added=21 "
          "reverse_qualified_identity=16 extra_family=5 "
          "S1_complete=0 backlog=279 unresolved_reverse=2 "
          "S2=NOT_AUDITED S3=NOT_AUDITED")
    print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
