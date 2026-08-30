#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IC_SUPPORT_ROOT = HERE.parents[1]
COMPARE_PATH = IC_SUPPORT_ROOT / "compare_benchmark.py"
VALIDATOR_PATH = HERE / "validate_extraction_candidate.py"
LOCK_PATH = HERE / "source-lock.json"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    compare = load_module(COMPARE_PATH, "ic_support_compare_contract_test")
    validator = load_module(VALIDATOR_PATH, "ic_support_candidate_contract_test")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    candidate = {
        "schema_version": "0.1.0",
        "benchmark_id": lock["benchmark_id"],
        "source_lock_id": lock["source_lock_id"],
        "source_digests": validator.expected_source_digests(lock),
        "extractor": {
            "name": "contract-selftest",
            "version": "1"
        },
        "observed": compare.build_projection()
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

    print("IC Support extraction contract tests PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"IC Support extraction contract tests FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
