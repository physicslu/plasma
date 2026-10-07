#!/usr/bin/env python3
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

import prepare_openocd_tier_a_route_candidates_v64 as v64

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "openocd-parts-canonical.csv"

EXPECTED_CATALOG_GIT_BLOB_SHA = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_QUALIFIED = 320
EXPECTED_BLOCKED = 69
EXPECTED_AMBIGUOUS = 0

PREFIX_MATCH_FAMILIES = {"STM32C0", "STM32L4", "STM32L1"}
MULTI_KIND_FAMILIES = {"STM32U3", "STM32H7"}

EXPECTED_QUALIFIED_FAMILY_COUNTS = {
    "STM32C0": 1,
    "STM32F2": 72,
    "STM32F3": 168,
    "STM32F7": 62,
    "STM32H7": 14,
    "STM32L1": 1,
    "STM32L4": 1,
    "STM32U3": 1,
}
EXPECTED_BLOCKED_FAMILY_COUNTS = {
    "STM32C0": 16,
    "STM32F3": 4,
    "STM32F4": 3,
    "STM32G0": 42,
    "STM32G4": 1,
    "STM32L1": 1,
    "STM32L4": 2,
}
EXPECTED_KIND_COUNTS = {"ordering_pattern": 307, "cmsis_device_name": 13}

QUALIFIED_FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "candidate_openocd_target_config","resolved_existing_identifier",
    "resolved_existing_identifier_kind","resolution_state",
    "openocd_distribution","route_validation_status",
    "programming_profile_state","programming_verified",
    "engineering_verified","hil_verified","production_write_authorized",
)

BLOCKED_FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "candidate_openocd_target_config","blocked_reason","match_count",
    "programming_profile_state","production_write_authorized",
)

class QualificationError(RuntimeError):
    pass

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise QualificationError(msg)

def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(raw)}\0".encode("ascii") + raw,
        usedforsecurity=False,
    ).hexdigest()

def pattern_matches(pattern: str, value: str) -> bool:
    expr = "".join("[A-Z0-9]" if c == "x" else re.escape(c) for c in pattern)
    return re.fullmatch(expr, value) is not None

def commercial_core(row: dict[str,str]) -> str:
    icpn=row["icpn"]
    core=icpn
    for suffix in ("TR","TT"):
        if core.endswith(suffix):
            core=core[:-len(suffix)]
            break

    # Preserve exactly the existing STM32F4 admission-policy normalization.
    if row["family"]=="STM32F4":
        if core.startswith("STM32F412") and core.endswith("P"):
            core=core[:-1]
        if core=="STM32F423ZHJ6I":
            core=core[:-1]
        if core=="STM32F446MEY6M":
            core=core[:-1]
    return core

def read_routes() -> list[dict[str,str]]:
    raw=CATALOG.read_bytes()
    req(git_blob_sha(raw)==EXPECTED_CATALOG_GIT_BLOB_SHA,
        "OpenOCD canonical route inventory Git blob drift")
    with io.StringIO(raw.decode("utf-8")) as stream:
        rows=list(csv.DictReader(stream))
    rows=[
        r for r in rows
        if r.get("vendor")=="STMicroelectronics"
        and r.get("openocd_distribution")=="upstream-openocd"
        and r.get("mapping_status")=="mapping_candidate"
        and r.get("validation_status")=="not_verified"
    ]
    req(rows, "ST upstream OpenOCD route inventory unexpectedly empty")
    return rows

def allowed_kinds(family: str) -> set[str]:
    if family in MULTI_KIND_FAMILIES:
        return {"ordering_pattern","cmsis_device_name"}
    return {"ordering_pattern"}

def resolve(candidate: dict[str,str], routes: list[dict[str,str]]) -> list[dict[str,str]]:
    family=candidate["family"]
    core=commercial_core(candidate)
    kinds=allowed_kinds(family)
    target=candidate["candidate_openocd_target_config"]
    pool=[
        r for r in routes
        if r.get("plasma_series")==family
        and r.get("identifier_kind") in kinds
        and r.get("target_config")==target
    ]
    if family in PREFIX_MATCH_FAMILIES:
        return [
            r for r in pool
            if r["part_number"].endswith("x")
            and core.startswith(r["part_number"][:-1])
        ]
    return [r for r in pool if pattern_matches(r["part_number"], core)]

def render_csv(fields: tuple[str,...], rows: list[dict[str,str]]) -> str:
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=fields,lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()

