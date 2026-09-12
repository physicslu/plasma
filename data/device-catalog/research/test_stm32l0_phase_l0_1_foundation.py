#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32l0_phase_l0_1_foundation import (
    EXPECTED_CMSIS_COUNT, EXPECTED_ORDERING_COUNT,
    EXPECTED_REPRESENTATIVE_EXACT_ICPNS, EXPECTED_ROW_COUNT,
    EXPECTED_SUBFAMILIES, EXPECTED_TARGETS,
    build_foundation_report, cmsis_alias_rows, commercial_ordering_rows,
    deterministic_initial_targets, read_catalog, validate_ordering_authority,
    validate_production_prestate, validate_retained_identity,
    validate_selection, validate_target_manifest,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l0-phase-l0.1-foundation-baseline.json"


class STM32L0PhaseL01FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_catalog()

    def test_report_matches_frozen_baseline(self) -> None:
        report = build_foundation_report(self.rows)
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(report, baseline)
        self.assertEqual(report["source_row_count"], EXPECTED_ROW_COUNT)
        self.assertEqual(report["identifier_kind_counts"], {"cmsis_device_name": EXPECTED_CMSIS_COUNT, "ordering_pattern": EXPECTED_ORDERING_COUNT})

    def test_deterministic_targets_cover_all_sixteen_subfamilies_once(self) -> None:
        self.assertEqual(tuple(deterministic_initial_targets(self.rows)), EXPECTED_TARGETS)
        self.assertEqual(len(EXPECTED_SUBFAMILIES), 16)

    def test_cmsis_aliases_never_enter_commercial_representative_selection(self) -> None:
        ordering = commercial_ordering_rows(self.rows)
        aliases = cmsis_alias_rows(self.rows)
        self.assertEqual(len(ordering), EXPECTED_ORDERING_COUNT)
        self.assertEqual(len(aliases), EXPECTED_CMSIS_COUNT)
        selected_bases = {base for _, base in EXPECTED_TARGETS}
        self.assertFalse(any(row["part_number"] in selected_bases for row in aliases))

    def test_identifier_kind_drift_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(row for row in rows if row.get("plasma_series") == "STM32L0" and row.get("identifier_kind") == "ordering_pattern")
        victim["identifier_kind"] = "cmsis_device_name"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_target_config_drift_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(row for row in rows if row.get("plasma_series") == "STM32L0")
        victim["target_config"] = "tcl/target/stm32l1.cfg"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_malformed_ordering_pattern_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        victim = next(row for row in rows if row.get("plasma_series") == "STM32L0" and row.get("identifier_kind") == "ordering_pattern")
        victim["part_number"] = "STM32L0_NOT_AN_ORDERING_PATTERN"
        with self.assertRaises(AcquisitionError):
            build_foundation_report(rows)

    def test_selection_is_hard_bound_and_research_only(self) -> None:
        validate_selection()
        payload_path = HERE / "stm32-post-c0-next-family-selection.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        payload["selected_next_research_family"] = "STM32L4"
        with tempfile.TemporaryDirectory() as tmp:
            mutated = Path(tmp) / payload_path.name
            mutated.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AcquisitionError):
                validate_selection(mutated)

    def test_target_manifest_is_hard_bound_to_sixteen_representatives(self) -> None:
        targets = validate_target_manifest()
        self.assertEqual(targets, {subfamily: base for subfamily, base in EXPECTED_TARGETS})

    def test_retained_identity_is_hard_bound_to_sixteen_active_representatives(self) -> None:
        targets = validate_retained_identity()
        self.assertEqual(set(targets), {base for _, base in EXPECTED_TARGETS})
        exact_count = sum(len(target["evidence"]["exact_icpns"]) for target in targets.values())
        self.assertEqual(exact_count, EXPECTED_REPRESENTATIVE_EXACT_ICPNS)

    def test_ordering_authority_is_complete_and_preserves_special_semantics(self) -> None:
        authorities = validate_ordering_authority()
        self.assertEqual(set(authorities), {base for _, base in EXPECTED_TARGETS})
        self.assertEqual(len({item["datasheet_id"] for item in authorities.values()}), 16)
        self.assertTrue(any("narrow grammar" in x for x in authorities["STM32L010C6"]["special_semantics"]))
        self.assertTrue(any("UFQFPN28" in x for x in authorities["STM32L031C4"]["special_semantics"]))

    def test_production_prestate_remains_912_and_excludes_l0(self) -> None:
        payload = validate_production_prestate()
        counts = {item["family"]: item["row_count"] for item in payload["sources"]}
        self.assertEqual(sum(counts.values()), 912)
        self.assertNotIn("STM32L0", counts)

    def test_representative_evidence_is_not_complete_inventory_claim(self) -> None:
        report = build_foundation_report(self.rows)
        self.assertEqual(report["evidence_foundation"]["scope"], "representative_evidence_only_not_complete_family_inventory")
        self.assertFalse(report["claims"]["complete_family_inventory_claimed"])

    def test_capability_and_admission_claims_stay_false(self) -> None:
        claims = build_foundation_report(self.rows)["claims"]
        self.assertTrue(claims)
        self.assertTrue(all(value is False for value in claims.values()))


if __name__ == "__main__":
    unittest.main()
