#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
PLAN = HERE / "stm32f4-phase4.2t-f410tb-admission-plan.json"
AUDIT = HERE / "stm32f4-phase4.2t-f410tb-admission-audit.json"
EXPECTED = {
    "STM32F410TBY3TR": "-40 to 125 C",
    "STM32F410TBY6TR": "-40 to 85 C",
    "STM32F410TBY7TR": "-40 to 105 C",
}
PLAN_SHA256 = "ea3f68cdaddfd99cae37483442ec5d5204bf6139fb363bcecd838a997446c61d"
PUBLISHED_CATALOG_SHA256 = "d74913a72995dbbf5a4e5b14934e816266cd89166e080fe9aa0b95c5eb52d539"
EVIDENCE_ID = "stm32f4-phase4.2t-f410tb-admission-2026-09-03-retained-20260903T095612Z-58e3ad1"


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 307
    assert len(rows) == len({row["icpn"] for row in rows})
    assert len({row["base_device"] for row in rows}) >= 101

    by_icpn = {row["icpn"]: row for row in rows}
    assert set(EXPECTED) <= set(by_icpn)
    for icpn, temperature_grade in EXPECTED.items():
        row = by_icpn[icpn]
        assert row["base_device"] == "STM32F410TB"
        assert row["package"] == "WLCSP"
        assert row["pin_count"] == "36"
        assert row["flash_size"] == "128 KiB"
        assert row["temperature_grade"] == temperature_grade
        assert row["option_suffix"] == "TR"
        assert row["openocd_target_config"] == "tcl/target/stm32f4x.cfg"
        assert EVIDENCE_ID in row["source_reference"]

    assert hashlib.sha256(PLAN.read_bytes()).hexdigest() == PLAN_SHA256
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert plan["decision_counts"] == {
        "admit": 3,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    assert plan["conflicts"] == 0
    assert {candidate["icpn"] for candidate in plan["candidates"]} == set(EXPECTED)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "published"
    assert audit["production_rows_before"] == 304
    assert audit["production_rows_after"] == 307
    assert audit["production_base_devices_before"] == 100
    assert audit["production_base_devices_after"] == 101
    assert set(audit["added_exact_icpns"]) == set(EXPECTED)
    assert audit["lifecycle_exclusions"] == []
    assert audit["admission_plan_sha256"] == PLAN_SHA256
    assert audit["canonical_csv_file_sha256"] == PUBLISHED_CATALOG_SHA256
    assert audit["retained_evidence_id"] == EVIDENCE_ID
    print("Phase 4.2T post-admission closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
