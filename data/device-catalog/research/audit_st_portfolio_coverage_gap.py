#!/usr/bin/env python3
"""Deterministic, fail-closed STM32 portfolio coverage gap *baseline* audit.

It compares five bounded official Active exact-MPN sentinels to ALL integrity-bound
ST Production CSV identities. It never claims a full ST active catalog export.
Other manufacturers may be appended to Production without invalidating this
frozen ST-only historical audit.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=HERE/"st-portfolio-gap-source-2026-09-29.json"
REPORT=HERE/"st-portfolio-coverage-gap-v0.2.json"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
SEGMENTS={
    "mainstream":("STM32F0","STM32F1","STM32F3","STM32G0","STM32G4","STM32C0"),
    "high_performance":("STM32F2","STM32F4","STM32F7","STM32H7RS","STM32H7"),
    "ultra_low_power":("STM32L0","STM32L1","STM32L4","STM32L5","STM32U0","STM32U3","STM32U5"),
    "wireless":("STM32WBA2X","STM32WLX","STM32WBX","STM32WBA5X","STM32WBA6X"),
}
EXPECTED_FAMILY_ORDER=tuple(x for names in SEGMENTS.values() for x in names)
SENTINELS=(
    ("STM32H5","STM32H503CBT6"),
    ("STM32C5","STM32C531CBT6"),
    ("STM32N6","STM32N657A0H3Q"),
    ("STM32WB0","STM32WB05KZV6TR"),
    ("STM32WL3","STM32WL33CCV6"),
)
EXPECTED_ST_MANIFEST_SHA="c8012b211a28b0a7811bfe978e7e697bc169c6f3"

def require(condition:bool,message:str)->None:
    if not condition:
        raise RuntimeError(message)

def load(path:Path)->dict:
    val=json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(val,dict),f"{path}: expected object")
    return val

def blob(data:bytes)->str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii")+data,
        usedforsecurity=False,
    ).hexdigest()

def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def render()->dict:
    snapshot=load(SOURCE)
    require(snapshot.get("schema_version")==1,"snapshot schema drifted")
    require(snapshot.get("snapshot_id")=="st-stm32-coverage-gap-bounded-audit-2026-09-29-v02",
            "snapshot identity drifted")
    require(snapshot.get("captured_date_utc")=="2026-09-29","snapshot date drifted")
    frozen=snapshot["production_baseline"]
    require(frozen["manifest_git_blob_sha"]==EXPECTED_ST_MANIFEST_SHA,"baseline Git blob drifted")
    require(frozen["manufacturer"]=="STMicroelectronics","manufacturer scope drifted")
    manifest_raw=MANIFEST.read_bytes()
    manifest=json.loads(manifest_raw)
    require(manifest.get("status")=="production","not a Production catalog")
    require(manifest.get("selection_policy")=="admitted_exact_manufacturer_part_number_only",
            "Production selection policy drifted")
    all_sources=manifest.get("sources")
    require(isinstance(all_sources,list),"Production source list missing")
    st_sources=[s for s in all_sources if s.get("manufacturer")=="STMicroelectronics"]
    require(st_sources==frozen["frozen_st_sources"],
            "ST Production source membership, order, row-count or content digest drifted; refresh audit")
    # Pin the original all-ST snapshot, but permit an independent new manufacturer's
    # publication, e.g. NXP KL25, without turning this historical ST audit stale.
    if len(st_sources)==len(all_sources):
        require(blob(manifest_raw)==EXPECTED_ST_MANIFEST_SHA,
                "frozen original all-ST manifest blob drifted")

    icpns=set()
    by_family={}
    for source in st_sources:
        path=(MANIFEST.parent/source["path"]).resolve()
        require(path.is_relative_to(ROOT),"source path escapes repository")
        raw=path.read_bytes()
        require(blob(raw)==source["git_blob_sha"],f"{source['family']}: Git blob mismatch")
        require(digest(raw)==source["sha256"],f"{source['family']}: SHA256 mismatch")
        rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        require(len(rows)==source["row_count"],f"{source['family']}: row count mismatch")
        family_set=set()
        for row in rows:
            require(row.get("manufacturer")=="STMicroelectronics" and
                    row.get("family")==source["family"],"row family/manufacturer mismatch")
            identity=(row.get("icpn") or "").strip().upper()
            require(identity.startswith("STM32") and identity==row.get("icpn"),
                    "Production row is not normalized exact STM32 identifier")
            require(identity not in icpns,f"duplicate Production exact ICPN: {identity}")
            icpns.add(identity)
            family_set.add(identity)
        by_family[source["family"]]=len(family_set)

    require(len(st_sources)==23 and len(icpns)==2683,"frozen ST Production size drifted")
    require(sum(by_family.values())==2683,"per-family count mismatch")
    require(set(by_family)==set(EXPECTED_FAMILY_ORDER),"ST family taxonomy drifted")
    segment_counts={name:sum(by_family[f] for f in group) for name,group in SEGMENTS.items()}
    require(segment_counts=={
        "mainstream":408,"high_performance":663,"ultra_low_power":1438,"wireless":174
    },"STM32 segment count drifted")

    statement=snapshot["official_portfolio_claim"]
    require(statement["threshold_exclusive"]==4500 and
            statement["comparator_type"]=="vendor_portfolio_marketing_statement" and
            statement["exact_active_icpn_export_available_in_this_snapshot"] is False and
            statement["same_lifecycle_population_as_production_confirmed"] is False,
            "vendor portfolio statement incorrectly promoted into an exact active denominator")
    require(statement["source_url"]=="https://www.st.com/en/microcontrollers-microprocessors.html",
            "official ST portfolio statement URL drifted")

    source_sentinels=snapshot["missing_family_sentinels"]
    require(len(source_sentinels)==5,"five bounded official sentinel families required")
    require(tuple((s["family"],s["exact_icpn"]) for s in source_sentinels)==SENTINELS,
            "bounded exact-MPN official sentinel selection drifted")
    observed=[]
    for s in source_sentinels:
        family=s["family"]
        exact=s["exact_icpn"]
        hostname=urlparse(s["source_url"]).hostname
        require(hostname in {"www.st.com","estore.st.com"},
                "sentinel must originate from an official ST domain")
        require(s["official_lifecycle"]=="Active","sentinel has no Active manufacturer observation")
        require(s["surface"] in {
            "Quality and Reliability exact-ICPN row",
            "ST official eStore Active exact part listing",
        },"unknown manufacturer evidence surface")
        require(exact.startswith(family),"candidate doesn't match declared ST series")
        require(family not in by_family,"missing ST family unexpectedly already published")
        require(exact not in icpns,f"official sentinel already admitted: {exact}")
        observed.append({
            "family":family,
            "exact_icpn":exact,
            "manufacturer_observed_lifecycle":"Active",
            "production_exact_match_count":0,
            "classification":"OFFICIAL_ACTIVE_EXACT_MPN_NOT_PUBLISHED",
            "official_url":s["source_url"],
            "official_evidence_surface":s["surface"],
            "remaining_gate":s["gate_domain"],
        })

    require(len(set(s["family"] for s in observed))==5,"duplicate sentinel family")
    require(len(set(s["exact_icpn"] for s in observed))==5,"duplicate sentinel MPN")
    return {
        "audit_id":snapshot["snapshot_id"],
        "snapshot_date_utc":snapshot["captured_date_utc"],
        "scope":snapshot["research_scope"],
        "record_state":"RESEARCH_BASELINE_NOT_CATALOG_ADMISSION",
        "production_baseline":{
            "manufacturer":"STMicroelectronics",
            "original_manifest_git_blob_sha":EXPECTED_ST_MANIFEST_SHA,
            "integrity_bound_source_count":len(st_sources),
            "unique_exact_icpns":len(icpns),
            "family_counts":dict(sorted(by_family.items())),
            "segment_counts":segment_counts,
        },
        "vendor_portfolio_reference":{
            "official_url":statement["source_url"],
            "manufacturer_claim":statement["claim"],
            "commercial_part_number_floor_exclusive":statement["threshold_exclusive"],
            "actual_active_exact_denominator":None,
            "same_population_comparability_verified":False,
            "inventory_scale_ratio_percent_using_4500_reference":round(len(icpns)/4500*100,2),
            "inventory_scale_ratio_is_coverage_metric":False,
        },
        "bounded_official_gap_sentinels":{
            "known_unpublished_family_count":len(observed),
            "known_unpublished_active_exact_mpn_minimum":len(observed),
            "entries":observed,
            "is_complete_vendor_delta":False,
        },
        "actual_active_exact_coverage_percent":None,
        "actual_missing_active_exact_icpns":None,
        "in_family_current_commercial_variants_not_yet_compared":True,
        "exclusions":{
            "stm32w108":"historical_structural_deferred_not_assumed_current_active",
            "other_st_product_classes":"MPU, STM8, analog, power, sensor, non-MCU and development boards are outside this audit",
        },
        "next_gate":"obtain complete dated official ST exact MPN and same-row lifecycle snapshot; verify authority and digests; compute exact set difference by family; classify OpenOCD/programming profile separately",
        "claims":{
            "all_official_ST_exact_icpns_enumerated":False,
            "all_existing_production_ST_rows_currently_Active_reverified":False,
            "the_4500_plus_commercial_count_is_an_Active_exact_denominator":False,
            "the_inventory_scale_ratio_is_an_actual_coverage_percentage":False,
            "all_missing_ST_series_have_programming_backend_support":False,
            "production_publication_authorized":False,
            "physical_programming_qualification_claimed":False,
        }
    }

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--json",action="store_true",help="Print deterministic audit data")
    args=parser.parse_args()
    calculated=render()
    if args.json:
        print(json.dumps(calculated,indent=2,sort_keys=True))
    stored=load(REPORT)
    require(stored==calculated,"stored ST coverage audit differs from deterministic replay")
    print("ST portfolio bounded gap audit: PASS")
    print("Production STM32=2683 exact ICPNs / 23 families; integrity=23/23 verified")
    print("Five official Active exact-MPN sentinels missing, five absent families")
    print("Actual complete-ST Active coverage=UNKNOWN; Production unchanged")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
