#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def clusters(pages: list[int]) -> str:
    if not pages:
        return "none"
    pages = sorted(set(pages))
    out: list[str] = []
    start = prev = pages[0]
    for page in pages[1:]:
        if page == prev + 1:
            prev = page
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = page
    out.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize KL25 applicability evidence candidates")
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()

    doc = json.loads(args.catalog.read_text(encoding="utf-8"))
    for claim_id, claim in doc["claims"].items():
        print(f"[{claim_id}]")
        print(f"  candidates: {claim['candidate_count']}")
        by_source: dict[str, list[dict]] = defaultdict(list)
        for evidence in claim["evidence"]:
            by_source[evidence["source_id"]].append(evidence)
        for source_id in sorted(by_source):
            records = by_source[source_id]
            print(
                f"  {source_id}: {len(records)} pages; clusters: "
                f"{clusters([r['pdf_page_number'] for r in records])}"
            )
            for record in records:
                if record["heading_candidates"]:
                    print(
                        f"    page {record['pdf_page_number']}: "
                        f"terms={record['matched_terms']} headings={record['heading_candidates']}"
                    )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
