#!/usr/bin/env python3
"""Validate checked-in OpenOCD expansion artifacts without network access."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def csv_rows(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    capabilities = csv_rows("openocd-target-capabilities.csv")
    parts = csv_rows("openocd-parts-expanded.csv")
    outcomes = csv_rows("openocd-expansion-outcomes.csv")
    rules = json.loads((ROOT / "mapping-rules.json").read_text(encoding="utf-8"))["rules"]
    manifest = json.loads((ROOT / "source-manifest.json").read_text(encoding="utf-8"))

    assert len(capabilities) == 114
    assert len(outcomes) == 114
    assert len(parts) == 1023
    assert len({row["target_config"] for row in parts}) == 36
    assert Counter(row["device_type"] for row in capabilities) == {"MCU": 110, "Wireless MCU": 4}
    assert Counter(row["expansion_outcome"] for row in outcomes) == {
        "source_adapter_pending": 69,
        "mapped": 36,
        "deferred": 9,
    }

    capability_by_target = {row["target_config"]: row for row in capabilities}
    assert len(capability_by_target) == len(capabilities)
    assert {row["target_config"] for row in outcomes} == set(capability_by_target)
    assert all(
        capability_by_target[row["target_config"]]["capability_status"] == "flash_driver_declared"
        for row in parts
    )
    assert all(row["validation_status"] == "not_verified" for row in parts + outcomes + capabilities)

    part_keys = {(row["vendor"], row["part_number"].upper(), row["target_config"]) for row in parts}
    assert len(part_keys) == len(parts)
    rule_ids = {row["rule_id"] for row in rules}
    assert all(row["mapping_rule_id"] in rule_ids for row in parts)
    source_keys = {
        (row["pack_vendor"], row["pack_name"], row["content_sha256"])
        for row in manifest["sources"]
    }
    assert len(source_keys) == 27
    assert all(
        (row["source_pack_vendor"], row["source_pack_name"], row["source_content_sha256"])
        in source_keys
        for row in parts
    )

    print("OpenOCD expansion artifacts: PASS")
    print("114 candidates; 1,023 identifiers; 36 mapped targets; 27 pinned PDSCs")


if __name__ == "__main__":
    main()
