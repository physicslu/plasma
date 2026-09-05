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
PLAN = HERE / "stm32f4-phase4.2ai-ay-wlcsp168-admission-plan.json"
AUDIT = HERE / "stm32f4-phase4.2ai-ay-wlcsp168-admission-audit.json"
PLAN_SHA256 = "c64c7c5d9d6248fc6042322785041b4326293a143cb7f5a859a86ac7433ab3c9"
PUBLISHED_CATALOG_SHA256 = "3ab4793d67f1b70e8c8f4c883bd9c24430f25b7a11a199ba32bb50fc48f39359"
EVIDENCE_ID = "stm32f4-phase4.2ai-ay-wlcsp168-admission-2026-09-05-retained-20260905T133254Z-de33e30"
EXPECTED = {
    "STM32F469AEH6": ("STM32F469AE", "UFBGA", "169", "512 KiB", "-40 to 85 C", ""),
    "STM32F469AEH7": ("STM32F469AE", "UFBGA", "169", "512 KiB", "-40 to 105 C", ""),
    "STM32F469AEH7TR": ("STM32F469AE", "UFBGA", "169", "512 KiB", "-40 to 105 C", "TR"),
    "STM32F469AGH6": ("STM32F469AG", "UFBGA", "169", "1024 KiB", "-40 to 85 C", ""),
    "STM32F469AGH6TR": ("STM32F469AG", "UFBGA", "169", "1024 KiB", "-40 to 85 C", "TR"),
    "STM32F469AGY6TR": ("STM32F469AG", "WLCSP", "168", "1024 KiB", "-40 to 85 C", "TR"),
    "STM32F469AIH6": ("STM32F469AI", "UFBGA", "169", "2048 KiB", "-40 to 85 C", ""),
    "STM32F469AIY6TR": ("STM32F469AI", "WLCSP", "168", "2048 KiB", "-40 to 85 C", "TR"),
    "STM32F479AGH6": ("STM32F479AG", "UFBGA", "169", "1024 KiB", "-40 to 85 C", ""),
    "STM32F479AIH6": ("STM32F479AI", "UFBGA", "169", "2048 KiB", "-40 to 85 C", ""),
    "STM32F479AIY6TR": ("STM32F479AI", "WLCSP", "168", "2048 KiB", "-40 to 85 C", "TR"),
}
B_T_BLOCKED = {
    "STM32F429BE", "STM32F429BG", "STM32F429BI", "STM32F439BG", "STM32F439BI",
    "STM32F469BE", "STM32F469BG", "STM32F469BI", "STM32F479BG", "STM32F479BI",
}


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 384
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) == 139

    by_icpn = {row["icpn"]: row for row in rows}
    assert set(EXPECTED) <= set(by_icpn)
    for icpn, expected in EXPECTED.items():
        base_device, package, pin_count, flash_size, temperature_grade, option_suffix = expected
        row = by_icpn[icpn]
        assert row["base_device"] == base_device
        assert row["package"] == package
        assert row["pin_count"] == pin_count
        assert row["flash_size"] == flash_size
        assert row["temperature_grade"] == temperature_grade
        assert row["option_suffix"] == option_suffix
        assert row["mapping_status"] == "deterministic_ordering_pattern"
        assert row["openocd_target_config"] == "tcl/target/stm32f4x.cfg"
        assert row["source_type"] == "official_st_product_page_retained_browser_evidence"
        assert row["source_authority"] == "STMicroelectronics official"
        assert row["verification_status"] == "verified_direct_st_retained_browser_exact_icpn"
        assert EVIDENCE_ID in row["source_reference"]

    assert hashlib.sha256(CATALOG.read_bytes()).hexdigest() == PUBLISHED_CATALOG_SHA256
    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == PLAN_SHA256
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert plan["candidate_count"] == 11
    assert plan["decision_counts"] == {
        "admit": 11,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    assert plan["conflicts"] == 0
    assert plan["canonical_rows_before"] == 373
    assert {candidate["icpn"] for candidate in plan["candidates"]} == set(EXPECTED)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "published"
    assert audit["proposal_run_id"] == 33971024145
    assert audit["proposal_artifact_id"] == 9970915767
    assert audit["proposal_artifact_zip_sha256"] == "c7bddf328cbedaf15227cda783ec1334ea05083e13b2fb84f3764458609d82cf"
    assert audit["production_rows_before"] == 373
    assert audit["production_rows_after"] == 384
    assert audit["production_base_devices_before"] == 134
    assert audit["production_base_devices_after"] == 139
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert audit["lifecycle_exclusions"] == []
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID

    inventory = build_inventory(catalog_path=OPENOCD_CATALOG, canonical_path=CATALOG)
    assert inventory["production"]["exact_icpn_rows"] == 384
    assert inventory["production"]["base_device_count"] == 139
    assert {expected[0] for expected in EXPECTED.values()} <= set(
        inventory["production"]["base_devices"]
    )
    assert inventory["gap"]["base_device_count"] == 10
    assert inventory["gap"]["policy_ready_count"] == 0
    assert inventory["gap"]["policy_blocked_count"] == 10
    assert inventory["gap"]["policy_ready"] == []
    blocked = {item["base_device"]: item for item in inventory["gap"]["policy_blocked"]}
    assert set(blocked) == B_T_BLOCKED
    for base_device in B_T_BLOCKED:
        assert blocked[base_device]["package_codes"] == ["T"]
        assert blocked[base_device]["policy_blockers"] == [
            "unsupported STM32F4 pin/package combination: B/T"
        ]

    print("Phase 4.2AI post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