def build() -> tuple[list[dict[str,str]],list[dict[str,str]],str,str,dict[str,Any]]:
    tier_a,_,v64_summary=v64.build()
    req(len(tier_a)==389, "v6.4 Tier A candidate count drift")
    req(v64_summary["candidate_exact_count"]==389, "v6.4 summary drift")

    routes=read_routes()
    qualified=[]
    blocked=[]
    ambiguous=0

    for candidate in tier_a:
        matches=resolve(candidate,routes)
        unique={
            (r["part_number"],r["identifier_kind"],r["target_config"]):r
            for r in matches
        }
        matches=list(unique.values())

        if len(matches)==1:
            route=matches[0]
            qualified.append({
                "manufacturer":candidate["manufacturer"],
                "icpn":candidate["icpn"],
                "family":candidate["family"],
                "series":candidate["series"],
                "base_device":candidate["base_device"],
                "candidate_openocd_target_config":candidate["candidate_openocd_target_config"],
                "resolved_existing_identifier":route["part_number"],
                "resolved_existing_identifier_kind":route["identifier_kind"],
                "resolution_state":"unique_policy_compatible_openocd_route",
                "openocd_distribution":route["openocd_distribution"],
                "route_validation_status":route["validation_status"],
                "programming_profile_state":"unresolved",
                "programming_verified":"false",
                "engineering_verified":"false",
                "hil_verified":"false",
                "production_write_authorized":"false",
            })
        else:
            if len(matches)>1:
                ambiguous += 1
                reason="ambiguous_policy_compatible_openocd_route"
            else:
                reason="no_policy_compatible_openocd_identifier"
            blocked.append({
                "manufacturer":candidate["manufacturer"],
                "icpn":candidate["icpn"],
                "family":candidate["family"],
                "series":candidate["series"],
                "base_device":candidate["base_device"],
                "candidate_openocd_target_config":candidate["candidate_openocd_target_config"],
                "blocked_reason":reason,
                "match_count":str(len(matches)),
                "programming_profile_state":"unresolved",
                "production_write_authorized":"false",
            })

    qualified.sort(key=lambda r:r["icpn"])
    blocked.sort(key=lambda r:r["icpn"])
    req(len(qualified)==EXPECTED_QUALIFIED, f"qualified count drift: {len(qualified)}")
    req(len(blocked)==EXPECTED_BLOCKED, f"blocked count drift: {len(blocked)}")
    req(ambiguous==EXPECTED_AMBIGUOUS, f"ambiguous count drift: {ambiguous}")

    qfam=dict(sorted(Counter(r["family"] for r in qualified).items()))
    bfam=dict(sorted(Counter(r["family"] for r in blocked).items()))
    kinds=dict(sorted(Counter(r["resolved_existing_identifier_kind"] for r in qualified).items()))
    req(qfam==dict(sorted(EXPECTED_QUALIFIED_FAMILY_COUNTS.items())),
        f"qualified family partition drift: {qfam}")
    req(bfam==dict(sorted(EXPECTED_BLOCKED_FAMILY_COUNTS.items())),
        f"blocked family partition drift: {bfam}")
    req(kinds==dict(sorted(EXPECTED_KIND_COUNTS.items())),
        f"identifier-kind partition drift: {kinds}")

    qcsv=render_csv(QUALIFIED_FIELDS,qualified)
    bcsv=render_csv(BLOCKED_FIELDS,blocked)
    qset_sha=hashlib.sha256(
        ("\n".join(r["icpn"] for r in qualified)+"\n").encode()
    ).hexdigest()
    bset_sha=hashlib.sha256(
        ("\n".join(r["icpn"] for r in blocked)+"\n").encode()
    ).hexdigest()

    summary={
        "schema_version":1,
        "qualification_id":"openocd-tier-a-identifier-qualification-v6.5",
        "record_state":"RESEARCH_ONLY_NOT_PRODUCTION_MAPPING",
        "input_tier_a_exact_count":389,
        "identifier_qualified_exact_count":len(qualified),
        "identifier_blocked_exact_count":len(blocked),
        "identifier_ambiguous_exact_count":ambiguous,
        "qualified_exact_set_sha256":qset_sha,
        "blocked_exact_set_sha256":bset_sha,
        "qualified_csv_sha256":hashlib.sha256(qcsv.encode()).hexdigest(),
        "blocked_csv_sha256":hashlib.sha256(bcsv.encode()).hexdigest(),
        "qualified_family_counts":qfam,
        "blocked_family_counts":bfam,
        "resolved_identifier_kind_counts":kinds,
        "route_inventory_git_blob_sha":EXPECTED_CATALOG_GIT_BLOB_SHA,
        "route_inventory_semantics":
            "upstream OpenOCD mapping candidates with validation_status=not_verified",
        "current_active_openocd_route_exact_count":3594,
        "projected_route_exact_count_if_qualified_set_later_promoted":3914,
        "scoped_active_denominator":4550,
        "projected_route_coverage_percent_if_qualified_set_later_promoted":86.0220,
        "projected_remaining_gap_if_qualified_set_later_promoted":636,
        "claims":{
            "production_write_authorized":False,
            "backend_mapping_promoted":False,
            "programming_profile_binding_claimed":False,
            "programming_verified_claimed":False,
            "engineering_verified_claimed":False,
            "hil_verified_claimed":False,
        }
    }
    return qualified,blocked,qcsv,bcsv,summary

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--qualified",type=Path)
    p.add_argument("--blocked",type=Path)
    p.add_argument("--summary",type=Path)
    args=p.parse_args()
    _,_,qcsv,bcsv,summary=build()
    if args.qualified:
        args.qualified.write_text(qcsv,encoding="utf-8")
    if args.blocked:
        args.blocked.write_text(bcsv,encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_TIER_A_IDENTIFIER_QUALIFICATION_V65_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
