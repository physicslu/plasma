#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32c0_phase_c0_1_foundation import (
    EXPECTED_CMSIS_COUNT,
    EXPECTED_ORDERING_COUNT,
    EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
    EXPECTED_ROW_COUNT,
    EXPECTED_TARGETS,
    build_foundation_report,
    cmsis_alias_rows,
    commercial_ordering_rows,
    deterministic_initial_targets,
    read_catalog,
    validate_ordering_authority,
    validate_retained_identity,
    validate_selection,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32c0-phase-c0.1-foundation-baseline.json"


class STM32C0PhaseC01FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_catalog()

    def test_report_matches_frozen_baseline(self) -> None:
        report = build_foundation_report(self.rows)
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(report, baseline)
        self.assertEqual(report["source_row_count"], EXPECTED_ROW_COUNT)
        self.assertEqual(
            report["identifier_kind_counts"],
            {
                "cmsis_device_name": EXPECTED_CMSIS_COUNT,
                "ordering_pattern": EXPECTED_ORDERING_COUNT,
            },
        )

    def test_deterministic_targets_cover_each_subfamily_once(self) -> None:
        self.assertEqual(tuple(deterministic_initial_targets(self.rows)), EXPECTED_TARGETS)

    def test_cmsis_aliases_never_enter_commercial_representative_selection(self) -> None:
        ordering = commercial_ordering_rows(self.rows)
        aliases = cmsis_alias_rows(self.rows)
        self.assertEqual(len(ordering), EXPECTED_ORDERING_COUNT)
        self.assertEqual(len(aliases), EXPECTED_CMSIS_COUNT)
        selected_bases = {base for _, base in deterministic_initial_targets(self.rows)}
        self.assertFalse(any(row["part_number"] in selected_bases for row in aliases))

    def test_identifier_kind_drift_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(
            row for row in rows
            if row.get("plasma_series") == "STM32C0" and row.get("identifier_kind") == "ordering_pattern"
        )
        victim["identifier_kind"] = "cmsis_device_name"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_target_config_drift_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(row for row in rows if row.get("plasma_series") == "STM32C0")
        victim["target_config"] = "tcl/target/stm32g0x.cfg"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_malformed_ordering_pattern_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(
            row for row in rows
            if row.get("plasma_series") == "STM32C0" and row.get("identifier_kind") == "ordering_pattern"
        )
        victim["part_number"] = "STM32C0_NOT_AN_ORDERING_PATTERN"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_cmsis_alias_cannot_be_promoted_to_ordering_pattern(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(
            row for row in rows
            if row.get("plasma_series") == "STM32C0" and row.get("identifier_kind") == "cmsis_device_name"
        )
        victim["identifier_kind"] = "ordering_pattern"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_selection_is_hard_bound_and_research_only(self) -> None:
        validate_selection()
        payload_path = HERE / "stm32-post-u0-next-family-selection.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        payload["authority_boundaries"]["canonical_admission_authorized"] = True
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / payload_path.name
            mutated.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AcquisitionError):
                validate_selection(mutated)

    def test_retained_identity_is_hard_bound_to_six_representatives(self) -> None:
        targets = validate_retained_identity()
        self.assertEqual(set(targets), {base for _, base in EXPECTED_TARGETS})
        self.assertEqual(
            sum(len(target["exact_icpns"]) for target in targets.values()),
            EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
        )

    def test_ordering_authority_is_hard_bound_and_official_st(self) -> None:
        authorities = validate_ordering_authority()
        self.assertEqual(set(authorities), {base for _, base in EXPECTED_TARGETS})
        self.assertEqual({item[0] for item in authorities.values()}, {"DS13866", "DS13867", "DS14721", "DS14693", "DS14720"})

    def test_representative_evidence_is_not_complete_inventory_claim(self) -> None:
        report = build_foundation_report(self.rows)
        self.assertEqual(
            report["evidence_foundation"]["scope"],
            "representative_evidence_only_not_complete_family_inventory",
        )
        self.assertFalse(report["claims"]["complete_family_inventory_claimed"])

    def test_capability_and_admission_claims_stay_false(self) -> None:
        claims = build_foundation_report(self.rows)["claims"]
        self.assertTrue(claims)
        self.assertTrue(all(value is False for value in claims.values()))


if __name__ == "__main__":
    unittest.main()
