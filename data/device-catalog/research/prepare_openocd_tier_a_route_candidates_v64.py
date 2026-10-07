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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
COVERAGE_AUDIT = HERE / "openocd-active-coverage-classification-v6.3.json"

FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "current_mapping_status","candidate_openocd_target_config",
    "same_series_mapped_sibling_count","candidate_evidence_state",
    "existing_identifier_proposed","existing_identifier_kind_proposed",
    "programming_profile_state","production_write_authorized",
)

EXPECTED_FAMILY_COUNTS = {
    "STM32F2":72,
    "STM32F3":172,
    "STM32F4":3,
    "STM32F7":62,
    "STM32G0":42,
    "STM32G4":1,
    "STM32C0":17,
    "STM32L4":3,
    "STM32L1":2,
    "STM32U3":1,
    "STM32H7":14,
}

class CandidateError(RuntimeError):
    pass

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise CandidateError(msg)

def read_rows(path: Path) -> list[dict[str,str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))

def build() -> tuple[list[dict[str,str]], str, dict[str,Any]]:
    audit=json.loads(COVERAGE_AUDIT.read_text(encoding="utf-8"))
    req(audit["active_no_mapping_exact_count"]==956, "v6.3 no_mapping gap drift")
    req(audit["classification"]["tier_a_same_series_existing_route"]["count"]==389,
        "v6.3 Tier A count drift")

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest["sources"]
    req(len(sources)==28, "Production source count drift")
    req(sum(int(s["row_count"]) for s in sources)==4629, "Production total drift")

    all_rows=[]
    family_rows=defaultdict(list)
    for src in sources:
        path=(MANIFEST.parent/src["path"]).resolve()
        rows=read_rows(path)
        req(len(rows)==int(src["row_count"]), f"{src['family']}: row-count drift")
        all_rows.extend(rows)
        family_rows[src["family"]].extend(rows)

    mapped_by_series=defaultdict(list)
    configs_by_series=defaultdict(set)
    for r in all_rows:
        if r["mapping_status"]!="no_mapping":
            key=(r["family"],r["series"])
            mapped_by_series[key].append(r)
            req(r["openocd_target_config"], f"{r['icpn']}: mapped row missing target config")
            configs_by_series[key].add(r["openocd_target_config"])

    candidates=[]
    for r in all_rows:
        if r["mapping_status"]!="no_mapping":
            continue
        key=(r["family"],r["series"])
        if key not in mapped_by_series:
            continue
        configs=configs_by_series[key]
        req(len(configs)==1, f"{r['family']} {r['series']}: conflicting sibling target configs")
        target=next(iter(configs))
        candidates.append({
            "manufacturer":r["manufacturer"],
            "icpn":r["icpn"],
            "family":r["family"],
            "series":r["series"],
            "base_device":r["base_device"],
            "current_mapping_status":"no_mapping",
            "candidate_openocd_target_config":target,
            "same_series_mapped_sibling_count":str(len(mapped_by_series[key])),
            "candidate_evidence_state":"same_series_single_consistent_openocd_target_config",
            "existing_identifier_proposed":"",
            "existing_identifier_kind_proposed":"",
            "programming_profile_state":"unresolved",
            "production_write_authorized":"false",
        })

    candidates.sort(key=lambda r:r["icpn"])
    req(len(candidates)==389, f"Tier A candidate count drift: {len(candidates)}")
    req(len({r["icpn"] for r in candidates})==389, "Tier A candidate duplicate")
    family_counts=dict(sorted(Counter(r["family"] for r in candidates).items()))
    req(family_counts==dict(sorted(EXPECTED_FAMILY_COUNTS.items())),
        f"Tier A family distribution drift: {family_counts}")

    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(candidates)
    csv_text=buf.getvalue()
    exact_sha=hashlib.sha256(
        ("\n".join(r["icpn"] for r in candidates)+"\n").encode()
    ).hexdigest()
    csv_sha=hashlib.sha256(csv_text.encode()).hexdigest()
    target_counts=dict(sorted(Counter(
        r["candidate_openocd_target_config"] for r in candidates
    ).items()))

    summary={
        "schema_version":1,
        "proposal_id":"openocd-tier-a-route-candidates-v6.4",
        "record_state":"RESEARCH_ROUTE_CANDIDATES_NOT_PRODUCTION_MAPPING",
        "production_write_authorized":False,
        "candidate_exact_count":389,
        "candidate_exact_set_sha256":exact_sha,
        "candidate_csv_sha256":csv_sha,
        "family_counts":family_counts,
        "target_config_counts":target_counts,
        "evidence_rule":
            "same family+series has one or more mapped siblings and all such siblings use exactly one identical OpenOCD target config",
        "identifier_synthesis_performed":False,
        "existing_identifier_binding_claimed":False,
        "programming_profile_binding_claimed":False,
        "programming_verified_claimed":False,
        "engineering_verified_claimed":False,
        "hil_verified_claimed":False,
        "current_active_openocd_route_exact_count":3594,
        "projected_route_exact_count_if_all_qualified":3983,
        "scoped_active_denominator":4550,
        "projected_route_coverage_percent_if_all_qualified":87.5385,
        "projected_remaining_gap_if_all_qualified":567,
    }
    return candidates,csv_text,summary

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--proposal",type=Path)
    parser.add_argument("--summary",type=Path)
    args=parser.parse_args()
    _,csv_text,summary=build()
    if args.proposal:
        args.proposal.write_text(csv_text,encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_TIER_A_ROUTE_CANDIDATES_V64_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
