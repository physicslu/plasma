#!/usr/bin/env python3
"""Fail-closed retained NXP KL25 official exact ICPN discovery validator."""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from pathlib import Path

from nxp_kl25_exact_icpn_discovery import (
  guarded_targets, DISCOVERY_ID, PATTERNS, EXPECTED_REPRESENTATIVE,
  EXPECTED_GATE_BLOB, EXPECTED_PRODUCTION_BLOB,
)

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EVIDENCE=HERE/"evidence/nxp-kl25-exact-icpn-live-2026-09-29"
GATE=HERE/"nxp-kl25-exact-icpn-discovery-gate.json"
PRODUCTION=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
EXPECTED_SET_SHA="dd2c3cee83552a9875ee84c7bdea2cc6bc9c671f528b4bde02bed02b753755d5"
EXPECTED_BLOBS={
 "targets.json":"df06360bf0b3e0a53f9f216bc17b1218e143b6c9",
 "commercial-rows.json":"61c1be96a3c14e28f05099762f64b9ab5e23c1fb",
 "discovery-summary.json":"10dab614b1d6c2f8a8c1ae64c8b725be0c3f0cd6",
 "exact-icpns.json":"3f0903108c515cd947a4330f757a478006959804",
 "provenance.json":"dff48c725ed1eb33dc9bdfe85700698bbae42cc8",
 "probe-status.json":"b6028e66223f354063405c43a03234c0319f072a",
}

def req(ok:bool,msg:str)->None:
    if not ok:raise SystemExit(msg)

def blob(path:Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode("ascii")+b,usedforsecurity=False).hexdigest()

def load(path:Path)->dict:
    req(path.is_file(),f"retained file missing: {path}")
    v=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(v,dict),f"{path}: expected JSON object")
    return v

