#!/usr/bin/env python3
"""NXP five-additional-official-product-page Exact SKU Discovery.

Read-only official Package/Quality lifecycle evidence. Uses existing
provenance-audited Playwright parser without changing the prior frozen 353
Active set or claiming manufacturer-wide denominator. Produces exact-SKU
discovery backlog, NEVER a Production admission.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter,defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from nxp_official_pilot_acquire_v1 import acquire
from nxp_bulk_admission_matrix_v1 import ACTIVE_HASH, exact_set_hash

HERE=Path(__file__).resolve().parent
SEEDS=HERE/"nxp-official-expansion-pages-v5.json"
ORIGINAL=HERE/"nxp-active-353-bulk-candidates-v1.csv"
FIELDS=("icpn","segment","lifecycle","official_source_count",
        "source_urls","source_dom_sha256","source_row_evidence_sha256",
        "discovery_state","production_catalog_authorized",
        "programming_profile_qualified")


def require(ok:bool,msg:str)->None:
    if not ok:raise ValueError(msg)


def run(destination:Path)->tuple[list[dict],dict]:
    config=json.loads(SEEDS.read_text(encoding="utf-8"))
    seeds=config["products"]
    require(config["schema_version"]==5 and config["manufacturer"]=="NXP" and
            config["full_vendor_denominator_claimed"] is False and
            config["production_publication_authorized"] is False and
            len(seeds)==len({x["id"] for x in seeds})==5,
            "five-product bounded manufacturer Discovery manifest drift")
    with ORIGINAL.open(encoding="utf-8",newline="") as f:
        previous={r["icpn"] for r in csv.DictReader(f)}
    require(len(previous)==353 and exact_set_hash(previous)==ACTIVE_HASH,
            "original exact manufacturer 353 snapshot drift")
    rows=defaultdict(list)
    capture_counts=Counter()
    reports=[]
    destination.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            context=browser.new_context(locale="en-US")
            page=context.new_page()
            for product in seeds:
                address=urlsplit(product["url"])
                require(address.scheme=="https" and
                        address.hostname in {"www.nxp.com","nxp.com"} and
                        product["prefix"] in {"LPC","MIMXRT"},
                        "out of scope or nonofficial Discovery URL")
                folder=destination/("source-"+product["id"])
                folder.mkdir(parents=True,exist_ok=True)
                try:
                    data=acquire(page,product,folder,browser.version)
                    require(data["status"]=="bounded_official_product_page_observed" and
                            data["source_population_complete"] is False and
                            data["global_active_denominator_claimed"] is False,
                            "source authority or incomplete scope marked complete")
                    capture_counts["verified_pages"]+=1
                    capture_counts["source_rows"]+=len(data["rows"])
                    for row in data["rows"]:
                        if row["lifecycle"]!="Active":
                            capture_counts["lifecycle_excluded"]+=1
                            continue
                        rows[row["icpn"]].append((product,row,data))
                    reports.append({"source":product["id"],"status":"OFFICIAL_EXACT_LIFECYCLE_ROWS_VERIFIED",
                                    "retrieved_exact_count":len(data["rows"]),
                                    "active_exact_rows":data["active_exact_count"],
                                    "sha256_rendered_dom":data["rendered_dom_sha256"]})
                except Exception as e:
                    reports.append({"source":product["id"],"status":"BLOCKED_SOURCE_REVIEW_REQUIRED",
                                    "error_type":type(e).__name__,"reason":str(e)[:240]})
                    capture_counts["blocked_pages"]+=1
                print(json.dumps(reports[-1],sort_keys=True),flush=True)
            context.close()
        finally:browser.close()
    output=[]
    for sku,records in sorted(rows.items()):
        segments={p["segment"] for p,_,_ in records}
        require(len(segments)==1,f"conflicting manufacturer product segments: {sku}")
        refs=sorted({r["source_url"] for p,r,d in records})
        doms=sorted({d["rendered_dom_sha256"] for p,r,d in records})
        row_digest=sorted({r["evidence_sha256"] for p,r,d in records})
        require(all(r["lifecycle"]=="Active" and r["icpn"]==sku
                    for p,r,d in records),"lifecycle source mismatch")
        output.append({
            "icpn":sku,"segment":next(iter(segments)),"lifecycle":"Active",
            "official_source_count":len(records),
            "source_urls":";".join(refs),
            "source_dom_sha256":";".join(doms),
            "source_row_evidence_sha256":";".join(row_digest),
            "discovery_state":"EXISTING_353_OFFICIAL_ACTIVE" if sku in previous
                              else "NEW_BOUNDED_OFFICIAL_ACTIVE_REVIEW_REQUIRED",
            "production_catalog_authorized":"false",
            "programming_profile_qualified":"false",
        })
    new=[x for x in output if x["discovery_state"].startswith("NEW_")]
    require(not {x["icpn"] for x in new} & previous and
            len(output)==len({x["icpn"] for x in output}),
            "source identity/Active duplicates or collision")
    stats={
        "schema_version":5,"manufacturer":"NXP",
        "source_pages_requested":5,
        "source_pages_verified":capture_counts["verified_pages"],
        "source_pages_blocked":capture_counts["blocked_pages"],
        "new_exact_active_discovered_beyond_frozen_353":len(new),
        "already_in_frozen_353_active":len(output)-len(new),
        "new_exact_active_set_sha256":exact_set_hash({x["icpn"] for x in new}),
        "old_353_sha256":ACTIVE_HASH,
        "other_lifecycle_exact_rows_excluded":capture_counts["lifecycle_excluded"],
        "per_page":reports,
        "manufacturer_wide_population_complete":False,
        "manufacturer_wide_active_denominator":None,
        "metadata_qualification_complete":False,
        "production_publication_authorized":False,
        "programming_profile_qualified":False,
    }
    return output,stats


def save(rows:list[dict],summary:dict,folder:Path)->None:
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    (folder/"nxp-five-page-expanded-active-evidence-v5.csv").write_text(buf.getvalue(),encoding="utf-8")
    (folder/"nxp-five-page-discovery-summary-v5.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    a,b=run(args.output)
    save(a,b,args.output)
    print("NXP_EXPANDED_DISCOVERY_SUMMARY="+json.dumps({
        "pages_verified":b["source_pages_verified"],
        "pages_blocked":b["source_pages_blocked"],
        "new_active_exact":b["new_exact_active_discovered_beyond_frozen_353"],
        "lifecycle_excluded":b["other_lifecycle_exact_rows_excluded"],
        "new_exact_sha256":b["new_exact_active_set_sha256"],
    },sort_keys=True),flush=True)
    print("NXP_DISCOVERY_ACTIVE_CSV_BEGIN",flush=True)
    print((args.output/"nxp-five-page-expanded-active-evidence-v5.csv").read_text(),
          end="",flush=True)
    print("NXP_DISCOVERY_ACTIVE_CSV_END",flush=True)


if __name__=="__main__":
    main()
