#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
OPENOCD_CATALOG = HERE / "openocd-parts-canonical.csv"
PRODUCTION_MANIFEST = REPO_ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
EXPECTED_CATALOG_SHA256 = "3ab4793d67f1b70e8c8f4c883bd9c24430f25b7a11a199ba32bb50fc48f39359"
LIFECYCLE_ONLY_ICPNS = {
    "STM32F429BET6",
    "STM32F429BGT6",
    "STM32F429BIT6",
    "STM32F429BIT7",
    "STM32F439BGT6",
    "STM32F439BIT6",
    "STM32F439BIT7",
}
POLICY_BLOCKED = {
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
    exact_icpns = {row["icpn"] for row in rows}
    assert len(rows) == len(exact_icpns) == 384
    assert len({row["base_device"] for row in rows}) == 139
    assert hashlib.sha256(CATALOG.read_bytes()).hexdigest() == EXPECTED_CATALOG_SHA256
    assert LIFECYCLE_ONLY_ICPNS.isdisjoint(exact_icpns)

    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["status"] == "production"
    assert manifest["selection_policy"] == "admitted_exact_manufacturer_part_number_only"
    sources = {(source["manufacturer"], source["family"]): source for source in manifest["sources"]}
    assert sources[("STMicroelectronics", "STM32F1")]["row_count"] == 75
    assert sources[("STMicroelectronics", "STM32F4")]["row_count"] == 384
    assert sum(source["row_count"] for source in sources.values()) == 459
    assert sources[("STMicroelectronics", "STM32F4")]["sha256"] == EXPECTED_CATALOG_SHA256

    inventory = build_inventory(catalog_path=OPENOCD_CATALOG, canonical_path=CATALOG)
    assert inventory["production"]["exact_icpn_rows"] == 384
    assert inventory["production"]["base_device_count"] == 139
    assert inventory["gap"]["base_device_count"] == 10
    assert inventory["gap"]["policy_ready_count"] == 0
    assert inventory["gap"]["policy_blocked_count"] == 10
    assert inventory["gap"]["policy_ready"] == []
    blocked = {item["base_device"]: item for item in inventory["gap"]["policy_blocked"]}
    assert set(blocked) == POLICY_BLOCKED
    for base_device in POLICY_BLOCKED:
        assert blocked[base_device]["package_codes"] == ["T"]
        assert blocked[base_device]["policy_blockers"] == [
            "unsupported STM32F4 pin/package combination: B/T"
        ]

    assert not (REPO_ROOT / ".github/workflows/device-catalog-phase42aj-discovery.yml").exists()
    assert not list((REPO_ROOT / ".github/workflows").glob("device-catalog-phase42aj-*"))
    print("Phase 4.2AJ lifecycle-only closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
