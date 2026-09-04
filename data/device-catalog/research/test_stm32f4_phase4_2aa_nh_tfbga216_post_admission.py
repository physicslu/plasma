#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
PLAN = HERE / "stm32f4-phase4.2aa-nh-tfbga216-admission-plan.json"
AUDIT = HERE / "stm32f4-phase4.2aa-nh-tfbga216-admission-audit.json"
PLAN_SHA256 = "3134a7efee2395c4d01f745c3e2624d311cb243967c2ed19917191ae488b79cd"
PUBLISHED_CATALOG_SHA256 = "064b4a563532f03ceef95d8d832b52ce79f5b88e5b0e4d9905aeee2092674cf5"
EVIDENCE_ID = "stm32f4-phase4.2aa-nh-tfbga216-admission-batch2-2026-09-05-retained-20260904T164441Z-a465a62"
EXPECTED = {
    "STM32F469NEH6": ("STM32F469NE", "512 KiB", "-40 to 85 C", ""),
    "STM32F469NGH6": ("STM32F469NG", "1024 KiB", "-40 to 85 C", ""),
    "STM32F469NIH6": ("STM32F469NI", "2048 KiB", "-40 to 85 C", ""),
    "STM32F469NIH6TR": ("STM32F469NI", "2048 KiB", "-40 to 85 C", "TR"),
    "STM32F469NIH7": ("STM32F469NI", "2048 KiB", "-40 to 105 C", ""),
    "STM32F479NGH6": ("STM32F479NG", "1024 KiB", "-40 to 85 C", ""),
    "STM32F479NIH6": ("STM32F479NI", "2048 KiB", "-40 to 85 C", ""),
}


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 352
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) == 124

    by_icpn = {row["icpn"]: row for row in rows}
    assert set(EXPECTED) <= set(by_icpn)
    for icpn, (base_device, flash_size, temperature_grade, option_suffix) in EXPECTED.items():
        row = by_icpn[icpn]
        assert row["base_device"] == base_device
        assert row["package"] == "TFBGA"
        assert row["pin_count"] == "216"
        assert row["flash_size"] == flash_size
        assert row["temperature_grade"] == temperature_grade
        assert row["option_suffix"] == option_suffix
        assert row["openocd_target_config"] == "tcl/target/stm32f4x.cfg"
        assert EVIDENCE_ID in row["source_reference"]

    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == PLAN_SHA256
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
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
    assert audit["production_rows_before"] == 345
    assert audit["production_rows_after"] == 352
    assert audit["production_base_devices_before"] == 119
    assert audit["production_base_devices_after"] == 124
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert audit["lifecycle_exclusions"] == []
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID
    print("Phase 4.2AA post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
