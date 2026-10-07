#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import qualify_openocd_tier_a_identifiers_v65 as v65

HERE = Path(__file__).resolve().parent
MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"

FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "candidate_openocd_target_config","option_suffix",
    "normalization_probe_state","normalized_core",
    "resolved_identifier_kind","resolved_existing_identifier",
    "match_count","programming_profile_state","production_write_authorized",
)

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def production_index() -> dict[str,dict[str,str]]:
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    out={}
    for src in manifest["sources"]:
        path=(MANIFEST.parent/src["path"]).resolve()
        with path.open(newline="",encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                out[row["icpn"]]=row
    return out

def resolve_normalized(
    candidate: dict[str,str],
    normalized_core: str,
    routes: list[dict[str,str]],
) -> list[dict[str,str]]:
    family=candidate["family"]
    target=candidate["candidate_openocd_target_config"]
    kinds=v65.allowed_kinds(family)
    pool=[
        r for r in routes
        if r.get("plasma_series")==family
        and r.get("identifier_kind") in kinds
        and r.get("target_config")==target
    ]
    if family in v65.PREFIX_MATCH_FAMILIES:
        matches=[
            r for r in pool
            if r["part_number"].endswith("x")
            and normalized_core.startswith(r["part_number"][:-1])
        ]
    else:
        matches=[r for r in pool if v65.pattern_matches(r["part_number"],normalized_core)]
    unique={
        (r["part_number"],r["identifier_kind"],r["target_config"]):r
        for r in matches
    }
    return list(unique.values())

def build() -> tuple[list[dict[str,str]],str,dict[str,Any]]:
    _,blocked,_,_,v65_summary=v65.build()
    req(len(blocked)==69, "v6.5 blocked cardinality drift")
    routes=v65.read_routes()
    prod=production_index()

    rows=[]
    states=Counter()
    family_states=defaultdict(Counter)
    suffix_states=defaultdict(Counter)

    for b in blocked:
        p=prod[b["icpn"]]
        suffix=p.get("option_suffix","")
        icpn=b["icpn"]

        if not suffix:
            state="not_applicable_empty_suffix"
            normalized=""
            matches=[]
        elif not icpn.endswith(suffix):
            state="invalid_catalog_suffix_binding"
            normalized=""
            matches=[]
        else:
            normalized=icpn[:-len(suffix)]
            matches=resolve_normalized(b,normalized,routes)
            if len(matches)==1:
                state="unique_after_catalog_suffix_removal"
            elif len(matches)==0:
                state="still_unmapped_after_catalog_suffix_removal"
            else:
                state="ambiguous_after_catalog_suffix_removal"

        states[state]+=1
        family_states[b["family"]][state]+=1
        suffix_states[suffix][state]+=1

        if len(matches)==1:
            route=matches[0]
            kind=route["identifier_kind"]
            ident=route["part_number"]
        else:
            kind=ident=""

        rows.append({
            "manufacturer":b["manufacturer"],
            "icpn":icpn,
            "family":b["family"],
            "series":b["series"],
            "base_device":b["base_device"],
            "candidate_openocd_target_config":b["candidate_openocd_target_config"],
            "option_suffix":suffix,
            "normalization_probe_state":state,
            "normalized_core":normalized,
            "resolved_identifier_kind":kind,
            "resolved_existing_identifier":ident,
            "match_count":str(len(matches)),
            "programming_profile_state":"unresolved",
            "production_write_authorized":"false",
        })

    rows.sort(key=lambda r:r["icpn"])
    req(len(rows)==69, "normalization probe cardinality drift")
    req(sum(states.values())==69, "normalization state partition drift")

    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    csv_text=buf.getvalue()

    unique=states["unique_after_catalog_suffix_removal"]
    summary={
        "schema_version":1,
        "probe_id":"openocd-tier-a-suffix-normalization-v6.7",
        "record_state":"RESEARCH_ONLY_NOT_MAPPING_POLICY",
        "input_blocked_exact_count":69,
        "blocked_exact_set_sha256":v65_summary["blocked_exact_set_sha256"],
        "probe_csv_sha256":hashlib.sha256(csv_text.encode()).hexdigest(),
        "probe_state_counts":dict(sorted(states.items())),
        "family_probe_state_counts":{
            fam:dict(sorted(cnt.items()))
            for fam,cnt in sorted(family_states.items())
        },
        "suffix_probe_state_counts":{
            suffix:dict(sorted(cnt.items()))
            for suffix,cnt in sorted(suffix_states.items())
        },
        "unique_after_catalog_suffix_removal_exact_count":unique,
        "potential_identifier_qualified_total_if_semantics_later_authorized":
            320+unique,
        "potential_active_openocd_route_exact_count_if_later_promoted":
            3594+320+unique,
        "scoped_active_denominator":4550,
        "potential_coverage_percent_if_later_promoted":round((3594+320+unique)/4550*100,4),
        "claims":{
            "suffix_removal_policy_authorized":False,
            "identifier_promoted":False,
            "production_write_authorized":False,
            "programming_profile_binding_claimed":False,
            "programming_verified_claimed":False,
            "engineering_verified_claimed":False,
            "hil_verified_claimed":False,
        }
    }
    return rows,csv_text,summary

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--probe",type=Path)
    p.add_argument("--summary",type=Path)
    args=p.parse_args()
    _,csv_text,summary=build()
    if args.probe:
        args.probe.write_text(csv_text,encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_TIER_A_SUFFIX_NORMALIZATION_V67_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
