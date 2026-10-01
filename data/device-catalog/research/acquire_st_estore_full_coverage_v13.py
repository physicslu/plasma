#!/usr/bin/env python3
"""Acquire and reconcile the complete public ST eStore STM32 MCU portfolio.

Research-only Catalog coverage audit. The source universe is four official
STM32 MCU eStore parent categories. Each category is exhaustively paginated,
every product card must contain exactly one exact STM32 MPN and one recognized
marketing state, and observed cardinalities must reconcile to the manufacturer's
Marketing Status facet.

This does not claim backend/programming/HIL support and cannot write Production.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
SIZE_LIMIT = 8 * 1024 * 1024
PART = re.compile(r"\bSTM32[A-Z0-9]{6,24}\b")
STATUS_TOKEN = re.compile(r"\b(Active|NRND)\b", re.I)

SEGMENTS = {
    "mainstream": {
        "title": "STM32 Mainstream MCUs",
        "url": "https://estore.st.com/en/products/microcontrollers-microprocessors/"
               "stm32-32-bit-arm-cortex-mcus/stm32-mainstream-mcus.html",
    },
    "high-performance": {
        "title": "STM32 High Performance MCUs",
        "url": "https://estore.st.com/en/products/microcontrollers-microprocessors/"
               "stm32-32-bit-arm-cortex-mcus/stm32-high-performance-mcus.html",
    },
    "ultra-low-power": {
        "title": "STM32 Ultra Low Power MCUs",
        "url": "https://estore.st.com/en/products/microcontrollers-microprocessors/"
               "stm32-32-bit-arm-cortex-mcus/stm32-ultra-low-power-mcus.html",
    },
    "wireless": {
        "title": "STM32 Wireless MCUs",
        "url": "https://estore.st.com/en/products/microcontrollers-microprocessors/"
               "stm32-32-bit-arm-cortex-mcus/stm32-wireless-mcus.html",
    },
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class Cards(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current: list[str] | None = None
        self.depth = 0
        self.hidden = 0
        self.cards: list[str] = []
        self.text: list[str] = []

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
        value = " ".join(data.split())
        self.text.append(value)
        if self.current is not None:
            self.current.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.hidden:
            self.hidden -= 1
        if tag == "li" and self.current is not None:
            self.depth -= 1
            if self.depth == 0:
                self.cards.append(" ".join(self.current))
                self.current = None


def fetch(url: str, agent: str) -> tuple[bytes, str]:
    request = Request(url, headers={
        "User-Agent": f"Mozilla/5.0 (PlasmaResearch-{agent}; ST-coverage-audit)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    last = None
    for attempt, backoff in enumerate((0, 2, 5, 10), start=1):
        if backoff:
            time.sleep(backoff)
        try:
            with urlopen(request, timeout=30) as response:
                final = response.geturl()
                parts = urlsplit(final)
                check(response.status == 200 and parts.scheme == "https" and
                      parts.hostname == "estore.st.com",
                      "response redirected outside official ST eStore")
                check("text/html" in response.headers.get("Content-Type", "").lower(),
                      "manufacturer returned non-HTML")
                raw = response.read(SIZE_LIMIT + 1)
            check(5000 <= len(raw) <= SIZE_LIMIT,
                  "blocked, truncated or oversized manufacturer response")
            return raw, final
        except HTTPError as error:
            last = error
            if error.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise
            print(f"Transient HTTP {error.code}; bounded retry {attempt}/4: {url}",
                  file=sys.stderr, flush=True)
        except URLError as error:
            last = error
            if attempt == 4:
                raise
            print(f"Transient URL error; bounded retry {attempt}/4: {url}",
                  file=sys.stderr, flush=True)
    raise RuntimeError(f"retry exhausted: {last}")


def parse_page(raw: bytes, segment: str, page: int) -> dict:
    cfg = SEGMENTS[segment]
    parser = Cards()
    parser.feed(raw.decode("utf-8-sig"))
    check(parser.current is None, "unterminated product card")
    text = " ".join(parser.text)
    check(cfg["title"] in text, f"{segment}: wrong manufacturer category")

    page_match = re.search(r"\bof\s+(\d+)\b", text)
    active_match = re.search(r"\bActive\s*(\d+)\s*item", text, re.I)
    nrnd_match = re.search(r"\bNRND\s*(\d+)\s*item", text, re.I)
    check(page_match is not None and active_match is not None,
          f"{segment}: missing pagination/Active facet")
    pages = int(page_match.group(1))
    active = int(active_match.group(1))
    nrnd = int(nrnd_match.group(1)) if nrnd_match else 0
    total = active + nrnd
    check(1 <= pages <= 250 and 1 <= active <= 2500 and 0 <= nrnd <= 500,
          f"{segment}: implausible facet dimensions")
    check(pages == math.ceil(total / 10),
          f"{segment}: pages={pages} does not reconcile Active+NRND={total}")
    check(1 <= page <= pages, "page outside category pagination")

    rows = []
    for card in parser.cards:
        ids = set(PART.findall(card.upper()))
        check(len(ids) == 1, f"{segment} page {page}: ambiguous/nonexact card identity")
        statuses = {m.group(1).upper() for m in STATUS_TOKEN.finditer(card)}
        check(statuses in ({"ACTIVE"}, {"NRND"}),
              f"{segment} page {page}: ambiguous/unrecognized marketing state {statuses}")
        rows.append((next(iter(ids)), next(iter(statuses))))
    expected = 10 if page < pages else total - 10 * (pages - 1)
    check(len(rows) == expected and len({x[0] for x in rows}) == len(rows),
          f"{segment} page {page}: card cardinality/duplicates mismatch")
    return {"pages": pages, "active": active, "nrnd": nrnd, "total": total, "rows": rows}


def acquire_segment(segment: str, out: Path, interval: float) -> dict:
    check(segment in SEGMENTS, "unknown segment")
    check(0.5 <= interval <= 5.0, "request pacing outside bounded policy")
    cfg = SEGMENTS[segment]
    out.mkdir(parents=True, exist_ok=True)
    raw_dir = out / "raw"
    raw_dir.mkdir(exist_ok=True)

    first_raw, first_url = fetch(cfg["url"] + "?p=1", f"ST-{segment}-v1.3")
    first = parse_page(first_raw, segment, 1)
    expected_shape = (first["pages"], first["active"], first["nrnd"], first["total"])
    rows = []
    ledger = []

    for page in range(1, first["pages"] + 1):
        if page == 1:
            raw, final, parsed = first_raw, first_url, first
        else:
            time.sleep(interval)
            raw, final = fetch(cfg["url"] + f"?p={page}", f"ST-{segment}-v1.3")
            parsed = parse_page(raw, segment, page)
            check((parsed["pages"], parsed["active"], parsed["nrnd"], parsed["total"]) ==
                  expected_shape, f"{segment}: facets changed during acquisition")
        name = f"page-{page:03}.html"
        (raw_dir / name).write_bytes(raw)
        captured = now()
        digest = sha256(raw)
        ledger.append({
            "page": page, "source_url": final, "raw_file": f"raw/{name}",
            "raw_bytes": len(raw), "sha256": digest, "captured_utc": captured,
            "card_count": len(parsed["rows"]),
        })
        for mpn, status in parsed["rows"]:
            rows.append((mpn, status, page, final, digest, captured))
        print(f"{segment} page {page:03}/{first['pages']}: "
              f"{len(parsed['rows'])} cards", flush=True)

    identities = [r[0] for r in rows]
    check(len(identities) == first["total"] and len(set(identities)) == first["total"],
          f"{segment}: full listed exact set does not reconcile")
    active_names = sorted(r[0] for r in rows if r[1] == "ACTIVE")
    nrnd_names = sorted(r[0] for r in rows if r[1] == "NRND")
    check(len(active_names) == first["active"] and len(nrnd_names) == first["nrnd"],
          f"{segment}: observed marketing states do not reconcile to facets")

    for status, names in (("active", active_names), ("nrnd", nrnd_names)):
        (out / f"{status}-exact.txt").write_text(
            "\n".join(names) + ("\n" if names else ""), encoding="utf-8")
    with (out / "observed-exact.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["exact_icpn", "marketing_status", "page", "source_url",
                         "source_raw_sha256", "captured_utc"])
        writer.writerows(sorted(rows))

    result = {
        "schema_version": 1,
        "segment": segment,
        "title": cfg["title"],
        "source_url": cfg["url"],
        "captured_utc": now(),
        "page_count": first["pages"],
        "active_exact_count": len(active_names),
        "nrnd_exact_count": len(nrnd_names),
        "listed_exact_count": len(identities),
        "active_exact_set_sha256": sha256(("\n".join(active_names) + "\n").encode()),
        "nrnd_exact_set_sha256": (
            sha256(("\n".join(nrnd_names) + "\n").encode()) if nrnd_names else None
        ),
        "page_ledger": ledger,
        "production_write_authorized": False,
    }
    (out / "segment-summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SEGMENT_RESULT " + json.dumps({
        "segment": segment, "pages": result["page_count"],
        "active": result["active_exact_count"], "nrnd": result["nrnd_exact_count"],
        "active_sha256": result["active_exact_set_sha256"],
    }, sort_keys=True), flush=True)
    return result


def production_set() -> tuple[set[str], dict[str, int]]:
    raw = PRODUCTION.read_bytes()
    payload = json.loads(raw)
    sources = payload.get("sources")
    check(payload.get("status") == "production" and isinstance(sources, list),
          "invalid Production manifest")
    check(git_blob(raw) == "c8012b211a28b0a7811bfe978e7e697bc169c6f3" and
          len(sources) == 23 and sum(int(x["row_count"]) for x in sources) == 2683,
          "frozen Production baseline drifted")
    names: set[str] = set()
    family_counts = {}
    for source in sources:
        path = (PRODUCTION.parent / source["path"]).resolve()
        check(path.is_relative_to(ROOT) and path.is_file(), "Production source path invalid")
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        exact = [r["icpn"].strip().upper() for r in rows]
        check(len(exact) == int(source["row_count"]) and len(set(exact)) == len(exact),
              f"{source['family']}: Production source cardinality drift")
        before = len(names)
        names.update(exact)
        check(len(names) == before + len(exact), "cross-family Production duplicate")
        family_counts[source["family"]] = len(exact)
    return names, family_counts


def aggregate(root: Path, out: Path) -> dict:
    production, family_counts = production_set()
    active_sets, nrnd_sets, segment_rows = {}, {}, {}
    for segment in SEGMENTS:
        base = root / segment
        summary = json.loads((base / "segment-summary.json").read_text(encoding="utf-8"))
        check(summary["segment"] == segment and summary["production_write_authorized"] is False,
              f"{segment}: invalid segment summary")
        active = {x.strip() for x in (base / "active-exact.txt").read_text(
            encoding="utf-8").splitlines() if x.strip()}
        nrnd = {x.strip() for x in (base / "nrnd-exact.txt").read_text(
            encoding="utf-8").splitlines() if x.strip()}
        check(len(active) == summary["active_exact_count"] and
              len(nrnd) == summary["nrnd_exact_count"] and not (active & nrnd),
              f"{segment}: set/summary mismatch")
        check(sha256(("\n".join(sorted(active)) + "\n").encode()) ==
              summary["active_exact_set_sha256"], f"{segment}: Active set digest mismatch")
        active_sets[segment], nrnd_sets[segment] = active, nrnd
        segment_rows[segment] = {
            "active": len(active), "nrnd": len(nrnd),
            "listed": len(active) + len(nrnd), "pages": summary["page_count"],
            "active_sha256": summary["active_exact_set_sha256"],
        }

    active_all = set().union(*active_sets.values())
    nrnd_all = set().union(*nrnd_sets.values())
    check(sum(map(len, active_sets.values())) == len(active_all),
          "same Active exact MPN appears in multiple top-level segments")
    check(sum(map(len, nrnd_sets.values())) == len(nrnd_all) and not (active_all & nrnd_all),
          "cross-segment NRND collision or Active/NRND conflict")

    covered = production & active_all
    missing = active_all - production
    production_not_active = production - active_all
    production_now_nrnd = production & nrnd_all
    production_not_estore_listed = production - active_all - nrnd_all

    out.mkdir(parents=True, exist_ok=True)
    for filename, values in (
        ("active-exact-all.txt", active_all),
        ("active-missing-from-production.txt", missing),
        ("production-current-active-intersection.txt", covered),
        ("production-not-current-active.txt", production_not_active),
        ("production-now-nrnd.txt", production_now_nrnd),
        ("production-not-estore-listed.txt", production_not_estore_listed),
    ):
        (out / filename).write_text(
            "\n".join(sorted(values)) + ("\n" if values else ""), encoding="utf-8")

    result = {
        "schema_version": 1,
        "audit_id": "st-estore-whole-stm32-active-exact-coverage-v1.3",
        "record_state": "RESEARCH_ONLY_NOT_PRODUCTION_ADMISSION",
        "captured_utc": now(),
        "scope": "ST eStore STM32 Mainstream + High Performance + Ultra Low Power + Wireless MCU categories",
        "segment_results": segment_rows,
        "estore_active_exact_denominator": len(active_all),
        "estore_nrnd_exact_count": len(nrnd_all),
        "estore_listed_exact_total": len(active_all) + len(nrnd_all),
        "production_exact_total": len(production),
        "production_current_active_intersection": len(covered),
        "active_exact_missing_from_production": len(missing),
        "production_not_current_active": len(production_not_active),
        "production_now_nrnd": len(production_now_nrnd),
        "production_not_estore_listed": len(production_not_estore_listed),
        "estore_active_catalog_coverage_percent": round(len(covered) / len(active_all) * 100, 4),
        "production_family_counts": family_counts,
        "active_exact_set_sha256": sha256(
            ("\n".join(sorted(active_all)) + "\n").encode()),
        "missing_active_exact_set_sha256": sha256(
            ("\n".join(sorted(missing)) + "\n").encode()),
        "claims": {
            "backend_support_implied": False,
            "physical_validation_implied": False,
            "production_write_authorized": False,
            "estore_surface_is_equated_to_all_possible_non_estore_ST_sales_channels": False,
            "lifecycle_of_production_not_estore_listed_is_inferred": False,
        },
        "next_gate": (
            "Review every Active-minus-Production exact MPN as a Catalog identity candidate; "
            "recheck Production-not-Active rows against ST Quality & Reliability before lifecycle "
            "changes; only then prepare separately approved Catalog publication batches."
        ),
    }
    (out / "coverage-summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("COVERAGE_RESULT " + json.dumps({
        k: result[k] for k in (
            "estore_active_exact_denominator", "estore_nrnd_exact_count",
            "production_exact_total", "production_current_active_intersection",
            "active_exact_missing_from_production", "production_not_current_active",
            "production_now_nrnd", "production_not_estore_listed",
            "estore_active_catalog_coverage_percent",
        )
    }, sort_keys=True), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--segment", choices=sorted(SEGMENTS))
    group.add_argument("--aggregate-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=0.8)
    args = parser.parse_args()
    if args.segment:
        acquire_segment(args.segment, args.output, args.interval_seconds)
    else:
        aggregate(args.aggregate_root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
