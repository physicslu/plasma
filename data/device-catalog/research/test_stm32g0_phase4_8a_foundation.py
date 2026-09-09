#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32g0_foundation import (
    EXPECTED_CMSIS_COUNT,
    EXPECTED_ORDERING_COUNT,
    EXPECTED_ROW_COUNT,
    TARGET_CONFIG,
    build_foundation_report,
    cmsis_alias_rows,
    commercial_ordering_rows,
    deterministic_initial_targets,
    read_catalog,
    resolve_ordering_pattern_mapping,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32g0-phase4.8a-foundation-baseline.json"
EXPECTED_TARGETS = [
    ("STM32G030", "STM32G030C6"),
    ("STM32G031", "STM32G031C4"),
    ("STM32G041", "STM32G041C6"),
    ("STM32G050", "STM32G050C6"),
    ("STM32G051", "STM32G051C6"),
    ("STM32G061", "STM32G061C6"),
    ("STM32G070", "STM32G070CB"),
    ("STM32G071", "STM32G071C8"),
    ("STM32G081", "STM32G081CB"),
    ("STM32G0B0", "STM32G0B0CE"),
    ("STM32G0B1", "STM32G0B1CB"),
    ("STM32G0C1", "STM32G0C1CC"),
]


class STM32G0Phase48AFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_catalog()

    def test_report_matches_frozen_baseline(self) -> None:
        report = build_foundation_report(self.rows)
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(report, baseline)
        self.assertEqual(report["source_row_count"], EXPECTED_ROW_COUNT)
        self.assertEqual(report["commercial_ordering_row_count"], EXPECTED_ORDERING_COUNT)
        self.assertEqual(report["cmsis_alias_row_count"], EXPECTED_CMSIS_COUNT)

    def test_deterministic_targets_cover_each_subfamily_once(self) -> None:
        self.assertEqual(deterministic_initial_targets(self.rows), EXPECTED_TARGETS)

    def test_cmsis_aliases_are_not_commercial_selection_inputs(self) -> None:
        ordering = commercial_ordering_rows(self.rows)
        aliases = cmsis_alias_rows(self.rows)
        self.assertEqual(len(ordering), 143)
        self.assertEqual(len(aliases), 39)
        self.assertTrue(all(row["identifier_kind"] == "ordering_pattern" for row in ordering))
        self.assertTrue(all(row["identifier_kind"] == "cmsis_device_name" for row in aliases))
        selected_bases = {base for _, base in deterministic_initial_targets(self.rows)}
        self.assertFalse(any(row["part_number"] in selected_bases for row in aliases))

    def test_unique_ordering_pattern_route_is_routing_only(self) -> None:
        mapping = resolve_ordering_pattern_mapping("STM32G030C6T6", self.rows)
        self.assertEqual(mapping["status"], "unique")
        self.assertEqual(mapping["target_configs"], [TARGET_CONFIG])
        self.assertEqual(mapping["identifier_kind"], "ordering_pattern")
        self.assertEqual(mapping["existing_identifier"], "STM32G030C6Tx")

    def test_invalid_route_is_unmapped(self) -> None:
        self.assertEqual(
            resolve_ordering_pattern_mapping("NOT_A_G0", self.rows),
            {"status": "unmapped", "match_count": 0, "target_configs": []},
        )

    def test_identifier_kind_drift_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(
            row for row in rows
            if row.get("plasma_series") == "STM32G0" and row.get("identifier_kind") == "ordering_pattern"
        )
        victim["identifier_kind"] = "cmsis_device_name"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_target_config_drift_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(row for row in rows if row.get("plasma_series") == "STM32G0")
        victim["target_config"] = "tcl/target/stm32g4x.cfg"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_claim_boundary_stays_false(self) -> None:
        claims = build_foundation_report(self.rows)["claims"]
        self.assertTrue(claims)
        self.assertTrue(all(value is False for value in claims.values()))


if __name__ == "__main__":
    unittest.main()
