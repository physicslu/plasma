#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_LOCK = HERE / "source-lock.json"
BOUNDARY = HERE / "reviewed-candidate-boundary.json"
DISCOVERY = HERE / "discovery-contract.json"
CONSTRUCTION = HERE / "evidence-unit-construction-contract.json"

HEADING_PATTERNS = [
    re.compile(r"^\s*\d+(?:\.\d+){1,4}\s+\S.+$"),
    re.compile(r"^\s*[A-Z][A-Z0-9 /()\-]{5,80}$"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_page(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


def extract_pages(pdf: Path) -> list[str]:
    proc = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [normalize_page(page) for page in proc.stdout.split("\f") if normalize_page(page)]


def heading_candidates(page: str) -> list[str]:
    found: list[str] = []
    for line in page.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 120:
            continue
        if any(p.match(stripped) for p in HEADING_PATTERNS):
            found.append(stripped)
    return found[:12]


def category_hits(page: str, categories: dict[str, list[str]]) -> dict[str, list[str]]:
    lower = page.lower()
    out: dict[str, list[str]] = {}
    for category, terms in categories.items():
        if category == "UNKNOWN":
            continue
        matched = [term for term in terms if term.lower() in lower]
        if matched:
            out[category] = matched
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic KL25 Evidence Unit construction candidates")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    boundary = json.loads(BOUNDARY.read_text(encoding="utf-8"))
    discovery = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    construction = json.loads(CONSTRUCTION.read_text(encoding="utf-8"))

    source_by_id = {s["source_id"]: s for s in lock["sources"]}
    pages_by_source: dict[str, list[str]] = {}

    for item in boundary["boundaries"]:
        if item["role"] not in construction["required_candidate_roles"]:
            continue
        source = source_by_id[item["source_id"]]
        if source["source_id"] not in pages_by_source:
            pdf = args.source_dir / source["local_filename"]
            if not pdf.is_file():
                raise SystemExit(f"missing locked source: {pdf}")
            if pdf.stat().st_size != source["integrity"]["byte_length"]:
                raise SystemExit(f"byte length mismatch: {pdf}")
            if sha256_file(pdf) != source["integrity"]["digest"]:
                raise SystemExit(f"sha256 mismatch: {pdf}")
            pages_by_source[source["source_id"]] = extract_pages(pdf)

    units = []
    for item in boundary["boundaries"]:
        if item["role"] not in construction["required_candidate_roles"]:
            continue
        pages = pages_by_source[item["source_id"]]
        start, end = item["pdf_pages"]
        records = []
        for page_number in range(start, end + 1):
            page = pages[page_number - 1]
            records.append({
                "pdf_page_number": page_number,
                "page_text_sha256": hashlib.sha256(page.encode("utf-8")).hexdigest(),
                "heading_candidates": heading_candidates(page),
                "category_hits": category_hits(page, discovery["categories"]),
            })
        units.append({
            "source_id": item["source_id"],
            "role": item["role"],
            "reviewed_pdf_pages": [start, end],
            "pages": records,
            "classification": "CONSTRUCTION_CANDIDATE"
        })

    output = {
        "schema_version": "0.1.0",
        "artifact_type": "evidence_unit_construction_candidates",
        "construction_id": construction["construction_id"],
        "source_lock_id": lock["source_lock_id"],
        "reviewed_boundary_id": boundary["boundary_id"],
        "target": construction["target"],
        "units": units,
        "trust_boundary": {
            "construction_candidate_catalog_complete": True,
            "evidence_unit_catalog_admission": False,
            "evidence_pack_admission": False,
            "semantic_extraction_admission": False,
            "canonical_dataset_admission": False,
            "hil_admission": False,
            "production_admission": False
        }
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    for unit in units:
        heading_pages = sum(bool(p["heading_candidates"]) for p in unit["pages"])
        print(f"{unit['role']} pages={len(unit['pages'])} heading_pages={heading_pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
