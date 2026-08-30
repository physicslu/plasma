#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
IC_SUPPORT_ROOT = HERE.parents[1]
SOURCE_LOCK = HERE / "source-lock.json"
GROUND_TRUTH = HERE / "ground-truth.json"
CONTRACT = HERE / "extraction-contract.json"
COMPARE_PATH = IC_SUPPORT_ROOT / "compare_benchmark.py"


class CandidateError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CandidateError(f"{path}: JSON root must be an object")
    return value


def load_compare_module():
    spec = importlib.util.spec_from_file_location("ic_support_compare_candidate", COMPARE_PATH)
    if spec is None or spec.loader is None:
        raise CandidateError("cannot load compare_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_source_digests(lock: dict[str, Any]) -> dict[str, str]:
    sources = lock.get("sources")
    if not isinstance(sources, list):
        raise CandidateError("source-lock sources array is required")
    out: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise CandidateError("source-lock entries must be objects")
        source_id = source.get("source_id")
        integrity = source.get("integrity")
        if not isinstance(source_id, str) or not isinstance(integrity, dict):
            raise CandidateError("source-lock source_id/integrity is invalid")
        algorithm = integrity.get("algorithm")
        digest = integrity.get("digest")
        if not isinstance(algorithm, str) or not isinstance(digest, str):
            raise CandidateError(f"{source_id}: source-lock digest is invalid")
        out[source_id] = f"{algorithm}:{digest}"
    return out


def validate_candidate(candidate: dict[str, Any]) -> list[str]:
    contract = load(CONTRACT)
    lock = load(SOURCE_LOCK)
    truth = load(GROUND_TRUTH)
    errors: list[str] = []

    required = contract["candidate_contract"]["required_fields"]
    for field in required:
        if field not in candidate:
            errors.append(f"$.{field}: missing")

    if candidate.get("schema_version") != contract["candidate_contract"]["schema_version"]:
        errors.append("$.schema_version: mismatch")
    if candidate.get("benchmark_id") != contract.get("benchmark_id"):
        errors.append("$.benchmark_id: mismatch")
    if candidate.get("source_lock_id") != lock.get("source_lock_id"):
        errors.append("$.source_lock_id: mismatch")

    digests = candidate.get("source_digests")
    expected_digests = expected_source_digests(lock)
    if digests != expected_digests:
        errors.append("$.source_digests: exact source-lock digest map required")

    extractor = candidate.get("extractor")
    if not isinstance(extractor, dict):
        errors.append("$.extractor: object required")
    else:
        for field in contract["candidate_contract"]["extractor_required_fields"]:
            value = extractor.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"$.extractor.{field}: non-empty string required")

    observed = candidate.get("observed")
    if not isinstance(observed, dict):
        errors.append("$.observed: object required")
    else:
        compare = load_compare_module()
        errors.extend(compare.compare(truth["expected"], observed))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an isolated STM32F103C extraction candidate")
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    try:
        candidate = load(args.candidate)
        errors = validate_candidate(candidate)
    except (OSError, json.JSONDecodeError, CandidateError) as exc:
        print(f"IC Support extraction candidate FAIL: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("IC Support extraction candidate FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("IC Support extraction candidate PASS: source lock and ground truth match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
