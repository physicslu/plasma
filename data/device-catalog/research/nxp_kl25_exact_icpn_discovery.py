#!/usr/bin/env python3
"""Bounded NXP KL25 current-commercial exact ICPN discovery from official NXP table.

Trust boundary: current official marketing identities and deterministic frozen
pattern mapping only; no metadata/route admission, publication or execution.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=HERE/"openocd-parts-canonical.csv"
SELECTION=HERE/"post-stm32-cross-vendor-pilot-selection.json"
GATE=HERE/"nxp-kl25-evidence-accessibility-gate.json"
PRODUCTION=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"

DISCOVERY_ID="nxp-kl25-bounded-current-commercial-exact-icpn-discovery-v1"
EXPECTED_SOURCE_SHA256="43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SELECTION_BLOB="61aeaba4601101cc665c2830453bbf2cc416c8c0"
EXPECTED_GATE_BLOB="0bb8ff2a0a59381243c5dc357be521bce882c881"
EXPECTED_PRODUCTION_BLOB="c8012b211a28b0a7811bfe978e7e697bc169c6f3"
PATTERNS=("MKL25Z128xxx4","MKL25Z32xxx4","MKL25Z64xxx4")
EXPECTED_REPRESENTATIVE="MKL25Z128VLK4"
NXP_URL="https://www.nxp.com/products/KL2x?tab=Package_Quality_Tab"
SKU_RE=re.compile(r"\bMKL25Z(?:128|32|64)[A-Z0-9]{3}4\b",re.I)

class DiscoveryError(RuntimeError):pass

def require(ok:bool,msg:str)->None:
    if not ok:raise DiscoveryError(msg)

def sha256(s:str)->str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def git_blob(path:Path)->str:
    b=path.read_bytes()
    return hashlib.sha1(f"blob {len(b)}\0".encode("ascii")+b,usedforsecurity=False).hexdigest()

def dump(path:Path,obj:dict[str,Any])->None:
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def match_pattern(sku:str,pattern:str)->bool:
    return len(sku)==len(pattern) and all(a=="x" or a==b for a,b in zip(pattern,sku))

def guarded_targets()->dict[str,Any]:
    require(hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED_SOURCE_SHA256,"candidate source drifted")
    require(git_blob(SELECTION)==EXPECTED_SELECTION_BLOB,"pilot selection drifted")
    require(git_blob(GATE)==EXPECTED_GATE_BLOB,"accessibility gate drifted")
    require(git_blob(PRODUCTION)==EXPECTED_PRODUCTION_BLOB,"Production prestate drifted")

    sel=json.loads(SELECTION.read_text(encoding="utf-8"))
    gate=json.loads(GATE.read_text(encoding="utf-8"))
    production=json.loads(PRODUCTION.read_text(encoding="utf-8"))
    require(sel.get("selected",{}).get("ordering_patterns")==list(PATTERNS),"selected ordering-pattern set drifted")
    require(sel.get("selected",{}).get("reviewed_exact_representative")==EXPECTED_REPRESENTATIVE,"representative drifted")
    require(gate.get("evidence_accessibility_ready_for_representative") is True,"official representative accessibility not ready")
    require(gate.get("catalog_admission_ready") is False,"accessibility prematurely admitted catalog")
    require(gate.get("next_gate")=="nxp-kl25-bounded-exact-icpn-discovery-gate","discovery next gate drifted")
    require(production.get("status")=="production" and len(production.get("sources",[]))==23
            and sum(int(x["row_count"]) for x in production["sources"])==2683,"Production boundary drifted")
    require(all(x["family"]!="KL25" for x in production["sources"]),"KL25 already published")

    with SOURCE.open(newline="",encoding="utf-8") as f:
        kl25=[r for r in csv.DictReader(f) if r["vendor"]=="NXP" and r["plasma_series"]=="KL25"]
    require(tuple(sorted(r["part_number"] for r in kl25))==PATTERNS,"canonical ordering-pattern rows drifted")
    require(all(r["target_config"]=="tcl/target/kl25.cfg"
                and r["identifier_kind"]=="ordering_pattern" for r in kl25),"route candidate surface drifted")
    return {
      "discovery_id":DISCOVERY_ID,
      "manufacturer":"NXP","family":"KL25",
      "source_url":NXP_URL,
      "target_config":"tcl/target/kl25.cfg",
      "candidate_source_sha256":EXPECTED_SOURCE_SHA256,
      "selection_git_blob_sha":EXPECTED_SELECTION_BLOB,
      "accessibility_gate_git_blob_sha":EXPECTED_GATE_BLOB,
      "production_manifest_git_blob_sha":EXPECTED_PRODUCTION_BLOB,
      "patterns":list(PATTERNS),
      "pattern_count":3,
      "scope":"bounded current official NXP KL2x product listing intersected with three frozen KL25 patterns",
      "manufacturer_reviewed_exact_representative":EXPECTED_REPRESENTATIVE,
      "catalog_admission_authorized":False
    }

def acquire(page:Any)->dict[str,Any]:
    response=page.goto(NXP_URL,wait_until="domcontentloaded",timeout=90000)
    require(response is not None,"NXP page navigation returned no response")
    require(response.status==200,f"NXP page HTTP {response.status}")
    page.wait_for_timeout(5000)
    html=page.content()
    body=page.locator("body").inner_text(timeout=15000)
    require("Package/Quality" in body and "Environmental Information" in body,
            "NXP page is missing expected product lifecycle surface")

    candidates:dict[str,list[dict[str,Any]]]=defaultdict(list)
    tr=page.locator("tr")
    for i in range(tr.count()):
        row=tr.nth(i)
        markup=row.evaluate("(node) => node.outerHTML")
        exact=sorted(set(m.group(0).upper() for m in SKU_RE.finditer(markup)))
        if not exact:continue
        text=row.inner_text(timeout=5000)
        active=bool(re.search(r"\bActive\b",text))
        nonactive=bool(re.search(r"\b(Obsolete|No Longer Manufactured|Not Recommended for New Designs|NRND|Discontinued)\b",text,re.I))
        require(not(active and nonactive),f"conflicting lifecycle statuses within a row: {exact}")
        for icpn in exact:
            matches=[pattern for pattern in PATTERNS if match_pattern(icpn,pattern)]
            require(len(matches)==1,f"{icpn}: no unique canonical ordering-pattern route")
            candidates[icpn].append({
              "icpn":icpn,
              "pattern":matches[0],
              "active":active,
              "nonactive":nonactive,
              "visible_row_excerpt":text[:350],
              "visible_row_sha256":sha256(text),
              "row_markup_sha256":sha256(markup)
            })
    require(EXPECTED_REPRESENTATIVE in candidates,"source-locked representative absent from official listing")

    active_evidence=[]
    exclusions=[]
    for icpn,rows in sorted(candidates.items()):
        active_rows=[r for r in rows if r["active"]]
        inactive_rows=[r for r in rows if r["nonactive"]]
        require(not(active_rows and inactive_rows),f"{icpn}: contradictory lifecycle records")
        require(len(active_rows)<=1,f"{icpn}: multiple official Active commercial rows")
        if active_rows:
            active=active_rows[0].copy()
            active["same_sku_table_row_count"]=len(rows)
            active["non_lifecycle_rows_seen"]=len(rows)-1
            active_evidence.append(active)
        elif inactive_rows:
            require(len(inactive_rows)==1,f"{icpn}: contradictory non-Active records")
            exclusions.append({"icpn":icpn,"pattern":inactive_rows[0]["pattern"],
                               "status_excerpt":inactive_rows[0]["visible_row_excerpt"],
                               "evidence_row_sha256":inactive_rows[0]["visible_row_sha256"]})
        else:
            raise DiscoveryError(f"{icpn}: only non-lifecycle quality row visible; commercial status absent")
    observed=sorted(r["icpn"] for r in active_evidence)
    by_pattern=dict(sorted(Counter(r["pattern"] for r in active_evidence).items()))
    require(set(by_pattern)==set(PATTERNS),"one or more frozen memory-size pattern groups lack Active commercial evidence")
    require(EXPECTED_REPRESENTATIVE in observed,"reviewed exact representative not Active in discovery")
    return {
      "discovery_id":DISCOVERY_ID,
      "status":"discovered",
      "http_status":200,
      "source_url":NXP_URL,
      "final_url":page.url,
      "page_title":page.title(),
      "acquisition_transport":"chromium_rendered_dom",
      "retrieved_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "rendered_dom_sha256":sha256(html),
      "visible_body_sha256":sha256(body),
      "table_row_count":tr.count(),
      "candidate_exact_sku_count":len(candidates),
      "active_exact_icpn_count":len(observed),
      "active_exact_icpns":observed,
      "active_exact_set_sha256":sha256("\n".join(observed)+"\n"),
      "pattern_active_counts":by_pattern,
      "excluded_non_active":exclusions,
      "active_row_evidence":active_evidence,
      "scope":"exact NXP KL25 identities visible in current official KL2x Package/Quality table, not extrapolated patterns",
    }

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",type=Path,required=True)
    args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    targets=guarded_targets()
    dump(args.output_dir/"targets.json",targets)
    browser_version=None
    result:dict[str,Any]
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            browser_version=browser.version
            ctx=browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",locale="en-US")
            result=acquire(ctx.new_page())
            ctx.close()
            browser.close()
    except Exception as exc:
        result={
          "discovery_id":DISCOVERY_ID,
          "status":"blocked_manual_review",
          "error_type":type(exc).__name__,
          "error":str(exc)[:600],
          "source_url":NXP_URL,
          "active_exact_icpn_count":0,
          "active_exact_icpns":[],
          "excluded_non_active":[],
        }
    success=result["status"]=="discovered"
    summary={
      "schema_version":1,
      "discovery_id":DISCOVERY_ID,
      "manufacturer":"NXP","family":"KL25",
      "frozen_ordering_pattern_count":3,
      "status":result["status"],
      "active_exact_icpn_count":result["active_exact_icpn_count"],
      "active_exact_icpns":result["active_exact_icpns"],
      "active_exact_set_sha256":result.get("active_exact_set_sha256"),
      "pattern_active_counts":result.get("pattern_active_counts",{}),
      "excluded_non_active":result["excluded_non_active"],
      "bounded_exact_discovery_complete":success,
      "manual_review_count":0 if success else 1,
      "next_gate":"nxp-kl25-bounded-exact-icpn-admission-readiness-gate" if success else None,
      "claims":{
        "catalog_admission_ready":False,
        "production_write_authorized":False,
        "production_publication_authorized":False,
        "software_executor_admission_implies_catalog_admission":False,
        "runtime_programming_support_claimed":False,
        "target_execution_authorized":False,
        "physical_validation_claimed":False,
      }
    }
    exact={
      "discovery_id":DISCOVERY_ID,
      "exact_icpn_count":summary["active_exact_icpn_count"],
      "exact_icpns":summary["active_exact_icpns"],
      "exact_set_sha256":summary["active_exact_set_sha256"],
      "excluded_non_active":summary["excluded_non_active"]
    }
    dump(args.output_dir/"commercial-rows.json",result)
    dump(args.output_dir/"discovery-summary.json",summary)
    dump(args.output_dir/"exact-icpns.json",exact)
    dump(args.output_dir/"provenance.json",{
      "discovery_id":DISCOVERY_ID,
      "source_repository":"physicslu/plasma",
      "browser_version":browser_version,
      "source_url":NXP_URL,
      "acquisition_transport":"chromium_rendered_dom",
      "selection_git_blob_sha":EXPECTED_SELECTION_BLOB,
      "accessibility_gate_git_blob_sha":EXPECTED_GATE_BLOB,
      "production_prestate_git_blob_sha":EXPECTED_PRODUCTION_BLOB,
      "generated_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
    })
    dump(args.output_dir/"probe-status.json",{"discovery_id":DISCOVERY_ID,
      "status":summary["status"],"manual_review_count":summary["manual_review_count"],
      "error":result.get("error")})
    print(json.dumps({
      "status":summary["status"],"exact":summary["active_exact_icpn_count"],
      "by_pattern":summary["pattern_active_counts"],
      "excluded":len(summary["excluded_non_active"]),
      "error":result.get("error"),
    },sort_keys=True))
    return 0 if success else 1

if __name__=="__main__":
    raise SystemExit(main())
