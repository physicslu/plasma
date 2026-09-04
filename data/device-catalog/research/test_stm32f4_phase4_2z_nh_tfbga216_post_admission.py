#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
PLAN = HERE / "stm32f4-phase4.2z-nh-tfbga216-admission-plan.json"
AUDIT = HERE / "stm32f4-phase4.2z-nh-tfbga216-admission-audit.json"
PLAN_SHA256 = "0717c9717fd3c4c9d3ab608a216fe8745cf47731cd59783a03850302caee489a"
PUBLISHED_CATALOG_SHA256 = "d1ffdeed2d6cc2bc2aea0688f4da213cade3e8e567aec159458ed873837cd07c"
EVIDENCE_ID = "stm32f4-phase4.2z-nh-tfbga216-admission-batch1-2026-09-04-retained-20260904T124757Z-6a606b9"
EXPECTED = {
    "STM32F429NEH6": ("STM32F429NE", "512 KiB", "-40 to 85 C", ""),
    "STM32F429NGH6": ("STM32F429NG", "1024 KiB", "-40 to 85 C", ""),
    "STM32F429NIH6": ("STM32F429NI", "2048 KiB", "-40 to 85 C", ""),
    "STM32F429NIH6TR": ("STM32F429NI", "2048 KiB", "-40 to 85 C", "TR"),
    "STM32F429NIH7": ("STM32F429NI", "2048 KiB", "-40 to 105 C", ""),
    "STM32F439NGH6": ("STM32F439NG", "1024 KiB", "-40 to 85 C", ""),
    "STM32F439NIH6": ("STM32F439NI", "2048 KiB", "-40 to 85 C", ""),
}


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 345
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) >= 119

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
    assert audit["production_rows_before"] == 338
    assert audit["production_rows_after"] == 345
    assert audit["production_base_devices_before"] == 114
    assert audit["production_base_devices_after"] == 119
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert audit["lifecycle_exclusions"] == []
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID
    print("Phase 4.2Z post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
