#!/usr/bin/env python3
"""Recover exactly the 15 STM32L4 L4.2 targets that timed out in run 34713341677."""
from __future__ import annotations
import argparse, hashlib, json, os, time
from collections import Counter
from pathlib import Path

from st_browser_acquisition import BROWSER_TRANSPORT
from st_dual_surface_browser_acquisition import STDualSurfaceBrowserAcquirer
from st_product_page_acquisition import AcquisitionError
from stm32l4_phase_l4_2_discovery import (
    AUTHORITY_SURFACE, COMMERCIAL_IDENTITY_AUTHORITY, DEFAULT_CATALOG,
    EXPECTED_L4_1_REPRESENTATIVES, FAMILY, PARSER_PROFILE, PHASE,
    RateLimitedFetcher, _excluded_ids, _routing_status,
    build_discovery_evidence_record, deterministic_targets, read_catalog,
    resolve_mapping, target_manifest, validate_targets,
)

INITIAL_RUN_ID=34713341677
INITIAL_ARTIFACT_ID=10304163363
INITIAL_EXEC_SHA="8d45ed34bd1029055ba9a6fd035f23ea4f4ebb6f"
INITIAL_ARTIFACT_SHA256="e04253546cfba83209bf0b55f8fe46de4b5e14110bbc1bb5b95aefcb46d984a4"
INITIAL_TIMEOUT=75.0
TIMEOUT_ERROR="STM32L4 L4.2 commercial discovery per-device global acquisition deadline exceeded"
RETRY=("STM32L412CB","STM32L412RB","STM32L412T8","STM32L451VC","STM32L471QG",
       "STM32L471VG","STM32L475RE","STM32L496QG","STM32L496VE","STM32L4P5ZE",
       "STM32L4Q5CG","STM32L4Q5RG","STM32L4R9VG","STM32L4S5ZI","STM32L4S9ZI")


def jbytes(v): return (json.dumps(v,indent=2,sort_keys=True)+"\n").encode()
def readj(p):
    v=json.loads(Path(p).read_text())
    if not isinstance(v,dict): raise AcquisitionError(f"{p}: expected object")
    return v
def fsha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def setsha(v): return hashlib.sha256("".join(x+"\n" for x in sorted(v)).encode()).hexdigest()


def validate_source(root:Path, targets):
    s=readj(root/"live-summary.json"); t=readj(root/"targets.json")
    if jbytes(t)!=jbytes(target_manifest(targets)): raise AcquisitionError("source target manifest drift")
    if (s.get("phase"),s.get("family"),s.get("base_device_count"),s.get("attempted"))!=(PHASE,FAMILY,138,138):
        raise AcquisitionError("source identity/count drift")
    b=s.get("browser",{})
    if b.get("headless") is not False or b.get("evidence_profile")!=PARSER_PROFILE or b.get("reuse_browser") is not True or b.get("per_device_global_deadline") is not True or b.get("per_device_timeout_seconds")!=75.0:
        raise AcquisitionError("source bounded-browser policy drift")
    if any(v is not False for v in s.get("claims",{}).values()): raise AcquisitionError("source claims escaped fail-closed")
    rows=s.get("results")
    if not isinstance(rows,list) or len(rows)!=138: raise AcquisitionError("source result count drift")
    by={}; failed=[]; ok=[]
    for r in rows:
        base=r.get("base_device") if isinstance(r,dict) else None
        if not isinstance(base,str) or base in by: raise AcquisitionError("source duplicate/invalid result")
        by[base]=r
        if r.get("acquisition_status")=="success": ok.append(base)
        else:
            failed.append(base)
            if r.get("error_type")!="AcquisitionError" or r.get("error")!=TIMEOUT_ERROR or r.get("manual_intervention_required") is not True:
                raise AcquisitionError(f"{base}: source failure is not approved timeout")
    if set(failed)!=set(RETRY) or len(ok)!=123: raise AcquisitionError("source must be exactly 123 success + fixed 15 timeout")
    if (s.get("commercial_identity_verified_targets"),s.get("identity_manual_intervention_required"),s.get("acquisition_failure"))!=(123,15,15):
        raise AcquisitionError("source timeout metrics drift")
    leaves=list((root/"evidence").glob("*.json"))
    if len(leaves)!=123 or {p.stem.upper() for p in leaves}!=set(ok): raise AcquisitionError("source leaf set drift")
    for p in leaves:
        if jbytes(readj(p))!=jbytes(by[p.stem.upper()]): raise AcquisitionError(f"{p.stem}: source leaf mismatch")
    return s,by


