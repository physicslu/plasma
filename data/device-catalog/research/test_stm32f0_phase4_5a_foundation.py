#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32f0_foundation import (
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
BASELINE = HERE / "stm32f0-phase4.5a-foundation-baseline.json"
EXPECTED_TARGETS = [
    ("STM32F030", "STM32F030C6"),
    ("STM32F031", "STM32F031C4"),
    ("STM32F038", "STM32F038C6"),
    ("STM32F042", "STM32F042C4"),
    ("STM32F048", "STM32F048C6"),
    ("STM32F051", "STM32F051C4"),
    ("STM32F058", "STM32F058C8"),
    ("STM32F070", "STM32F070C6"),
    ("STM32F071", "STM32F071C8"),
    ("STM32F072", "STM32F072C8"),
    ("STM32F078", "STM32F078CB"),
    ("STM32F091", "STM32F091CB"),
    ("STM32F098", "STM32F098CC"),
]
SYNTHETIC_ROUTING_VALUES = [
    "STM32F030C6T6",
    "STM32F031C4T6",
    "STM32F038C6T6",
    "STM32F042C4T6",
    "STM32F048C6U6",
    "STM32F051C4T6",
    "STM32F058C8U6",
    "STM32F070C6T6",
    "STM32F071C8T6",
    "STM32F072C8T6",
    "STM32F078CBT6",
    "STM32F091CBT6",
    "STM32F098CCT6",
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
    assert len(rows) == 111
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

    # Synthetic routing probes prove source-pattern routing only. They are not
    # manufacturer evidence and must never be retained as commercial ICPNs.
    report = build_foundation_report(catalog)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert report == baseline
    assert set(report["claims"].values()) == {False}

    target_drift = copy.deepcopy(catalog)
    f0_row = next(row for row in target_drift if row.get("plasma_series") == "STM32F0")
    f0_row["target_config"] = "tcl/target/stm32f1x.cfg"
    _must_fail(target_drift, "STM32F0 target-config drift must fail closed")

    kind_drift = copy.deepcopy(catalog)
    f0_row = next(row for row in kind_drift if row.get("plasma_series") == "STM32F0")
    f0_row["identifier_kind"] = "cmsis_device_name"
    _must_fail(kind_drift, "STM32F0 identifier-kind drift must fail closed")

    pattern_drift = copy.deepcopy(catalog)
    f0_row = next(row for row in pattern_drift if row.get("plasma_series") == "STM32F0")
    f0_row["part_number"] = "STM32F030"
    _must_fail(pattern_drift, "STM32F0 non-concrete ordering surface must fail closed")

    missing = copy.deepcopy(catalog)
    for index, row in enumerate(missing):
        if row.get("plasma_series") == "STM32F0":
            del missing[index]
            break
    _must_fail(missing, "STM32F0 row-count drift must fail closed")

    print("Phase 4.5A STM32F0 bounded discovery foundation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
