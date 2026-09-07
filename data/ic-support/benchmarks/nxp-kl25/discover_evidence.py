#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_LOCK = HERE / "source-lock.json"
CONTRACT = HERE / "discovery-contract.json"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover candidate NXP KL25 evidence pages deterministically")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    candidates = []

    for source in lock["sources"]:
        pdf = args.source_dir / source["local_filename"]
        if not pdf.is_file():
            raise SystemExit(f"missing locked source: {pdf}")
        if pdf.stat().st_size != source["integrity"]["byte_length"]:
            raise SystemExit(f"byte length mismatch: {pdf}")
        if sha256_file(pdf) != source["integrity"]["digest"]:
            raise SystemExit(f"sha256 mismatch: {pdf}")

        pages = extract_pages(pdf)
        for page_index, page in enumerate(pages):
            lower = page.lower()
            category_hits = {}
            for category, terms in contract["categories"].items():
                if category == "UNKNOWN":
                    continue
                matched = [term for term in terms if term.lower() in lower]
                if matched:
                    category_hits[category] = matched
            if not category_hits:
                continue
            candidates.append({
                "source_id": source["source_id"],
                "document_role": source["document_role"],
                "pdf_page_index": page_index,
                "pdf_page_number": page_index + 1,
                "categories": sorted(category_hits),
                "matched_terms": {k: category_hits[k] for k in sorted(category_hits)},
                "page_text_sha256": hashlib.sha256(page.encode("utf-8")).hexdigest(),
                "classification": "CANDIDATE"
            })

    output = {
        "schema_version": "0.1.0",
        "artifact_type": "candidate_evidence_catalog",
        "catalog_id": "nxp-kl25-deterministic-candidates-v0",
        "discovery_id": contract["discovery_id"],
        "source_lock_id": lock["source_lock_id"],
        "target": contract["target"],
        "candidates": candidates,
        "trust_boundary": {
            "candidate_catalog_complete": True,
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
    print(f"candidates {len(candidates)}")
    for category in contract["categories"]:
        if category == "UNKNOWN":
            continue
        count = sum(category in c["categories"] for c in candidates)
        print(f"{category} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
