#!/usr/bin/env python3
"""Fail-closed one-time ST eStore STM32C5 category evidence collector (research-only).

The 18-page/172-Active count is a publicly observed *category facet* and is
NOT independently verified exact-ICPN completeness until this run succeeds.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

URL = ("https://estore.st.com/en/products/microcontrollers-microprocessors/"
       "stm32-32-bit-arm-cortex-mcus/stm32-mainstream-mcus/stm32c5-series.html")
PAGES, COUNT, SIZE_LIMIT = 18, 172, 6 * 1024 * 1024
PART = re.compile(r"\bSTM32C5[A-Z0-9]{5,20}\b")
NEGATIVE = re.compile(r"\b(NRND|Obsolete|Discontinued|Proposal|Preview)\b", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


class CategoryCards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.depth = 0
        self.hidden = 0
        self.cards = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "li":
            classes = set(dict(attrs).get("class", "").lower().split())
            if self.current is None and "product-item" in classes:
                self.current, self.depth = [], 1
            elif self.current is not None:
                self.depth += 1

    def handle_data(self, data):
        if self.hidden or not data.strip():
            return
        self.text.append(data.strip())
        if self.current is not None:
            self.current.append(data.strip())

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.hidden:
            self.hidden -= 1
        if tag == "li" and self.current is not None:
            self.depth -= 1
            if self.depth == 0:
                self.cards.append(" ".join(self.current))
                self.current = None


def parse_html(raw: bytes, page: int) -> list[str]:
    check(1 <= page <= PAGES, "unexpected pagination index")
    check(len(raw) <= SIZE_LIMIT, "oversized HTML")
    parser = CategoryCards()
    parser.feed(raw.decode("utf-8-sig"))
    check(parser.current is None, "unterminated product card")
    text = " ".join(parser.text)
    check("STM32C5 series" in text, "not the manufacturer C5 category")
    check(re.search(r"\bof\s+18\b", text), "pagination is not 18")
    check(re.search(r"\bActive\s*172\s*item", text, re.I),
          "official page Active facet no longer reports 172 items")
    expected = 2 if page == 18 else 10
    check(len(parser.cards) == expected,
          f"page {page}: expected {expected} product cards, got {len(parser.cards)}")
    result = []
    for card in parser.cards:
        identities = set(PART.findall(card))
        check(len(identities) == 1, "missing, ambiguous or nonexact product card")
        check(re.search(r"\bActive\b", card, re.I) and not NEGATIVE.search(card),
              "card has unknown/non-Active marketing status")
        result.append(next(iter(identities)))
    check(len(result) == len(set(result)), "duplicate commercial code on page")
    return result


def fetch(page: int) -> tuple[bytes, str]:
    request = Request(f"{URL}?p={page}", headers={
        "User-Agent": "Mozilla/5.0 (PlasmaResearch-ST-C5-v0.6; 18-page-one-time-audit)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urlopen(request, timeout=25) as response:
        final = response.geturl()
        parts = urlsplit(final)
        check(response.status == 200 and parts.scheme == "https" and
              parts.hostname == "estore.st.com" and "stm32c5-series" in parts.path,
              "blocked response or redirect outside ST C5 category")
        check("text/html" in response.headers.get("Content-Type", "").lower(),
              "vendor returned a non-HTML response")
        raw = response.read(SIZE_LIMIT + 1)
    check(5000 <= len(raw) <= SIZE_LIMIT, "blocked, truncated or oversized response")
    return raw, final


def collect(out: Path, interval: float = 1.0) -> dict:
    check(0.5 <= interval <= 5.0, "request interval must remain polite")
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw").mkdir(exist_ok=True)
    manifest = {
        "schema_version": 1, "scope": "ST official C5 eStore category only",
        "started_utc": now(), "finished_utc": None,
        "status": "ACQUISITION_BLOCKED", "expected_pages": PAGES,
        "observed_vendor_active_facet": COUNT, "pages": [], "error": None,
        "manufacturer_as_of_date_certified": False,
        "complete_whole_st_portfolio": False, "production_write_authorized": False,
        "actual_whole_st_coverage": None,
    }
    rows = []
    try:
        for page in range(1, PAGES + 1):
            if page > 1:
                time.sleep(interval)
            raw, final = fetch(page)
            filename = f"page-{page:02}.html"
            (out / "raw" / filename).write_bytes(raw)  # raw bytes retained BEFORE parsing
            entry = {"page": page, "url": final, "file": f"raw/{filename}",
                     "raw_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                     "captured_utc": now()}
            manifest["pages"].append(entry)
            exact = parse_html(raw, page)
            entry["exact_active_rows"] = len(exact)
            for mpn in exact:
                rows.append((mpn, "Active", page, final, entry["sha256"], entry["captured_utc"]))
            print(f"C5 page {page:02}/18: exact rows {len(exact)}, SHA256 {entry['sha256']}", flush=True)
        names = [row[0] for row in rows]
        check(len(names) == COUNT and len(set(names)) == COUNT,
              "incomplete, inconsistent or overlapping 172-page-category identity set")
        check("STM32C531CBT6" in names, "previously verified C5 sentinel not found")
        with (out / "observed-active-exact-c5.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["exact_icpn", "marketing_status", "page", "source_url",
                             "source_raw_sha256", "captured_utc"])
            writer.writerows(sorted(rows))
        manifest["observed_exact_active_mpn_count"] = COUNT
        manifest["observed_exact_set_sha256"] = hashlib.sha256(
            ("\n".join(sorted(names)) + "\n").encode()).hexdigest()
        manifest["status"] = "OBSERVED_C5_CATEGORY_CANDIDATE_REQUIRES_INDEPENDENT_REVIEW"
    except Exception as error:
        manifest["error"] = f"{type(error).__name__}: {error}"
        print(f"ACQUISITION_BLOCKED: {manifest['error']}", file=sys.stderr)
    finally:
        manifest["finished_utc"] = now()
        (out / "capture-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--output", type=Path, required=True)
    arg.add_argument("--interval-seconds", type=float, default=1.0)
    options = arg.parse_args()
    result = collect(options.output, options.interval_seconds)
    print("Result:", result["status"])
    return 0 if result["status"].startswith("OBSERVED_C5_CATEGORY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
