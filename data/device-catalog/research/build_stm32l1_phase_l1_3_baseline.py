#!/usr/bin/env python3
"""Build deterministic STM32L1 L1.3 metadata-policy baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from stm32l1_metadata_policy import DEFAULT_EXCEPTIONS, DEFAULT_ORDERING_AUTHORITY
from stm32l1_phase_l1_3_policy import build_plan, plan_is_clean, summary

HERE = Path(__file__).resolve().parent
L1_2_BASELINE = HERE / "stm32l1-phase-l1.2-discovery-baseline.json"
L1_2_ACTIVE_SET_SHA256 = "0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12"
EXPECTED_PRODUCTION_GIT_BLOB = "1aa2311a25a69742c428147a402816ed5071e04e"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_baseline() -> dict[str, object]:
    plan = build_plan()
    if not plan_is_clean(plan):
        raise RuntimeError("L1.3 plan is not clean; refusing to freeze baseline")
    frozen = summary(plan)
    return {
        "schema_version": 1,
        "phase": "L1.3",
        "family": "STM32L1",
        "authority": {
            "primary": "official ST datasheet Ordering Information",
            "generation_migration_authority": "TN1176",
            "authority_record_count": 10,
            "unique_datasheet_count": 10,
            "exact_variant_exception_count": 0,
            "exact_variant_exception_icpns": [],
        },
        "source_bindings": {
            "l1_2_baseline_sha256": sha256(L1_2_BASELINE),
            "l1_2_active_exact_set_sha256": L1_2_ACTIVE_SET_SHA256,
            "ordering_authority_sha256": sha256(DEFAULT_ORDERING_AUTHORITY),
            "exact_variant_exceptions_sha256": sha256(DEFAULT_EXCEPTIONS),
            "production_manifest_git_blob": EXPECTED_PRODUCTION_GIT_BLOB,
        },
        "result": frozen,
        "claims": {
            "canonical_admission_authorized": False,
            "production_write_authorized": False,
            "programming_policy_defined": False,
            "flash_geometry_qualified": False,
            "option_security_semantics_qualified": False,
            "physical_hil_qualified": False,
            "runtime_programming_support_claimed": False,
            "scope_expansion_authorized": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    value = build_baseline()
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
