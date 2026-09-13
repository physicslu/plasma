#!/usr/bin/env python3
"""Permanent hard-lock validator for STM32L4 Phase L4.3 metadata policy."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from build_stm32l4_phase_l4_3_baseline import build_baseline
from stm32l4_metadata_policy import (
    DEFAULT_EXCEPTIONS,
    DEFAULT_ORDERING_AUTHORITY,
    EXPECTED_EXCEPTION_ICPNS,
    load_exact_variant_exceptions,
    load_ordering_authority,
)
from stm32l4_phase_l4_3_policy import build_plan, plan_is_clean
from validate_stm32l4_phase_l4_2_retained_evidence import main as validate_l4_2_retained

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l4-phase-l4.3-policy-baseline.json"
L4_2_BASELINE = HERE / "stm32l4-phase-l4.2-discovery-baseline.json"
EXPECTED_ORDERING_AUTHORITY_SHA256 = "da0dd36a6f9a7d9ac75b5910d45bfb477c664c94c1bedc9d482292cd7bb479ec"
EXPECTED_EXCEPTIONS_SHA256 = "d7514a5db450d36b6acbbfd8e6650074134f3637c2012047a549557149d6bc31"
EXPECTED_L4_2_BASELINE_SHA256 = "eeb538cfac4ace738878ca5b60adad2ef122a46881565d3917d77078af8fe804"
EXPECTED_L4_2_ACTIVE_SET_SHA256 = "cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45"
EXPECTED_PRODUCTION_PRESTATE_SHA256 = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"
EMPTY_SET_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def main() -> int:
    req(validate_l4_2_retained() == 0, "L4.2 retained evidence validation failed")
    req(sha256(DEFAULT_ORDERING_AUTHORITY) == EXPECTED_ORDERING_AUTHORITY_SHA256, "L4.3 Ordering Information authority digest drifted")
    req(sha256(DEFAULT_EXCEPTIONS) == EXPECTED_EXCEPTIONS_SHA256, "L4.3 exact-variant exception digest drifted")
    req(sha256(L4_2_BASELINE) == EXPECTED_L4_2_BASELINE_SHA256, "L4.2 discovery baseline digest drifted")

    authorities = load_ordering_authority()
    exceptions = load_exact_variant_exceptions()
    req(len(authorities) == 24, "L4.3 authority series count drifted")
    req(len({item["document_id"] for item in authorities.values()}) == 20, "L4.3 unique datasheet count drifted")
    req(set(exceptions) == EXPECTED_EXCEPTION_ICPNS, "L4.3 exact exception whitelist drifted")

    baseline = read_json(BASELINE)
    expected_bindings = {
        "exact_variant_exceptions_sha256": EXPECTED_EXCEPTIONS_SHA256,
        "l4_2_active_exact_set_sha256": EXPECTED_L4_2_ACTIVE_SET_SHA256,
        "l4_2_baseline_sha256": EXPECTED_L4_2_BASELINE_SHA256,
        "ordering_authority_sha256": EXPECTED_ORDERING_AUTHORITY_SHA256,
        "production_prestate_sha256": EXPECTED_PRODUCTION_PRESTATE_SHA256,
    }
    req(baseline.get("schema_version") == 1 and baseline.get("phase") == "L4.3" and baseline.get("family") == "STM32L4", "L4.3 baseline identity/schema drifted")
    req(baseline.get("source_bindings") == expected_bindings, "L4.3 baseline source bindings drifted")
    claims = baseline.get("claims")
    req(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "L4.3 baseline claims escaped fail-closed state")

    rebuilt = build_baseline()
    req(rebuilt == baseline, "L4.3 committed baseline is not byte-semantic equivalent to deterministic rebuild")

    plan = build_plan()
    req(plan_is_clean(plan), "L4.3 deterministic plan is not clean")
    req(plan["candidate_count"] == 446 and plan["base_device_count"] == 138, "L4.3 candidate boundary drifted")
    req(plan["decision_counts"] == {"metadata_ready": 446, "manual_review_required": 0, "reject": 0}, "L4.3 disposition drifted")
    req(plan["metadata_ready_set_sha256"] == EXPECTED_L4_2_ACTIVE_SET_SHA256, "L4.3 metadata-ready set is not exactly the retained L4.2 Active exact set")
    req(plan["manual_review_set_sha256"] == EMPTY_SET_SHA256 and plan["reject_set_sha256"] == EMPTY_SET_SHA256, "L4.3 non-ready sets are not empty")
    req(plan["exact_variant_exception_icpns"] == sorted(EXPECTED_EXCEPTION_ICPNS), "L4.3 exception use drifted")
    req(plan["issues"] == [] and plan["manual_review_base_devices"] == [], "L4.3 unresolved metadata issues remain")

    production = plan["production_snapshot"]
    req(production["manifest_sha256"] == EXPECTED_PRODUCTION_PRESTATE_SHA256, "Production prestate digest drifted")
    req(production["exact_icpn_count"] == 1272 and production["base_device_count"] == 392 and production["family_count"] == 11, "Production aggregate boundary drifted")
    req(production["stm32l4_exact_icpn_count"] == 0, "L4.3 wrote STM32L4 into Production")
    req(plan["production_write_applied"] is False and plan["canonical_dataset_admission"] == "deferred", "L4.3 crossed the admission/publication boundary")

    contract = plan["metadata_contract"]
    for key in (
        "canonical_admission_authorized", "production_write_authorized", "programming_policy_defined",
        "flash_geometry_qualified", "option_security_semantics_qualified", "physical_hil_qualified",
        "runtime_programming_support_claimed", "scope_expansion_authorized",
    ):
        req(contract[key] is False, f"L4.3 contract escaped fail-closed state: {key}")
    req(contract["exact_variant_exception_count"] == 3 and contract["exact_variant_exceptions_expand_identity_scope"] is False, "L4.3 exception contract drifted")

    print("STM32L4 L4.3 permanent metadata hard-lock: PASS")
    print(json.dumps({
        "family": "STM32L4",
        "phase": "L4.3",
        "metadata_ready": 446,
        "manual_review": 0,
        "reject": 0,
        "exact_variant_exceptions": 3,
        "production_exact_icpns": 1272,
        "production_stm32l4_exact_icpns": 0,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
