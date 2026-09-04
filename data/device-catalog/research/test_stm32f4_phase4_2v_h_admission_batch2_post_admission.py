#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
PLAN = HERE / "stm32f4-phase4.2v-h-admission-batch2-plan.json"
AUDIT = HERE / "stm32f4-phase4.2v-h-admission-batch2-audit.json"
PLAN_SHA256 = "1b223c19b01f413d7bcfa32117dc7a7222f46a6a5e66a82d86fc48787fee5042"
PUBLISHED_CATALOG_SHA256 = "361ed0f6f0ffd7e6cb31c31425d7b13d7e39538d8e8c8218fbe8b48316735e7b"
EVIDENCE_ID = "stm32f4-phase4.2v-h-admission-batch2-2026-09-03-retained-20260904T011528Z-cd38d54"
EXCLUDED = {
    "STM32F423CHU3",
    "STM32F423RHT3",
    "STM32F423VHH3",
    "STM32F423VHT3",
    "STM32F423ZHJ3",
}
EXPECTED = {
    "STM32F423CHU6": ("STM32F423CH", "UFQFPN", "48", "-40 to 85 C", ""),
    "STM32F423RHT6": ("STM32F423RH", "LQFP", "64", "-40 to 85 C", ""),
    "STM32F423RHT6TR": ("STM32F423RH", "LQFP", "64", "-40 to 85 C", "TR"),
    "STM32F423VHH6": ("STM32F423VH", "UFBGA", "100", "-40 to 85 C", ""),
    "STM32F423VHT6": ("STM32F423VH", "LQFP", "100", "-40 to 85 C", ""),
    "STM32F423VHT6TR": ("STM32F423VH", "LQFP", "100", "-40 to 85 C", "TR"),
    "STM32F423ZHJ6": ("STM32F423ZH", "UFBGA", "144", "-40 to 85 C", ""),
    "STM32F423ZHJ6I": ("STM32F423ZH", "UFBGA", "144", "-40 to 85 C", "I"),
    "STM32F423ZHT3": ("STM32F423ZH", "LQFP", "144", "-40 to 125 C", ""),
    "STM32F423ZHT6": ("STM32F423ZH", "LQFP", "144", "-40 to 85 C", ""),
}


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 331
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) >= 109

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
        "admit": 10,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    assert plan["conflicts"] == 0
    assert {candidate["icpn"] for candidate in plan["candidates"]} == set(EXPECTED)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "published"
    assert audit["production_rows_before"] == 321
    assert audit["production_rows_after"] == 331
    assert audit["production_base_devices_before"] == 105
    assert audit["production_base_devices_after"] == 109
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert set(audit["lifecycle_exclusions"]) == EXCLUDED
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID
    print("Phase 4.2V post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
