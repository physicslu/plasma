#!/usr/bin/env python3
"""Read-only NXP /part/ exact SKU manufacturer metadata acquisition, 341 at once.

This augments identity evidence; missing/ambiguous fields never become
inferred canonical Production metadata. Separate HIL/backend qualification.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
CANDIDATES = HERE / "nxp-active-353-bulk-candidates-v1.csv"
SNAPSHOT = HERE / "nxp-official-bounded-snapshot-2026-10-13-v1.json"
HEADING = re.compile(r"\b[A-Z][A-Z0-9._/-]{4,63}\b")
PKG = re.compile(r"(?m)^([A-Z][A-Z0-9-]*\d{2,4})\s*:")
TERM = re.compile(r"\b(\d{2,4})\s+(?:terminals?|pins?|balls?|leads?)\b", re.I)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def official(url: str) -> bool:
    p = urlsplit(url)
    return p.scheme == "https" and p.hostname in {"nxp.com", "www.nxp.com"}


def rows() -> list[str]:
    with CANDIDATES.open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    active = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["reconciliation"]["observed_active_icpns"]
    require(len(records) == len(active) == 353 and
            [r["icpn"] for r in records] == active,
            "NXP 353 frozen Exact ICPN matrix drift")
    require(all(r["production_publication_authorized"] == "false"
                and r["programming_backend_qualified"] == "false"
                for r in records), "NXP production/backend permission drift")
    missing = [r["icpn"] for r in records if
               r["metadata_gate"] == "manufacturer_metadata_missing"]
    require(len(missing) == 341, "NXP bulk metadata gap cardinality drift")
    require(all(re.fullmatch(r"[A-Z0-9]+", sku) for sku in missing),
            "unsafe manufacturer SKU for deterministic URL/artifact path")
    return missing


def value_from_rows(tables: list[list[str]], labels: tuple[str, ...]) -> str | None:
    found = set()
    for cells in tables:
        if len(cells) != 2:
            continue
        label = " ".join(cells[0].split())
        if label in labels:
            raw = " ".join(cells[1].split())
            if raw:
                found.add(raw)
    require(len(found) <= 1, f"contradictory official NXP product feature: {labels}")
    return next(iter(found), None)


def parse_official_part(body: str, table_rows: list[list[str]], sku: str,
                        headings: list[str]) -> dict:
    """Extraction only; never infer flash/temperature from ordering suffix."""
    require(sku in HEADING.findall(body), "exact NXP commercial part absent from page")
    matched = any(h.strip().upper() == sku for h in headings)
    # A suffix URL can redirect to a parent part. Parent specs must NOT
    # masquerade as evidence for the requested exact commercial SKU.
    require(matched, "official part heading does not match requested exact SKU")
    package_code = package_pins = None
    if matched:
        m = re.search(r"(?m)^Package\s*$([\s\S]*?)(?=^Buy Options\s*$|^Operating Features\s*$)", body, re.M)
        if m:
            pkg = PKG.search(m.group(1).strip())
            if pkg:
                package_code = pkg.group(1)
                pin_match = TERM.search(m.group(1)[pkg.start():pkg.start()+250])
                if pin_match:
                    package_pins = int(pin_match.group(1))
                    # Require pack name/description agree on terminal count.
                    name_digits = re.search(r"(\d{2,4})$", package_code)
                    require(not name_digits or int(name_digits.group(1)) == package_pins,
                            "NXP official package terminal count disagreement")
    flash = value_from_rows(table_rows, ("Flash (kB)",))
    ambient = value_from_rows(table_rows, (
        "Ambient Operating Temperature (Min to Max) (℃)",
        "Ambient Operating Temperature (Min to Max) (°C)",
    ))
    junction = value_from_rows(table_rows, (
        "Junction Temperature (Min to Max) (℃)",
        "Junction Temperature (Min to Max) (°C)",
    ))
    flash_kb = None
    if flash is not None:
        require(re.fullmatch(r"\d{1,7}", flash) is not None,
                "official flash parameter is not an exact numeric kB value")
        flash_kb = int(flash)
        require(flash_kb > 0, "invalid NXP official flash capacity")
    for val in (ambient, junction):
        if val is not None:
            require(re.fullmatch(r"-?\d+(?:\.\d+)?\s+to\s+-?\d+(?:\.\d+)?", val)
                    is not None, "unsupported official temperature range")
    return {
        "heading_matches_exact_sku": matched,
        "package_raw": package_code,
        "package_terminals": package_pins,
        "flash_kb_raw": flash_kb,
        "ambient_temperature_raw": ambient,
        "junction_temperature_raw": junction,
        "manufacturer_metadata_fields_observed": sum(x is not None for x in
            (package_code, package_pins, flash_kb, ambient)),
        "canonical_metadata_admission_authorized": False,
        "programming_backend_qualified": False,
    }


def capture(page, sku: str, out: Path) -> dict:
    url = f"https://www.nxp.com/part/{sku}"
    require(official(url), "source URL non-manufacturer")
    response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    require(response is not None and response.status == 200, "NXP exact part not HTTP 200")
    require(official(page.url) and
            urlsplit(page.url).path.lower() == f"/part/{sku}".lower(),
            "NXP exact part redirected to another identity or unauthorized route")
    page.wait_for_timeout(2400)
    html = page.content()
    body = page.locator("body").inner_text(timeout=15000)
    headings = page.locator("h1").all_inner_texts()
    table_rows = [tr.locator("td").all_inner_texts()
                  for tr in page.locator("tr").all()
                  if tr.locator("td").count() == 2]
    data = parse_official_part(body, table_rows, sku, headings)
    source_sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
    file_path = out / f"{sku}.html.gz"
    with gzip.open(file_path, "wb") as gz:
        gz.write(html.encode("utf-8"))
    return {
        "icpn": sku, "status": "official_nxp_part_metadata_observed",
        "source_url": page.url, "source_sha256": source_sha,
        "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **data,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--shards", type=int, default=8)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    require(args.shards == 8 and 0 <= args.shard < 8,
            "NXP metadata eight-shard contract drift")
    all_skus = rows()
    selected = [sku for i, sku in enumerate(all_skus) if i % args.shards == args.shard]
    require(len(selected) in (42, 43), "NXP 341-row shard size drift")
    args.output.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(locale="en-US")
            page = ctx.new_page()
            for i, sku in enumerate(selected, 1):
                try:
                    item = capture(page, sku, args.output)
                except Exception as exc:
                    item = {
                        "icpn": sku, "status": "blocked_source_or_schema",
                        "source_url": f"https://www.nxp.com/part/{sku}",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:400],
                        "canonical_metadata_admission_authorized": False,
                    }
                results.append(item)
                print(json.dumps({"shard": args.shard, "index": i,
                                  "icpn": sku, "status": item["status"],
                                  "fields": item.get("manufacturer_metadata_fields_observed", 0)},
                                 sort_keys=True), flush=True)
            ctx.close()
        finally:
            browser.close()
    payload = {
        "schema_version": 1,
        "scope": "341 previously metadata-unreviewed official NXP Active exact SKUs",
        "manufacturer": "NXP",
        "shard": args.shard, "shard_count": args.shards,
        "requested": len(selected),
        "observed": sum(x["status"] == "official_nxp_part_metadata_observed" for x in results),
        "blocked": sum(x["status"] == "blocked_source_or_schema" for x in results),
        "production_write_authorized": False,
        "results": results,
    }
    (args.output / "metadata-shard.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
