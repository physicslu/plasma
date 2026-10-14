#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
LEDGER = HERE / "enrichment-coverage" / "st-m1-enrichment-program-v1.json"
DEVICE_BASIC_ROOT = HERE / "device-basic"

EXPECTED_FAMILY_COUNTS = {
    "STM32C5": 172, "STM32F0": 263, "STM32F3": 192, "STM32F4": 387,
    "STM32F7": 173, "STM32H5": 190, "STM32H7": 205, "STM32H7RS": 36,
    "STM32L0": 360, "STM32L1": 146, "STM32L4": 449, "STM32L5": 49,
    "STM32N6": 32, "STM32U0": 68, "STM32U3": 107, "STM32U5": 265,
    "STM32WB0": 24, "STM32WBA2X": 14, "STM32WBA5X": 40,
    "STM32WBA6X": 39, "STM32WBX": 50, "STM32WL3": 47, "STM32WLX": 31,
}
EXPECTED_ADMITTED = {
    "STM32H7RS": "data/ic-support/device-basic/stm32h7rs-device-basic-v1.json",
    "STM32L5": "data/ic-support/device-basic/stm32l5-device-basic-v1.json",
}
FORBIDDEN_SOURCE_MARKERS = ("/datasheet/", "openocd", "programming")


def main() -> int:
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert payload["program_id"] == "st-m1-enrichment-program-v1"
    assert payload["status"] == "complete_evidence_disposition"
    assert payload["manufacturer"] == "STMicroelectronics"
    assert payload["scope"] == {
        "baseline_m1_exact_icpns": 1290,
        "remaining_exact_icpns_reviewed": 3339,
        "families_reviewed": 23,
    }
    assert payload["result"] == {
        "newly_admitted_exact_icpns": 85,
        "blocked_exact_icpns": 3254,
        "post_program_m1_exact_icpns": 1375,
        "post_program_st_m1_gap": 3254,
    }
    assert payload["source_policy"]["allowed_surfaces"] == [
        "st_product_selector", "st_estore"
    ]
    assert set(payload["source_policy"]["prohibited_derivation_sources"]) >= {
        "datasheet", "programming_guide", "OpenOCD", "family_name_inference"
    }
    assert all(value is False for value in payload["authority_boundary"].values())

    families = payload["families"]
    assert len(families) == 23
    actual_counts = {item["family"]: item["production_exact_count"] for item in families}
    assert actual_counts == EXPECTED_FAMILY_COUNTS
    assert sum(actual_counts.values()) == 3339

    admitted = {item["family"]: item for item in families if item["disposition"] == "admitted"}
    assert {family: item["profile_path"] for family, item in admitted.items()} == EXPECTED_ADMITTED
    assert sum(item["production_exact_count"] for item in admitted.values()) == 85

    blocked = [item for item in families if item["disposition"].startswith("blocked_")]
    assert len(blocked) == 21
    assert sum(item["production_exact_count"] for item in blocked) == 3254
    assert all(isinstance(item.get("blocker"), str) and item["blocker"] for item in blocked)

    for item in families:
        for source in item.get("sources", []):
            lower = source.lower()
            assert source.startswith(("https://www.st.com/", "https://estore.st.com/"))
            assert not any(marker in lower for marker in FORBIDDEN_SOURCE_MARKERS)
        if item["disposition"] == "admitted":
            profile = REPO_ROOT / item["profile_path"]
            assert profile.is_file()
            profile_payload = json.loads(profile.read_text(encoding="utf-8"))
            assert profile_payload["family"] == item["family"]
            assert profile_payload["binding_count"] == item["production_exact_count"]

    print("ST M1 enrichment program disposition tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
