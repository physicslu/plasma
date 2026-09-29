#!/usr/bin/env python3
"""Bounded official NXP live-current-commercial evidence accessibility probe.

One exact manufacturer-reviewed representative only. Does not perform full KL25
enumeration, metadata admission, production routing, runtime, or programming.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SELECTION = HERE / "post-stm32-cross-vendor-pilot-selection.json"
LOCK = ROOT / "data/ic-support/benchmarks/nxp-kl25/source-lock.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

PROBE_ID = "nxp-kl25-official-current-commercial-evidence-accessibility-v1"
EXPECTED_SELECTION_BLOB = "61aeaba4601101cc665c2830453bbf2cc416c8c0"
EXPECTED_LOCK_BLOB = "4927139f202bee1ee3e813ef57e3cfdfd3333ba6"
EXPECTED_PRODUCTION_BLOB = "c8012b211a28b0a7811bfe978e7e697bc169c6f3"
EXPECTED_IDENTITY = "MKL25Z128VLK4"
URL = "https://www.nxp.com/products/KL2x?tab=Package_Quality_Tab"

class EvidenceError(RuntimeError):
    pass

def require(ok: bool, msg: str) -> None:
    if not ok:
        raise EvidenceError(msg)

def git_blob(path: Path) -> str:
    b = path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode("ascii") + b, usedforsecurity=False).hexdigest()

def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def guarded_target() -> dict[str, Any]:
    require(git_blob(SELECTION) == EXPECTED_SELECTION_BLOB, "pilot selection blob drifted")
    require(git_blob(LOCK) == EXPECTED_LOCK_BLOB, "manufacturer source lock drifted")
    require(git_blob(PRODUCTION) == EXPECTED_PRODUCTION_BLOB, "Production prestate drifted")
    s=json.loads(SELECTION.read_text(encoding="utf-8"))
    require(s.get("selection_id")=="post-stm32-nxp-kl25-bounded-cross-vendor-pilot-v1","selection ID drifted")
    require(s.get("status")=="selected_for_official_manufacturer_evidence_accessibility_only","pilot status drifted")
    require(s.get("next_gate")=="nxp-kl25-bounded-official-manufacturer-current-commercial-evidence-accessibility-gate","next gate drifted")
    selected=s.get("selected") or {}
    require(selected.get("reviewed_exact_representative")==EXPECTED_IDENTITY,"exact representative drifted")
    require(selected.get("ordering_patterns")==["MKL25Z128xxx4","MKL25Z32xxx4","MKL25Z64xxx4"],"selected patterns drifted")
    require(selected.get("matching_pattern")=="MKL25Z128xxx4","representative mapping drifted")
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock.get("targets")==[EXPECTED_IDENTITY],"source lock exact identity drifted")
    require(lock.get("trust_boundary",{}).get("production_admission") is False,"source lock admission drifted")
    m=json.loads(PRODUCTION.read_text(encoding="utf-8"))
    require(len(m["sources"])==23 and sum(int(x["row_count"]) for x in m["sources"])==2683,"production boundary drifted")
    require(all(x["family"]!="KL25" for x in m["sources"]),"NXP KL25 already published")
    return {
      "probe_id":PROBE_ID,
      "manufacturer":"NXP",
      "family":"KL25",
      "exact_representative":EXPECTED_IDENTITY,
      "matching_canonical_pattern":"MKL25Z128xxx4",
      "source_url":URL,
      "selection_git_blob_sha":EXPECTED_SELECTION_BLOB,
      "source_lock_git_blob_sha":EXPECTED_LOCK_BLOB,
      "production_manifest_git_blob_sha":EXPECTED_PRODUCTION_BLOB,
      "scope":"one exact KL25 representative official manufacturer identity and lifecycle accessibility",
      "full_exact_discovery_authorized":False
    }

def acquire(page: Any) -> dict[str,Any]:
    response=page.goto(URL,wait_until="domcontentloaded",timeout=90000)
    if response is None:
        raise EvidenceError("NXP page navigation did not return an HTTP response")
    http_status=int(response.status)
    if http_status!=200:
        raise EvidenceError(f"NXP product page HTTP {http_status}")
    page.wait_for_timeout(5000)
    # Important: status must be taken from the SAME visible commercial table row.
    # No global page-level 'Active' search, which could belong to another product.
    html=page.content()
    body=page.locator("body").inner_text(timeout=15000)
    title=page.title()
    matching_rows=[]
    rows=page.locator("tr")
    for idx in range(rows.count()):
        row=rows.nth(idx)
        markup=row.evaluate("(node) => node.outerHTML")
        if re.search(r"(?<![A-Z0-9])"+EXPECTED_IDENTITY+r"(?![A-Z0-9])",markup,re.I):
            text=row.inner_text(timeout=5000)
            matching_rows.append({
              "visible_row_sha256":sha256(text),
              "row_markup_sha256":sha256(markup),
              "visible_row_excerpt":text[:500],
              "identity_in_row_markup":True,
              "same_row_active_status":bool(re.search(r"\bActive\b",text)),
              "same_row_other_status":bool(re.search(r"\b(Obsolete|No Longer Manufactured|NRND|Not Recommended for New Designs)\b",text,re.I)),
            })
    # A SKU may also occur in the distinct Quality Information table. That
    # second table is not lifecycle evidence. Require exactly one Active row,
    # and reject ANY contradictory lifecycle row for the same exact identity.
    if not matching_rows:
        raise EvidenceError("No exact SKU row found in official NXP rendered DOM")
    if any(row["same_row_other_status"] for row in matching_rows):
        raise EvidenceError("Conflicting non-Active lifecycle status for exact SKU")
    commercial=[row for row in matching_rows if row["same_row_active_status"]]
    if len(commercial)!=1:
        diag=[{"active":r["same_row_active_status"],"other":r["same_row_other_status"],
               "excerpt":r["visible_row_excerpt"][:160]} for r in matching_rows]
        raise EvidenceError(f"Expected one unambiguous Active commercial row: {diag}")
    row=commercial[0]
    row["matching_exact_sku_rows_seen"]=len(matching_rows)
    row["non_lifecycle_quality_rows_seen"]=len(matching_rows)-1
    return {
      "acquisition_status":"success",
      "commercial_identity_status":"verified_active_on_official_manufacturer_listing",
      "http_status":http_status,
      "exact_icpn":EXPECTED_IDENTITY,
      "marketing_status":"Active",
      "acquisition_transport":"chromium_rendered_dom",
      "final_url":page.url,
      "source_url":URL,
      "page_title":title,
      "rendered_dom_sha256":sha256(html),
      "visible_body_sha256":sha256(body),
      "commercial_row":row,
      "retrieved_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "claim_scope":"one exact representative; no full-family enumeration"
    }

def main()->int:
    args=argparse.ArgumentParser()
    args.add_argument("--output-dir",type=Path,required=True)
    ns=args.parse_args()
    ns.output_dir.mkdir(parents=True,exist_ok=True)
    target=guarded_target()
    dump(ns.output_dir/"target.json",target)

    evidence:dict[str,Any]={}
    browser_version: str | None=None
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            browser_version=browser.version
            ctx=browser.new_context(
              user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
              locale="en-US",
            )
            page=ctx.new_page()
            evidence=acquire(page)
            ctx.close()
            browser.close()
    except Exception as exc:
        evidence={
          "acquisition_status":"blocked_manual_review",
          "commercial_identity_status":"unverified",
          "exact_icpn":EXPECTED_IDENTITY,
          "source_url":URL,
          "error_type":type(exc).__name__,
          "error":str(exc)[:400],
          "retrieved_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
          "claim_scope":"no exact identity/lifecycle admission"
        }
    dump(ns.output_dir/"mkl25z128vlk4.json",evidence)
    ok=evidence.get("acquisition_status")=="success"
    summary={
      "schema_version":1,
      "probe_id":PROBE_ID,
      "scope":"one exact manufacturer-reviewed KL25 representative",
      "attempted_targets":1,
      "successful_targets":1 if ok else 0,
      "manual_review_targets":0 if ok else 1,
      "exact_active_identity_observed":[EXPECTED_IDENTITY] if ok else [],
      "status":"accessible" if ok else "blocked_manual_review",
      "evidence_accessibility_ready_for_representative":ok,
      "full_exact_icpn_discovery_completed":False,
      "catalog_admission_ready":False,
      "next_gate":"nxp-kl25-bounded-exact-icpn-discovery-gate" if ok else None,
      "result":evidence,
      "claims":{
          "full_exact_icpn_discovery_completed":False,
          "catalog_admission_ready":False,
          "production_write_authorized":False,
          "software_executor_admission_implies_catalog_admission":False,
          "runtime_programming_support_claimed":False,
          "physical_validation_claimed":False,
          "target_execution_authorized":False,
      }
    }
    provenance={
      "probe_id":PROBE_ID,
      "source_repository":"physicslu/plasma",
      "selection_git_blob_sha":EXPECTED_SELECTION_BLOB,
      "source_lock_git_blob_sha":EXPECTED_LOCK_BLOB,
      "production_prestate_git_blob_sha":EXPECTED_PRODUCTION_BLOB,
      "browser_version":browser_version,
      "acquisition_transport":"chromium_rendered_dom",
      "generated_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    }
    dump(ns.output_dir/"probe-summary.json",summary)
    dump(ns.output_dir/"provenance.json",provenance)
    print(json.dumps({
      "probe_id":PROBE_ID,"status":summary["status"],
      "success":summary["successful_targets"],
      "manual_review":summary["manual_review_targets"],
      "exact":EXPECTED_IDENTITY,
      "error":evidence.get("error")
    },sort_keys=True))
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(main())
