#!/usr/bin/env python3
import json
from pathlib import Path

from stm32f4_admission_policy import FLASH_BY_CODE
from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
TARGETS = {"STM32F413VH", "STM32F423VH"}

assert FLASH_BY_CODE["H"] == "1536 KiB"
evidence = json.loads((HERE / "stm32f4-phase4.2r-h1536-policy-evidence.json").read_text())
assert set(evidence["newly_policy_ready"]) == TARGETS
assert evidence["production_write_applied"] is False
assert evidence["exact_icpn_admission_deferred"] is True
assert evidence["algorithm_equivalence_claimed"] is False

inventory = build_inventory(
    catalog_path=HERE / "openocd-parts-canonical.csv",
    canonical_path=HERE / "stm32f4-commercial-icpn.csv",
)
ready = {item["base_device"] for item in inventory["gap"]["policy_ready"]}
blocked = {item["base_device"] for item in inventory["gap"]["policy_blocked"]}
assert TARGETS <= ready
assert TARGETS.isdisjoint(blocked)
assert inventory["production"]["exact_icpn_rows"] == 304
assert inventory["production"]["base_device_count"] == 100
print("Phase 4.2R H=1536 KiB policy PASS")
