#!/usr/bin/env python3
"""Generate NXP KL25 catalog admission candidate from retained exact manufacturer evidence.

Independent of NXP IC-Support Software Executor admission; no Production writes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=HERE/"openocd-parts-canonical.csv"
SOURCE_LOCK=ROOT/"data/ic-support/benchmarks/nxp-kl25/source-lock.json"
DISCOVERY=HERE/"evidence/nxp-kl25-exact-icpn-live-2026-09-29"
DISCOVERY_GATE=HERE/"nxp-kl25-exact-icpn-discovery-gate.json"
AUTHORITY=HERE/"nxp-kl25-metadata-authority.json"
PRODUCTION=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"

MANUFACTURER="NXP"
FAMILY="KL25"
SERIES="KL25"
TARGET="tcl/target/kl25.cfg"
EXPECTED_COUNT=12
EXPECTED_EXACT_SHA="dd2c3cee83552a9875ee84c7bdea2cc6bc9c671f528b4bde02bed02b753755d5"
EXPECTED_SOURCE_SHA="43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SOURCE_LOCK_BLOB="4927139f202bee1ee3e813ef57e3cfdfd3333ba6"
EXPECTED_DISCOVERY_GATE_BLOB = None
EXPECTED_DISCOVERY_ROW_BLOB="61c1be96a3c14e28f05099762f64b9ab5e23c1fb"
EXPECTED_DISCOVERY_EXACT_BLOB="3f0903108c515cd947a4330f757a478006959804"
EXPECTED_PRODUCTION_BLOB="c8012b211a28b0a7811bfe978e7e697bc169c6f3"
PATTERNS=("MKL25Z128xxx4","MKL25Z32xxx4","MKL25Z64xxx4")
MEMORY_KIB={"32":32,"64":64,"128":128}
PACKAGE_CODES={
 "VFM4":("HVQFN","32","HVQFN32","QFN"),
 "VFT4":("HVQFN","48","HVQFN48","QFN"),
 "VLH4":("LQFP","64","LQFP64","LQFP"),
 "VLK4":("LQFP","80","LQFP80","LQFP"),
}
PRODUCTION_FIELDS=(
 "manufacturer","icpn","family","series","base_device","package","pin_count",
 "flash_size","temperature_grade","option_suffix","cmsis_device_name",
 "existing_identifier","existing_identifier_kind","mapping_status",
 "openocd_target_config","source_type","source_reference","source_authority","verification_status"
)
EXACT_SKU_RE=re.compile(r"^(MKL25Z)(128|32|64)(VFM4|VFT4|VLH4|VLK4)$")

def req(ok:bool,msg:str)->None:
    if not ok:raise RuntimeError(msg)

def sha256(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def blob_bytes(data:bytes)->str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data,usedforsecurity=False).hexdigest()

def load(path:Path)->dict[str,Any]:
    o=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(o,dict),f"{path.name}: expected JSON object")
    return o

def sha_exact(values:list[str])->str:
    return sha256(("\n".join(values)+"\n").encode("utf-8"))

def pattern_matches(sku:str,pattern:str)->bool:
    return len(sku)==len(pattern) and all(p=="x" or p==c for p,c in zip(pattern,sku))

def inputs()->tuple[list[str],dict[str,dict[str,Any]],list[dict[str,str]],dict[str,Any]]:
    req(sha256(SOURCE.read_bytes())==EXPECTED_SOURCE_SHA,"canonical candidate inventory drifted")
    req(blob_bytes(SOURCE_LOCK.read_bytes())==EXPECTED_SOURCE_LOCK_BLOB,"NXP source lock drifted")
    req(blob_bytes(PRODUCTION.read_bytes())==EXPECTED_PRODUCTION_BLOB,"Production prestate drifted")
    req(blob_bytes((DISCOVERY/"commercial-rows.json").read_bytes())==EXPECTED_DISCOVERY_ROW_BLOB,"live commercial row evidence drifted")
    req(blob_bytes((DISCOVERY/"exact-icpns.json").read_bytes())==EXPECTED_DISCOVERY_EXACT_BLOB,"retained exact-set blob drifted")
    gate=load(DISCOVERY_GATE)
    req(gate.get("gate_id")=="nxp-kl25-bounded-current-commercial-exact-icpn-discovery-v1","discovery gate id drifted")
    req(gate.get("bounded_exact_discovery_complete") is True,"discovery not complete")
    req(gate.get("catalog_admission_ready") is False,"previous gate prematurely admitted catalog")
    req(gate.get("exact_set_sha256")==EXPECTED_EXACT_SHA,"discovery gate exact hash drifted")
    req(gate.get("next_gate")=="nxp-kl25-bounded-exact-icpn-admission-readiness-gate","readiness next gate drifted")
    lock=load(SOURCE_LOCK)
    req(lock.get("targets")==["MKL25Z128VLK4"],"manufacturer-reviewed exact representative drifted")
    docs=lock.get("sources") or []
    req({(d["source_id"],str(d["revision"]),d["integrity"]["digest"]) for d in docs}=={
      ("nxp_kl25_ds_rev5","5","e42271b7f612ac1b0812001e62bef10d217be4a61dbee5bb0a1e5c4076209a3b"),
      ("nxp_kl25_rm_rev3","3","7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241"),
    },"NXP locked manufacturer document authority drifted")

    ex=load(DISCOVERY/"exact-icpns.json")
    commercial=load(DISCOVERY/"commercial-rows.json")
    summary=load(DISCOVERY/"discovery-summary.json")
    req(ex.get("exact_icpn_count")==EXPECTED_COUNT and ex.get("exact_set_sha256")==EXPECTED_EXACT_SHA,"exact identity snapshot drifted")
    exact=ex.get("exact_icpns")
    req(isinstance(exact,list) and len(exact)==EXPECTED_COUNT and exact==sorted(set(exact)),"exact identities malformed")
    req(sha_exact(exact)==EXPECTED_EXACT_SHA,"recomputed exact hash drifted")
    req(ex.get("excluded_non_active")==[],"non-Active identities retained")
    req(summary.get("status")=="discovered" and summary.get("bounded_exact_discovery_complete") is True and summary.get("manual_review_count")==0,"discovery summary incomplete")
    req(summary.get("active_exact_icpns")==exact,"discovery summary exact identities differ")
    req(commercial.get("status")=="discovered" and commercial.get("http_status")==200,"manufacturer commercial listing status drifted")
    req(commercial.get("active_exact_icpns")==exact and commercial.get("excluded_non_active")==[],"commercial Active set drifted")
    records=commercial.get("active_row_evidence")
    req(isinstance(records,list) and len(records)==EXPECTED_COUNT,"commercial row evidence count drifted")
    identity_rows={r.get("icpn"):r for r in records if isinstance(r,dict)}
    req(set(identity_rows)==set(exact),"commercial evidence identity set drifted")

    authority=load(AUTHORITY)
    req(authority.get("authority_id")=="nxp-kl25-commercial-metadata-authority-v1","metadata authority drifted")
    req(authority.get("retained_source_lock_git_blob_sha")==EXPECTED_SOURCE_LOCK_BLOB,"metadata authority NXP source lock drifted")
    req(authority.get("active_commercial_identity_source",{}).get("evidence_git_blob_sha")==EXPECTED_DISCOVERY_ROW_BLOB,"metadata authority live source drifted")
    adocs=authority.get("documents") or []
    req({(d["source_id"],d["sha256"]) for d in adocs} =={
     ("nxp_kl25_ds_rev5","e42271b7f612ac1b0812001e62bef10d217be4a61dbee5bb0a1e5c4076209a3b"),
     ("nxp_kl25_rm_rev3","7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241"),
    },"metadata authority documents drifted")
    req(authority.get("metadata_rules",{}).get("temperature_grade")=="-40..105 C","temperature authority drifted")
    req(authority.get("metadata_rules",{}).get("memory_codes_kib")=={k:v for k,v in MEMORY_KIB.items()},"memory authority drifted")
    req(all(v is False for v in (authority.get("claims") or {}).values()),"metadata authority claim escaped")

    with SOURCE.open(encoding="utf-8",newline="") as f:
        candidates=[r for r in csv.DictReader(f) if r["vendor"]==MANUFACTURER and r["plasma_series"]==SERIES]
    req(len(candidates)==3 and tuple(sorted(r["part_number"] for r in candidates))==PATTERNS,"frozen KL25 pattern surface drifted")
    req(all(r["identifier_kind"]=="ordering_pattern" and r["target_config"]==TARGET and r["validation_status"]=="not_verified" for r in candidates),"canonical route candidate drifted")
    req(len({r["part_number"] for r in candidates})==3,"duplicate source pattern")

    production=load(PRODUCTION)
    req(production.get("status")=="production" and len(production.get("sources",[]))==23 and sum(int(s["row_count"]) for s in production["sources"])==2683,"Production count drifted")
    req(all(s["manufacturer"]!="NXP" for s in production["sources"]),"NXP was already published")

    return exact,identity_rows,candidates,authority

def build_rows()->list[dict[str,str]]:
    exact, evidence, candidates, authority=inputs()
    result=[]
    for sku in exact:
        m=EXACT_SKU_RE.fullmatch(sku)
        req(m is not None,f"{sku}: unexpected NXP exact order-code structure")
        size=m.group(2)
        pkg_code=m.group(3)
        flash=MEMORY_KIB[size]
        package,pins,official_pkg,ds_pkg=PACKAGE_CODES[pkg_code]
        matches=[row for row in candidates if pattern_matches(sku,row["part_number"])]
        req(len(matches)==1,f"{sku}: expected exactly one frozen ordering pattern, got {len(matches)}")
        candidate=matches[0]
        retained=evidence[sku]
        req(retained.get("pattern")==candidate["part_number"],f"{sku}: live route pattern differs from frozen canonical")
        req(retained.get("active") is True and retained.get("nonactive") is False,f"{sku}: not verified Active")
        req(retained.get("same_sku_table_row_count")==2 and retained.get("non_lifecycle_rows_seen")==1,f"{sku}: official table identity row cardinality drifted")
        excerpt=retained.get("visible_row_excerpt","")
        req(f"Package : {official_pkg}" in excerpt,f"{sku}: official live package differs from datasheet map")
        req(sku in excerpt and "Active" in excerpt,f"{sku}: same-row commercial evidence incomplete")
        req(authority["metadata_rules"]["suffix_to_package_and_pins"][pkg_code]=={
            "manufacturer_product_package":official_pkg,
            "datasheet_package":ds_pkg,
            "normalized_package":package,
            "pin_count":pins
        },f"{sku}: manufacturer package decode drifted")
        result.append({
           "manufacturer":MANUFACTURER,
           "icpn":sku,
           "family":FAMILY,
           "series":SERIES,
           "base_device":f"MKL25Z{size}",
           "package":package,
           "pin_count":pins,
           "flash_size":f"{flash} KiB",
           "temperature_grade":"-40..105 C",
           "option_suffix":"",
           "cmsis_device_name":"",
           "existing_identifier":candidate["part_number"],
           "existing_identifier_kind":"ordering_pattern",
           "mapping_status":"deterministic_ordering_pattern",
           "openocd_target_config":candidate["target_config"],
           "source_type":"official_nxp_datasheet_reference_manual_and_retained_current_active_listing",
           "source_reference":"KL25P80M48SF0 Rev 5 p2; KL25P80M48SF0RM Rev 3 Table 2-11 p44",
           "source_authority":"https://www.nxp.com/docs/en/data-sheet/KL25P80M48SF0.pdf",
           "verification_status":"verified_nxp_manufacturer_documents_and_retained_active_commercial_identity",
        })
    req(len(result)==EXPECTED_COUNT and len({r["icpn"] for r in result})==EXPECTED_COUNT,"canonical row cardinality drifted")
    req(Counter(r["existing_identifier"] for r in result)==Counter({p:4 for p in PATTERNS}),"canonical pattern count drifted")
    req(Counter(r["package"] for r in result)==Counter({"HVQFN":6,"LQFP":6}),"canonical package count drifted")
    req(Counter(r["pin_count"] for r in result)==Counter({"32":3,"48":3,"64":3,"80":3}),"canonical pin count drifted")
    req(Counter(r["flash_size"] for r in result)==Counter({"32 KiB":4,"64 KiB":4,"128 KiB":4}),"canonical flash count drifted")
    req({r["openocd_target_config"] for r in result}=={TARGET},"route target changed")
    req(all(r["cmsis_device_name"]=="" and r["mapping_status"]=="deterministic_ordering_pattern" for r in result),"CMSIS bridge or ambiguous route opened")
    return result

def canonical_csv(rows:list[dict[str,str]])->str:
    o=io.StringIO(newline="")
    w=csv.DictWriter(o,fieldnames=PRODUCTION_FIELDS,lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return o.getvalue()

def build_readiness(rows:list[dict[str,str]],csv_text:str)->dict[str,Any]:
    data=csv_text.encode("utf-8")
    return {
      "schema_version":1,
      "readiness_id":"nxp-kl25-bounded-exact-icpn-admission-readiness-v1",
      "scope":"research_only_catalog_admission_readiness",
      "authority":"research_only",
      "manufacturer":MANUFACTURER,
      "research_series":SERIES,
      "family":FAMILY,
      "production_exact_icpn_count":2683,
      "production_family_count":23,
      "frozen_exact_icpn_count":EXPECTED_COUNT,
      "frozen_exact_icpn_set_sha256":EXPECTED_EXACT_SHA,
      "excluded_non_active_part_number_count":0,
      "excluded_non_active_part_numbers":[],
      "identity_ready_count":EXPECTED_COUNT,
      "lifecycle_ready_count":EXPECTED_COUNT,
      "metadata_ready_count":EXPECTED_COUNT,
      "route_ready_count":EXPECTED_COUNT,
      "manual_review_count":0,
      "metadata_exception_count":0,
      "route_bridge_count":0,
      "route_assignment_kind_counts":{"ordering_pattern":EXPECTED_COUNT},
      "mapping_status_counts":{"deterministic_ordering_pattern":EXPECTED_COUNT},
      "target_config":TARGET,
      "flash_size_counts":dict(sorted(Counter(r["flash_size"] for r in rows).items())),
      "package_counts":dict(sorted(Counter(r["package"] for r in rows).items())),
      "pin_count_counts":dict(sorted(Counter(r["pin_count"] for r in rows).items())),
      "temperature_grade_counts":dict(sorted(Counter(r["temperature_grade"] for r in rows).items())),
      "metadata_authority":"nxp-kl25-metadata-authority.json",
      "canonical_candidate":"nxp-kl25-commercial-icpn.csv",
      "canonical_candidate_sha256":sha256(data),
      "canonical_candidate_git_blob_sha":blob_bytes(data),
      "catalog_admission_ready":True,
      "next_gate":"nxp-kl25-production-publication-gate",
      "claims":{
        "production_write_authorized":False,
        "production_publication_authorized":False,
        "software_executor_admission_implies_catalog_admission":False,
        "programming_algorithm_equivalence_claimed":False,
        "runtime_programming_support_claimed":False,
        "target_execution_authorized":False,
        "physical_validation_claimed":False,
        "security_mutation_authorized":False,
        "cmsis_bridge_authorizes_production_route":False,
      }
    }

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--csv-output",type=Path)
    p.add_argument("--readiness-output",type=Path)
    args=p.parse_args()
    rows=build_rows()
    candidate=canonical_csv(rows)
    readiness=json.dumps(build_readiness(rows,candidate),indent=2,sort_keys=True)+"\n"
    if args.csv_output:args.csv_output.write_text(candidate,encoding="utf-8")
    else:print(candidate,end="")
    if args.readiness_output:args.readiness_output.write_text(readiness,encoding="utf-8")
    else:print(readiness,end="")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
