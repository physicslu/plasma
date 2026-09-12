#!/usr/bin/env python3
"""STM32L0 L0.3 deterministic metadata-policy planner."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import CandidateManualReview, CandidateReject
from stm32l0_metadata_policy import FAMILY, METADATA_FIELDS, build_candidate_inputs, build_metadata_row, load_ordering_authority
from validate_stm32l0_phase_l0_2_retained_evidence import main as validate_retained

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PHASE = "L0.3"
ADMISSION_PHASE = "L0.4"
PRODUCTION = REPO / "data/device-catalog/production/icpn-v1-manifest.json"
EXPECTED_PRODUCTION_BLOB = "8abfcc870e51ac4232cdf8d807828cfe4ff5662d"
EXPECTED_PRODUCTION_COUNTS = {
    "STM32F0":42,"STM32F1":75,"STM32F2":33,"STM32F3":10,"STM32F4":384,
    "STM32F7":19,"STM32G0":47,"STM32G4":25,"STM32U0":68,"STM32C0":209,
}


def _git_blob(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode()+body).hexdigest()


def _set_sha(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values))+"\n").encode()).hexdigest()


def _rows_sha(rows: list[dict[str,str]]) -> str:
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def production_snapshot() -> dict[str,Any]:
    if _git_blob(PRODUCTION) != EXPECTED_PRODUCTION_BLOB:
        raise RuntimeError("L0.3 Production manifest byte identity drifted")
    payload=json.loads(PRODUCTION.read_text())
    counts={x["family"]:x["row_count"] for x in payload["sources"]}
    if counts != EXPECTED_PRODUCTION_COUNTS:
        raise RuntimeError(f"L0.3 Production family counts drifted: {counts}")
    bases=set()
    import csv
    for src in payload["sources"]:
        path=(PRODUCTION.parent/src["path"]).resolve()
        with path.open(newline="",encoding="utf-8") as f:
            rows=list(csv.DictReader(f))
        if len(rows)!=src["row_count"]:
            raise RuntimeError(f"{src['family']}: Production source count drifted")
        bases.update((src["family"],r["base_device"]) for r in rows)
    if sum(counts.values())!=912 or len(bases)!=293 or counts.get(FAMILY,0)!=0:
        raise RuntimeError("L0.3 Production aggregate prestate drifted")
    return {"exact_icpn_count":912,"base_device_count":293,"family_exact_icpn_counts":counts,"stm32l0_exact_icpn_count":0,"manifest_git_blob_sha":EXPECTED_PRODUCTION_BLOB}


def contract() -> dict[str,Any]:
    return {
        "identity_lifecycle_authority":"retained L0.2 official ST dual-surface exact-set evidence",
        "metadata_authority":"official ST datasheet Ordering Information",
        "canonical_admission_authorized":False,
        "production_write_authorized":False,
        "programming_policy_defined":False,
        "flash_geometry_qualified":False,
        "option_security_semantics_qualified":False,
        "physical_hil_qualified":False,
        "runtime_programming_support_claimed":False,
        "openocd_routing_gates_metadata":False,
        "cmsis_alias_gates_metadata":False,
        "scope_expansion_authorized":False,
        "admission_deferred_to":ADMISSION_PHASE,
    }


def build_plan() -> dict[str,Any]:
    if validate_retained()!=0:
        raise RuntimeError("L0.2 retained evidence validation failed")
    load_ordering_authority()
    items=[]; counts=Counter(); rows=[]
    for candidate in build_candidate_inputs():
        decision="metadata_ready"; issues=[]; row=None
        try:
            row=build_metadata_row(candidate,list(METADATA_FIELDS))
        except CandidateManualReview as exc:
            decision="manual_review_required"; issues=[str(exc)]
        except CandidateReject as exc:
            decision="reject"; issues=[str(exc)]
        counts[decision]+=1
        if row is not None: rows.append(row)
        items.append({"base_device":candidate["base_device"],"icpn":candidate["icpn"],"decision":decision,"issues":issues,"metadata":row})
    items.sort(key=lambda x:(x["base_device"],x["icpn"]))
    rows.sort(key=lambda x:(x["base_device"],x["icpn"]))
    dist={field:dict(sorted(Counter(r[field] for r in rows).items())) for field in ("flash_size","package","pin_count","temperature_grade","option_suffix","series")}
    ready=[x["icpn"] for x in items if x["decision"]=="metadata_ready"]
    manual=[x["icpn"] for x in items if x["decision"]=="manual_review_required"]
    rejected=[x["icpn"] for x in items if x["decision"]=="reject"]
    return {
        "schema_version":1,"phase":PHASE,"family":FAMILY,
        "candidate_count":len(items),"base_device_count":len({x["base_device"] for x in items}),
        "decision_counts":{"metadata_ready":counts["metadata_ready"],"manual_review_required":counts["manual_review_required"],"reject":counts["reject"]},
        "metadata_ready_set_sha256":_set_sha(ready),"manual_review_set_sha256":_set_sha(manual),"reject_set_sha256":_set_sha(rejected),
        "metadata_rows_sha256":_rows_sha(rows),"metadata_distribution":dist,
        "issues":sorted({i for x in items for i in x["issues"]}),
        "manual_review_base_devices":sorted({x["base_device"] for x in items if x["decision"]=="manual_review_required"}),
        "production_snapshot":production_snapshot(),"metadata_contract":contract(),
        "canonical_dataset_admission":"deferred","production_write_applied":False,
        "programming_algorithm_equivalence_claimed":False,"physical_hil_qualified":False,"runtime_support_claimed":False,
        "candidates":items,
    }


def plan_is_clean(plan: dict[str,Any]) -> bool:
    dc=plan.get("decision_counts",{})
    return (
        plan.get("candidate_count")==360 and plan.get("base_device_count")==99
        and dc.get("metadata_ready",0)+dc.get("manual_review_required",0)+dc.get("reject",0)==360
        and dc.get("reject",0)==0
        and plan.get("production_snapshot",{}).get("exact_icpn_count")==912
        and plan.get("production_snapshot",{}).get("base_device_count")==293
        and plan.get("production_snapshot",{}).get("stm32l0_exact_icpn_count")==0
        and plan.get("canonical_dataset_admission")=="deferred" and plan.get("production_write_applied") is False
        and set(plan.get("metadata_contract",{}).get(k) for k in ("canonical_admission_authorized","production_write_authorized","programming_policy_defined","flash_geometry_qualified","option_security_semantics_qualified","physical_hil_qualified","runtime_programming_support_claimed","scope_expansion_authorized"))=={False}
    )


def summary(plan: dict[str,Any]) -> dict[str,Any]:
    return {k:plan[k] for k in ("phase","family","candidate_count","base_device_count","decision_counts","metadata_ready_set_sha256","manual_review_set_sha256","reject_set_sha256","metadata_rows_sha256","metadata_distribution","issues","manual_review_base_devices","production_snapshot","metadata_contract")}


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--output"); p.add_argument("--summary-only",action="store_true"); a=p.parse_args()
    plan=build_plan(); out=summary(plan) if a.summary_only else plan
    text=json.dumps(out,indent=2,sort_keys=True)+"\n"
    if a.output: Path(a.output).write_text(text,encoding="utf-8")
    else: print(text,end="")
    return 0 if plan_is_clean(plan) else 1

if __name__=="__main__": raise SystemExit(main())
