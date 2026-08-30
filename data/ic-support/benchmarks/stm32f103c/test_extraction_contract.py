#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR_PATH = HERE / "validate_extraction_candidate.py"
LOCK_PATH = HERE / "source-lock.json"
TRUTH_PATH = HERE / "extraction-ground-truth.json"
CONTRACT_PATH = HERE / "extraction-contract.json"
SCHEMA_PATH = HERE / "extraction-observed.schema.json"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    validator = load_module(VALIDATOR_PATH, "ic_support_candidate_contract_test")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    truth = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$id"] == contract["observed_schema_id"]
    forbidden = set(contract["forbidden_repository_inputs"])
    assert "data/ic-support/benchmarks/stm32f103c/extraction-ground-truth.json" in forbidden
    assert "data/ic-support/benchmarks/stm32f103c/ground-truth.json" in forbidden
    assert "profiles" not in json.dumps(schema).lower()
    assert "stm32f1-medium-density-flash-v0" not in json.dumps(schema)

    candidate = {
        "schema_version": contract["candidate_contract"]["schema_version"],
        "benchmark_id": lock["benchmark_id"],
        "source_lock_id": lock["source_lock_id"],
        "source_digests": validator.expected_source_digests(lock),
        "extractor": {
            "name": "contract-selftest",
            "version": "2"
        },
        "observed": copy.deepcopy(truth["expected"])
    }
    assert validator.validate_candidate(candidate) == []

    wrong_source = copy.deepcopy(candidate)
    first_source = next(iter(wrong_source["source_digests"]))
    wrong_source["source_digests"][first_source] = "sha256:" + "0" * 64
    errors = validator.validate_candidate(wrong_source)
    assert any("source_digests" in error for error in errors)

    wrong_fact = copy.deepcopy(candidate)
    wrong_fact["observed"]["parts"]["STM32F103C8T6"]["flash_size_bytes"] = 131072
    errors = validator.validate_candidate(wrong_fact)
    assert any("flash_size_bytes" in error for error in errors)

    leaked_profile_id = json.dumps(candidate)
    assert "stm32f1-medium-density-flash-v0" not in leaked_profile_id

    print("IC Support extraction contract tests PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"IC Support extraction contract tests FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
