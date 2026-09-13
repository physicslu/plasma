#!/usr/bin/env python3
"""Build the deterministic STM32L4 L4.3 frozen metadata-policy baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from stm32l4_metadata_policy import DEFAULT_EXCEPTIONS, DEFAULT_ORDERING_AUTHORITY, EXPECTED_EXCEPTION_ICPNS
from stm32l4_phase_l4_3_policy import build_plan, plan_is_clean, summary

HERE = Path(__file__).resolve().parent
L4_2_BASELINE = HERE / "stm32l4-phase-l4.2-discovery-baseline.json"
PRODUCTION_PRESTATE_SHA256 = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"
L4_2_ACTIVE_SET_SHA256 = "cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_baseline() -> dict[str, object]:
    plan = build_plan()
    if not plan_is_clean(plan):
        raise RuntimeError("L4.3 plan is not clean; refusing to freeze baseline")
    frozen = summary(plan)
    return {
        "schema_version": 1,
        "phase": "L4.3",
        "family": "STM32L4",
        "authority": {
            "primary": "official ST datasheet Ordering Information",
            "exact_variant_exception_policy": "three retained Active exact ICPNs only; current official ST exact-part surface overrides only the omitted/conflicting field",
            "series_count": 24,
            "unique_datasheet_count": 20,
            "exact_variant_exception_count": 3,
            "exact_variant_exception_icpns": sorted(EXPECTED_EXCEPTION_ICPNS),
        },
        "source_bindings": {
            "l4_2_baseline_sha256": sha256(L4_2_BASELINE),
            "l4_2_active_exact_set_sha256": L4_2_ACTIVE_SET_SHA256,
            "ordering_authority_sha256": sha256(DEFAULT_ORDERING_AUTHORITY),
            "exact_variant_exceptions_sha256": sha256(DEFAULT_EXCEPTIONS),
            "production_prestate_sha256": PRODUCTION_PRESTATE_SHA256,
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
