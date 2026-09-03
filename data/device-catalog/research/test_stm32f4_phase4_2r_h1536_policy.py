#!/usr/bin/env python3
import json
from pathlib import Path

from stm32f4_admission_policy import FLASH_BY_CODE
from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
EXPECTED_POLICY_READY = {
    "STM32F413CH",
    "STM32F413RH",
    "STM32F413VH",
    "STM32F413ZH",
    "STM32F423CH",
    "STM32F423RH",
    "STM32F423VH",
    "STM32F423ZH",
}

assert FLASH_BY_CODE["H"] == "1536 KiB"
evidence = json.loads((HERE / "stm32f4-phase4.2r-h1536-policy-evidence.json").read_text())
assert set(evidence["newly_policy_ready"]) == EXPECTED_POLICY_READY
assert evidence["production_write_applied"] is False
assert evidence["exact_icpn_admission_deferred"] is True
assert evidence["algorithm_equivalence_claimed"] is False

inventory = build_inventory(
    catalog_path=HERE / "openocd-parts-canonical.csv",
    canonical_path=HERE / "stm32f4-commercial-icpn.csv",
)
ready = {item["base_device"] for item in inventory["gap"]["policy_ready"]}
blocked = {item["base_device"] for item in inventory["gap"]["policy_blocked"]}
production = set(inventory["production"]["base_devices"])
remaining_expected = EXPECTED_POLICY_READY - production
assert ready == remaining_expected
assert EXPECTED_POLICY_READY - remaining_expected <= production
assert EXPECTED_POLICY_READY.isdisjoint(blocked)
assert inventory["gap"]["policy_ready_count"] == len(remaining_expected)
assert inventory["production"]["exact_icpn_rows"] >= 307
assert inventory["production"]["base_device_count"] >= 101
print("Phase 4.2R H=1536 KiB policy PASS")
