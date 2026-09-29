#!/usr/bin/env python3
"""Validate retained official NXP KL25 one-representative live evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from nxp_kl25_official_accessibility_probe import (
    EXPECTED_IDENTITY, EXPECTED_LOCK_BLOB, EXPECTED_PRODUCTION_BLOB,
    EXPECTED_SELECTION_BLOB, PROBE_ID, guarded_target,
)

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EVIDENCE=HERE/"evidence/nxp-kl25-accessibility-live-2026-09-29"
GATE=HERE/"nxp-kl25-evidence-accessibility-gate.json"
PRODUCTION=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"

def req(ok:bool, message:str)->None:
    if not ok:raise SystemExit(message)

def load(path:Path)->dict:
    req(path.is_file(),f"missing: {path}")
    v=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(v,dict),f"{path}: expected object")
    return v

def blob(path:Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode("ascii")+b,usedforsecurity=False).hexdigest()

def main()->int:
    target=load(EVIDENCE/"target.json")
    result=load(EVIDENCE/"mkl25z128vlk4.json")
    summary=load(EVIDENCE/"probe-summary.json")
    provenance=load(EVIDENCE/"provenance.json")
    gate=load(GATE)

    req(target==guarded_target(),"target manifest is not frozen pilot replay")
    req(target["selection_git_blob_sha"]==EXPECTED_SELECTION_BLOB,"selection provenance drifted")
    req(target["source_lock_git_blob_sha"]==EXPECTED_LOCK_BLOB,"manufacturer source lock drifted")
    req(target["production_manifest_git_blob_sha"]==EXPECTED_PRODUCTION_BLOB,"production prestate drifted")
    req(target["exact_representative"]==EXPECTED_IDENTITY,"exact representative drifted")

    req(result["acquisition_status"]=="success","live acquisition did not succeed")
    req(result["acquisition_transport"]=="chromium_rendered_dom","transport drifted")
    req(result["http_status"]==200,"official NXP page did not return HTTP 200")
    req(result["exact_icpn"]==EXPECTED_IDENTITY,"observed exact identity drifted")
    req(result["marketing_status"]=="Active","lifecycle is not Active")
    req(result["commercial_identity_status"]=="verified_active_on_official_manufacturer_listing","commercial identity status drifted")
    req(result["source_url"]=="https://www.nxp.com/products/KL2x?tab=Package_Quality_Tab","source URL drifted")
    row=result.get("commercial_row") or {}
    req(row.get("identity_in_row_markup") is True,"exact part not proven within commercial row")
    req(row.get("same_row_active_status") is True,"same-row Active status not proven")
    req(row.get("same_row_other_status") is False,"conflicting lifecycle status retained")
    req(row.get("matching_exact_sku_rows_seen")==2,"matching-row diagnostics drifted")
    req(row.get("non_lifecycle_quality_rows_seen")==1,"quality row distinction drifted")
    req(row.get("row_markup_sha256")=="f64ffa1c5f90fed7c1be44dd116f9bd1498c7f1bc0ad2f14132c09911abbda2b","commercial row markup digest drifted")
    req(row.get("visible_row_sha256")=="cd4e5765936dc1ba4c6bdbe13d94e344658fbd6746c602eff0c2dd8be51e3deb","commercial row text digest drifted")
    req(result.get("rendered_dom_sha256")=="8fda353c7b698f2b80fce1a2d71ebaa0075055e0c06b845bbcfeed8b5ff91198","rendered DOM digest drifted")

    req(summary["probe_id"]==PROBE_ID,"summary probe id drifted")
    req(summary["attempted_targets"]==1 and summary["successful_targets"]==1 and summary["manual_review_targets"]==0,"one-target success counts drifted")
    req(summary["result"]==result,"standalone result differs from retained summary")
    req(summary["exact_active_identity_observed"]==[EXPECTED_IDENTITY],"observed exact set drifted")
    req(summary["status"]=="accessible" and summary["evidence_accessibility_ready_for_representative"] is True,"accessibility status drifted")
    req(summary["full_exact_icpn_discovery_completed"] is False and summary["catalog_admission_ready"] is False,"premature admission in summary")
    req(summary["next_gate"]=="nxp-kl25-bounded-exact-icpn-discovery-gate","discovery next gate drifted")
    req(summary["claims"] and all(v is False for v in summary["claims"].values()),"summary trust boundary escaped")
    req(provenance["browser_version"]=="153.0.8010.12","browser provenance drifted")
    req(provenance["probe_id"]==PROBE_ID,"provenance probe id drifted")
    req(provenance["selection_git_blob_sha"]==EXPECTED_SELECTION_BLOB,"provenance selection drifted")
    req(provenance["source_lock_git_blob_sha"]==EXPECTED_LOCK_BLOB,"provenance source lock drifted")
    req(provenance["production_prestate_git_blob_sha"]==EXPECTED_PRODUCTION_BLOB,"provenance production boundary drifted")

    req(gate["gate_id"]==PROBE_ID,"gate id drifted")
    live=gate.get("live_acquisition") or {}
    req(live["workflow_run_id"]==36505413690 and live["workflow_attempt"]==1,"workflow run provenance drifted")
    req(live["executed_head"]=="fd904a931d09a85f9208c87fc749057be860882a","executed head drifted")
    req(live["artifact_id"]==11006364246,"artifact ID drifted")
    req(live["artifact_zip_sha256"]=="53d52aacb2627f2c133f53cda044df6fb9c7e3a5203069b2bb3fb9f6ddf06993","artifact ZIP digest drifted")
    req(live["browser_version"]==provenance["browser_version"],"gate/provenance browser differs")
    require_evidence=gate["official_manufacturer_evidence"]
    req(require_evidence["exact_icpn"]==result["exact_icpn"] and
        require_evidence["marketing_status"]==result["marketing_status"] and
        require_evidence["rendered_dom_sha256"]==result["rendered_dom_sha256"],"gate evidence summary drifted")
    req(gate["evidence_accessibility_ready_for_representative"] is True,"gate accessibility not opened")
    req(gate["exact_icpn_discovery_completed"] is False and gate["catalog_admission_ready"] is False,"premature admission in gate")
    req(gate["next_gate"]=="nxp-kl25-bounded-exact-icpn-discovery-gate","gate next step drifted")
    req(gate["claims"] and all(v is False for v in gate["claims"].values()),"gate trust boundary escaped")
    req(blob(PRODUCTION)==EXPECTED_PRODUCTION_BLOB,"Production modified during research")
    production=load(PRODUCTION)
    req(len(production["sources"])==23 and sum(int(x["row_count"]) for x in production["sources"])==2683,"Production count changed")
    req(all(x["family"]!="KL25" for x in production["sources"]),"KL25 leaked into Production")

    print("NXP KL25 official representative evidence accessibility: PASS")
    print("one exact=MKL25Z128VLK4 status=Active HTTP=200 manual=0")
    print("full discovery=pending; Production unchanged 2683 / 23")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
