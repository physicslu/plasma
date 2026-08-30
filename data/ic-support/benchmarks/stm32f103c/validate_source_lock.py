#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IC_SUPPORT_ROOT = HERE.parents[1]
REPO_ROOT = IC_SUPPORT_ROOT.parents[1]
SOURCE_CATALOG = IC_SUPPORT_ROOT / "evidence" / "sources.json"
SOURCE_LOCK = HERE / "source-lock.json"
GROUND_TRUTH = HERE / "ground-truth.json"
EXTRACTION_CONTRACT = HERE / "extraction-contract.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ValidationError(RuntimeError):
    pass


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"{path}: JSON root must be an object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def main() -> int:
    catalog_payload = load(SOURCE_CATALOG)
    lock = load(SOURCE_LOCK)
    truth = load(GROUND_TRUTH)
    contract = load(EXTRACTION_CONTRACT)

    catalog_sources = catalog_payload.get("sources")
    lock_sources = lock.get("sources")
    require(isinstance(catalog_sources, list), "sources.json sources array is required")
    require(isinstance(lock_sources, list) and lock_sources, "source-lock sources array is required")
    catalog = {
        source.get("source_id"): source
        for source in catalog_sources
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }

    require(lock.get("source_lock_id") == truth.get("source_lock_id"), "ground truth source_lock_id mismatch")
    require(lock.get("source_lock_id") == contract.get("source_lock_id"), "extraction contract source_lock_id mismatch")
    require(lock.get("benchmark_id") == truth.get("benchmark_id"), "ground truth benchmark_id mismatch")
    require(lock.get("benchmark_id") == contract.get("benchmark_id"), "extraction contract benchmark_id mismatch")
    require(lock.get("targets") == truth.get("targets"), "ground truth target set mismatch")
    require(lock.get("targets") == contract.get("targets"), "extraction contract target set mismatch")

    locked_ids: list[str] = []
    for entry in lock_sources:
        require(isinstance(entry, dict), "source-lock entries must be objects")
        source_id = entry.get("source_id")
        require(isinstance(source_id, str) and source_id, "source-lock source_id is required")
        require(source_id not in locked_ids, f"duplicate source-lock source_id: {source_id}")
        locked_ids.append(source_id)
        source = catalog.get(source_id)
        require(isinstance(source, dict), f"{source_id}: missing from source catalog")
        require(entry.get("authority") == source.get("authority"), f"{source_id}: authority mismatch")

        integrity = entry.get("integrity")
        require(isinstance(integrity, dict), f"{source_id}: integrity object is required")
        algorithm = integrity.get("algorithm")
        digest = integrity.get("digest")
        if algorithm == "sha256":
            require(entry.get("authority") == "manufacturer_official", f"{source_id}: sha256 lock must be manufacturer evidence")
            require(isinstance(digest, str) and HEX64.fullmatch(digest) is not None, f"{source_id}: invalid sha256 digest")
            byte_length = integrity.get("byte_length")
            require(isinstance(byte_length, int) and byte_length > 0, f"{source_id}: invalid byte_length")
            require(entry.get("document_number") == source.get("document_number"), f"{source_id}: document_number mismatch")
            require(entry.get("revision") == source.get("revision"), f"{source_id}: revision mismatch")
            require(entry.get("requested_url") == source.get("url"), f"{source_id}: requested_url mismatch")
        elif algorithm == "git_blob_sha1":
            require(isinstance(digest, str) and HEX40.fullmatch(digest) is not None, f"{source_id}: invalid Git blob digest")
            path = entry.get("path")
            require(isinstance(path, str) and path == source.get("path"), f"{source_id}: catalog path mismatch")
            actual = git_blob_sha(REPO_ROOT / path)
            require(actual == digest, f"{source_id}: Git blob drift: {actual} != {digest}")
        else:
            raise ValidationError(f"{source_id}: unsupported integrity algorithm {algorithm!r}")

    truth_ids = truth.get("evidence_source_ids")
    contract_ids = contract.get("allowed_input_source_ids")
    require(truth_ids == locked_ids, "ground truth evidence_source_ids must match source-lock order")
    require(contract_ids == locked_ids, "extraction contract allowed_input_source_ids must match source-lock order")

    provenance = lock.get("discovery_provenance")
    require(isinstance(provenance, dict), "source-lock discovery_provenance is required")
    artifact_digest = provenance.get("artifact_digest")
    require(
        isinstance(artifact_digest, str)
        and artifact_digest.startswith("sha256:")
        and HEX64.fullmatch(artifact_digest.removeprefix("sha256:")) is not None,
        "source-lock artifact digest is invalid",
    )

    print(f"IC Support source-lock validation PASS: {len(locked_ids)} locked sources")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"IC Support source-lock validation FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
