#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
STM32F1_CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
LIFECYCLE_ROOT = HERE / "lifecycle-evidence"
BASELINE = HERE / "stm32f4-phase4.2al-lifecycle-gap-classification-baseline.json"


def main() -> int:
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert expected["schema_version"] == 1
    assert expected["production_write_authorized"] is False
    assert expected["policy_change_authorized"] is False
    inventory = build_inventory(
        catalog_path=CATALOG,
        canonical_path=CANONICAL,
        lifecycle_evidence_root=LIFECYCLE_ROOT,
    )

    assert inventory["schema_version"] == 1
    production = expected["production_invariants"]
    assert inventory["production"]["exact_icpn_rows"] == production["stm32f4_exact_icpns"]
    assert inventory["production"]["base_device_count"] == production["stm32f4_base_devices"]
    assert hashlib.sha256(CANONICAL.read_bytes()).hexdigest() == production["stm32f4_catalog_sha256"]
    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    assert (
        sum(source["row_count"] for source in manifest["sources"])
        == production["st_exact_icpns"]
    )
    with STM32F1_CANONICAL.open(encoding="utf-8") as handle:
        stm32f1_base_devices = {
            row["base_device"] for row in csv.DictReader(handle)
        }
    stm32f4_base_devices = set(inventory["production"]["base_devices"])
    assert stm32f1_base_devices.isdisjoint(stm32f4_base_devices)
    assert len(stm32f1_base_devices | stm32f4_base_devices) == production["st_base_devices"]

    raw_gap = inventory["gap"]
    assert raw_gap["base_device_count"] == expected["raw_gap"]["base_device_count"]
    assert raw_gap["policy_ready_count"] == expected["raw_gap"]["policy_ready_count"]
    assert raw_gap["policy_blocked_count"] == expected["raw_gap"]["policy_blocked_count"]
    raw_gap_bases = {item["base_device"] for item in raw_gap["policy_blocked"]}

    closure = inventory["lifecycle_closure"]
    assert closure["classification_basis"] == "validated_retained_official_st_evidence"
    assert closure["canonical_dataset_admission"] is False
    expected_closure = expected["lifecycle_closure"]
    assert closure["evidence_package_count"] == expected_closure["evidence_package_count"]
    assert closure["base_device_count"] == expected_closure["base_device_count"]
    assert closure["exact_part_number_count"] == expected_closure["exact_part_number_count"]
    assert closure["lifecycle_status_counts"] == expected_closure["lifecycle_status_counts"]
    assert closure["base_devices"] == expected_closure["base_devices"]
    assert set(closure["base_devices"]) == raw_gap_bases
    assert [
        package["evidence_id"] for package in closure["evidence_packages"]
    ] == expected_closure["evidence_ids"]

    closed_exact_icpns: set[str] = set()
    for item in closure["items"]:
        assert item["base_device"] in closure["base_devices"]
        assert item["package_codes"] == ["T"]
        assert item["admission_policy_ready"] is False
        assert item["policy_blockers"] == [
            "unsupported STM32F4 pin/package combination: B/T"
        ]
        assert (
            item["closure_reason"]
            == "official_st_evidence_contains_no_active_exact_icpn"
        )
        records = item["excluded_non_active_part_numbers"]
        assert len(records) == item["excluded_non_active_part_number_count"]
        for record in records:
            assert record["icpn"].startswith(item["base_device"])
            assert record["icpn"] not in closed_exact_icpns
            closed_exact_icpns.add(record["icpn"])
    assert len(closed_exact_icpns) == closure["exact_part_number_count"]

    actionable = inventory["actionable_gap"]
    expected_actionable = expected["actionable_gap"]
    assert actionable["base_device_count"] == expected_actionable["base_device_count"]
    assert actionable["policy_ready_count"] == expected_actionable["policy_ready_count"]
    assert actionable["policy_blocked_count"] == expected_actionable["policy_blocked_count"]
    assert actionable["policy_ready"] == []
    assert actionable["policy_blocked"] == []

    raw_inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
    assert "lifecycle_closure" not in raw_inventory
    assert "actionable_gap" not in raw_inventory
    assert raw_inventory["gap"] == raw_gap
    print("Phase 4.2AL lifecycle-aware actionable-gap classification PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
