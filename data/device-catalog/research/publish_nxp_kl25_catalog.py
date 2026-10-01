#!/usr/bin/env python3
"""Deterministically render NXP KL25 Production ICPN publication transaction.

Bounded Catalog identity/metadata only; never implies IC Support Software
Executor admission, physical programming or target execution.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
CANONICAL=HERE/"nxp-kl25-commercial-icpn.csv"
READINESS=HERE/"nxp-kl25-admission-readiness.json"

EXPECTED_PRESTATE_BLOB="c8012b211a28b0a7811bfe978e7e697bc169c6f3"
EXPECTED_READINESS_BLOB="b76e1e3f55e8fd3a68a4ccdf7bfd16a4ed71dc27"
EXPECTED_CSV_BLOB="53087e9082445e7948f88e688ecd890b0454d788"
EXPECTED_CSV_SHA256="73876af1a6344c298dd98559f2ea824362b8ce4935308e7b598d842d537bab95"
EXPECTED_SET_SHA="dd2c3cee83552a9875ee84c7bdea2cc6bc9c671f528b4bde02bed02b753755d5"
EXPECTED_EXACT=12

def req(ok:bool,msg:str)->None:
    if not ok:raise RuntimeError(msg)

def blob(data:bytes)->str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data,usedforsecurity=False).hexdigest()

def sha256(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def load(path:Path)->dict[str,Any]:
    obj=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(obj,dict),f"{path.name}: expected JSON object")
    return obj

def validate_inputs()->None:
    readiness_bytes=READINESS.read_bytes()
    req(blob(readiness_bytes)==EXPECTED_READINESS_BLOB,"frozen readiness blob drifted")
    ready=json.loads(readiness_bytes)
    req(ready.get("readiness_id")=="nxp-kl25-bounded-exact-icpn-admission-readiness-v1","readiness id drifted")
    req(ready.get("manufacturer")=="NXP" and ready.get("family")=="KL25","readiness identity drifted")
    req(ready.get("catalog_admission_ready") is True,"KL25 not catalog admission ready")
    req(ready.get("next_gate")=="nxp-kl25-production-publication-gate","publication gate drifted")
    req(ready.get("frozen_exact_icpn_count")==EXPECTED_EXACT and ready.get("frozen_exact_icpn_set_sha256")==EXPECTED_SET_SHA,"frozen exact set drifted")
    for field in ("identity_ready_count","lifecycle_ready_count","metadata_ready_count","route_ready_count"):
        req(ready.get(field)==EXPECTED_EXACT,f"{field} drifted")
    for field in ("manual_review_count","metadata_exception_count","route_bridge_count","excluded_non_active_part_number_count"):
        req(ready.get(field)==0,f"{field} reopened")
    req(ready.get("excluded_non_active_part_numbers")==[],"unexpected non-Active identities")
    req(ready.get("route_assignment_kind_counts")=={"ordering_pattern":12},"readiness route counts drifted")
    req(ready.get("mapping_status_counts")=={"deterministic_ordering_pattern":12},"readiness mapping drifted")
    req(ready.get("target_config")=="tcl/target/kl25.cfg","readiness target config drifted")
    req(ready.get("canonical_candidate_git_blob_sha")==EXPECTED_CSV_BLOB,"readiness canonical blob binding drifted")
    req(ready.get("canonical_candidate_sha256")==EXPECTED_CSV_SHA256,"readiness canonical SHA binding drifted")
    req(ready.get("claims") and all(v is False for v in ready["claims"].values()),"unsafe readiness claim escaped")

    b=CANONICAL.read_bytes()
    req(blob(b)==EXPECTED_CSV_BLOB and sha256(b)==EXPECTED_CSV_SHA256,"canonical CSV integrity drifted")
    rows=list(csv.DictReader(io.StringIO(b.decode("utf-8"))))
    req(len(rows)==EXPECTED_EXACT,"canonical exact row count drifted")
    icpns=[r["icpn"] for r in rows]
    req(icpns==sorted(set(icpns)),"canonical identities are not sorted unique")
    req(sha256(("\n".join(icpns)+"\n").encode("utf-8"))==EXPECTED_SET_SHA,"canonical exact-set identity digest drifted")
    req({r["base_device"] for r in rows}=={"MKL25Z32","MKL25Z64","MKL25Z128"},"canonical memory Base Devices drifted")
    req(all(r["manufacturer"]=="NXP" and r["family"]=="KL25"
            and r["series"]=="KL25"
            and r["mapping_status"]=="deterministic_ordering_pattern"
            and r["existing_identifier_kind"]=="ordering_pattern"
            and r["openocd_target_config"]=="tcl/target/kl25.cfg"
            and r["cmsis_device_name"]==""
            and r["verification_status"]=="verified_nxp_manufacturer_documents_and_retained_active_commercial_identity"
            for r in rows),"canonical source/route fields drifted")

def source_entry()->dict[str,Any]:
    return {
        "manufacturer":"NXP",
        "family":"KL25",
        "path":"../research/nxp-kl25-commercial-icpn.csv",
        "row_count":EXPECTED_EXACT,
        "git_blob_sha":EXPECTED_CSV_BLOB,
        "sha256":EXPECTED_CSV_SHA256,
    }

def counts(manifest:dict[str,Any])->tuple[int,int]:
    sources=manifest.get("sources")
    req(isinstance(sources,list),"manifest sources missing")
    return sum(int(s["row_count"]) for s in sources),len(sources)

def render()->tuple[dict[str,Any],dict[str,Any]]:
    validate_inputs()
    current=load(MANIFEST)
    sources=current.get("sources")
    req(isinstance(sources,list),"Production sources missing")
    existing=[s for s in sources if isinstance(s,dict) and s.get("manufacturer")=="NXP"]
    req(len(existing)<=1,"multiple NXP Production source entries")
    req(not existing or existing==[source_entry()],"unexpected NXP Production identity")
    pre={**current,"sources":[s for s in sources if s not in existing]}
    req(counts(pre)==(2683,23),"pre-publication count/family drifted")
    req({s["manufacturer"] for s in pre["sources"]}=={"STMicroelectronics"},"unexpected cross-vendor Production prestate")
    pre_bytes=(json.dumps(pre,indent=2,ensure_ascii=False)+"\n").encode("utf-8")
    req(blob(pre_bytes)==EXPECTED_PRESTATE_BLOB,"Production prestate manifest blob drifted")
    post={**pre,"sources":[*pre["sources"],source_entry()]}
    req(counts(post)==(2695,24),"proposed poststate count/family drifted")

    proposal={
        "schema_version":1,
        "transaction":"nxp-kl25-production-catalog-publication",
        "status":"publication_ready_pending_explicit_merge_approval",
        "manufacturer":"NXP",
        "research_series":"KL25",
        "family":"KL25",
        "readiness_baseline":"nxp-kl25-admission-readiness.json",
        "readiness_git_blob_sha":EXPECTED_READINESS_BLOB,
        "canonical_csv_git_blob_sha":EXPECTED_CSV_BLOB,
        "canonical_csv_sha256":EXPECTED_CSV_SHA256,
        "exact_icpn_set_sha256":EXPECTED_SET_SHA,
        "published_exact_icpns":EXPECTED_EXACT,
        "published_active_base_devices":3,
        "excluded_non_active_part_numbers":0,
        "marketing_status_observed":{"Active":12},
        "route_assignment_kind_counts":{"ordering_pattern":12},
        "mapping_status_counts":{"deterministic_ordering_pattern":12},
        "metadata_exception_count":0,
        "route_bridge_count":0,
        "production_exact_icpns_before":2683,
        "production_exact_icpns_after":2695,
        "production_family_count_before":23,
        "production_family_count_after":24,
        "production_manifest_git_blob_before":EXPECTED_PRESTATE_BLOB,
        "catalog_admission_policy":"icpn-catalog-admission-separation",
        "ppu_hil_required_for_catalog_admission":False,
        "socket_hil_required_for_catalog_admission":False,
        "physical_programming_success_required_for_catalog_admission":False,
        "physical_validation_claimed":False,
        "programming_algorithm_equivalence_claimed":False,
        "runtime_programming_support_claimed":False,
        "software_executor_admission_implies_catalog_admission":False,
        "security_mutation_support_claimed":False,
        "debug_attach_support_claimed":False,
        "catalog_membership_authorizes_target_execution":False,
        "cmsis_bridge_authorizes_production_route":False,
    }
    return post,proposal

def main()->int:
    post,proposal=render()
    print(json.dumps({"manifest":post,"proposal":proposal},indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
