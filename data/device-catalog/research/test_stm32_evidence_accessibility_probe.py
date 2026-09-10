#!/usr/bin/env python3
"""Offline contracts for the STM32U0/C0/L1 evidence accessibility probe."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32_evidence_accessibility_probe import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    EXPECTED_SHORTLIST,
    EXPECTED_TARGET_COUNT,
    ProbeTarget,
    deterministic_targets,
    probe_is_clean,
    read_catalog,
    read_manifest,
    run_probe,
)

EXPECTED_TARGETS = [
    ("STM32U0", "STM32U031", "STM32U031C6"),
    ("STM32U0", "STM32U073", "STM32U073C8"),
    ("STM32U0", "STM32U083", "STM32U083CC"),
    ("STM32C0", "STM32C011", "STM32C011F4"),
    ("STM32C0", "STM32C031", "STM32C031C4"),
    ("STM32C0", "STM32C051", "STM32C051C6"),
    ("STM32C0", "STM32C071", "STM32C071C8"),
    ("STM32C0", "STM32C091", "STM32C091CB"),
    ("STM32C0", "STM32C092", "STM32C092CB"),
    ("STM32L1", "STM32L100", "STM32L100C6"),
    ("STM32L1", "STM32L151", "STM32L151C6"),
    ("STM32L1", "STM32L152", "STM32L152C6"),
    ("STM32L1", "STM32L162", "STM32L162QC"),
]


class STM32EvidenceAccessibilityProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = read_catalog(DEFAULT_CATALOG)

    def test_deterministic_target_set(self) -> None:
        self.assertEqual(deterministic_targets(self.rows), EXPECTED_TARGETS)
        self.assertEqual(len(EXPECTED_TARGETS), EXPECTED_TARGET_COUNT)

    def test_manifest_is_exact_projection_of_guarded_selection(self) -> None:
        pilot_id, targets = read_manifest(DEFAULT_MANIFEST, self.rows)
        self.assertTrue(pilot_id)
        self.assertEqual(
            [(target.series, target.subfamily, target.base_device) for target in targets],
            EXPECTED_TARGETS,
        )
        self.assertEqual(tuple(dict.fromkeys(target.series for target in targets)), EXPECTED_SHORTLIST)

    def test_cmsis_aliases_do_not_participate_in_selection(self) -> None:
        ordering_parts = {
            row["part_number"]
            for row in self.rows
            if row.get("plasma_series") in EXPECTED_SHORTLIST
            and row.get("identifier_kind") == "ordering_pattern"
        }
        cmsis_parts = {
            row["part_number"]
            for row in self.rows
            if row.get("plasma_series") in EXPECTED_SHORTLIST
            and row.get("identifier_kind") == "cmsis_device_name"
        }
        self.assertTrue(cmsis_parts)
        for _, _, base in EXPECTED_TARGETS:
            self.assertTrue(any(part.startswith(base) for part in ordering_parts))
            self.assertNotIn(base, cmsis_parts)

    def test_manifest_target_drift_fails_closed(self) -> None:
        payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        payload["targets"][0]["base_device"] = "STM32U031C8"
        payload["targets"][0]["source_url"] = "https://www.st.com/en/microcontrollers-microprocessors/stm32u031c8.html"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(AcquisitionError, "target selection drifted"):
                read_manifest(path, self.rows)

    @staticmethod
    def _fake_fetch(source_url: str, timeout_seconds: float):
        del timeout_seconds
        return b"synthetic", source_url, None, None

    @staticmethod
    def _active_builder(**kwargs):
        base = kwargs["base_device"]
        return {
            "exact_icpns": [f"{base}T6"],
            "excluded_non_active_part_numbers": [],
            "base_device": base,
        }

    def test_all_active_synthetic_probe_is_clean_but_does_not_select(self) -> None:
        pilot, targets = read_manifest(DEFAULT_MANIFEST, self.rows)
        summary = run_probe(
            pilot_id=pilot,
            targets=targets,
            fetcher=self._fake_fetch,
            evidence_builder=self._active_builder,
        )
        self.assertTrue(probe_is_clean(summary))
        self.assertTrue(summary["bounded_probe_clean"])
        self.assertIsNone(summary["selected_next_research_family"])
        self.assertEqual(summary["manual_review_targets"], 0)
        self.assertTrue(all(value is False for value in summary["claims"].values()))

    def test_canonical_404_is_disposition_not_manual_failure(self) -> None:
        pilot, targets = read_manifest(DEFAULT_MANIFEST, self.rows)
        first_url = targets[0].source_url

        def fetch(source_url: str, timeout_seconds: float):
            del timeout_seconds
            if source_url == first_url:
                raise AcquisitionError("browser navigation returned HTTP 404")
            return b"synthetic", source_url, None, None

        summary = run_probe(
            pilot_id=pilot,
            targets=targets,
            fetcher=fetch,
            evidence_builder=self._active_builder,
        )
        self.assertTrue(probe_is_clean(summary))
        self.assertEqual(summary["manual_review_targets"], 0)
        self.assertEqual(summary["by_series"]["STM32U0"]["source_unavailable_404"], 1)
        self.assertFalse(summary["by_series"]["STM32U0"]["commercial_identity_access_clean"])

    def test_foreign_exact_identity_fails_to_manual_review(self) -> None:
        pilot, targets = read_manifest(DEFAULT_MANIFEST, self.rows)
        first_base = targets[0].base_device

        def builder(**kwargs):
            base = kwargs["base_device"]
            exact = ["STM32F999ZZT6"] if base == first_base else [f"{base}T6"]
            return {"exact_icpns": exact, "excluded_non_active_part_numbers": []}

        summary = run_probe(
            pilot_id=pilot,
            targets=targets,
            fetcher=self._fake_fetch,
            evidence_builder=builder,
        )
        self.assertFalse(probe_is_clean(summary))
        self.assertEqual(summary["manual_review_targets"], 1)
        self.assertEqual(summary["by_series"]["STM32U0"]["manual_review"], 1)
        self.assertIsNone(summary["selected_next_research_family"])

    def test_identifier_kind_drift_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.rows)
        for row in mutated:
            if row.get("plasma_series") == "STM32U0" and row.get("identifier_kind") == "cmsis_device_name":
                row["identifier_kind"] = "ordering_pattern"
                break
        with self.assertRaisesRegex(AcquisitionError, "identifier-kind surface drifted"):
            deterministic_targets(mutated)


if __name__ == "__main__":
    unittest.main()
