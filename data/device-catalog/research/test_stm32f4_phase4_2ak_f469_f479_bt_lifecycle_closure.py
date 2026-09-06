#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
CATALOG = HERE / "stm32f4-commercial-icpn.csv"
OPENOCD_CATALOG = HERE / "openocd-parts-canonical.csv"
PRODUCTION_MANIFEST = REPO_ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
LIFECYCLE_ROOT = HERE / "lifecycle-evidence"
PHASE_AJ = LIFECYCLE_ROOT / "stm32f4-phase4.2aj-f429-f439-bt-lifecycle-live-2026-09-06"
PHASE_AK = LIFECYCLE_ROOT / "stm32f4-phase4.2ak-f469-f479-bt-lifecycle-live-2026-09-06"
EXPECTED_CATALOG_SHA256 = "3ab4793d67f1b70e8c8f4c883bd9c24430f25b7a11a199ba32bb50fc48f39359"
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


def retained_lifecycle_inventory() -> tuple[set[str], set[str], Counter[str]]:
    bases: set[str] = set()
    icpns: set[str] = set()
    statuses: Counter[str] = Counter()
    for evidence_dir in (PHASE_AJ, PHASE_AK):
        baseline = json.loads((evidence_dir / "lifecycle-baseline.json").read_text(encoding="utf-8"))
        assert baseline["canonical_dataset_admission"] is False
        assert baseline["policy_change_authorized"] is False
        assert baseline["production_write_authorized"] is False
        for target in baseline["targets"]:
            base = target["base_device"]
            assert base not in bases
            bases.add(base)
            for record in target["excluded_non_active_part_numbers"]:
                icpn = record["icpn"]
                assert icpn.startswith(base)
                assert icpn not in icpns
                icpns.add(icpn)
                status = record["marketing_status"]
                if status.startswith("NRND"):
                    statuses["NRND"] += 1
                elif status.startswith("Proposal"):
                    statuses["Proposal"] += 1
                else:
                    raise AssertionError(f"unsupported lifecycle status: {status}")
    return bases, icpns, statuses


def main() -> int:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    exact_icpns = {row["icpn"] for row in rows}
    assert len(rows) == len(exact_icpns) == 384
    assert len({row["base_device"] for row in rows}) == 139
    assert hashlib.sha256(CATALOG.read_bytes()).hexdigest() == EXPECTED_CATALOG_SHA256

    lifecycle_bases, lifecycle_icpns, lifecycle_statuses = retained_lifecycle_inventory()
    assert lifecycle_bases == POLICY_BLOCKED
    assert len(lifecycle_icpns) == 13
    assert lifecycle_statuses == {"NRND": 12, "Proposal": 1}
    assert lifecycle_icpns.isdisjoint(exact_icpns)

    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
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
    blocked = {item["base_device"]: item for item in inventory["gap"]["policy_blocked"]}
    assert set(blocked) == POLICY_BLOCKED
    for base_device in POLICY_BLOCKED:
        assert blocked[base_device]["package_codes"] == ["T"]
        assert blocked[base_device]["policy_blockers"] == [
            "unsupported STM32F4 pin/package combination: B/T"
        ]

    for phase in ("42aj", "42ak"):
        assert not list((REPO_ROOT / ".github/workflows").glob(f"device-catalog-phase{phase}-*"))
    print("Phase 4.2AK complete B/T lifecycle-only closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
