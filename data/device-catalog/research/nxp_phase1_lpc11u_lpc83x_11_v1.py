#!/usr/bin/env python3
"""NXP ADR-0002 Phase 1: incremental 11 exact material 12NC/datasheet review.

Read-only historical NXP 240 S1 identity baseline + 11 independently matched
manufacturer exact material records. No Production, SUPPORTED, HIL qualification.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path

import nxp_phase1_funnel_audit_v1 as baseline

HERE = Path(__file__).resolve().parent
SOURCE = "nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv"
SOURCE_GIT_BLOB = "0a90ceb12dde7e37fbee0e1ede0f230bea0891f5"

# The expected tuple binds exact manufacturer order code -> ordering-table base,
# material 12NC, package alias, datasheet terminal count, flash, SRAM, VDD,
# and document family. No suffix or family arithmetic is accepted.
# Format: (base,12nc,commercial_pkg,ds_pkg,pins,flash_kb,sram_kb,vmin,vmax,ds)
EXPECTED = {
 "LPC11U24FHI33/301Y": ("LPC11U24FHI33/301","935297186518","HVQFN32","HVQFN33",33,32,8,"1.8","3.6","LPC11U2X"),
 "LPC11U67JBD100E": ("LPC11U67JBD100","935304421551","LQFP100","LQFP100",100,128,20,"2.4","3.6","LPC11U6X"),
 "LPC11U67JBD48E": ("LPC11U67JBD48","935302193551","LQFP48","LQFP48",48,128,20,"2.4","3.6","LPC11U6X"),
 "LPC11U67JBD64E": ("LPC11U67JBD64","935304418551","LQFP64","LQFP64",64,128,20,"2.4","3.6","LPC11U6X"),
 "LPC11U68JBD48E": ("LPC11U68JBD48","935303821551","LQFP48","LQFP48",48,256,36,"2.4","3.6","LPC11U6X"),
 "LPC11U68JBD48K": ("LPC11U68JBD48","935303821557","LQFP48","LQFP48",48,256,36,"2.4","3.6","LPC11U6X"),
 "LPC11U68JBD64E": ("LPC11U68JBD64","935302501551","LQFP64","LQFP64",64,256,36,"2.4","3.6","LPC11U6X"),
 "LPC11U68JBD64K": ("LPC11U68JBD64","935302501557","LQFP64","LQFP64",64,256,36,"2.4","3.6","LPC11U6X"),
 "LPC11U68JBD64Y": ("LPC11U68JBD64","935302501518","LQFP64","LQFP64",64,256,36,"2.4","3.6","LPC11U6X"),
 "LPC832M101FDH20FP": ("LPC832M101FDH20","935309057129","TSSOP20","TSSOP20",20,16,4,"1.8","3.6","LPC83X"),
 "LPC834M101FHI33Y": ("LPC834M101FHI33","935309056518","HVQFN32","HVQFN33",33,32,4,"1.8","3.6","LPC83X"),
}

def need(ok, msg):
    if not ok:
        raise ValueError("NXP Phase1 11 material: " + msg)

def load():
    raw = (HERE / SOURCE).read_bytes()
    need(baseline.git_blob(raw) == SOURCE_GIT_BLOB,
         "PLASMA-transcribed official-source crosswalk Git blob mismatch")
    data = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    need(data and not any(None in row for row in data), "bad CSV rows")
    return data

def verify_rows(rows, old_names, reverse_names):
    need(len(rows) == len(EXPECTED) == 11, "unexpected number of new material rows")
    need({r["icpn"] for r in rows} == set(EXPECTED),
         "missing/extra/fabricated manufacturer exact materials or duplicates")
    need(len({r["manufacturer_12nc"] for r in rows}) == 11,
         "duplicate NXP 12NC material identity")
    for r in rows:
        part = r["icpn"]
        base,nc,pkg,ds_pkg,pins,flash,ram,vmin,vmax,ds = EXPECTED[part]
        got = (r["manufacturer_base"],r["manufacturer_12nc"],
               r["manufacturer_package_alias"],r["datasheet_package"],
               int(r["datasheet_terminals_including_exposed_pad"]),
               int(r["flash_kb"]),int(r["sram_kb"]),
               r["working_vdd_min_v"],r["working_vdd_max_v"],r["datasheet_id"])
        need(got == EXPECTED[part], "exact code/base/12NC/geometry/voltage mismatch: "+part)
        page = ("https://www.nxp.com/products/LPC81X_LPC83X?tab=Package_Quality_Tab"
                if ds == "LPC83X" else
                "https://www.nxp.com/products/LPC11U00?tab=Package_Quality_Tab")
        need(r["official_exact_material_page"] == page
             and r["datasheet_url"] ==
                 "https://www.nxp.com/docs/en/data-sheet/" + ds + ".pdf"
             and r["manufacturer_material_status"] == "Active"
             and r["observed_on"] == "2026-10-15"
             and r["source_evidence_scope"] ==
                "NXP_EXACT_MATERIAL_12NC_PLUS_OFFICIAL_BASE_DATASHEET_RESEARCH_ONLY"
             and r["datasheet_revision"] and r["datasheet_ordering_locator"],
             "NXP official page, document version, material lifecycle or source scope missing")
        need(all(r[k] == "false" for k in (
            "original_datasheet_pdf_bytes_archived",
            "original_manufacturer_html_bytes_archived",
            "exact_silicon_revision_verified",
            "openocd_programming_qualified",
            "production_admitted",
            "physical_hil_verified")),
            "falsified original NXP bytes custody / Phase2 / Production / HIL")
        need(part not in old_names and part in reverse_names,
             "material not in originally disjoint OpenOCD reverse wave")
    # Distinguish SRAM topology for LPC11U24; separately account for USB RAM.
    by_name={r["icpn"]:r for r in rows}
    need("Main SRAM 6 kB + USB SRAM 2 kB" in
         by_name["LPC11U24FHI33/301Y"]["sram_topology_note"],
         "LPC11U24 aggregate SRAM hides separate USB memory")
    need(by_name["LPC834M101FHI33Y"]["manufacturer_package_alias"] ==
         "HVQFN32" and by_name["LPC834M101FHI33Y"]["datasheet_package"] ==
         "HVQFN33", "exposed center pad/package distinction erased")
    return {r["icpn"] for r in rows}

def build():
    old = baseline.verify()
    need(old["phase1_identified_s1"] == 240
         and old["phase1_identity_review_backlog"] == 326
         and old["phase1_information_complete_s1_complete"] == 0,
         "prior approved Phase1 source audit changed")
    legacy = baseline.read("legacy")
    reverse = baseline.read("reverse")
    new = verify_rows(load(), {r["icpn"] for r in legacy},
                      {r["icpn_observation"] for r in reverse})
    assert len(new) == 11
    combined = {
       "schema_version": 1,
       "manufacturer": "NXP",
       "policy": "ADR-0002_PHASE1_EXACT_ICPN_IDENTIFIED",
       "baseline_inventory": "NXP_PHASE1_FUNNEL_INVENTORY_V1",
       "baseline_phase1_identified": 240,
       "official_new_exact_materials": 11,
       "new_source_git_blob": SOURCE_GIT_BLOB,
       "official_source_binary_bytes_archived_for_new_11": False,
       "verified_nxp_exact_material_12nc_to_datasheet_base": sorted(new),
       "historical_research_universe": 566,
       "phase1_identified_s1": 251,
       "phase1_information_complete_s1_complete": 0,
       "phase1_identity_review_backlog": 315,
       "phase1_backlog_components": {
          "legacy_html_partial_and_base_unknown": 70,
          "legacy_source_blocked_or_schema": 207,
          "reverse_discovery_still_requires_crosswalk": 38,
       },
       "phase2_supported_s2": None,
       "phase3_hil_passed_s3": None,
       "production_admission_changes": 0,
       "public_catalog_or_ic_selector_changes": 0,
    }
    need(sum(combined["phase1_backlog_components"].values()) == 315
         and 251+315 == 566,
         "Phase1 exact-ICPN subset/unique scope invariant failed")
    return combined

if __name__ == "__main__":
    report=build()
    print("NXP_PHASE1_11_OFFICIAL_MATERIAL_PASS universe=566 S1=251 "
          "new=11 S1_complete=0 backlog=315 reverse_remain=38 "
          "S2=NOT_AUDITED S3=NOT_AUDITED")
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
