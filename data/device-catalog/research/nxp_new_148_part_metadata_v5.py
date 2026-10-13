#!/usr/bin/env python3
"""Read-only 148 new Active Exact LPC/i.MX RT orderables metadata acquisition.

Discovery lifecycle is independently proven by exact Package/Quality
material-declaration SKU rows. Each exact /part/ page is optional
metadata evidence, never needed to invent a surrogate/parent SKU.
Run 8 bounded shards, preserve source HTML gzip and individual SHA-256,
then reconcile all 148 with unknown/blocked left pending.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup
from nxp_bulk_part_metadata_v1 import capture
from nxp_manufacturer_device_bulk_v5 import EVIDENCE_LABELS, field, source_cells

HERE=Path(__file__).resolve().parent
SOURCE=HERE/"nxp-new-148-active-discovery-v5.csv"
OUTPUT_FIELDS=[
    "manufacturer","icpn","segment","marketing_lifecycle",
    "metadata_state","package","pin_count","flash_kb",
    "ram_kb","operating_vdd","ambient_temperature",
    "source_url","source_html_sha256",
    "ram_evidence_state","vdd_evidence_state",
    "canonical_admission_qualified",
    "production_publication_authorized",
    "programming_profile_qualified",
]


def require(ok:bool,msg:str)->None:
    if not ok: raise ValueError(msg)


def read_ids()->list[dict]:
    with SOURCE.open(encoding="utf-8",newline="") as f:
        rows=list(csv.DictReader(f))
    require(len(rows)==148 and len({x["icpn"] for x in rows})==148 and
            all(x["lifecycle"]=="Active" and
                x["discovery_state"]=="NEW_BOUNDED_OFFICIAL_ACTIVE_REVIEW_REQUIRED" and
                x["production_catalog_authorized"]=="false" and
                x["programming_profile_qualified"]=="false"
                for x in rows),
            "148 new official manufacturer Active exact source drift")
    return rows


def shard(index:int,output:Path)->None:
    from playwright.sync_api import sync_playwright
    rows=read_ids()
    require(index in range(8),"NXP shard index out of range")
    selected=[x for i,x in enumerate(rows) if i%8==index]
    output.mkdir(parents=True,exist_ok=True)
    batch=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            context=browser.new_context(locale="en-US")
            page=context.new_page()
            for i,r in enumerate(selected):
                sku=r["icpn"]
                try:
                    observed=capture(page,sku,output)
                except Exception as error:
                    observed={
                        "icpn":sku,"status":"blocked_source_or_schema",
                        "source_url":f"https://www.nxp.com/part/{sku}",
                        "reason":type(error).__name__+": "+str(error)[:280],
                        "canonical_metadata_admission_authorized":False,
                        "programming_backend_qualified":False,
                    }
                batch.append(observed)
                print(json.dumps({"shard":index,"icpn":sku,
                    "status":observed["status"]},sort_keys=True),flush=True)
            context.close()
        finally:browser.close()
    report={"schema_version":5,"manufacturer":"NXP","shard":index,
            "requested":len(selected),"exact_skus":[x["icpn"] for x in selected],
            "observed":sum(x["status"]=="official_nxp_part_metadata_observed" for x in batch),
            "blocked":sum(x["status"]=="blocked_source_or_schema" for x in batch),
            "production_publication_authorized":False,
            "results":batch}
    (output/"shard.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")


def aggregate(root:Path,destination:Path)->dict:
    expected=read_ids()
    by_code={}
    status=Counter()
    results=[]
    for idx in range(8):
        folder=root/f"nxp-new-148-part-metadata-shard-{idx}"
        doc=json.loads((folder/"shard.json").read_text(encoding="utf-8"))
        subset=[x["icpn"] for i,x in enumerate(expected) if i%8==idx]
        require(doc["shard"]==idx and doc["manufacturer"]=="NXP" and
                doc["requested"]==len(subset) and doc["exact_skus"]==subset and
                doc["production_publication_authorized"] is False and
                [x["icpn"] for x in doc["results"]]==subset,
                f"NXP new 148 source shard mismatch: {idx}")
        for x in doc["results"]:
            sku=x["icpn"]
            require(sku not in by_code,"duplicate NXP new exact source")
            by_code[sku]=(x,folder)
    require(len(by_code)==148,"incomplete 148 official product page metadata snapshot")
    for row in expected:
        sku=row["icpn"]
        x,folder=by_code[sku]
        observed=x["status"]=="official_nxp_part_metadata_observed"
        require(observed or x["status"]=="blocked_source_or_schema",
                f"{sku}: unsupported original manufacturer source state")
        ram=vdd=ram_state=vdd_state=""
        pin=flash=ambient=package=sha=""
        if observed:
            raw=gzip.decompress((folder/f"{sku}.html.gz").read_bytes())
            sha=hashlib.sha256(raw).hexdigest()
            require(sha==x["source_sha256"] and
                    x["source_url"]==f"https://www.nxp.com/part/{sku}" and
                    x["heading_matches_exact_sku"] is True,
                    f"{sku}: unverified original exact manufacturer source")
            cells=source_cells(BeautifulSoup(raw,"html.parser"))
            ram,ram_state=field(cells,EVIDENCE_LABELS["ram_kb"])
            if ram and not ram.replace(".","",1).isdigit():ram,ram_state="","nonnumeric_sram"
            vdd,vdd_state=field(cells,EVIDENCE_LABELS["vdd_range"])
            package=x.get("package_raw") or ""
            pin=str(x.get("package_terminals") or "")
            flash=str(x.get("flash_kb_raw") or "")
            ambient=x.get("ambient_temperature_raw") or ""
        state=("FOUR_BASIC_FIELDS_OBSERVED_REVIEW_REQUIRED"
               if all((package,pin,flash,ambient)) else
               "PARTIAL_EXACT_PAGE_FIELDS_REVIEW_REQUIRED" if observed else
               "OFFICIAL_EXACT_PART_PAGE_BLOCKED")
        status[state]+=1
        results.append({
            "manufacturer":"NXP","icpn":sku,"segment":row["segment"],
            "marketing_lifecycle":"Active","metadata_state":state,
            "package":package,"pin_count":pin,"flash_kb":flash,
            "ram_kb":ram,"operating_vdd":vdd,"ambient_temperature":ambient,
            "source_url":x["source_url"],"source_html_sha256":sha,
            "ram_evidence_state":ram_state,"vdd_evidence_state":vdd_state,
            "canonical_admission_qualified":"false",
            "production_publication_authorized":"false",
            "programming_profile_qualified":"false",
        })
    require(len(results)==148 and sum(status.values())==148,
            "new Active exact manufacturer metadata review coverage incomplete")
    destination.mkdir(parents=True,exist_ok=True)
    writer=io.StringIO(newline="")
    w=csv.DictWriter(writer,fieldnames=OUTPUT_FIELDS,lineterminator="\n")
    w.writeheader();w.writerows(results)
    content=writer.getvalue()
    (destination/"nxp-148-new-official-metadata-review-v5.csv").write_text(content,encoding="utf-8")
    summary={"schema_version":5,"manufacturer":"NXP",
             "new_exact_active_qualified_lifecycle":148,
             "metadata_state_counts":dict(sorted(status.items())),
             "source_workflow_metadata_shards":8,
             "global_nxp_active_denominator":None,
             "production_publication_authorized":False,
             "programming_profile_qualified":False}
    (destination/"nxp-148-metadata-summary-v5.json").write_text(
        json.dumps(summary,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("NXP_NEW148_METADATA_SUMMARY="+json.dumps(summary,sort_keys=True),flush=True)
    print("NXP_NEW148_METADATA_CSV_BEGIN",flush=True)
    print(content,end="",flush=True)
    print("NXP_NEW148_METADATA_CSV_END",flush=True)
    return summary


def main()->None:
    ap=argparse.ArgumentParser()
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--shard",type=int)
    group.add_argument("--aggregate-root",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if args.shard is not None:shard(args.shard,args.output)
    else:aggregate(args.aggregate_root,args.output)


if __name__=="__main__":
    main()
