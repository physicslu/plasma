#!/usr/bin/env python3
"""Permanent hard-lock validator for STM32L1 Phase L1.3 metadata policy."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from build_stm32l1_phase_l1_3_baseline import build_baseline
from stm32l1_metadata_policy import (
    DEFAULT_EXCEPTIONS,
    DEFAULT_ORDERING_AUTHORITY,
    load_exact_variant_exceptions,
    load_ordering_authority,
)
from stm32l1_phase_l1_3_policy import build_plan, plan_is_clean
from validate_stm32l1_phase_l1_2_retained_evidence import main as validate_l1_2_retained

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l1-phase-l1.3-policy-baseline.json"
L1_2_BASELINE = HERE / "stm32l1-phase-l1.2-discovery-baseline.json"

EXPECTED_BASELINE_SHA256 = "6da49ceda71a3611244e1961e6aca3809d5809f8f7106834123c6ae48e726e62"
EXPECTED_ORDERING_AUTHORITY_SHA256 = "c689e848a58a45e3b1d855e56f9a4bba5fb953a89a9565091c687fc7bb392bc9"
EXPECTED_EXCEPTIONS_SHA256 = "1b2c4bba21169e1351185d094b0da984ed2c0f03b4fb5ddf1edb431b9e74a763"
EXPECTED_L1_2_BASELINE_SHA256 = "2f44e54dfac6904cc9af485e14eeb54e2d1a564f1cb633668fdf8f3a78ab4f92"
EXPECTED_L1_2_ACTIVE_SET_SHA256 = "0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12"
EXPECTED_METADATA_ROWS_SHA256 = "c794a21a63e72d805170034defe4af4e749ce456966f9083efe2f4abfa4fe247"
EXPECTED_PRODUCTION_GIT_BLOB = "1aa2311a25a69742c428147a402816ed5071e04e"
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
    req(validate_l1_2_retained() == 0, "L1.2 retained evidence validation failed")
    req(sha256(BASELINE) == EXPECTED_BASELINE_SHA256, "L1.3 frozen baseline digest drifted")
    req(sha256(DEFAULT_ORDERING_AUTHORITY) == EXPECTED_ORDERING_AUTHORITY_SHA256, "L1.3 Ordering Information authority drifted")
    req(sha256(DEFAULT_EXCEPTIONS) == EXPECTED_EXCEPTIONS_SHA256, "L1.3 exact-variant exception file drifted")
    req(sha256(L1_2_BASELINE) == EXPECTED_L1_2_BASELINE_SHA256, "L1.2 discovery baseline drifted")

    authorities = load_ordering_authority()
    exceptions = load_exact_variant_exceptions()
    req(len(authorities) == 10, "L1.3 authority record count drifted")
    req(len({row["document_id"] for row in authorities}) == 10, "L1.3 unique datasheet count drifted")
    req(exceptions == {}, "L1.3 exact exception whitelist is no longer empty")
    req(
        [row["authority_id"] for row in authorities] == [
            "l100-gen-a", "l100-xc", "l15-gen-a", "l15-xc-low-pin",
            "l15-xc-high-pin", "l15-xd", "l15-xe", "l162-xc",
            "l162-xd", "l162-xe",
        ],
        "L1.3 authority ordering/identity drifted",
    )

    baseline = read_json(BASELINE)
    req(
        baseline.get("schema_version") == 1
        and baseline.get("phase") == "L1.3"
        and baseline.get("family") == "STM32L1",
        "L1.3 baseline identity/schema drifted",
    )
    expected_bindings = {
        "exact_variant_exceptions_sha256": EXPECTED_EXCEPTIONS_SHA256,
        "l1_2_active_exact_set_sha256": EXPECTED_L1_2_ACTIVE_SET_SHA256,
        "l1_2_baseline_sha256": EXPECTED_L1_2_BASELINE_SHA256,
        "ordering_authority_sha256": EXPECTED_ORDERING_AUTHORITY_SHA256,
        "production_manifest_git_blob": EXPECTED_PRODUCTION_GIT_BLOB,
    }
    req(baseline.get("source_bindings") == expected_bindings, "L1.3 source bindings drifted")
    authority = baseline.get("authority")
    req(
        authority == {
            "authority_record_count": 10,
            "exact_variant_exception_count": 0,
            "exact_variant_exception_icpns": [],
            "generation_migration_authority": "TN1176",
            "primary": "official ST datasheet Ordering Information",
            "unique_datasheet_count": 10,
        },
        "L1.3 authority summary drifted",
    )
    claims = baseline.get("claims")
    req(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "L1.3 claims escaped fail-closed state")

    rebuilt = build_baseline()
    req(rebuilt == baseline, "L1.3 committed baseline differs from deterministic rebuild")

    plan = build_plan()
    req(plan_is_clean(plan), "L1.3 deterministic plan is not clean")
    req(plan["candidate_count"] == 144 and plan["base_device_count"] == 59, "L1.3 candidate boundary drifted")
    req(
        plan["decision_counts"] == {"metadata_ready": 144, "manual_review_required": 0, "reject": 0},
        "L1.3 metadata disposition drifted",
    )
    req(plan["metadata_ready_set_sha256"] == EXPECTED_L1_2_ACTIVE_SET_SHA256, "L1.3 ready set differs from L1.2 Active set")
    req(plan["metadata_rows_sha256"] == EXPECTED_METADATA_ROWS_SHA256, "L1.3 metadata row set drifted")
    req(
        plan["manual_review_set_sha256"] == EMPTY_SET_SHA256
        and plan["reject_set_sha256"] == EMPTY_SET_SHA256,
        "L1.3 non-ready sets are no longer empty",
    )
    req(plan["exact_variant_exception_icpns"] == [], "L1.3 exact exception use drifted")
    req(plan["issues"] == [] and plan["manual_review_base_devices"] == [], "L1.3 unresolved metadata issues remain")

    production = plan["production_snapshot"]
    req(production["manifest_git_blob"] == EXPECTED_PRODUCTION_GIT_BLOB, "Production manifest binding drifted")
    req(
        production["exact_icpn_count"] == 1718
        and production["base_device_count"] == 530
        and production["family_count"] == 12
        and production["stm32l1_exact_icpn_count"] == 0,
        "L1.3 Production boundary drifted",
    )
    req(plan["production_write_applied"] is False and plan["canonical_dataset_admission"] == "deferred", "L1.3 crossed publication boundary")

    contract = plan["metadata_contract"]
    req(contract["admission_deferred_to"] == "L1.4", "L1.3 next-phase boundary drifted")
    req(contract["exact_variant_exception_count"] == 0, "L1.3 exception count drifted")
    req(contract["exact_variant_exceptions_expand_identity_scope"] is False, "L1.3 exceptions expanded identity scope")
    for key in (
        "canonical_admission_authorized", "production_write_authorized", "programming_policy_defined",
        "flash_geometry_qualified", "option_security_semantics_qualified", "physical_hil_qualified",
        "runtime_programming_support_claimed", "openocd_routing_gates_metadata",
        "cmsis_alias_gates_metadata", "scope_expansion_authorized",
    ):
        req(contract[key] is False, f"L1.3 contract escaped fail-closed state: {key}")

    print("STM32L1 L1.3 permanent metadata hard-lock: PASS")
    print(json.dumps({
        "family": "STM32L1",
        "phase": "L1.3",
        "metadata_ready": 144,
        "manual_review": 0,
        "reject": 0,
        "exact_variant_exceptions": 0,
        "authority_records": 10,
        "unique_datasheets": 10,
        "production_exact_icpns": 1718,
        "production_stm32l1_exact_icpns": 0,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
