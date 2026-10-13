#!/usr/bin/env python3
"""Merge six official MCX series index link-candidate snapshots.

No completeness or total Active population inference is permitted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

HERE=Path(__file__).resolve().parent

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def read(path):
    obj=json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(obj, dict), "malformed index JSON")
    return obj

def digest(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def scan(root):
    sources=read(HERE/"nxp-mcx-series-index-sources-v1.json")
    require(sources["globally_complete"] is False and sources["production_write_authorized"] is False,
            "index promotion not authorized")
    all_leads=set()
    missing=set()
    rows=[]
    for source in sources["series"]:
        letter=source["series"]
        directory=root/("nxp-mcx-index-"+letter)
        data=read(directory/"index-status.json")
        raw=(directory/"rendered-index.html").read_text(encoding="utf-8")
        require(data["status"]=="official_mcx_series_link_candidates_observed", "blocked series")
        require(data["series"]==letter and data["manufacturer"]=="NXP", "series mismatch")
        require(data["raw_index_sha256"]==digest(raw), "index raw source hash mismatch")
        require(data["index_population_complete_proven"] is False and
                data["commercial_exact_icpn_denominator"] is None, "false manufacturer denominator")
        links=data["candidate_product_page_links"]
        require(links==sorted(set(links)) and len(links)>0, "invalid candidate link set")
        require(data["index_link_candidate_count"]==len(links), "candidate count mismatch")
        for link in links:
            u=urlsplit(link)
            require(u.hostname=="www.nxp.com" and u.scheme=="https", "untrusted series link")
            require(u.path.startswith("/products/MCX-"+letter), "wrong-series product route")
        all_leads.update(links)
        missing.update(data["not_yet_in_pilot"])
        rows.append({"series":letter,"observed_links":len(links),
                     "not_in_pilot":len(data["not_yet_in_pilot"])})
    return {
        "schema_version":1, "manufacturer":"NXP",
        "status":"bounded_mcx_index_link_audit",
        "official_series_index_pages":len(rows),
        "observed_unique_product_page_leads":len(all_leads),
        "candidate_product_pages_not_in_pilot":sorted(missing),
        "candidate_product_pages_not_in_pilot_count":len(missing),
        "observed_links_by_series":rows,
        "mcx_series_population_complete":False,
        "full_nxp_active_icpn_denominator":None,
        "production_write_authorized":False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=scan(a.root)
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/"mcx-index-gap.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":
    main()
