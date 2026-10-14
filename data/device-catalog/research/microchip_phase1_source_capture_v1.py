#!/usr/bin/env python3
"""Capture immutable original Microchip Phase-1 source bytes, never programming data.

Captures *only* two reviewed manufacturer URLs. A successful HTTP response
is NOT a verified field extraction or manufacturer-identity admission.
This tool is a research evidence acquisition and offline hash-replay helper.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

from microchip_phase1_information_v1 import DEFAULT_PATH, check

ALLOWED = {
    "microchip-atsamd21g18-product-page": {
        "url": "https://www.microchip.com/en-us/product/ATSAMD21G18",
        "type": "html",
        "filename": "microchip-atsamd21g18-product-original.html",
    },
    "microchip-sam-d21-da1-family-datasheet-ds40001882h": {
        "url": ("https://ww1.microchip.com/downloads/aemDocuments/"
                "documents/MCU32/ProductDocuments/DataSheets/"
                "SAM-D21-DA1-Family-Data-Sheet-DS40001882H.pdf"),
        "type": "pdf",
        "filename": "microchip-ds40001882h-original.pdf",
    },
}
MAX_BYTES = 20 * 1024 * 1024
MAX_SOURCE_COUNT = 2
TIMEOUT_S = 30
STATES = frozenset(("SOURCE_BYTES_CAPTURED", "SOURCE_NOT_AVAILABLE",
                    "SOURCE_RESPONSE_INVALID"))


def require(value, message):
    if not value:
        raise ValueError(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_dataset_sources(dataset):
    check(dataset)
    source_ids = {x["id"] for x in dataset["source_records"]}
    require(source_ids == set(ALLOWED),
            "unreviewed source set or missing required manufacturer source")
    for source in dataset["source_records"]:
        allow = ALLOWED[source["id"]]
        require(source["url"] == allow["url"], "source URL changed")
        require(source["raw_capture_retained"] is False
                and source["raw_capture_sha256"] is None,
                "capture cannot retroactively overwrite promoted evidence")
    return True


def inspect_raw(source_id, raw):
    """Non-semantic HTTP payload sanity only. Never emits VERIFIED fields."""
    kind = ALLOWED[source_id]["type"]
    if kind == "pdf":
        require(raw.startswith(b"%PDF-"), "PDF source response not original PDF")
        require(b"%%EOF" in raw[-65536:], "PDF trailer absent")
        return {"content_type": "application/pdf",
                "catalog_identity_evidence_replayed": False,
                "field_specifications_replayed": False}
    require(b"<html" in raw[:30000].lower() or
            b"<!doctype html" in raw[:30000].lower(),
            "product response not HTML")
    # A text token in script markup is not proof of a structured Catalog Parts
    # table. It remains mere source discovery, pending exact row extraction.
    return {"content_type": "text/html",
            "catalog_sku_tokens_present_unverified": {
                part: part.encode() in raw
                for part in ("ATSAMD21G18A-MU", "ATSAMD21G18A-MF")
            },
            "catalog_identity_evidence_replayed": False,
            "field_specifications_replayed": False}


def capture(dataset, output_root, opener=urllib.request.urlopen):
    validate_dataset_sources(dataset)
    root = Path(output_root)
    require(root.name != "production" and
            "production" not in {x.lower() for x in root.resolve().parts},
            "Production output path forbidden")
    require(not root.exists(), "output folder must not exist for immutable capture")
    root.mkdir(parents=True)
    reports = []
    for source_id, allowed in ALLOWED.items():
        current = {
            "source_id": source_id,
            "url": allowed["url"],
            "kind": allowed["type"],
            "state": "SOURCE_NOT_AVAILABLE",
            "file": None,
            "original_bytes_sha256": None,
            "original_bytes_count": None,
            "content_check": None,
            "http_status": None,
            "diagnostic": None,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            request = urllib.request.Request(
                allowed["url"],
                headers={"User-Agent": "PLASMA-Phase1-ResearchEvidence/1.0"},
            )
            with opener(request, timeout=TIMEOUT_S) as response:
                current["http_status"] = response.status
                require(response.status == 200,
                        "manufacturer source did not return HTTP 200")
                raw = response.read(MAX_BYTES + 1)
                require(0 < len(raw) <= MAX_BYTES,
                        "manufacturer response exceeds evidence size bound")
            current["content_check"] = inspect_raw(source_id, raw)
            (root / allowed["filename"]).write_bytes(raw)
            current["file"] = allowed["filename"]
            current["original_bytes_sha256"] = sha256(raw)
            current["original_bytes_count"] = len(raw)
            current["state"] = "SOURCE_BYTES_CAPTURED"
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                OSError, ValueError) as exc:
            current["state"] = ("SOURCE_RESPONSE_INVALID"
                                if isinstance(exc, ValueError)
                                else "SOURCE_NOT_AVAILABLE")
            current["diagnostic"] = f"{type(exc).__name__}: {str(exc)[:240]}"
        reports.append(current)
    manifest = {
        "schema_version": 1,
        "phase": 1,
        "manufacturer": "Microchip",
        "authority": "ADR-0002 Phase 1 Research source-only evidence capture",
        "manufacturer_data_admitted": False,
        "production_write_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_hil_authorized": False,
        "fields_verified_by_source_capture": False,
        "source_records": reports,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return verify_capture(dataset, root)


def verify_capture(dataset, root):
    validate_dataset_sources(dataset)
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("schema_version") == 1
            and manifest.get("phase") == 1
            and manifest.get("manufacturer") == "Microchip",
            "invalid archived source manifest")
    for flag in ("manufacturer_data_admitted", "production_write_authorized",
                 "phase2_programming_authorized", "phase3_hil_authorized",
                 "fields_verified_by_source_capture"):
        require(manifest.get(flag) is False, "unapproved source capability claim")
    reports = manifest.get("source_records")
    require(isinstance(reports, list) and len(reports) == MAX_SOURCE_COUNT,
            "incomplete manufacturer source capture manifest")
    seen = set()
    for rec in reports:
        source_id = rec["source_id"]
        require(source_id in ALLOWED and source_id not in seen,
                "untrusted/duplicate source")
        seen.add(source_id)
        rule = ALLOWED[source_id]
        require(rec["url"] == rule["url"] and rec["kind"] == rule["type"],
                "record URL/type not from approved manufacturer source")
        require(rec["state"] in STATES, "unsupported source state")
        if rec["state"] == "SOURCE_BYTES_CAPTURED":
            require(rec["file"] == rule["filename"]
                    and rec["original_bytes_count"] is not None
                    and isinstance(rec["original_bytes_sha256"], str),
                    "captured data does not identify original bytes")
            raw = (root / rec["file"]).read_bytes()
            require(0 < len(raw) <= MAX_BYTES
                    and sha256(raw) == rec["original_bytes_sha256"]
                    and len(raw) == rec["original_bytes_count"],
                    "original manufacturer source byte SHA-256 mismatch")
            require(rec["content_check"] == inspect_raw(source_id, raw),
                    "source type sanity/replay changed")
        else:
            require(rec["file"] is None
                    and rec["original_bytes_sha256"] is None
                    and rec["original_bytes_count"] is None,
                    "failed source capture cannot claim archived original bytes")
    return {
        "source_count": MAX_SOURCE_COUNT,
        "source_byte_captures": sum(
            x["state"] == "SOURCE_BYTES_CAPTURED" for x in reports),
        "source_blockers": [
            {"source_id": x["source_id"], "state": x["state"],
             "diagnostic": x["diagnostic"]}
            for x in reports if x["state"] != "SOURCE_BYTES_CAPTURED"
        ],
        "original_byte_sha256_replay_passed": True,
        "product_catalog_exact_rows_verified": False,
        "manufacturer_fields_verified_from_capture": False,
        "internal_admission_ready": False,
        "production_write_authorized": False,
        "phase2_or_3_performed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", type=Path)
    group.add_argument("--verify", type=Path)
    args = parser.parse_args()
    dataset = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    result = (capture(dataset, args.capture) if args.capture
              else verify_capture(dataset, args.verify))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
