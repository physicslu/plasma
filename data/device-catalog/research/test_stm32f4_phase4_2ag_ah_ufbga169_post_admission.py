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
PLAN = HERE / "stm32f4-phase4.2ag-ah-ufbga169-admission-plan.json"
AUDIT = HERE / "stm32f4-phase4.2ag-ah-ufbga169-admission-audit.json"
PLAN_SHA256 = "b2d8976f6562c1d7e7aee90f25e466399d4f72216161a14510bc4d4ef8ca4ad0"
PUBLISHED_CATALOG_SHA256 = "c3b4ae36d659226224b64941860631444f8d1bd7f52c44729ad46dfa90cd13ae"
EVIDENCE_ID = "stm32f4-phase4.2ag-ah-ufbga169-admission-2026-09-05-retained-20260905T041556Z-bee616f"
EXPECTED = {
    "STM32F427AGH6": ("STM32F427AG", "1024 KiB", ""),
    "STM32F427AIH6": ("STM32F427AI", "2048 KiB", ""),
    "STM32F427AIH6TR": ("STM32F427AI", "2048 KiB", "TR"),
    "STM32F429AGH6": ("STM32F429AG", "1024 KiB", ""),
    "STM32F429AGH6TR": ("STM32F429AG", "1024 KiB", "TR"),
    "STM32F429AIH6": ("STM32F429AI", "2048 KiB", ""),
    "STM32F437AIH6": ("STM32F437AI", "2048 KiB", ""),
    "STM32F437AIH6TR": ("STM32F437AI", "2048 KiB", "TR"),
    "STM32F439AIH6": ("STM32F439AI", "2048 KiB", ""),
}
A_Y_BLOCKED = {
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
    for icpn, (base_device, flash_size, option_suffix) in EXPECTED.items():
        row = by_icpn[icpn]
        assert row["base_device"] == base_device
        assert row["package"] == "UFBGA"
        assert row["pin_count"] == "169"
        assert row["flash_size"] == flash_size
        assert row["temperature_grade"] == "-40 to 85 C"
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
    assert plan["candidate_count"] == 9
    assert plan["decision_counts"] == {
        "admit": 9,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    assert plan["conflicts"] == 0
    assert plan["canonical_rows_before"] == 364
    assert {candidate["icpn"] for candidate in plan["candidates"]} == set(EXPECTED)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "published"
    assert audit["proposal_run_id"] == 33944452604
    assert audit["proposal_artifact_id"] == 9962871328
    assert audit["proposal_artifact_zip_sha256"] == "a82aaa78b3378b71fc48cfd2d04dc0f761293afa8cae34ecad9f1e28cdd42478"
    assert audit["production_rows_before"] == 364
    assert audit["production_rows_after"] == 373
    assert audit["production_base_devices_before"] == 128
    assert audit["production_base_devices_after"] == 134
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert audit["lifecycle_exclusions"] == []
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID

    inventory = build_inventory(catalog_path=OPENOCD_CATALOG, canonical_path=CATALOG)
    assert inventory["production"]["exact_icpn_rows"] == 373
    assert inventory["production"]["base_device_count"] == 134
    assert {base for base, _flash, _option in EXPECTED.values()} <= set(
        inventory["production"]["base_devices"]
    )
    assert inventory["gap"]["base_device_count"] == 15
    assert inventory["gap"]["policy_ready_count"] == 0
    assert inventory["gap"]["policy_blocked_count"] == 15
    assert inventory["gap"]["policy_ready"] == []
    blocked = {item["base_device"]: item for item in inventory["gap"]["policy_blocked"]}
    assert set(blocked) == A_Y_BLOCKED | B_T_BLOCKED
    for base_device in A_Y_BLOCKED:
        assert blocked[base_device]["package_codes"] == ["H", "Y"]
        assert blocked[base_device]["policy_blockers"] == [
            "unsupported STM32F4 pin/package combination: A/Y"
        ]
    for base_device in B_T_BLOCKED:
        assert blocked[base_device]["package_codes"] == ["T"]
        assert blocked[base_device]["policy_blockers"] == [
            "unsupported STM32F4 pin/package combination: B/T"
        ]

    print("Phase 4.2AG post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
