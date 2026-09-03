#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
PLAN = HERE / "stm32f4-phase4.2u-h-admission-batch1-plan.json"
AUDIT = HERE / "stm32f4-phase4.2u-h-admission-batch1-audit.json"
PLAN_SHA256 = "13251cba507dea125654da403d808382850b8b602921f5dbca1fd1790c8c8852"
PUBLISHED_CATALOG_SHA256 = "6c5138d5de50187d4f877fe3dcbeb9e0b68189f2e957a085fe2d7128965f0831"
EVIDENCE_ID = "stm32f4-phase4.2u-h-admission-batch1-2026-09-03-retained-20260903T123710Z-a642f06"
EXCLUDED = {"STM32F413VHT3", "STM32F413ZHJ3"}
EXPECTED = {
    "STM32F413CHU3": ("STM32F413CH", "UFQFPN", "48", "-40 to 125 C", ""),
    "STM32F413CHU3TR": ("STM32F413CH", "UFQFPN", "48", "-40 to 125 C", "TR"),
    "STM32F413CHU6": ("STM32F413CH", "UFQFPN", "48", "-40 to 85 C", ""),
    "STM32F413CHU6TR": ("STM32F413CH", "UFQFPN", "48", "-40 to 85 C", "TR"),
    "STM32F413RHT3": ("STM32F413RH", "LQFP", "64", "-40 to 125 C", ""),
    "STM32F413RHT6": ("STM32F413RH", "LQFP", "64", "-40 to 85 C", ""),
    "STM32F413RHT6TR": ("STM32F413RH", "LQFP", "64", "-40 to 85 C", "TR"),
    "STM32F413VHH3": ("STM32F413VH", "UFBGA", "100", "-40 to 125 C", ""),
    "STM32F413VHH6": ("STM32F413VH", "UFBGA", "100", "-40 to 85 C", ""),
    "STM32F413VHT6": ("STM32F413VH", "LQFP", "100", "-40 to 85 C", ""),
    "STM32F413ZHJ6": ("STM32F413ZH", "UFBGA", "144", "-40 to 85 C", ""),
    "STM32F413ZHJ6TR": ("STM32F413ZH", "UFBGA", "144", "-40 to 85 C", "TR"),
    "STM32F413ZHT3": ("STM32F413ZH", "LQFP", "144", "-40 to 125 C", ""),
    "STM32F413ZHT6": ("STM32F413ZH", "LQFP", "144", "-40 to 85 C", ""),
}


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 321
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) >= 105

    by_icpn = {row["icpn"]: row for row in rows}
    assert set(EXPECTED) <= set(by_icpn)
    assert EXCLUDED.isdisjoint(by_icpn)
    for icpn, (base_device, package, pin_count, temperature_grade, option_suffix) in EXPECTED.items():
        row = by_icpn[icpn]
        assert row["base_device"] == base_device
        assert row["package"] == package
        assert row["pin_count"] == pin_count
        assert row["flash_size"] == "1536 KiB"
        assert row["temperature_grade"] == temperature_grade
        assert row["option_suffix"] == option_suffix
        assert row["openocd_target_config"] == "tcl/target/stm32f4x.cfg"
        assert EVIDENCE_ID in row["source_reference"]

    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == PLAN_SHA256
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert plan["decision_counts"] == {
        "admit": 14,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    assert plan["conflicts"] == 0
    assert {candidate["icpn"] for candidate in plan["candidates"]} == set(EXPECTED)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "published"
    assert audit["production_rows_before"] == 307
    assert audit["production_rows_after"] == 321
    assert audit["production_base_devices_before"] == 101
    assert audit["production_base_devices_after"] == 105
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert set(audit["lifecycle_exclusions"]) == EXCLUDED
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID
    print("Phase 4.2U post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