def main()->int:
    for name,digest in EXPECTED_BLOBS.items():
        req(blob(EVIDENCE/name)==digest,f"retained evidence blob drifted: {name}")
    target=load(EVIDENCE/"targets.json")
    rows=load(EVIDENCE/"commercial-rows.json")
    summary=load(EVIDENCE/"discovery-summary.json")
    exact=load(EVIDENCE/"exact-icpns.json")
    provenance=load(EVIDENCE/"provenance.json")
    status=load(EVIDENCE/"probe-status.json")
    gate=load(GATE)

    req(target==guarded_targets(),"frozen discovery target manifest mismatch")
    req(target["patterns"]==list(PATTERNS),"target ordering patterns drifted")
    req(target["accessibility_gate_git_blob_sha"]==EXPECTED_GATE_BLOB,"accessibility gate binding drifted")
    req(target["production_manifest_git_blob_sha"]==EXPECTED_PRODUCTION_BLOB,"Production prestate binding drifted")
    req(rows["discovery_id"]==DISCOVERY_ID and rows["status"]=="discovered","raw row discovery state drifted")
    req(rows["http_status"]==200,"official manufacturer HTTP status drifted")
    req(rows["acquisition_transport"]=="chromium_rendered_dom","acquisition transport drifted")
    req(rows["source_url"]=="https://www.nxp.com/products/KL2x?tab=Package_Quality_Tab","manufacturer source URL drifted")
    req(rows["rendered_dom_sha256"]=="168fca906e76b463d10d34d70772d28c35082ebba601521ef32d48b08527524b","rendered DOM digest drifted")
    req(rows["candidate_exact_sku_count"]==12 and rows["active_exact_icpn_count"]==12,"raw candidate/Active count drifted")
    req(rows["pattern_active_counts"]=={p:4 for p in PATTERNS},"raw per-pattern counts drifted")
    req(rows["excluded_non_active"]==[],"unexpected non-Active record")
    parts=rows["active_exact_icpns"]
    req(parts==sorted(set(parts)) and len(parts)==12,"raw Active identity set malformed")
    req(EXPECTED_REPRESENTATIVE in parts,"source-locked representative omitted")
    req(hashlib.sha256(("\n".join(parts)+"\n").encode("utf-8")).hexdigest()==EXPECTED_SET_SHA,"exact-set digest mismatch")
    req(rows["active_exact_set_sha256"]==EXPECTED_SET_SHA,"raw exact-set digest drifted")

    evidence=rows["active_row_evidence"]
    req(isinstance(evidence,list) and len(evidence)==12,"commercial row evidence cardinality drifted")
    req(sorted(x["icpn"] for x in evidence)==parts,"commercial evidence identities differ from exact set")
    req(Counter(x["pattern"] for x in evidence)==Counter({p:4 for p in PATTERNS}),"row pattern coverage drifted")
    for row in evidence:
        req(row["active"] is True and row["nonactive"] is False,f"{row['icpn']}: lifecycle status drifted")
        req(row["same_sku_table_row_count"]==2 and row["non_lifecycle_rows_seen"]==1,f"{row['icpn']}: duplicate quality-row model drifted")
        req(len(row["visible_row_sha256"])==64 and len(row["row_markup_sha256"])==64,f"{row['icpn']}: row provenance missing")

    req(summary["discovery_id"]==DISCOVERY_ID and summary["status"]=="discovered","discovery status drifted")
    req(summary["active_exact_icpn_count"]==12 and summary["active_exact_icpns"]==parts,"summary Active set drifted")
    req(summary["active_exact_set_sha256"]==EXPECTED_SET_SHA,"summary digest drifted")
    req(summary["pattern_active_counts"]=={p:4 for p in PATTERNS},"summary pattern counts drifted")
    req(summary["excluded_non_active"]==[] and summary["manual_review_count"]==0,"unresolved lifecycle/manual review")
    req(summary["bounded_exact_discovery_complete"] is True,"bounded discovery incomplete")
    req(summary["next_gate"]=="nxp-kl25-bounded-exact-icpn-admission-readiness-gate","admission readiness gate missing")
    req(summary["claims"] and all(v is False for v in summary["claims"].values()),"discovery trust boundary escaped")

    req(exact["discovery_id"]==DISCOVERY_ID and exact["exact_icpn_count"]==12,"exact snapshot cardinality drifted")
    req(exact["exact_icpns"]==parts and exact["exact_set_sha256"]==EXPECTED_SET_SHA,"exact snapshot differs from raw commercial evidence")
    req(exact["excluded_non_active"]==[],"exact snapshot lifecycle exclusions drifted")
    req(status["status"]=="discovered" and status["manual_review_count"]==0 and status["error"] is None,"status report drifted")
    req(provenance["discovery_id"]==DISCOVERY_ID and provenance["browser_version"]=="153.0.8010.12","browser/discovery provenance drifted")
    req(provenance["accessibility_gate_git_blob_sha"]==EXPECTED_GATE_BLOB,"provenance accessibility gate drifted")
    req(provenance["production_prestate_git_blob_sha"]==EXPECTED_PRODUCTION_BLOB,"provenance Production prestate drifted")

    req(gate["gate_id"]==DISCOVERY_ID and gate["bounded_exact_discovery_complete"] is True,"discovery gate state drifted")
    req(gate["exact_active_count"]==12 and gate["exact_set_sha256"]==EXPECTED_SET_SHA,"gate exact set drifted")
    req(gate["active_per_pattern"]=={p:4 for p in PATTERNS},"gate pattern counts drifted")
    req(gate["catalog_admission_ready"] is False and gate["next_gate"]=="nxp-kl25-bounded-exact-icpn-admission-readiness-gate","premature catalog admission in gate")
    req(gate["claims"] and all(v is False for v in gate["claims"].values()),"gate trust boundary escaped")
    live=gate["live_acquisition"]
    req(live["workflow_run_id"]==36505881833 and live["executed_head"]=="2550eadb472bdd421f2ffc890f6f393d1675d537","workflow run/head drifted")
    req(live["artifact_id"]==11006907910 and live["artifact_zip_sha256"]=="c5beba673e4dfb1ff3a66534b576dc0d3b30525e0483ef638aee7ed4b7391677","artifact provenance drifted")
    req(gate["evidence_git_blobs"]=={name.removesuffix(".json").replace("-","_"):val for name,val in EXPECTED_BLOBS.items()} or
      gate["evidence_git_blobs"]=={
       "targets":EXPECTED_BLOBS["targets.json"],"commercial_rows":EXPECTED_BLOBS["commercial-rows.json"],
       "discovery_summary":EXPECTED_BLOBS["discovery-summary.json"],"exact_icpns":EXPECTED_BLOBS["exact-icpns.json"],
       "provenance":EXPECTED_BLOBS["provenance.json"],"probe_status":EXPECTED_BLOBS["probe-status.json"],
      },"gate retained evidence binding drifted")

    req(blob(PRODUCTION)==EXPECTED_PRODUCTION_BLOB,"Production manifest changed")
    production=load(PRODUCTION)
    req(len(production["sources"])==23 and sum(int(s["row_count"]) for s in production["sources"])==2683,"Production counts drifted")
    req(all(s["family"]!="KL25" for s in production["sources"]),"NXP KL25 prematurely published")
    print("NXP KL25 exact-ICPN discovery: PASS")
    print("12 Active exact identities, 3 patterns x 4, excluded=0, manual=0")
    print("Production unchanged=2683/23 next=admission-readiness")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
