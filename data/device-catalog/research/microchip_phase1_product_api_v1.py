#!/usr/bin/env python3
"""Microchip official Product Data API Phase 1 exact-order-code evidence.

Read-only bounded original-byte capture, two-pagination reconciliation and
offline replay. Independent manufacturer API fields are evidence, NOT IC
admission, OpenOCD software support or PPU/HIL qualification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
PILOT = HERE / "microchip-adr0002-phase1-ic-information-pilot-v1.json"
API = "https://www.microchip.com/designresources/product-catalog/api/productInfo"
DOC = "https://www.microchip.com/designresources/PartnerDataExchange/ProductAPI-user-guide.html"
PRIMARY_SIZE, INDEPENDENT_SIZE = 20, 60
MAX_TOTAL, MAX_BYTES = 120, 3 * 1024 * 1024
PILOT_QUERY = "ATSAMD21G18A"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def url_for(query, size, number):
    require(re.fullmatch(r"[A-Z0-9]{3,64}", query or "") is not None,
            "invalid bounded base-device query")
    require(size in (PRIMARY_SIZE, INDEPENDENT_SIZE), "unapproved page size")
    require(type(number) is int and 1 <= number <= 10,
            "invalid page number")
    return API + "?" + urllib.parse.urlencode(
        {"part": query, "pagesize": size, "pagenumber": number})


def official_url(url):
    parsed = urllib.parse.urlparse(url)
    return (parsed.scheme == "https" and parsed.hostname == "www.microchip.com"
            and parsed.path == "/designresources/product-catalog/api/productInfo"
            and not parsed.username and not parsed.password and parsed.port is None)


def exact_query_prefix(icpn, query):
    require(isinstance(icpn, str), "invalid manufacturer part_number")
    if not icpn.upper().startswith(query.upper()):
        return False
    suffix = icpn[len(query):]
    # A bare base device is not independently proven to be a complete
    # commercial ordering number. 'T-' is a Microchip tape-and-reel infix.
    return suffix.startswith(("-", "/", "T-", "T/"))


def parse_response(raw, expected_query, page_size, page_number):
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("non-JSON official Product API response") from exc
    require(isinstance(payload, dict), "API response must be object")
    for field, wanted in (("pagesize", page_size), ("pagenumber", page_number)):
        require(type(payload.get(field)) is int and payload[field] == wanted,
                "API pagination identity mismatch: " + field)
    total = payload.get("totalRecords")
    count_pages = payload.get("totalPages")
    require(type(total) is int and 0 < total <= MAX_TOTAL,
            "empty/unbounded API search is not complete inventory evidence")
    require(type(count_pages) is int
            and count_pages == (total + page_size - 1) // page_size,
            "API totalPages mismatch")
    rows = payload.get("data")
    require(isinstance(rows, list)
            and len(rows) == max(0, min(page_size, total - page_size * (page_number - 1))),
            "API page length disagrees with total")
    seen = set()
    normalized = []
    for index, row in enumerate(rows):
        require(isinstance(row, dict), "non-object API row")
        ident = row.get("part_number")
        require(isinstance(ident, str) and 3 <= len(ident) <= 120
                and ident == ident.strip(), "missing/malformed exact manufacturer SKU")
        require(ident.upper() not in seen, "duplicate commercial code within API page")
        seen.add(ident.upper())
        manufacturer = row.get("manufacturer")
        require(isinstance(manufacturer, str)
                and "microchip" in manufacturer.casefold(),
                "unexpected Product API manufacturer")
        base = row.get("base_part_number")
        require(isinstance(base, str) and base.strip() == base and bool(base),
                "API base_part_number missing")
        pin = row.get("pin_count")
        if pin in (None, ""):
            pin_value = None
        else:
            require(isinstance(pin, str) and re.fullmatch(r"[1-9][0-9]{0,3}", pin),
                    "API pin_count invalid")
            pin_value = int(pin)
        package = row.get("package_type")
        require(package is None or isinstance(package, str),
                "API package_type malformed")
        normalized.append({
            "icpn": ident,
            "base_device_raw": base,
            "package_raw": package or None,
            "pin_count": pin_value,
            "lifecycle_raw_not_admission": row.get("lifecycle_status"),
            "datasheet_url_raw": row.get("datasheet_url"),
            "parametric_data_url_raw": row.get("parametric_data_url"),
            "is_query_prefix_ordering_candidate": exact_query_prefix(ident, expected_query),
            "response_data_index": index
        })
    return {"totalRecords": total, "totalPages": count_pages,
            "records": normalized}


def fetch(url):
    require(official_url(url), "off-domain API request prohibited")
    req = urllib.request.Request(
        url, headers={"Accept": "application/json",
                      "User-Agent": "PLASMA-Phase1-Research/1.0"})
    with urllib.request.urlopen(req, timeout=18) as response:
        final = urllib.parse.urlparse(response.geturl())
        require(response.status == 200 and official_url(response.geturl()),
                "unexpected API status/redirect host: "
                f"http={response.status} host={final.hostname} path={final.path}")
        raw = response.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "API response size cap exceeded")
        return raw


def capture(root, query, getter=fetch):
    root = Path(root)
    require(not root.exists(), "original-source directory already exists")
    root.mkdir(parents=True)
    manifest = {
        "schema_version": 1, "manufacturer": "Microchip", "phase": 1,
        "source": DOC, "endpoint": API, "query": query,
        "sizes": [PRIMARY_SIZE, INDEPENDENT_SIZE],
        "source_capture_complete": False,
        "captured": [], "error": None,
        "research_only": True, "production_write_authorized": False,
    }
    try:
        for size in (PRIMARY_SIZE, INDEPENDENT_SIZE):
            number = 1
            expected_total = None
            while True:
                uri = url_for(query, size, number)
                raw = getter(uri)
                parsed = parse_response(raw, query, size, number)
                total = parsed["totalRecords"]
                if expected_total is None:
                    expected_total = total
                require(total == expected_total,
                        "changing totalRecords across pages")
                filename = f"api-size{size}-page{number}.json"
                (root / filename).write_bytes(raw)
                manifest["captured"].append({
                    "url": uri, "file": filename, "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw), "page_size": size,
                    "page_number": number, "totalRecords": total,
                    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                })
                if number >= parsed["totalPages"]:
                    break
                number += 1
        manifest["source_capture_complete"] = True
    except (ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        # Even partial original bytes are retained, never misrepresented as success.
    (root / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    require(manifest["source_capture_complete"], "SOURCE_NOT_AVAILABLE: " + str(manifest["error"]))
    return replay(root, query)


def pilot_comparison(records, pilot):
    require(isinstance(pilot, dict) and pilot.get("manufacturer") == "Microchip"
            and pilot.get("phase") == 1, "invalid pilot dataset")
    by_id = {r["icpn"].upper(): r for r in records}
    comparisons = []
    for entry in pilot["records"]:
        identity = entry["icpn"]
        matches = by_id.get(identity.upper())
        if matches is None:
            comparisons.append({"icpn": identity, "status": "NOT_OBSERVED",
                                "fields": {}})
            continue
        results = {}
        observed = {"base_device": matches["base_device_raw"].upper(),
                    "package": matches["package_raw"],
                    "pin_count": matches["pin_count"]}
        for field, value in observed.items():
            if value is None:
                results[field] = "UNKNOWN"
                continue
            prior = entry["fields"][field]["value"]
            results[field] = ("AGREE" if prior is not None and
                              str(value).upper() == str(prior).upper()
                              else "CONFLICT" if prior is not None else "NEW_OBSERVATION")
        comparisons.append({"icpn": identity, "status": "OBSERVED",
                            "fields": results})
    return comparisons


def replay(root, query, pilot_path=PILOT):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("schema_version") == 1
            and manifest.get("manufacturer") == "Microchip"
            and manifest.get("phase") == 1
            and manifest.get("endpoint") == API
            and manifest.get("source_capture_complete") is True
            and manifest.get("query") == query
            and manifest.get("sizes") == [PRIMARY_SIZE, INDEPENDENT_SIZE]
            and manifest.get("research_only") is True
            and manifest.get("production_write_authorized") is False,
            "incomplete/untrusted official Product API manifest")
    events = manifest.get("captured")
    require(isinstance(events, list) and events, "missing source bytes")
    collections = {}
    original_refs = {}
    for size in (PRIMARY_SIZE, INDEPENDENT_SIZE):
        subset = [e for e in events if e.get("page_size") == size]
        require(subset and [e.get("page_number") for e in subset] ==
                list(range(1, len(subset) + 1)), "missing/out-of-order API page")
        all_rows = {}
        totals = set()
        for e in subset:
            filename = e.get("file")
            require(isinstance(filename, str)
                    and re.fullmatch(r"api-size(?:20|60)-page[1-9][0-9]*\.json", filename)
                    and filename == f"api-size{size}-page{e['page_number']}.json",
                    "unsafe original API evidence file")
            require(e.get("url") == url_for(query, size, e["page_number"]),
                    "API source URL mismatch")
            raw = (root / filename).read_bytes()
            require(len(raw) == e.get("size_bytes")
                    and hashlib.sha256(raw).hexdigest() == e.get("sha256"),
                    "original API bytes SHA-256 mismatch")
            page = parse_response(raw, query, size, e["page_number"])
            totals.add(page["totalRecords"])
            for row in page["records"]:
                identity = row["icpn"].upper()
                require(identity not in all_rows,
                        "duplicate API commercial ICPN across pages")
                all_rows[identity] = row
                if size == PRIMARY_SIZE:
                    original_refs[identity] = {
                        "source_file": filename, "source_sha256": e["sha256"],
                        "source_locator": f"data[{row['response_data_index']}]",
                    }
        require(len(totals) == 1 and len(all_rows) == next(iter(totals))
                and len(subset) == (len(all_rows) + size - 1) // size,
                "API source pages incomplete/ambiguous")
        collections[size] = all_rows
    a, b = collections[PRIMARY_SIZE], collections[INDEPENDENT_SIZE]
    # The per-page data[] index changes with page size. Compare *content*,
    # not that page-local locator; only PRIMARY is the archived locator source.
    def compare_rows(value):
        return {key: field for key, field in value.items()
                if key != "response_data_index"}
    require(set(a) == set(b) and
            all(compare_rows(a[identity]) == compare_rows(b[identity])
                for identity in a),
            "independent API pagination disagrees about product identities/fields")
    candidates = []
    for identity, row in sorted(a.items()):
        if row["is_query_prefix_ordering_candidate"]:
            candidates.append({
                **row, **original_refs[identity],
                "evidence_scope": "exact_manufacturer_product_api_row",
                "identity_admission_state": "NOT_ADMITTED",
                "field_values_are_not_software_support": True,
            })
    pilot = json.loads(Path(pilot_path).read_text(encoding="utf-8"))
    comparisons = pilot_comparison(candidates, pilot) if query == PILOT_QUERY else []
    return {
        "schema_version": 1, "policy": "ADR-0002 Phase 1",
        "manufacturer": "Microchip", "official_source": DOC,
        "query": query, "original_api_pages_replayed": True,
        "independent_page_size_agreement": True,
        "raw_response_files": len(events),
        "source_total_results": len(a),
        "exact_prefix_candidate_count": len(candidates),
        "fuzzy_or_base_only_results_excluded": len(a) - len(candidates),
        "exact_identity_candidates": candidates,
        "pilot_crosscheck": comparisons,
        "manufacturer_population_complete": False,
        "internal_admission_count": 0,
        "software_supported_count": None,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=PILOT_QUERY)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", type=Path)
    mode.add_argument("--replay", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    url_for(args.query, PRIMARY_SIZE, 1)
    out = args.capture or args.replay
    require("production" not in {p.casefold() for p in out.resolve().parts},
            "Production output path prohibited")
    if args.report:
        require("production" not in {p.casefold() for p in args.report.resolve().parts},
                "Production report path prohibited")
    report = (capture(args.capture, args.query) if args.capture
              else replay(args.replay, args.query))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("source_total_results", "exact_prefix_candidate_count",
                       "fuzzy_or_base_only_results_excluded",
                       "original_api_pages_replayed")}, sort_keys=True))


if __name__ == "__main__":
    main()
