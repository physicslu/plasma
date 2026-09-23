#!/usr/bin/env python3
"""Fail-closed validator for retained STM32WBA6X exact ICPN discovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wba6x_exact_icpn_discovery import (
    DISCOVERY_ID, EXPECTED_BASE_DEVICE_COUNT, EXPECTED_BASES,
    EXPECTED_SUBFAMILIES, EXPECTED_TARGET_CONFIG, EXPECTED_SERIES,
    deterministic_targets, target_manifest,
)

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EVIDENCE=HERE/"evidence"/"stm32wba6x-exact-icpn-live-2026-09-23"
TARGETS=EVIDENCE/"targets.json"
SUMMARY=EVIDENCE/"discovery-summary.json"
EXACT=EVIDENCE/"exact-icpns.json"
PROVENANCE=EVIDENCE/"provenance.json"
PRODUCTION=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_COUNT=39
EXPECTED_EXCLUDED=["STM32WBA63CGU6TR","STM32WBA65MGF6"]
EXPECTED_SHA256="b5acc2f981635fa0464456fae74365407492d3345ded9b7c9edf885ffdfeddac"
EXPECTED_NEXT="stm32wba6x-bounded-exact-icpn-admission-readiness-gate"
EXPECTED_RUN_ID=35834958903
EXPECTED_EXECUTED_SHA="c3f3caff0db656b130e8e42b283779af04f879a6"
EXPECTED_BROWSER="151.0.7922.34"
EXPECTED_PRODUCTION_COUNT=2644
EXPECTED_PRODUCTION_FAMILIES=22
EXPECTED_ACTIVE_COUNTS={
 "STM32WBA62CG":1,"STM32WBA62CI":2,"STM32WBA62MG":1,"STM32WBA62MI":1,"STM32WBA62PG":2,"STM32WBA62PI":2,
 "STM32WBA63CG":2,"STM32WBA63CI":3,
 "STM32WBA64CG":2,"STM32WBA64CI":2,
 "STM32WBA65CG":2,"STM32WBA65CI":2,"STM32WBA65MG":2,"STM32WBA65MI":2,"STM32WBA65PG":2,"STM32WBA65PI":4,"STM32WBA65RG":3,"STM32WBA65RI":4,
}
EXPECTED_EXCLUDED_BY_BASE={"STM32WBA63CG":["STM32WBA63CGU6TR"],"STM32WBA65MG":["STM32WBA65MGF6"]}

def req(ok:bool,msg:str)->None:
    if not ok: raise SystemExit(msg)

def load(path:Path)->dict[str,Any]:
    req(path.is_file(),f"missing retained file: {path}")
    value=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value,dict),f"{path.name}: expected object")
    return value

def main()->int:
    targets,summary,exact_obj,prov,production=map(load,(TARGETS,SUMMARY,EXACT,PROVENANCE,PRODUCTION))
    req(targets==target_manifest(deterministic_targets()),"retained target manifest is not deterministic replay")
    req(targets.get("discovery_id")==DISCOVERY_ID,"target discovery id drifted")
    req(targets.get("base_device_count")==18,"target Base Device count drifted")
    mt=targets.get("targets")
    req(isinstance(mt,list) and tuple(x.get("base_device") for x in mt)==EXPECTED_BASES,"target Base Device order drifted")
    req({x.get("subfamily") for x in mt}==set(EXPECTED_SUBFAMILIES),"target subfamily coverage drifted")

    req(summary.get("discovery_id")==DISCOVERY_ID,"summary discovery id drifted")
    req(summary.get("selected_wireless_frontier")==EXPECTED_SERIES,"summary frontier drifted")
    req(summary.get("target_config")==EXPECTED_TARGET_CONFIG,"summary target config drifted")
    req(summary.get("base_device_count")==EXPECTED_BASE_DEVICE_COUNT==18,"summary base count drifted")
    req(summary.get("attempted_targets")==18 and summary.get("successful_targets")==18,"discovery coverage drifted")
    req(summary.get("manual_review_targets")==0,"manual review opened")
    req(summary.get("active_exact_icpn_count")==EXPECTED_COUNT,"Active exact count drifted")
    req(summary.get("excluded_non_active_part_number_count")==2,"lifecycle exclusion count drifted")
    req(summary.get("excluded_non_active_part_numbers")==EXPECTED_EXCLUDED,"lifecycle exclusion identities drifted")
    req(summary.get("active_exact_icpn_set_sha256")==EXPECTED_SHA256,"exact-set digest drifted")
    req(summary.get("bounded_exact_discovery_complete") is True,"bounded discovery incomplete")
    req(summary.get("status")=="discovered","discovery status drifted")
    req(summary.get("next_gate")==EXPECTED_NEXT,"next gate drifted")
    req(summary.get("browser_version")==EXPECTED_BROWSER,"browser version drifted")

    claims=summary.get("claims")
    req(isinstance(claims,dict),"claims missing")
    req(claims.get("exact_icpn_discovery_completed") is True,"completion claim missing")
    req(all(v is False for k,v in claims.items() if k!="exact_icpn_discovery_completed"),"unsafe claim escaped")

    exact=summary.get("active_exact_icpns")
    req(isinstance(exact,list) and len(exact)==EXPECTED_COUNT,"exact set malformed")
    req(exact==sorted(set(exact)),"exact set not sorted unique")
    req(hashlib.sha256(("\n".join(exact)+"\n").encode()).hexdigest()==EXPECTED_SHA256,"exact digest recompute failed")
    req(exact_obj.get("exact_icpn_count")==EXPECTED_COUNT and exact_obj.get("exact_icpn_set_sha256")==EXPECTED_SHA256,"exact snapshot drifted")
    req(exact_obj.get("exact_icpns")==exact,"exact snapshot differs from summary")

    results=summary.get("results")
    req(isinstance(results,list) and len(results)==18,"result count drifted")
    req([x.get("base_device") for x in results]==list(EXPECTED_BASES),"result Base Device order drifted")
    active_owner={}
    excluded_owner={}
    for item in results:
        base=item.get("base_device")
        req(base in EXPECTED_ACTIVE_COUNTS,f"unexpected Base Device {base}")
        req(item.get("acquisition_status")=="success",f"{base}: acquisition failure")
        req(item.get("manual_intervention_required") is False,f"{base}: manual review")
        evidence=item.get("evidence")
        req(isinstance(evidence,dict),f"{base}: evidence missing")
        req(evidence.get("acquisition_transport")==BROWSER_TRANSPORT,f"{base}: transport drifted")
        active=evidence.get("exact_icpns")
        excluded=evidence.get("excluded_non_active_part_numbers")
        req(isinstance(active,list) and len(active)==EXPECTED_ACTIVE_COUNTS[base],f"{base}: Active count drifted")
        req(isinstance(excluded,list),f"{base}: exclusion list missing")
        expected_ex=EXPECTED_EXCLUDED_BY_BASE.get(base,[])
        req([x.get("icpn") for x in excluded]==expected_ex,f"{base}: exclusion identities drifted")
        req(all(str(x.get("marketing_status","")).startswith("Proposal") for x in excluded),f"{base}: exclusion no longer Proposal")
        req(item.get("active_exact_icpns")==active,f"{base}: summary/evidence Active mismatch")
        req(item.get("excluded_non_active_icpns")==expected_ex,f"{base}: summary/evidence exclusion mismatch")
        req(load(EVIDENCE/f"{base.lower()}.json")==evidence,f"{base}: standalone evidence mismatch")
        for icpn in active:
            req(icpn not in active_owner,f"{icpn}: duplicate Active")
            active_owner[icpn]=base
        for icpn in expected_ex:
            req(icpn not in excluded_owner,f"{icpn}: duplicate excluded")
            excluded_owner[icpn]=base
    req(sorted(active_owner)==exact,"per-Base Active set differs from summary")
    req(sorted(excluded_owner)==EXPECTED_EXCLUDED,"per-Base excluded set differs from summary")

    req(prov.get("discovery_id")==DISCOVERY_ID,"provenance discovery id drifted")
    req(prov.get("workflow_run_id")==EXPECTED_RUN_ID,"workflow run drifted")
    req(prov.get("workflow_run_attempt")==1,"workflow attempt drifted")
    req(prov.get("executed_git_sha")==EXPECTED_EXECUTED_SHA,"executed SHA drifted")
    req(prov.get("browser_version")==EXPECTED_BROWSER,"provenance browser drifted")
    req(prov.get("acquisition_transport")==BROWSER_TRANSPORT,"provenance transport drifted")
    req(prov.get("candidate_source_sha256")==targets.get("candidate_source_sha256"),"source digest mismatch")
    req(prov.get("selection_sha256")==targets.get("selection_sha256"),"selection digest mismatch")
    req(prov.get("commercial_scope_reconciliation_sha256")==targets.get("commercial_scope_reconciliation_sha256"),"reconciliation digest mismatch")

    sources=production.get("sources")
    req(isinstance(sources,list),"Production sources missing")
    req(sum(int(x.get("row_count",0)) for x in sources)==EXPECTED_PRODUCTION_COUNT,"Production exact count changed")
    req(len(sources)==EXPECTED_PRODUCTION_FAMILIES,"Production family count changed")
    req(all(x.get("family")!="STM32WBA6X" for x in sources),"STM32WBA6X leaked into Production")

    print("STM32WBA6X exact ICPN discovery validation: PASS")
    print("bases=18 active=39 excluded=2 manual=0 next=admission-readiness")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
