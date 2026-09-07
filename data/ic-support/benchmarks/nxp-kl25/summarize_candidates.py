#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def contiguous_ranges(pages: list[int]) -> list[tuple[int, int]]:
    if not pages:
        return []
    pages = sorted(set(pages))
    ranges: list[tuple[int, int]] = []
    start = prev = pages[0]
    for page in pages[1:]:
        if page == prev + 1:
            prev = page
            continue
        ranges.append((start, prev))
        start = prev = page
    ranges.append((start, prev))
    return ranges


def fmt_range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize deterministic KL25 candidate page clusters")
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()

    data = json.loads(args.catalog.read_text(encoding="utf-8"))
    by_category: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    terms: dict[tuple[str, str, int], dict[str, list[str]]] = {}

    for candidate in data["candidates"]:
        source = candidate["source_id"]
        page = candidate["pdf_page_number"]
        for category in candidate["categories"]:
            by_category[category][source].append(page)
        terms[(source, candidate["document_role"], page)] = candidate["matched_terms"]

    for category in sorted(by_category):
        print(f"[{category}]")
        for source in sorted(by_category[category]):
            pages = sorted(set(by_category[category][source]))
            clusters = contiguous_ranges(pages)
            print(f"  {source}: {len(pages)} pages; clusters: " + ", ".join(fmt_range(a, b) for a, b in clusters))
        print()

    focus = {
        "FLASH_COMMAND_ENGINE",
        "PROGRAMMING_SEQUENCE",
        "COMMAND_STATUS",
        "DEBUG_PROGRAMMING_INTERFACE",
        "SECURITY",
        "CONFIGURATION",
    }
    print("[FOCUS_PAGES]")
    for candidate in data["candidates"]:
        cats = [c for c in candidate["categories"] if c in focus]
        if not cats:
            continue
        matched = {c: candidate["matched_terms"][c] for c in cats}
        print(
            f"  {candidate['source_id']} page {candidate['pdf_page_number']}: "
            f"{','.join(cats)} {json.dumps(matched, ensure_ascii=False, sort_keys=True)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
