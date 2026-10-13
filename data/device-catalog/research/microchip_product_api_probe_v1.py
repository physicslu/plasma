#!/usr/bin/env python3
"""Read-only, fixed-endpoint Microchip Product Data API pagination probe.

Captures raw response bytes for the official guide's PIC10F202 sample query.
It validates transport/pagination shape only; lifecycle codes are preserved raw.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://www.microchip.com/designresources/product-catalog/api/productInfo"
QUERY = "PIC10F202"
PAGE_SIZE = 2
MAX_PAGES = 100
TIMEOUT_SECONDS = 25


class ProbeError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def validate_page(payload: object, expected_page: int, page_size: int) -> dict:
    require(isinstance(payload, dict), "response must be a JSON object")
    for key in ("totalRecords", "totalPages", "pagenumber", "pagesize", "data"):
        require(key in payload, f"response missing {key}")
    total_records = payload["totalRecords"]
    total_pages = payload["totalPages"]
    page_number = payload["pagenumber"]
    returned_page_size = payload["pagesize"]
    require(type(total_records) is int and total_records >= 0, "invalid totalRecords")
    require(type(total_pages) is int and total_pages >= 0, "invalid totalPages")
    require(type(page_number) is int and page_number == expected_page,
            "pagenumber does not match requested page")
    require(type(returned_page_size) is int and returned_page_size == page_size,
            "pagesize does not match request")
    require(isinstance(payload["data"], list), "data must be a list")
    expected_total_pages = (total_records + page_size - 1) // page_size
    require(total_pages == expected_total_pages,
            "totalPages does not match totalRecords/pagesize")
    require((total_records == 0 and expected_page == 1) or
            (total_records > 0 and expected_page <= total_pages),
            "requested page is outside the reported result range")
    for row in payload["data"]:
        require(isinstance(row, dict), "each data row must be an object")
        require(isinstance(row.get("part_number"), str) and row["part_number"].strip(),
                "row missing exact part_number")
        require("base_part_number" in row, "row missing base_part_number")
        require("lifecycle_status" in row, "row missing raw lifecycle_status")
    return payload


def parse_json_response(raw: bytes) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        prefix = repr(raw[:160].decode("utf-8", errors="replace"))
        digest = hashlib.sha256(raw).hexdigest()
        raise ProbeError(
            f"response is not valid JSON (bytes={len(raw)}, sha256={digest}, prefix={prefix})"
        ) from exc


def fetch_page(page_number: int) -> bytes:
    query = urlencode({
        "part": QUERY,
        "pagesize": str(PAGE_SIZE),
        "pagenumber": str(page_number),
    })
    request = Request(
        f"{API_BASE}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "plasma-microchip-research-probe/1.0",
        },
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                require(response.status == 200, f"unexpected HTTP status {response.status}")
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise ProbeError(f"API request failed after three attempts: {last_error}")


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    records: list[dict] = []
    page_metadata: list[dict] = []
    shared_totals: tuple[int, int] | None = None
    try:
        first_bytes = fetch_page(1)
        first_path = output_dir / "page-001.json"
        first_path.write_bytes(first_bytes)
        first = validate_page(parse_json_response(first_bytes), 1, PAGE_SIZE)
        shared_totals = (first["totalRecords"], first["totalPages"])
        require(first["totalPages"] <= MAX_PAGES,
                f"reported totalPages exceeds safety limit {MAX_PAGES}")
        pages = [first]
        page_hashes = [hashlib.sha256(first_bytes).hexdigest()]
        for page_number in range(2, first["totalPages"] + 1):
            raw = fetch_page(page_number)
            (output_dir / f"page-{page_number:03d}.json").write_bytes(raw)
            payload = validate_page(parse_json_response(raw), page_number, PAGE_SIZE)
            require((payload["totalRecords"], payload["totalPages"]) == shared_totals,
                    "pagination totals changed between pages")
            pages.append(payload)
            page_hashes.append(hashlib.sha256(raw).hexdigest())

        for page_number, payload in enumerate(pages, start=1):
            rows = payload["data"]
            records.extend(rows)
            page_metadata.append({
                "pagenumber": page_number,
                "row_count": len(rows),
                "response_sha256": page_hashes[page_number - 1],
            })

        part_numbers = [row["part_number"].strip() for row in records]
        duplicates = sorted({part for part in part_numbers if part_numbers.count(part) > 1})
        total_records, total_pages = shared_totals
        summary = {
            "schema_version": 1,
            "source": API_BASE,
            "query_part": QUERY,
            "requested_pagesize": PAGE_SIZE,
            "retrieved_at_utc": retrieved_at,
            "reported_total_records": total_records,
            "reported_total_pages": total_pages,
            "fetched_page_count": len(pages),
            "fetched_row_count": len(records),
            "unique_exact_part_number_count": len(set(part_numbers)),
            "duplicate_exact_part_numbers": duplicates,
            "pagination_count_consistent": len(records) == total_records,
            "pages": page_metadata,
            "raw_lifecycle_values": sorted({
                str(row["lifecycle_status"]) for row in records
            }),
            "interpretation": "raw manufacturer API response only; lifecycle codes are not mapped",
        }
        require(summary["pagination_count_consistent"],
                "sum of fetched rows does not equal totalRecords")
        require(not duplicates, "duplicate exact part_number values across pages")
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return summary
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "source": API_BASE,
            "query_part": QUERY,
            "requested_pagesize": PAGE_SIZE,
            "retrieved_at_utc": retrieved_at,
            "error": f"{type(exc).__name__}: {exc}",
            "interpretation": "partial raw capture only; do not use as a complete source population",
        }
        (output_dir / "probe-error.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.output_dir)
    except Exception as exc:
        print(f"Microchip API probe failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