def acquire(target,fetcher,timeout,rows):
    r={"subfamily":target.subfamily,"base_device":target.base_device,"source_url":target.source_url,"selection_reason":target.selection_reason}
    try:
        body,final,etag,lm=fetcher(target.source_url,timeout)
        ev=build_discovery_evidence_record(body=body,source_url=target.source_url,final_url=final,base_device=target.base_device,
            retrieved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),http_etag=etag,http_last_modified=lm)
        active=ev.get("exact_icpns"); excluded=_excluded_ids(ev.get("excluded_non_active_part_numbers"),target.base_device)
        if ev.get("evidence_surface")!=AUTHORITY_SURFACE or not isinstance(active,list) or not all(isinstance(x,str) for x in active):
            raise AcquisitionError(f"{target.base_device}: malformed authority evidence")
        if any(not x.startswith(target.base_device) for x in active) or (not active and not excluded):
            raise AcquisitionError(f"{target.base_device}: invalid exact identity disposition")
        maps=[{"icpn":x,**resolve_mapping(x,rows)} for x in active]; route=_routing_status(maps)
        r.update(acquisition_status="success",disposition="active_candidates" if active else "lifecycle_excluded",
            commercial_identity_status="verified_active" if active else "verified_non_active_only",evidence=ev,
            routing_observations=maps,openocd_routing={"status":route,"gates_commercial_identity":False},manual_intervention_required=False)
    except (AcquisitionError,OSError) as e:
        r.update(acquisition_status="failure",disposition="manual_review",commercial_identity_status="unverified",
            manual_intervention_required=True,error_type=type(e).__name__,error=str(e))
    return r


