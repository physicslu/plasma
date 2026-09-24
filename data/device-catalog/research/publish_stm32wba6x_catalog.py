#!/usr/bin/env python3
"""Render STM32WBA6X Production catalog publication."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION_MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
READINESS = HERE / "stm32wba6x-admission-readiness.json"
CANONICAL = HERE / "stm32wba6x-commercial-icpn.csv"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32WBA6X"
SERIES = "STM32WBA6X"

EXPECTED_ROWS = 39
EXPECTED_BASES = 18
EXPECTED_PRESTATE_EXACT = 2644
EXPECTED_POSTSTATE_EXACT = 2683
EXPECTED_PRESTATE_FAMILIES = 22
EXPECTED_POSTSTATE_FAMILIES = 23
EXPECTED_CANONICAL_SHA256 = "87e5bde7efc3fd3aee7397a80e9f4f972eb5ff42370b8d54cf1a333b3252004d"
EXPECTED_CANONICAL_GIT_BLOB_SHA = "0ab09918b2d845c0f21f10c5edb4a150d0c8c4f5"
EXPECTED_READINESS_GIT_BLOB_SHA = "d62d3756e90d9d130512722de3dd8f92a3f398e4"
EXPECTED_EXACT_SET_SHA256 = "b5acc2f981635fa0464456fae74365407492d3345ded9b7c9edf885ffdfeddac"
EXPECTED_PRESTATE_MANIFEST_GIT_BLOB_SHA = "5ddd901e6827a6c0a7f7fd2b0286c79411965777"

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def load_json(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value,dict),f"{path.name}: expected object")
    return value

def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data,usedforsecurity=False).hexdigest()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def set_sha(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values))+"\n").encode("utf-8")).hexdigest()

def validate_readiness() -> None:
    data=READINESS.read_bytes()
    req(git_blob(data)==EXPECTED_READINESS_GIT_BLOB_SHA,"readiness blob drifted")
    r=json.loads(data)
    req(r.get("readiness_id")=="stm32wba6x-bounded-exact-icpn-admission-readiness-v1","readiness id drifted")
    req(r.get("catalog_admission_ready") is True,"catalog admission is not ready")
    req(r.get("next_gate")=="stm32wba6x-production-publication-gate","publication gate drifted")
    req(r.get("frozen_exact_icpn_count")==EXPECTED_ROWS,"exact count drifted")
    req(r.get("frozen_exact_icpn_set_sha256")==EXPECTED_EXACT_SET_SHA256,"exact-set digest drifted")
    req(r.get("metadata_ready_count")==EXPECTED_ROWS,"metadata readiness drifted")
    req(r.get("route_ready_count")==EXPECTED_ROWS,"route readiness drifted")
    req(r.get("manual_review_count")==0,"manual review opened")
    req(r.get("metadata_exception_count")==0,"metadata exception opened")
    req(r.get("route_bridge_count")==0,"route bridge unexpectedly opened")
    req(r.get("route_assignment_kind_counts")=={"ordering_pattern":39},"route assignment drifted")
    req(r.get("mapping_status_counts")=={"deterministic_ordering_pattern":39},"mapping status drifted")
    req(r.get("canonical_candidate_sha256")==EXPECTED_CANONICAL_SHA256,"canonical SHA drifted")
    req(r.get("canonical_candidate_git_blob_sha")==EXPECTED_CANONICAL_GIT_BLOB_SHA,"canonical blob drifted")
    req(all(v is False for v in (r.get("claims") or {}).values()),"readiness fail-closed claim escaped")

def validate_canonical() -> bytes:
    data=CANONICAL.read_bytes()
    req(sha256(data)==EXPECTED_CANONICAL_SHA256,"canonical SHA-256 drifted")
    req(git_blob(data)==EXPECTED_CANONICAL_GIT_BLOB_SHA,"canonical Git blob drifted")
    rows=list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
    req(len(rows)==EXPECTED_ROWS,"canonical row count drifted")
    icpns=[row["icpn"] for row in rows]
    req(len(set(icpns))==EXPECTED_ROWS and set_sha(icpns)==EXPECTED_EXACT_SET_SHA256,"exact set drifted")
    req(len({row["base_device"] for row in rows})==EXPECTED_BASES,"Base Device count drifted")
    req({row["family"] for row in rows}=={FAMILY},"foreign family in canonical CSV")
    req({row["existing_identifier_kind"] for row in rows}=={"ordering_pattern"},"non-direct route entered canonical CSV")
    req({row["mapping_status"] for row in rows}=={"deterministic_ordering_pattern"},"mapping status drifted")
    req(all(row["cmsis_device_name"]=="" for row in rows),"CMSIS bridge unexpectedly opened")
    return data

def snapshot(manifest: dict[str,Any]) -> tuple[int,int]:
    sources=manifest.get("sources")
    req(isinstance(sources,list),"Production sources missing")
    return sum(int(s["row_count"]) for s in sources), len(sources)

def render() -> tuple[dict[str,Any],dict[str,Any]]:
    validate_readiness()
    validate_canonical()
    current=load_json(PRODUCTION_MANIFEST)
    sources=current.get("sources")
    req(isinstance(sources,list),"Production sources missing")
    existing=[s for s in sources if isinstance(s,dict) and s.get("family")==FAMILY]
    req(len(existing)<=1,"duplicate WBA6X Production source")
    pre={**current,"sources":[s for s in sources if not (isinstance(s,dict) and s.get("family")==FAMILY)]}
    pre_bytes=(json.dumps(pre,indent=2,ensure_ascii=False)+"\n").encode("utf-8")
    req(git_blob(pre_bytes)==EXPECTED_PRESTATE_MANIFEST_GIT_BLOB_SHA,"Production prestate blob drifted")
    req(snapshot(pre)==(EXPECTED_PRESTATE_EXACT,EXPECTED_PRESTATE_FAMILIES),"Production prestate counts drifted")

    source={
      "manufacturer":MANUFACTURER,
      "family":FAMILY,
      "path":"../research/stm32wba6x-commercial-icpn.csv",
      "row_count":EXPECTED_ROWS,
      "git_blob_sha":EXPECTED_CANONICAL_GIT_BLOB_SHA,
      "sha256":EXPECTED_CANONICAL_SHA256,
    }
    post={**pre,"sources":[*pre["sources"],source]}
    req(snapshot(post)==(EXPECTED_POSTSTATE_EXACT,EXPECTED_POSTSTATE_FAMILIES),"Production poststate counts drifted")
    if existing:
        req(existing[0]==source,"checked-in WBA6X source binding drifted")

    proposal={
      "schema_version":1,
      "transaction":"stm32wba6x-production-catalog-publication",
      "status":"publication_ready",
      "manufacturer":MANUFACTURER,
      "research_series":SERIES,
      "family":FAMILY,
      "readiness_baseline":"stm32wba6x-admission-readiness.json",
      "readiness_git_blob_sha":EXPECTED_READINESS_GIT_BLOB_SHA,
      "canonical_csv_git_blob_sha":EXPECTED_CANONICAL_GIT_BLOB_SHA,
      "canonical_csv_sha256":EXPECTED_CANONICAL_SHA256,
      "exact_icpn_set_sha256":EXPECTED_EXACT_SET_SHA256,
      "published_exact_icpns":EXPECTED_ROWS,
      "published_active_base_devices":EXPECTED_BASES,
      "excluded_non_active_part_numbers":2,
      "excluded_non_active_identities":["STM32WBA63CGU6TR","STM32WBA65MGF6"],
      "marketing_status_observed":{"Active":EXPECTED_ROWS,"Proposal":2},
      "route_assignment_kind_counts":{"ordering_pattern":39},
      "mapping_status_counts":{"deterministic_ordering_pattern":39},
      "metadata_exception_count":0,
      "route_bridge_count":0,
      "production_exact_icpns_before":EXPECTED_PRESTATE_EXACT,
      "production_exact_icpns_after":EXPECTED_POSTSTATE_EXACT,
      "production_family_count_before":EXPECTED_PRESTATE_FAMILIES,
      "production_family_count_after":EXPECTED_POSTSTATE_FAMILIES,
      "production_manifest_git_blob_before":EXPECTED_PRESTATE_MANIFEST_GIT_BLOB_SHA,
      "catalog_admission_policy":"icpn-catalog-admission-separation",
      "ppu_hil_required_for_catalog_admission":False,
      "socket_hil_required_for_catalog_admission":False,
      "physical_programming_success_required_for_catalog_admission":False,
      "physical_validation_claimed":False,
      "programming_algorithm_equivalence_claimed":False,
      "runtime_programming_support_claimed":False,
      "wireless_radio_operation_authorized":False,
      "wireless_security_operation_authorized":False,
      "security_mutation_support_claimed":False,
      "debug_attach_support_claimed":False,
      "catalog_membership_authorizes_target_execution":False,
      "remaining_wireless_families_rejected":False,
      "stm32w108_rejected":False,
      "cmsis_bridge_authorizes_production_route":False,
    }
    return post,proposal

def main() -> int:
    post,proposal=render()
    print(json.dumps({"manifest":post,"proposal":proposal},indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
