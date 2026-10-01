#!/usr/bin/env python3
"""Research-only live acquisition for ST families absent from Plasma Production.

Acquires exact Active commercial MPNs from official ST public surfaces only:
- STM32H5, STM32N6, STM32WB0: complete ST eStore category pagination.
- STM32WL3: official ST product-selector base-device set, then each base device's
  Quality & Reliability table.

No Production publication, backend/programming support, or physical qualification.
Raw source bytes are retained before parsing.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, re, sys, time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
C5_LOCKED = Path(__file__).resolve().parent / "st-c5-estore-172-active-exact-mpn-v0.7.txt"
SIZE_LIMIT = 7 * 1024 * 1024
NEGATIVE = re.compile(r"\b(NRND|Obsolete|Discontinued|Proposal|Preview|Evaluation)\b", re.I)

ESTORE = {
    "STM32H5": {
        "url": "https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-high-performance-mcus/stm32h5-series.html",
        "pattern": re.compile(r"\bSTM32H5[A-Z0-9]{5,20}\b"),
        "title": "STM32H5 Series", "sentinel": "STM32H503CBT6",
    },
    "STM32N6": {
        "url": "https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-high-performance-mcus/stm32n6-series.html",
        "pattern": re.compile(r"\bSTM32N6[A-Z0-9]{5,20}\b"),
        "title": "STM32N6 Series", "sentinel": "STM32N657A0H3Q",
    },
    "STM32WB0": {
        "url": "https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-wireless-mcus/stm32wb0-series.html",
        "pattern": re.compile(r"\bSTM32WB0[A-Z0-9]{5,20}\b"),
        "title": "STM32WB0 Series", "sentinel": "STM32WB05KZV6TR",
    },
}
WL3_SELECTOR = "https://www.st.com/en/microcontrollers-microprocessors/stm32wl3x/products.html"
WL3_BASES = {
    "STM32WL3RK8", "STM32WL33KC", "STM32WL3RKB", "STM32WL33C8",
    "STM32WL33CB", "STM32WL33CC", "STM32WL31K8", "STM32WL31KB",
    "STM32WL31C8", "STM32WL33K8", "STM32WL33KB", "STM32WL31CB",
    "STM32WL30K8", "STM32WL30KB",
}
WL3_EXACT = re.compile(r"\bSTM32WL(?:3R|30|31|33)[A-Z0-9]{3,20}\b")

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def get(url: str, agent: str) -> tuple[bytes, str]:
    request = Request(url, headers={
        "User-Agent": f"Mozilla/5.0 (PlasmaResearch-{agent}; catalog-coverage-audit)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urlopen(request, timeout=30) as response:
        final = response.geturl()
        parts = urlsplit(final)
        check(response.status == 200 and parts.scheme == "https" and
              parts.hostname in {"estore.st.com", "www.st.com"},
              "blocked response or redirect outside official ST domains")
        check("text/html" in response.headers.get("Content-Type", "").lower(),
              "manufacturer returned non-HTML")
        raw = response.read(SIZE_LIMIT + 1)
    check(5000 <= len(raw) <= SIZE_LIMIT, "blocked, truncated or oversized HTML")
    return raw, final

class Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.depth = self.hidden = 0
        self.cards, self.text = [], []

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

class LinksAndRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.href = None
        self.anchor = []
        self.links = []
        self.in_tr = False
        self.row, self.rows = [], []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "a" and not self.hidden:
            self.href = dict(attrs).get("href")
            self.anchor = []
        if tag == "tr" and not self.hidden:
            self.in_tr, self.row = True, []

    def handle_data(self, data):
        if self.hidden or not data.strip():
            return
        value = " ".join(data.split())
        if self.href is not None:
            self.anchor.append(value)
        if self.in_tr:
            self.row.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.hidden:
            self.hidden -= 1
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join(self.anchor)))
            self.href, self.anchor = None, []
        if tag == "tr" and self.in_tr:
            self.rows.append(" | ".join(self.row))
            self.in_tr, self.row = False, []

def parse_estore(raw: bytes, family: str, page: int) -> tuple[list[str], int, int, int]:
    cfg = ESTORE[family]
    parser = Cards()
    parser.feed(raw.decode("utf-8-sig"))
    check(parser.current is None, "unterminated product card")
    text = " ".join(parser.text)
    check(cfg["title"] in text, f"not official {family} category")
    pm = re.search(r"\bof\s+(\d+)\b", text)
    am = re.search(r"\bActive\s*(\d+)\s*item", text, re.I)
    check(pm is not None and am is not None, "missing official pagination or Active facet")
    pages, active = int(pm.group(1)), int(am.group(1))
    check(1 <= pages <= 100 and 1 <= active <= 1000 and 1 <= page <= pages,
          "implausible category dimensions")
    names = []
    for card in parser.cards:
        ids = set(cfg["pattern"].findall(card))
        check(len(ids) == 1, f"{family} page {page}: ambiguous/nonexact product card")
        check(re.search(r"\bActive\b", card, re.I) and not NEGATIVE.search(card),
              f"{family} page {page}: card not Active-only")
        names.append(next(iter(ids)))
    check(names and len(names) == len(set(names)), f"{family} page {page}: empty/duplicate cards")
    return names, pages, active, len(parser.cards)

def acquire_estore(family: str, out: Path, interval: float) -> dict:
    cfg = ESTORE[family]
    dest, rawdir = out / family.lower(), out / family.lower() / "raw"
    rawdir.mkdir(parents=True, exist_ok=True)
    first, final = get(cfg["url"] + "?p=1", f"ST-{family}-v1.2")
    first_names, pages, active, page_size = parse_estore(first, family, 1)
    check(pages == math.ceil(active / page_size),
          f"{family}: pagination/card-size inconsistent with Active facet")
    rows, ledger = [], []
    for page in range(1, pages + 1):
        if page == 1:
            raw, page_url, names = first, final, first_names
        else:
            time.sleep(interval)
            raw, page_url = get(cfg["url"] + f"?p={page}", f"ST-{family}-v1.2")
            names, seen_pages, seen_active, seen_size = parse_estore(raw, family, page)
            check((seen_pages, seen_active) == (pages, active),
                  f"{family}: facet/pagination changed mid-acquisition")
            expected = page_size if page < pages else active - page_size * (pages - 1)
            check(seen_size == expected, f"{family}: unexpected page cardinality")
        filename = f"page-{page:02}.html"
        (rawdir / filename).write_bytes(raw)
        sha, captured = digest(raw), now()
        ledger.append({"page": page, "source_url": page_url, "raw_file": f"raw/{filename}",
                       "raw_bytes": len(raw), "sha256": sha,
                       "exact_active_rows": len(names), "captured_utc": captured})
        rows.extend((mpn, "Active", page, page_url, sha, captured) for mpn in names)
        print(f"{family} page {page:02}/{pages}: {len(names)} exact Active", flush=True)
    names = [r[0] for r in rows]
    check(len(names) == active and len(set(names)) == active,
          f"{family}: category set does not equal official Active facet")
    check(cfg["sentinel"] in names, f"{family}: previous official sentinel disappeared")
    with (dest / "observed-active-exact.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["exact_icpn", "marketing_status", "page", "source_url",
                    "source_raw_sha256", "captured_utc"])
        w.writerows(sorted(rows))
    return {"family": family, "surface": "ST official eStore category",
            "category_url": cfg["url"], "pages": pages, "active_facet": active,
            "exact_active_count": len(names),
            "exact_set_sha256": digest(("\n".join(sorted(names)) + "\n").encode()),
            "page_ledger": ledger, "exact_names": sorted(names)}

def selector_bases(raw: bytes) -> dict[str, str]:
    parser = LinksAndRows()
    parser.feed(raw.decode("utf-8-sig"))
    found = {}
    for href, anchor in parser.links:
        token = anchor.strip().upper()
        if token not in WL3_BASES:
            continue
        absolute = urljoin(WL3_SELECTOR, href)
        parts = urlsplit(absolute)
        check(parts.scheme == "https" and parts.hostname == "www.st.com" and
              parts.path.endswith("/" + token.lower() + ".html"),
              f"WL3 selector link mismatch: {token} {absolute}")
        check(token not in found or found[token] == absolute,
              "duplicate conflicting WL3 selector link")
        found[token] = absolute
    check(set(found) == WL3_BASES,
          f"WL3 selector base-device set drift: missing={sorted(WL3_BASES-set(found))}")
    return found

def qnr_active(raw: bytes, base: str) -> list[str]:
    parser = LinksAndRows()
    parser.feed(raw.decode("utf-8-sig"))
    decoded = raw.decode("utf-8-sig", errors="replace")
    check(base in decoded, f"WL3 page identity mismatch: {base}")
    names = []
    for row in parser.rows:
        ids = set(WL3_EXACT.findall(row.upper()))
        if not ids or "PRODUCT IS IN VOLUME PRODUCTION" not in row.upper():
            continue
        check(len(ids) == 1 and "ACTIVE" in row.upper() and not NEGATIVE.search(row),
              f"WL3 {base}: ambiguous/non-Active Q&R row")
        name = next(iter(ids))
        check(name.startswith(base), f"WL3 {base}: row belongs to another base: {name}")
        names.append(name)
    check(names and len(names) == len(set(names)),
          f"WL3 {base}: no unique Active Q&R exact rows")
    return sorted(names)

def acquire_wl3(out: Path, interval: float) -> dict:
    dest, rawdir = out / "stm32wl3", out / "stm32wl3" / "raw"
    rawdir.mkdir(parents=True, exist_ok=True)
    selector_raw, selector_final = get(WL3_SELECTOR, "ST-WL3-v1.2")
    (rawdir / "selector.html").write_bytes(selector_raw)
    bases = selector_bases(selector_raw)
    rows, ledger = [], []
    for index, base in enumerate(sorted(bases)):
        if index:
            time.sleep(interval)
        raw, final = get(bases[base], "ST-WL3-v1.2")
        names = qnr_active(raw, base)
        filename = base.lower() + ".html"
        (rawdir / filename).write_bytes(raw)
        sha, captured = digest(raw), now()
        ledger.append({"base_device": base, "source_url": final, "raw_file": f"raw/{filename}",
                       "raw_bytes": len(raw), "sha256": sha,
                       "exact_active_rows": len(names), "captured_utc": captured})
        rows.extend((mpn, "Active", base, final, sha, captured) for mpn in names)
        print(f"STM32WL3 {base}: {len(names)} exact Active", flush=True)
    names = [r[0] for r in rows]
    check(len(names) == len(set(names)), "WL3 exact MPN appears under multiple Base Devices")
    check("STM32WL33CCV6" in names, "WL3 previous official sentinel disappeared")
    with (dest / "observed-active-exact.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["exact_icpn", "marketing_status", "base_device", "source_url",
                    "source_raw_sha256", "captured_utc"])
        w.writerows(sorted(rows))
    return {"family": "STM32WL3", "surface": "ST product selector + Quality & Reliability",
            "selector_url": selector_final, "selector_base_device_count": len(bases),
            "selector_raw_sha256": digest(selector_raw),
            "exact_active_count": len(names),
            "exact_set_sha256": digest(("\n".join(sorted(names)) + "\n").encode()),
            "page_ledger": ledger, "exact_names": sorted(names)}

def production_boundary() -> dict:
    payload = json.loads(PRODUCTION.read_text(encoding="utf-8"))
    sources = payload.get("sources")
    check(payload.get("status") == "production" and isinstance(sources, list),
          "invalid Production manifest")
    check(len(sources) == 23 and sum(int(s["row_count"]) for s in sources) == 2683,
          "frozen ST Production count drifted")
    families = {s["family"] for s in sources}
    for family in ("STM32C5", "STM32H5", "STM32N6", "STM32WB0", "STM32WL3"):
        check(family not in families, f"{family} no longer absent from Production")
    return {"exact_icpns": 2683, "families": 23,
            "manifest_git_blob_expected": "c8012b211a28b0a7811bfe978e7e697bc169c6f3"}

def collect(out: Path, interval: float) -> dict:
    check(0.4 <= interval <= 5.0, "request interval must remain polite")
    out.mkdir(parents=True, exist_ok=True)
    summary = {"schema_version": 1,
               "audit_id": "st-missing-family-active-live-acquisition-v1.2",
               "started_utc": now(), "finished_utc": None,
               "status": "ACQUISITION_BLOCKED",
               "production_baseline": production_boundary(),
               "families": [], "error": None,
               "complete_whole_st_active_exact_denominator": False,
               "production_write_authorized": False,
               "backend_support_implied": False}
    try:
        c5 = [x.strip() for x in C5_LOCKED.read_text(encoding="utf-8").splitlines() if x.strip()]
        check(len(c5) == len(set(c5)) == 172 and "STM32C531CBT6" in c5,
              "locked C5 exact set drifted")
        live_sets = {"STM32C5": set(c5)}
        summary["families"].append({
            "family": "STM32C5", "surface": "previous evidence-locked ST eStore category",
            "exact_active_count": 172,
            "exact_set_sha256": digest(("\n".join(sorted(c5)) + "\n").encode()),
            "reused_locked_v07": True})
        for family in ("STM32H5", "STM32N6", "STM32WB0"):
            result = acquire_estore(family, out, interval)
            live_sets[family] = set(result.pop("exact_names"))
            summary["families"].append(result)
        wl3 = acquire_wl3(out, interval)
        live_sets["STM32WL3"] = set(wl3.pop("exact_names"))
        summary["families"].append(wl3)
        union = set().union(*live_sets.values())
        check(sum(len(v) for v in live_sets.values()) == len(union),
              "cross-family exact MPN collision")
        summary["confirmed_missing_family_active_exact_count"] = len(union)
        summary["confirmed_missing_family_active_exact_set_sha256"] = digest(
            ("\n".join(sorted(union)) + "\n").encode())
        summary["confirmed_set_inventory_coverage_percent"] = round(
            2683 / (2683 + len(union)) * 100, 4)
        summary["confirmed_set_inventory_coverage_is_true_whole_st_coverage"] = False
        summary["status"] = "OBSERVED_MISSING_FAMILY_ACTIVE_EXACT_COHORT_REQUIRES_REVIEW"
    except Exception as error:
        summary["error"] = f"{type(error).__name__}: {error}"
        print(f"ACQUISITION_BLOCKED: {summary['error']}", file=sys.stderr)
    finally:
        summary["finished_utc"] = now()
        (out / "capture-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--interval-seconds", type=float, default=0.6)
    args = ap.parse_args()
    result = collect(args.output, args.interval_seconds)
    print(json.dumps({k: v for k, v in result.items() if k != "families"},
                     indent=2, sort_keys=True))
    for item in result.get("families", []):
        print(f"FAMILY {item['family']}: exact_active_count={item['exact_active_count']} "
              f"set_sha256={item['exact_set_sha256']}")
    return 0 if result["status"].startswith("OBSERVED_MISSING_FAMILY") else 2

if __name__ == "__main__":
    raise SystemExit(main())
