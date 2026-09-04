#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
PLAN = HERE / "stm32f4-phase4.2x-my-wlcsp81-admission-plan.json"
AUDIT = HERE / "stm32f4-phase4.2x-my-wlcsp81-admission-audit.json"
PLAN_SHA256 = "a6789820fc0fd301556486342293bfc115538efc173211608c0e6f3ad9f4faba"
PUBLISHED_CATALOG_SHA256 = "8d2a4ccc3bcf6b29614087888b65072376a240534117e3f83877d19d193a1ba7"
EVIDENCE_ID = "stm32f4-phase4.2x-my-wlcsp81-admission-2026-09-04-retained-20260904T091210Z-94f6bdf"
EXCLUDED = {"STM32F413MGY3TR", "STM32F413MHY3TR"}
EXPECTED = {
    "STM32F413MGY6TR": ("STM32F413MG", "1024 KiB", "-40 to 85 C", "TR"),
    "STM32F413MHY6TR": ("STM32F413MH", "1536 KiB", "-40 to 85 C", "TR"),
    "STM32F423MHY3TR": ("STM32F423MH", "1536 KiB", "-40 to 125 C", "TR"),
    "STM32F423MHY6TR": ("STM32F423MH", "1536 KiB", "-40 to 85 C", "TR"),
    "STM32F446MCY6TR": ("STM32F446MC", "256 KiB", "-40 to 85 C", "TR"),
    "STM32F446MEY6MTR": ("STM32F446ME", "512 KiB", "-40 to 85 C", "MTR"),
    "STM32F446MEY6TR": ("STM32F446ME", "512 KiB", "-40 to 85 C", "TR"),
}


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 338
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) >= 114

    by_icpn = {row["icpn"]: row for row in rows}
    assert set(EXPECTED) <= set(by_icpn)
    assert EXCLUDED.isdisjoint(by_icpn)
    for icpn, (base_device, flash_size, temperature_grade, option_suffix) in EXPECTED.items():
        row = by_icpn[icpn]
        assert row["base_device"] == base_device
        assert row["package"] == "WLCSP"
        assert row["pin_count"] == "81"
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
    assert audit["production_rows_before"] == 331
    assert audit["production_rows_after"] == 338
    assert audit["production_base_devices_before"] == 109
    assert audit["production_base_devices_after"] == 114
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert set(audit["lifecycle_exclusions"]) == EXCLUDED
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID
    print("Phase 4.2X post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
