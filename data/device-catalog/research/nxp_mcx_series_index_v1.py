#!/usr/bin/env python3
"""Read-only official NXP MCX series index to surface missing product page leads.

Candidate-link discovery is not evidence that official index enumeration is
exhaustive. No Active exact SKU number is inferred from an index link.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "nxp-mcx-series-index-sources-v1.json"
PRODUCTS = HERE / "nxp-official-pilot-products-v1.json"
URL_RE = re.compile(r"^/products/MCX-([ACELNW])[A-Za-z0-9-]+$", re.I)

def insist(ok: bool, explanation: str) -> None:
    if not ok:
        raise ValueError(explanation)

def official(url: str) -> bool:
    p = urlsplit(url)
    return p.scheme == "https" and p.hostname in {"www.nxp.com", "nxp.com"}

def hash_text(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def normalize_leads(urls: list[str], series: str) -> list[str]:
    links: set[str] = set()
    for value in urls:
        # NXP indexes also link to community, partners and documents.
        # Ignore foreign navigation links; they are not MCU product leads.
        if not official(value):
            continue
        parts = urlsplit(value)
        m = URL_RE.fullmatch(parts.path)
        if m and m.group(1).upper() == series:
            links.add("https://www.nxp.com" + parts.path)
    return sorted(links)

def audit(page, source: dict, product_paths: set[str], output: Path, browser_version: str) -> dict:
    url = source["url"]
    insist(official(url), "non-official NXP series index")
    response = page.goto(url, wait_until="domcontentloaded", timeout=90000)
    insist(response is not None and response.status == 200, "official index HTTP failure")
    insist(official(page.url), "series index redirected off NXP")
    page.wait_for_timeout(3500)
    raw = page.content()
    (output/"rendered-index.html").write_text(raw, encoding="utf-8")
    body = page.locator("body").inner_text(timeout=15000)
    insist(source["heading"] in body, "official series products heading missing")
    discovered = page.locator("a[href]").evaluate_all(
        """els => els.map(el => {
          try { return new URL(el.getAttribute('href'), location.href).href }
          catch (e) { return '' }
        }).filter(Boolean)"""
    )
    links = normalize_leads(discovered, source["series"])
    insist(len(links) > 0, "no MCX exact series product links found")
    matched = sorted(set(links) & product_paths)
    return {
        "schema_version": 1,
        "status": "official_mcx_series_link_candidates_observed",
        "manufacturer": "NXP",
        "series": source["series"],
        "source_url": page.url,
        "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "browser_version": browser_version,
        "raw_index_sha256": hash_text(raw),
        "visible_body_sha256": hash_text(body),
        "index_link_candidate_count": len(links),
        "pilot_page_links_in_index": matched,
        "not_yet_in_pilot": sorted(set(links) - product_paths),
        "candidate_product_page_links": links,
        "index_population_complete_proven": False,
        "commercial_exact_icpn_denominator": None,
        "production_write_authorized": False
    }

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--series", choices=list("ACELNW"), required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    products = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    insist(cfg["globally_complete"] is False and
           cfg["production_write_authorized"] is False, "source gate boundary")
    sources = {item["series"]: item for item in cfg["series"]}
    insist(len(sources) == 6, "index source drift")
    pilot = {"https://www.nxp.com"+urlsplit(x["url"]).path
             for x in products["products"] if x["id"].startswith("mcx-")}
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "blocked", "series": args.series}
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            try:
                page = b.new_page(locale="en-US")
                result = audit(page, sources[args.series], pilot, out, b.version)
            finally:
                b.close()
        print(json.dumps({"series": args.series, "linked_product_leads":result["index_link_candidate_count"],
                          "not_yet_in_pilot":len(result["not_yet_in_pilot"]), "status":result["status"]}, sort_keys=True))
        return 0
    except Exception as exc:
        result.update({"error_type":type(exc).__name__, "error":str(exc)[:600]})
        print(json.dumps(result, sort_keys=True))
        return 1
    finally:
        (out/"index-status.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")

if __name__ == "__main__":
    raise SystemExit(main())
