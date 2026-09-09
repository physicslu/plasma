#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32f7_foundation import (
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
BASELINE = HERE / "stm32f7-phase4.6a-foundation-baseline.json"
EXPECTED_TARGETS = [
    ("STM32F722", "STM32F722IC"),
    ("STM32F723", "STM32F723IC"),
    ("STM32F730", "STM32F730I8"),
    ("STM32F732", "STM32F732IE"),
    ("STM32F733", "STM32F733IE"),
    ("STM32F745", "STM32F745IE"),
    ("STM32F746", "STM32F746BE"),
    ("STM32F750", "STM32F750N8"),
    ("STM32F756", "STM32F756BG"),
    ("STM32F765", "STM32F765BG"),
    ("STM32F767", "STM32F767BG"),
    ("STM32F768", "STM32F768AI"),
    ("STM32F769", "STM32F769AG"),
    ("STM32F777", "STM32F777BI"),
    ("STM32F778", "STM32F778AI"),
    ("STM32F779", "STM32F779AI"),
]
SYNTHETIC_ROUTING_VALUES = [
    "STM32F722ICK6",
    "STM32F723ICK6",
    "STM32F730I8K6",
    "STM32F732IEK6",
    "STM32F733IEK6",
    "STM32F745IEK6",
    "STM32F746BET6",
    "STM32F750N8H6",
    "STM32F756BGT6",
    "STM32F765BGT6",
    "STM32F767BGT6",
    "STM32F768AIY6",
    "STM32F769AGY6",
    "STM32F777BIT6",
    "STM32F778AIY6",
    "STM32F779AIY6",
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
    assert len(rows) == 123
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

    # Synthetic probes prove routing behavior only. They are not manufacturer
    # evidence and must never be persisted as commercial identities.
    report = build_foundation_report(catalog)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert report == baseline
    assert set(report["claims"].values()) == {False}

    target_drift = copy.deepcopy(catalog)
    f7_row = next(row for row in target_drift if row.get("plasma_series") == "STM32F7")
    f7_row["target_config"] = "tcl/target/stm32f4x.cfg"
    _must_fail(target_drift, "STM32F7 target-config drift must fail closed")

    kind_drift = copy.deepcopy(catalog)
    f7_row = next(row for row in kind_drift if row.get("plasma_series") == "STM32F7")
    f7_row["identifier_kind"] = "cmsis_device_name"
    _must_fail(kind_drift, "STM32F7 identifier-kind drift must fail closed")

    distribution_drift = copy.deepcopy(catalog)
    f7_row = next(row for row in distribution_drift if row.get("plasma_series") == "STM32F7")
    f7_row["openocd_distribution"] = "vendor-fork"
    _must_fail(distribution_drift, "STM32F7 distribution drift must fail closed")

    mapping_drift = copy.deepcopy(catalog)
    f7_row = next(row for row in mapping_drift if row.get("plasma_series") == "STM32F7")
    f7_row["mapping_status"] = "verified"
    _must_fail(mapping_drift, "STM32F7 mapping-status drift must fail closed")

    validation_drift = copy.deepcopy(catalog)
    f7_row = next(row for row in validation_drift if row.get("plasma_series") == "STM32F7")
    f7_row["validation_status"] = "verified"
    _must_fail(validation_drift, "STM32F7 validation-status drift must fail closed")

    pattern_drift = copy.deepcopy(catalog)
    f7_row = next(row for row in pattern_drift if row.get("plasma_series") == "STM32F7")
    f7_row["part_number"] = "STM32F722"
    _must_fail(pattern_drift, "STM32F7 non-concrete ordering surface must fail closed")

    missing = copy.deepcopy(catalog)
    for index, row in enumerate(missing):
        if row.get("plasma_series") == "STM32F7":
            del missing[index]
            break
    _must_fail(missing, "STM32F7 row-count drift must fail closed")

    print("Phase 4.6A STM32F7 bounded discovery foundation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
