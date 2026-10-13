#!/usr/bin/env python3
"""Live read-only NXP official Package/Quality snapshot, bounded to pinned URLs.

This is a manufacturer-evidence acquisition pilot, NOT a full portfolio crawl.
No external command execution, no Production files, no device programming.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "nxp-official-pilot-products-v1.json"
CODES = re.compile(r"\b(?:MCX[A-Z0-9]{5,22}|MKL25Z[A-Z0-9]{3,18}|LPC[A-Z0-9]{5,22}|K32[A-Z0-9]{5,22}|MIMXRT[A-Z0-9]{5,22}|KW45[A-Z0-9]{5,22})\b")
STATUS = re.compile(r"\b(No Longer Manufactured|Not Recommended for New Designs|Discontinued|Qualification|Obsolete|NRND|Active)\b", re.I)
KNOWN = {
    "active": "Active",
    "qualification": "Qualification",
    "nrnd": "NRND",
    "not recommended for new designs": "NRND",
    "obsolete": "Obsolete",
    "discontinued": "Discontinued",
    "no longer manufactured": "No Longer Manufactured",
}

def require(value: bool, label: str) -> None:
    if not value:
        raise ValueError(label)

def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def official(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname in {"www.nxp.com", "nxp.com"}

def exact_code(first_cell_text: str, prefix: str) -> str | None:
    codes = {value for value in CODES.findall(first_cell_text.upper()) if value.startswith(prefix)}
    require(len(codes) <= 1, "ambiguous exact NXP ordering code in product cell")
    return next(iter(codes), None)

def lifecycle(row_text: str) -> str | None:
    states = {KNOWN[x.lower()] for x in STATUS.findall(row_text)}
    require(len(states) <= 1, "contradictory NXP lifecycle in row")
    return next(iter(states), None)

def orderable_from_environment_cells(cell_texts: list[str], prefix: str) -> tuple[str, str] | None:
    """Find the *orderable* material-declaration SKU immediately before Status.

    The first Part/Package cell is often a rowspan/group label. For example
    MCXC041VFK can group separate MCXC041VFK and MCXC041VFKR orderable
    material-declaration rows. Continuation rows omit the group cell.
    Quality Information rows have no official Status cell and are ignored.
    """
    matches = []
    for i in range(1, len(cell_texts)):
        status_text = " ".join(cell_texts[i].split())
        state = lifecycle(status_text)
        if state is None or status_text.casefold() not in KNOWN:
            continue
        code = exact_code(cell_texts[i - 1], prefix)
        if code:
            matches.append((code, state))
    require(len(matches) <= 1, "ambiguous orderable SKU/status in NXP row")
    return matches[0] if matches else None

def consolidate_lifecycle_rows(grouped: dict) -> list[dict]:
    """Keep all source evidence for same-state duplicates, reject any conflict."""
    rows = []
    for icpn, records in sorted(grouped.items()):
        require(len(records) > 0, "empty grouped NXP lifecycle evidence")
        require(all(record["icpn"] == icpn for record in records),
                "part number/evidence row disagreement")
        statuses = {record["lifecycle"] for record in records}
        require(len(statuses) == 1, "same exact IC has contradictory marketing states")
        consolidated = dict(records[0])
        consolidated["official_lifecycle_row_occurrences"] = len(records)
        consolidated["row_evidence_sha256s"] = sorted({
            record["evidence_sha256"] for record in records
        })
        consolidated["row_markup_sha256s"] = sorted({
            record["row_markup_sha256"] for record in records
        })
        rows.append(consolidated)
    return rows

def acquire(page, source: dict, out: Path, browser_version: str) -> dict:
    url, prefix = source["url"], source["prefix"]
    require(official(url), "untrusted acquisition URL")
    response = page.goto(url, wait_until="domcontentloaded", timeout=90000)
    require(response is not None and response.status == 200, "official NXP page not HTTP 200")
    require(official(page.url), "unexpected redirect away from NXP")
    page.wait_for_timeout(4500)
    html = page.content()
    (out / "rendered-page.html").write_text(html, encoding="utf-8")
    body = page.locator("body").inner_text(timeout=20000)
    require("Package/Quality" in body and "Environmental Information" in body,
            "manufacturer lifecycle source surface unavailable")
    grouped = defaultdict(list)
    # NXP renders its Package/Quality environmental table as HTML rows. The
    # other Quality Information table lacks Marketing Status, so ignore it.
    for tr in page.locator("tr").all():
        cells = tr.locator("td")
        if cells.count() < 2:
            continue
        orderable = orderable_from_environment_cells(cells.all_inner_texts(), prefix)
        if orderable is None:
            continue
        code, state = orderable
        visible = tr.inner_text(timeout=3000)
        markup = tr.evaluate("(node) => node.outerHTML")
        grouped[code].append({
            "icpn": code,
            "lifecycle": state,
            "source_url": page.url,
            "evidence_sha256": digest(visible),
            "row_markup_sha256": digest(markup),
            "visible_row_excerpt": visible[:450],
        })
    require(source["must_include"] in grouped, "frozen representative missing")
    rows = consolidate_lifecycle_rows(grouped)
    require(len(rows) > 0, "no exact orderable identities on NXP product page")
    result = {
        "schema_version": 1,
        "acquisition_id": source["id"],
        "segment": source["segment"],
        "manufacturer": "NXP",
        "status": "bounded_official_product_page_observed",
        "source_url": page.url,
        "source_http_status": response.status,
        "source_population_complete": False,
        "global_active_denominator_claimed": False,
        "official_count_authority": None,
        "browser_version": browser_version,
        "page_title": page.title(),
        "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rendered_dom_sha256": digest(html),
        "visible_body_sha256": digest(body),
        "source_product_row_count": len(rows),
        "active_exact_count": sum(r["lifecycle"] == "Active" for r in rows),
        "qualification_exact_count": sum(r["lifecycle"] == "Qualification" for r in rows),
        "rows": rows,
    }
    (out / "acquisition.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(cfg["global_active_denominator_claimed"] is False, "global denominator policy changed")
    require(cfg["production_write_authorized"] is False, "read-only acquisition policy changed")
    products = {x["id"]: x for x in cfg["products"]}
    require(len(products) == len(cfg["products"]) and args.product in products, "unknown NXP product")
    result = {"status": "blocked", "product": args.product, "source_url": products[args.product]["url"]}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(locale="en-US")
                page = ctx.new_page()
                result = acquire(page, products[args.product], args.output, browser.version)
                ctx.close()
            finally:
                browser.close()
        print(json.dumps({"product": args.product, "status": result["status"],
                          "total": result["source_product_row_count"],
                          "active": result["active_exact_count"],
                          "qualification": result["qualification_exact_count"]}, sort_keys=True))
        return 0
    except Exception as exc:
        result.update({"error_type": type(exc).__name__, "error": str(exc)[:700]})
        print(json.dumps(result, sort_keys=True))
        return 1
    finally:
        (args.output / "status.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if __name__ == "__main__":
    raise SystemExit(main())
