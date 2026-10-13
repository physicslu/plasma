#!/usr/bin/env python3
"""Evidence-gated NXP KW45 exact commercial Flash from official PDF Table 1.

Eight exact ordering SKUs had *ambiguous multi-valued product page Flash*
rather than an absent official Flash. This reads the exact NXP PDF page 4
table, validates every SKU's visible position and memory group, and keeps
Catalog admission disabled. Does not infer flash from a naming suffix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import fitz

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "nxp-official-bounded-snapshot-2026-10-13-v1.json"
MAP = HERE / "nxp-bulk-353-status-map-v2.json"
CANDIDATES = HERE / "nxp-active-353-bulk-candidates-v1.csv"
PDF_URL = "https://www.nxp.com/docs/en/data-sheet/KW45.pdf"
ALTERNATE_OFFICIAL_PDF_URL = "https://www.nxp.jp/docs/en/data-sheet/KW45.pdf"
# Independently transcribed and verified against page 4 of official KW45
# Rev 9 Table 1: memory cells spanning distinct rows of exact radio SKUs.
EXACT = {
    "KW45B41Z52AFPBT":512,
    "KW45B41Z52AFTBT":512,
    "KW45B41Z53AFPBT":512,
    "KW45B41Z53AFTBT":512,
    "KW45B41Z82AFPBT":1024,
    "KW45B41Z82AFTBT":1024,
    "KW45B41Z83AFPBT":1024,
    "KW45B41Z83AFTBT":1024,
}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def from_blocked_source() -> set[str]:
    import csv
    with CANDIDATES.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    status = json.loads(MAP.read_text(encoding="utf-8"))
    frozen = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["reconciliation"]
    require(len(rows) == len(status["blocked_reason_map"]) == 353
            and [x["icpn"] for x in rows] == frozen["observed_active_icpns"],
            "353 official exact SKU index drift")
    x = {row["icpn"] for row, cause in zip(rows, status["blocked_reason_map"])
         if cause == "F"}
    require(x == set(EXACT), "KW45 blocked ambiguous-Flash official exact SKU set drift")
    require(status["claims"]["production_write_authorized"] is False,
            "unexpected Production permission in frozen source")
    return x


def pdf_table(source: bytes, source_url: str = PDF_URL) -> dict:
    require(source.startswith(b"%PDF") and len(source) >= 1000,
            "official KW45 PDF invalid")
    doc = fitz.open(stream=source, filetype="pdf")
    try:
        require(doc.page_count >= 5, "NXP KW45 manufacturer datasheet page count drift")
        page = doc[3]
        text = page.get_text(sort=True)
        require("Ordering Information of radio parts" in text,
                "official KW45 datasheet table 1 not found at page 4")
        require("512 KB/128 KB" in text and "1 MB/128 KB" in text,
                "two independent manufacturer radio memory groups absent")
        positions = {}
        for sku in EXACT:
            matches = page.search_for(sku)
            require(len(matches) == 1, f"NXP KW45 exact Table1 part missing/duplicate: {sku}")
            positions[sku] = matches[0]
        group_512 = [positions[s] for s,v in EXACT.items() if v==512]
        group_1024 = [positions[s] for s,v in EXACT.items() if v==1024]
        require(max(r.y0 for r in group_512) < min(r.y0 for r in group_1024),
                "NXP KW45 exact part order crosses the radio memory rowspans")
        groups = {
            512:page.search_for("512 KB/128 KB"),
            1024:page.search_for("1 MB/128 KB")
        }
        require(all(len(v) == 1 for v in groups.values()),
                "manufacturer Table1 flash group not uniquely visible")
        first_y=min(r.y0 for r in group_512)
        second_y=min(r.y0 for r in group_1024)
        last_y=max(r.y1 for r in group_1024)
        require(first_y-12 <= groups[512][0].y0 < second_y and
                second_y-12 <= groups[1024][0].y0 <= last_y+12,
                "NXP KW45 PDF flash cells do not align with exact row groups")
        return {
            "source_url":source_url,
            "source_pdf_sha256":hashlib.sha256(source).hexdigest(),
            "source_pdf_page_count":doc.page_count,
            "source_pdf_zero_index_page":3,
            "source_table":"Table 1. Ordering Information of radio parts",
            "qualification_state":"MANUFACTURER_PDF_EXACT_ROW_VERIFIED_CATALOG_REVIEW_REQUIRED",
            "flash_candidates":[{
                "icpn":sku,
                "flash_kb_from_exact_datasheet_table":v,
                "source_page":4,
                "official_ordering_identity_verified":True,
                "production_write_authorized":False,
            } for sku,v in sorted(EXACT.items())],
            "global_nxp_active_denominator":None,
            "production_write_authorized":False,
            "runtime_programming_qualified":False,
        }
    finally:
        doc.close()


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--pdf-file",type=Path)
    args=ap.parse_args()
    from_blocked_source()
    if args.pdf_file:
        content=args.pdf_file.read_bytes()
    else:
        content = None
        actual_url = None
        errors = []
        for url in (PDF_URL, ALTERNATE_OFFICIAL_PDF_URL):
            require(urlsplit(url).scheme == "https" and
                    urlsplit(url).hostname in {"www.nxp.com", "www.nxp.jp"},
                    "non-manufacturer datasheet URL rejected")
            try:
                request=urllib.request.Request(url,headers={
                    "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    "Accept":"application/pdf,*/*;q=0.5"})
                with urllib.request.urlopen(request,timeout=70) as reply:
                    require(reply.status==200 and urlsplit(reply.url).hostname in
                            {"nxp.com","www.nxp.com","nxp.jp","www.nxp.jp"},
                            "manufacturer PDF redirected to nonofficial source")
                    data=reply.read(12_000_000)
                    require(data.startswith(b"%PDF"), "returned content not PDF")
                    content=data
                    actual_url=reply.url
                break
            except (OSError,ValueError) as exc:
                errors.append(url+":"+type(exc).__name__+":"+str(exc)[:150])
        require(content is not None, "both official NXP regional PDF URLs unavailable: " +
                "; ".join(errors))
    result=pdf_table(content, actual_url or PDF_URL)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"kw45-official-datasheet.pdf").write_bytes(content)
    (args.output/"kw45-eight-exact-flash-datasheet-evidence-v3.json").write_text(
        json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="flash_candidates"},sort_keys=True))


if __name__=="__main__":
    main()
