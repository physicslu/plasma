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
CONTRACT = HERE / "applicability-contract.json"

HEADING_PATTERNS = [
    re.compile(r"^\s*\d+(?:\.\d+){1,5}\s+\S.+$"),
    re.compile(r"^\s*[A-Z][A-Z0-9 /()&\-]{5,100}$"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_page(text: str) -> str:
    return "\n".join(
        line.rstrip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()


def extract_pages(pdf: Path) -> list[str]:
    proc = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [normalize_page(page) for page in proc.stdout.split("\f") if normalize_page(page)]


def headings(page: str) -> list[str]:
    out: list[str] = []
    for line in page.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 140:
            continue
        if any(pattern.match(stripped) for pattern in HEADING_PATTERNS):
            out.append(stripped)
    return out[:12]


def matched_terms(page: str, terms: list[str], mode: str) -> list[str]:
    if mode == "whole_token":
        matched = []
        for term in terms:
            pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", re.IGNORECASE)
            if pattern.search(page):
                matched.append(term)
        return matched
    lower = page.lower()
    return [term for term in terms if term.lower() in lower]


def page_allowed(claim: dict, source_id: str, page_number: int) -> bool:
    page_ranges = claim.get("page_ranges")
    if not page_ranges:
        return True
    ranges = page_ranges.get(source_id, [])
    return any(start <= page_number <= end for start, end in ranges)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover deterministic KL25 applicability evidence candidates")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source_by_id = {source["source_id"]: source for source in lock["sources"]}
    pages_by_source: dict[str, list[str]] = {}

    for source in lock["sources"]:
        pdf = args.source_dir / source["local_filename"]
        if not pdf.is_file():
            raise SystemExit(f"missing locked source: {pdf}")
        if pdf.stat().st_size != source["integrity"]["byte_length"]:
            raise SystemExit(f"byte length mismatch: {pdf}")
        if sha256_file(pdf) != source["integrity"]["digest"]:
            raise SystemExit(f"sha256 mismatch: {pdf}")
        pages_by_source[source["source_id"]] = extract_pages(pdf)

    claims: dict[str, dict] = {}
    for claim_id, claim in contract["candidate_claims"].items():
        mode = claim.get("match_mode", "literal")
        evidence = []
        for source_id in claim["source_ids"]:
            source = source_by_id[source_id]
            for page_index, page in enumerate(pages_by_source[source_id]):
                page_number = page_index + 1
                if not page_allowed(claim, source_id, page_number):
                    continue
                matched = matched_terms(page, claim["terms"], mode)
                if not matched:
                    continue
                evidence.append({
                    "source_id": source_id,
                    "document_role": source["document_role"],
                    "pdf_page_number": page_number,
                    "matched_terms": matched,
                    "match_mode": mode,
                    "heading_candidates": headings(page),
                    "page_text_sha256": hashlib.sha256(page.encode("utf-8")).hexdigest(),
                    "classification": "APPLICABILITY_EVIDENCE_CANDIDATE"
                })
        claims[claim_id] = {
            "purpose": claim["purpose"],
            "optional": bool(claim.get("optional", False)),
            "absence_policy": claim.get("absence_policy"),
            "evidence": evidence,
            "candidate_count": len(evidence),
            "review_status": "PENDING"
        }

    output = {
        "schema_version": "0.2.0",
        "artifact_type": "applicability_evidence_candidates",
        "applicability_id": contract["applicability_id"],
        "source_lock_id": lock["source_lock_id"],
        "target": contract["target"],
        "claims": claims,
        "scope_bridge": contract["scope_bridge"],
        "unit_requirements": contract["unit_requirements"],
        "trust_boundary": {
            "candidate_evidence_complete": True,
            "scope_bridge_reviewed": False,
            "evidence_unit_catalog_admission": False,
            "applicability_binding_admission": False,
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
    for claim_id, item in claims.items():
        suffix = " optional" if item["optional"] else ""
        print(f"{claim_id} {item['candidate_count']}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
