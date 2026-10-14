#!/usr/bin/env python3
"""One bounded P1 pass for NXP 38, pinned OpenOCD 0.12.0 source only."""
from pathlib import Path
import csv
import io
import json
from collections import Counter
from nxp_adr0002_core_qual_v10 import build as build_v10, LEDGER as V10_LEDGER, to_csv as v10_csv
from nxp_adr0002_openocd_triage_v9 import blob, LOCK as V9_LOCK, upstream_source

HERE=Path(__file__).resolve().parent
LEDGER=HERE/"nxp-38-p1-one-pass-v12.csv"
LOCK=HERE/"nxp-38-p1-source-lock-v12.json"
FIELDS=("icpn investigation_group research_priority openocd_software_support_state "
    "openocd_version openocd_source_commit target_family_source_path driver_source_path "
    "bounded_review_status pinned_source_positive pinned_exact_variant_identification "
    "driver_geometry_qualified required_program_erase_verify_qualified "
    "exact_icpn_applicability_verified public_catalog_visibility_authorized "
    "production_identity_existing physical_hil_qualified stop_or_reopen_rule").split()
STOP="PARK_AFTER_ONE_BOUNDED_CHECK_REOPEN_ON_PINNED_OPENOCD_SOURCE_CHANGE_OR_OFFICIAL_EXACT_ID_EVIDENCE_OR_OWNER_DEMAND"

def require(ok, msg):
    if not ok:raise ValueError(msg)

def load():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["schema_version"]==12 and lock["adr"]=="ADR-0002"
      and lock["pinned_commit"]=="9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c",
      "P1 pin changed")
    require(blob(V10_LEDGER.read_bytes())==lock["input_v10_git_blob"]
      and V10_LEDGER.read_bytes()==v10_csv(build_v10()),"501 original NXP source drift")
    require(blob(V9_LOCK.read_bytes())==lock["upstream_v9_source_lock_git_blob"]
      and lock["reviewed_source_blobs"]==json.loads(V9_LOCK.read_text())["upstream_git_blobs"],
      "original upstream OpenOCD source pin changed")
    require(lock["count"]=={"LPC802_LPC804":18,"K32L2":20},"P1 bounded quota changed")
    return lock

def upstream(root):
    lock=load()
    upstream_source(root,json.loads(V9_LOCK.read_text(encoding="utf-8")))
    for name,sha in lock["extra_source_blob"].items():
        path=root/name
        require(path.exists() and blob(path.read_bytes())==sha,"pinned KE driver changed")
    lpc=(root/"src/flash/nor/lpc2000.c").read_text(encoding="utf-8")
    kin=(root/"src/flash/nor/kinetis.c").read_text(encoding="utf-8")
    ke=(root/"src/flash/nor/kinetis_ke.c").read_text(encoding="utf-8")
    lcfg=(root/"tcl/target/lpc8xx.cfg").read_text(encoding="utf-8")
    lbase=(root/"tcl/target/lpc1xxx.cfg").read_text(encoding="utf-8")
    require("source [find target/lpc1xxx.cfg]" in lcfg and
      "flash bank $_FLASHNAME lpc2000" in lbase,
      "LPC8xx generic target/flash source proof disappeared")
    for marker in ("LPC802_", "LPC804_"):
        require(marker not in lpc, "new exact LPC80x ID path requires re-review: "+marker)
    require("K32L2" not in kin and "K32L2" not in ke,
            "new pinned K32L2 source reference requires re-review")
    configs=[p.name.lower() for p in (root/"tcl/target").glob("*.cfg")]
    require(not any(p.startswith("k32") for p in configs),
            "new pinned K32L2 target config may exist: re-review")

def build():
    load()
    rows=[]
    for r in build_v10():
        if r["research_priority"]!="P1":continue
        is_lpc=r["icpn"].startswith(("LPC802","LPC804"))
        require(is_lpc or r["icpn"].startswith("K32L2"),"unexpected P1 device")
        rows.append({
        "icpn":r["icpn"],
        "investigation_group":"LPC802_804" if is_lpc else "K32L2",
        "research_priority":"P1",
        "openocd_software_support_state":"CANDIDATE",
        "openocd_version":r["openocd_version"],
        "openocd_source_commit":r["openocd_source_commit"],
        "target_family_source_path":r["target_config"],
        "driver_source_path":r["flash_driver_source"],
        "bounded_review_status":"COMPLETED_FOR_PINNED_COMMIT",
        "pinned_source_positive":"GENERIC_LPC8XX_CFG_FLASH_BANK_LPC2000_ERASE_WRITE_PROBE" if is_lpc else
             "GENERIC_KINETIS_FAMILY_FLASH_DRIVER_ERASE_WRITE_PROBE",
        "pinned_exact_variant_identification":"LPC802_804_PART_IDS_NOT_LISTED_IN_PINNED_LPC2000_AUTO_PROBE" if is_lpc else
             "K32L2_EXACT_TARGET_IDENTIFICATION_NOT_FOUND_IN_REVIEWED_KINETIS_SOURCES",
        "driver_geometry_qualified":"false",
        "required_program_erase_verify_qualified":"false",
        "exact_icpn_applicability_verified":"false",
        "public_catalog_visibility_authorized":"false",
        "production_identity_existing":r["production_identity_admitted"],
        "physical_hil_qualified":"false",
        "stop_or_reopen_rule":STOP})
    require(len(rows)==38 and Counter(r["investigation_group"] for r in rows)==
            {"LPC802_804":18,"K32L2":20}, "P1 bounded source set changed")
    require(all(r["openocd_software_support_state"]=="CANDIDATE" and
                r["exact_icpn_applicability_verified"]=="false" and
                r["public_catalog_visibility_authorized"]=="false" for r in rows),
            "P1 source-only result falsely promoted SUPPORTED")
    return rows

def serialize(rows):
    result=io.StringIO(newline="")
    writer=csv.DictWriter(result,fieldnames=FIELDS,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    return result.getvalue().encode("utf-8")

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--upstream-root",type=Path)
    a=p.parse_args()
    if a.upstream_root:upstream(a.upstream_root)
    require(LEDGER.read_bytes()==serialize(build()),"P1 38 immutable bounded review drift")
    print("NXP_P1_38_V12_PASS LPC802_804=18 K32L2=20; BOUNDED_PASS_PARKED=38; new SUPPORTED=0")
if __name__=="__main__":main()
