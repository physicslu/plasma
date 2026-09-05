#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
PLAN = HERE / "stm32f4-phase4.2ac-f410-x8-admission-plan.json"
AUDIT = HERE / "stm32f4-phase4.2ac-f410-x8-admission-audit.json"
PLAN_SHA256 = "99ae4906573f168574c4ac6bce0b35b9e692a67a8d05183c020b96f5251b61a9"
PUBLISHED_CATALOG_SHA256 = "8f6db734cc62b37b2de349c186b5f0d7fcfe8489dbda6ccf8ed121b4cbd75883"
EVIDENCE_ID = "stm32f4-phase4.2ac-f410-x8-admission-2026-09-05-retained-20260904T174206Z-160bb17"
EXPECTED = {
    "STM32F410C8U6": ("STM32F410C8", "UFQFPN", "48", "-40 to 85 C", ""),
    "STM32F410C8U6TR": ("STM32F410C8", "UFQFPN", "48", "-40 to 85 C", "TR"),
    "STM32F410C8U7": ("STM32F410C8", "UFQFPN", "48", "-40 to 105 C", ""),
    "STM32F410C8U7TR": ("STM32F410C8", "UFQFPN", "48", "-40 to 105 C", "TR"),
    "STM32F410T8Y6TR": ("STM32F410T8", "WLCSP", "36", "-40 to 85 C", "TR"),
}


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 384
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) == 139

    by_icpn = {row["icpn"]: row for row in rows}
    assert set(EXPECTED) <= set(by_icpn)
    for icpn, (base_device, package, pin_count, temperature_grade, option_suffix) in EXPECTED.items():
        row = by_icpn[icpn]
        assert row["base_device"] == base_device
        assert row["package"] == package
        assert row["pin_count"] == pin_count
        assert row["flash_size"] == "64 KiB"
        assert row["temperature_grade"] == temperature_grade
        assert row["option_suffix"] == option_suffix
        assert row["openocd_target_config"] == "tcl/target/stm32f4x.cfg"
        assert EVIDENCE_ID in row["source_reference"]

    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == PLAN_SHA256
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert plan["decision_counts"] == {
        "admit": 5,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    assert plan["conflicts"] == 0
    assert {candidate["icpn"] for candidate in plan["candidates"]} == set(EXPECTED)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "published"
    assert audit["production_rows_before"] == 352
    assert audit["production_rows_after"] == 357
    assert audit["production_base_devices_before"] == 124
    assert audit["production_base_devices_after"] == 126
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert audit["lifecycle_exclusions"] == []
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID
    print("Phase 4.2AC post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
