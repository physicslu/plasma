#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32f3_foundation import (
    DEFAULT_CATALOG,
    EXPECTED_SUBFAMILY_COUNTS,
    TARGET_CONFIG,
    build_foundation_report,
    deterministic_initial_targets,
    guarded_rows,
    read_catalog,
    resolve_ordering_pattern_mapping,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32f3-phase4.4a-foundation-baseline.json"
EXPECTED_TARGETS = [
    ("STM32F301", "STM32F301C6"),
    ("STM32F302", "STM32F302C6"),
    ("STM32F303", "STM32F303C6"),
    ("STM32F373", "STM32F373C8"),
    ("STM32F3x4", "STM32F334C4"),
    ("STM32F3x8", "STM32F318C8"),
]
SYNTHETIC_ROUTING_VALUES = [
    "STM32F301C6T6",
    "STM32F302C6T6",
    "STM32F303C6T6",
    "STM32F373C8T6",
    "STM32F334C4T6",
    "STM32F318C8T6",
]


def _must_fail(rows: list[dict[str, str]], message: str) -> None:
    try:
        guarded_rows(rows)
    except AcquisitionError:
        return
    raise AssertionError(message)


def main() -> int:
    catalog = read_catalog(DEFAULT_CATALOG)
    rows = guarded_rows(catalog)
    assert len(rows) == 90
    assert {row["target_config"] for row in rows} == {TARGET_CONFIG}
    assert all(row["identifier_kind"] == "ordering_pattern" for row in rows)
    assert all(row["openocd_distribution"] == "upstream-openocd" for row in rows)
    assert all(row["mapping_status"] == "mapping_candidate" for row in rows)
    assert all(row["validation_status"] == "not_verified" for row in rows)

    observed_counts: dict[str, int] = {}
    for row in rows:
        observed_counts[row["subfamily"]] = observed_counts.get(row["subfamily"], 0) + 1
    assert observed_counts == EXPECTED_SUBFAMILY_COUNTS

    assert deterministic_initial_targets(catalog) == EXPECTED_TARGETS

    for value in SYNTHETIC_ROUTING_VALUES:
        mapping = resolve_ordering_pattern_mapping(value, catalog)
        assert mapping["status"] == "unique", (value, mapping)
        assert mapping["match_count"] == 1
        assert mapping["target_configs"] == [TARGET_CONFIG]

    # The routing examples above are synthetic ordering-pattern probes only.
    # Phase 4.4A must not convert them into manufacturer ICPN claims.
    report = build_foundation_report(catalog)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert report == baseline
    assert set(report["claims"].values()) == {False}

    target_drift = copy.deepcopy(catalog)
    f3_row = next(row for row in target_drift if row.get("plasma_series") == "STM32F3")
    f3_row["target_config"] = "tcl/target/stm32f4x.cfg"
    _must_fail(target_drift, "STM32F3 target-config drift must fail closed")

    kind_drift = copy.deepcopy(catalog)
    f3_row = next(row for row in kind_drift if row.get("plasma_series") == "STM32F3")
    f3_row["identifier_kind"] = "cmsis_device_name"
    _must_fail(kind_drift, "STM32F3 identifier-kind drift must fail closed")

    pattern_drift = copy.deepcopy(catalog)
    f3_row = next(row for row in pattern_drift if row.get("plasma_series") == "STM32F3")
    f3_row["part_number"] = "STM32F3x4"
    _must_fail(pattern_drift, "STM32F3 non-concrete ordering surface must fail closed")

    missing = copy.deepcopy(catalog)
    for index, row in enumerate(missing):
        if row.get("plasma_series") == "STM32F3":
            del missing[index]
            break
    _must_fail(missing, "STM32F3 row-count drift must fail closed")

    print("Phase 4.4A STM32F3 bounded discovery foundation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