def recompute(template,targets,results):
    validate_targets(targets)
    if len(results)!=138: raise AcquisitionError("merged result count drift")
    m=Counter(); routing=Counter(); active_seen={}; excluded_seen={}; reps={}
    for t,r in zip(targets,results):
        base=t.base_device; m["attempted"]+=1
        if r.get("base_device")!=base or r.get("subfamily")!=t.subfamily or r.get("source_url")!=t.source_url: raise AcquisitionError(f"{base}: target/result drift")
        if r.get("acquisition_status")!="success" or r.get("manual_intervention_required") is not False: raise AcquisitionError(f"{base}: unresolved acquisition")
        ev=r.get("evidence")
        if not isinstance(ev,dict) or ev.get("base_device")!=base or ev.get("evidence_surface")!=AUTHORITY_SURFACE or ev.get("parser_profile")!=PARSER_PROFILE:
            raise AcquisitionError(f"{base}: evidence binding drift")
        active=ev.get("exact_icpns"); excluded=_excluded_ids(ev.get("excluded_non_active_part_numbers"),base)
        if not isinstance(active,list) or (not active and not excluded): raise AcquisitionError(f"{base}: no lifecycle disposition")
        for x in active:
            if not isinstance(x,str) or not x.startswith(base) or x in active_seen or x in excluded_seen: raise AcquisitionError(f"{base}: duplicate/invalid Active ICPN {x}")
            active_seen[x]=base
        for x in excluded:
            if x in active_seen or x in excluded_seen: raise AcquisitionError(f"{base}: duplicate/cross-set excluded ICPN {x}")
            excluded_seen[x]=base
        want=("verified_active","active_candidates") if active else ("verified_non_active_only","lifecycle_excluded")
        if (r.get("commercial_identity_status"),r.get("disposition"))!=want: raise AcquisitionError(f"{base}: disposition drift")
        m["active_candidates" if active else "lifecycle_excluded"]+=1; m["verified"]+=1
        route=r.get("openocd_routing",{}); rs=str(route.get("status")) if active else "not_applicable"
        if route.get("gates_commercial_identity") is not False or rs not in {"unique","ambiguous","unmapped","not_applicable"}: raise AcquisitionError(f"{base}: routing drift")
        routing[rs]+=1
        if base in EXPECTED_L4_1_REPRESENTATIVES: reps[base]=str(r.get("commercial_identity_status"))
    repclean=set(reps)==EXPECTED_L4_1_REPRESENTATIVES and set(reps.values())=={"verified_active"}
    if m["verified"]!=138 or m["active_candidates"]+m["lifecycle_excluded"]!=138 or not repclean: raise AcquisitionError("merged clean-state invariant failed")
    s=dict(template); s.update(base_device_count=138,attempted=138,dispositioned_targets=138,commercial_identity_verified_targets=138,
        active_candidate_targets=m["active_candidates"],lifecycle_excluded_targets=m["lifecycle_excluded"],source_unavailable_exclusions=0,
        identity_manual_intervention_required=0,acquisition_failure=0,active_exact_icpn_candidates=len(active_seen),
        excluded_non_active_part_numbers=len(excluded_seen),representative_continuity_clean=True,commercial_identity_clean=True,bounded_discovery_clean=True,
        openocd_routing={"unique":routing["unique"],"ambiguous":routing["ambiguous"],"unmapped":routing["unmapped"],"not_applicable":routing["not_applicable"],"gates_commercial_identity":False},
        routing_followup_required=routing["ambiguous"]+routing["unmapped"],results=results,acquisition_transport=BROWSER_TRANSPORT,
        commercial_identity_authority=COMMERCIAL_IDENTITY_AUTHORITY)
    if any(v is not False for v in s.get("claims",{}).values()): raise AcquisitionError("merged claims escaped fail-closed")
    return s


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--source-root",type=Path,required=True); ap.add_argument("--output-root",type=Path,required=True)
    ap.add_argument("--timeout",type=float,default=180.0); ap.add_argument("--delay",type=float,default=1.0); ap.add_argument("--headless",action="store_true"); a=ap.parse_args()
    if a.timeout<=INITIAL_TIMEOUT: raise AcquisitionError("recovery timeout must exceed 75 seconds")
    rows=read_catalog(DEFAULT_CATALOG); targets=deterministic_targets(rows); validate_targets(targets)
    if len(targets)!=138 or not set(RETRY).issubset({t.base_device for t in targets}): raise AcquisitionError("fixed retry set escaped deterministic boundary")
    source,old=validate_source(a.source_root,targets); retry=[t for t in targets if t.base_device in RETRY]
    if len(retry)!=15: raise AcquisitionError("retry count escaped fixed 15-device boundary")
    with STDualSurfaceBrowserAcquirer(base_by_url={t.source_url:t.base_device for t in retry},family_label="STM32L4 L4.2 targeted timeout recovery",
            headless=a.headless,reuse_browser=True,global_deadline=True) as acq:
        fetch=RateLimitedFetcher(delay_seconds=a.delay,fetcher=acq.fetch); recovered=[acquire(t,fetch,a.timeout,rows) for t in retry]; browser_version=acq.browser_version
    a.output_root.mkdir(parents=True,exist_ok=True)
    (a.output_root/"recovery-summary.json").write_bytes(jbytes({"schema_version":1,"phase":PHASE,"family":FAMILY,"initial_run_id":INITIAL_RUN_ID,
        "retry_base_devices":[t.base_device for t in retry],"retry_timeout_seconds":a.timeout,"results":recovered}))
    bad=[r for r in recovered if r.get("acquisition_status")!="success"]
    if bad:
        print(json.dumps({"recovered":15-len(bad),"failed":[r.get("base_device") for r in bad]},indent=2)); return 1
    recovered_by={r["base_device"]:r for r in recovered}
    if set(recovered_by)!=set(RETRY): raise AcquisitionError("recovered set drift")
    merged=[recovered_by.get(t.base_device,old[t.base_device]) for t in targets]; summary=recompute(source,targets,merged)
    browser={"headless":a.headless,"browser_version":browser_version,"evidence_profile":PARSER_PROFILE,"reuse_browser":True,"per_device_global_deadline":True,
        "acquisition_run_count":2,"initial_per_device_timeout_seconds":75.0,"recovery_per_device_timeout_seconds":a.timeout}
    summary["browser"]=browser; (a.output_root/"live-summary.json").write_bytes(jbytes(summary)); (a.output_root/"targets.json").write_bytes(jbytes(target_manifest(targets)))
    edir=a.output_root/"evidence"; edir.mkdir(exist_ok=True)
    for r in merged: (edir/f"{r['base_device'].lower()}.json").write_bytes(jbytes(r))
    leaves={p.name:fsha(p) for p in sorted(edir.glob("*.json"))}
    if len(leaves)!=138: raise AcquisitionError("retained leaf count drift")
    (a.output_root/"leaf-digests.json").write_bytes(jbytes({"schema_version":1,"phase":PHASE,"family":FAMILY,"leaf_count":138,"sha256_by_file":leaves}))
    run=int(os.environ["GITHUB_RUN_ID"]); attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]); sha=os.environ["GITHUB_SHA"]
    prov={"schema_version":2,"phase":PHASE,"family":FAMILY,"source_repository":os.environ["GITHUB_REPOSITORY"],"source_branch":os.environ["GITHUB_REF_NAME"],
        "workflow_run_id":run,"workflow_run_attempt":attempt,"executed_git_sha":sha,"workflow_role":"targeted_timeout_recovery_and_retention",
        "acquisition_transport":BROWSER_TRANSPORT,"browser":browser,"target_count":138,"active_candidate_targets":summary["active_candidate_targets"],
        "lifecycle_excluded_targets":summary["lifecycle_excluded_targets"],"active_exact_icpn_candidates":summary["active_exact_icpn_candidates"],
        "excluded_non_active_part_numbers":summary["excluded_non_active_part_numbers"],"routing_followup_required":summary["routing_followup_required"],"bounded_discovery_clean":True,
        "acquisition_runs":[
          {"role":"initial_partial_acquisition","workflow_run_id":INITIAL_RUN_ID,"workflow_run_attempt":1,"artifact_id":INITIAL_ARTIFACT_ID,
           "artifact_sha256":INITIAL_ARTIFACT_SHA256,"executed_git_sha":INITIAL_EXEC_SHA,"per_device_timeout_seconds":75.0,"reuse_browser":True,
           "per_device_global_deadline":True,"browser":source.get("browser"),"successful_target_count":123,"timeout_target_count":15,"timeout_base_devices":list(RETRY),
           "contributed_base_device_count":123,"contributed_base_device_set_sha256":setsha([t.base_device for t in targets if t.base_device not in RETRY])},
          {"role":"targeted_timeout_recovery","workflow_run_id":run,"workflow_run_attempt":attempt,"executed_git_sha":sha,"per_device_timeout_seconds":a.timeout,
           "reuse_browser":True,"per_device_global_deadline":True,"browser":{"headless":a.headless,"browser_version":browser_version,"evidence_profile":PARSER_PROFILE,"per_device_timeout_seconds":a.timeout},"successful_target_count":15,"contributed_base_device_count":15,
           "contributed_base_devices":list(RETRY),"contributed_base_device_set_sha256":setsha(RETRY)}],
        "canonical_admission_authorized":False,"production_write_authorized":False,"runtime_programming_support_claimed":False}
    (a.output_root/"provenance.json").write_bytes(jbytes(prov))
    retained={"schema_version":2,"phase":PHASE,"family":FAMILY,"scope":"retained manufacturer-authoritative commercial discovery evidence with bounded targeted timeout recovery",
        "base_device_count":138,"active_exact_icpn_candidates":summary["active_exact_icpn_candidates"],"excluded_non_active_part_numbers":summary["excluded_non_active_part_numbers"],
        "acquisition_run_count":2,"live_summary_sha256":fsha(a.output_root/"live-summary.json"),"targets_sha256":fsha(a.output_root/"targets.json"),
        "provenance_sha256":fsha(a.output_root/"provenance.json"),"leaf_digests_sha256":fsha(a.output_root/"leaf-digests.json"),
        "claims":{"canonical_admission_authorized":False,"production_write_authorized":False,"runtime_programming_support_claimed":False}}
    (a.output_root/"retained-manifest.json").write_bytes(jbytes(retained))
    print(json.dumps({"base_device_count":138,"recovered_timeout_targets":15,"active_exact_icpn_candidates":summary["active_exact_icpn_candidates"],
        "excluded_non_active_part_numbers":summary["excluded_non_active_part_numbers"],"routing_followup_required":summary["routing_followup_required"],"bounded_discovery_clean":True},indent=2,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
