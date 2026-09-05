#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
OPENOCD_CATALOG = HERE / "openocd-parts-canonical.csv"
PLAN = HERE / "stm32f4-phase4.2ae-f410-rx-admission-plan.json"
AUDIT = HERE / "stm32f4-phase4.2ae-f410-rx-admission-audit.json"
PLAN_SHA256 = "6fd04aa2c1dfa1a362bb881f69c614b597604d1e2f14550e53e80f449fe14a9a"
PUBLISHED_CATALOG_SHA256 = "0a471928141fdd07529904bd74c952275b97eb225979ad8fcc596263dec785c7"
EVIDENCE_ID = "stm32f4-phase4.2ae-f410-rx-admission-2026-09-05-retained-20260904T223827Z-38671c7"
EXPECTED = {
    "STM32F410R8T6": ("STM32F410R8", "LQFP", "64", "64 KiB", "-40 to 85 C", ""),
    "STM32F410RBI3": ("STM32F410RB", "UFBGA", "64", "128 KiB", "-40 to 125 C", ""),
    "STM32F410RBI6": ("STM32F410RB", "UFBGA", "64", "128 KiB", "-40 to 85 C", ""),
    "STM32F410RBT6": ("STM32F410RB", "LQFP", "64", "128 KiB", "-40 to 85 C", ""),
    "STM32F410RBT6TR": ("STM32F410RB", "LQFP", "64", "128 KiB", "-40 to 85 C", "TR"),
    "STM32F410RBT7": ("STM32F410RB", "LQFP", "64", "128 KiB", "-40 to 105 C", ""),
    "STM32F410RBT7TR": ("STM32F410RB", "LQFP", "64", "128 KiB", "-40 to 105 C", "TR"),
}
A_Y_READY = {
    "STM32F469AE",
    "STM32F469AG",
    "STM32F469AI",
    "STM32F479AG",
    "STM32F479AI",
}
B_T_BLOCKED = {
    "STM32F429BE",
    "STM32F429BG",
    "STM32F429BI",
    "STM32F439BG",
    "STM32F439BI",
    "STM32F469BE",
    "STM32F469BG",
    "STM32F469BI",
    "STM32F479BG",
    "STM32F479BI",
}


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 373
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) == 134

    by_icpn = {row["icpn"]: row for row in rows}
    assert set(EXPECTED) <= set(by_icpn)
    for icpn, (base_device, package, pin_count, flash_size, temperature_grade, option_suffix) in EXPECTED.items():
        row = by_icpn[icpn]
        assert row["base_device"] == base_device
        assert row["package"] == package
        assert row["pin_count"] == pin_count
        assert row["flash_size"] == flash_size
        assert row["temperature_grade"] == temperature_grade
        assert row["option_suffix"] == option_suffix
        assert row["mapping_status"] == "deterministic_ordering_pattern"
        assert row["openocd_target_config"] == "tcl/target/stm32f4x.cfg"
        assert EVIDENCE_ID in row["source_reference"]

    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == PLAN_SHA256
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert plan["candidate_count"] == 7
    assert plan["decision_counts"] == {
        "admit": 7,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    assert plan["conflicts"] == 0
    assert {candidate["icpn"] for candidate in plan["candidates"]} == set(EXPECTED)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "published"
    assert audit["proposal_run_id"] == 33936475732
    assert audit["proposal_artifact_id"] == 9960336185
    assert audit["proposal_artifact_zip_sha256"] == "1fc390581bab2c469826e429ff98a93d6e6d37e330a2c33566e9eb011732c416"
    assert audit["production_rows_before"] == 357
    assert audit["production_rows_after"] == 364
    assert audit["production_base_devices_before"] == 126
    assert audit["production_base_devices_after"] == 128
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert audit["lifecycle_exclusions"] == []
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID

    inventory = build_inventory(catalog_path=OPENOCD_CATALOG, canonical_path=CATALOG)
    assert inventory["production"]["exact_icpn_rows"] == 373
    assert inventory["production"]["base_device_count"] == 134
    assert inventory["gap"]["base_device_count"] == 15
    assert inventory["gap"]["policy_ready_count"] == 5
    assert inventory["gap"]["policy_blocked_count"] == 10
    assert {item["base_device"] for item in inventory["gap"]["policy_ready"]} == A_Y_READY
    assert {
        "STM32F427AG",
        "STM32F427AI",
        "STM32F429AG",
        "STM32F429AI",
        "STM32F437AI",
        "STM32F439AI",
    } <= set(inventory["production"]["base_devices"])

    blocked = {item["base_device"]: item for item in inventory["gap"]["policy_blocked"]}
    assert set(blocked) == B_T_BLOCKED
    for base_device in B_T_BLOCKED:
        assert blocked[base_device]["package_codes"] == ["T"]
        assert blocked[base_device]["policy_blockers"] == [
            "unsupported STM32F4 pin/package combination: B/T"
        ]

    print("Phase 4.2AE post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
