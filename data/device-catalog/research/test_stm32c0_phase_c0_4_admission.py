#!/usr/bin/env python3
from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import CandidateManualReview
from stm32c0_admission_policy import CANONICAL_FIELDS, TARGET_CONFIG, build_canonical_row
from stm32c0_metadata_policy import build_candidate_inputs, build_metadata_row
from stm32c0_phase_c0_1_foundation import DEFAULT_CATALOG, read_catalog
from stm32c0_phase_c0_2_discovery import resolve_mapping
from stm32c0_phase_c0_4_admission import (
    EXPECTED_ADMITTABLE_COUNT,
    EXPECTED_CAPABILITY_UNRESOLVED,
    EXPECTED_CAPABILITY_UNRESOLVED_SHA256,
    LIVE_PRODUCTION_MANIFEST,
    STM32C0AdmissionError,
    admission_plan_is_clean,
    admission_summary,
    build_admission_plan,
    validate_frozen_plan,
)


class STM32C0PhaseC04AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = build_admission_plan()

    def test_clean_plan_has_expected_counts(self) -> None:
        self.assertTrue(admission_plan_is_clean(self.plan))
        self.assertEqual(self.plan["manufacturer_verified_identity_count"], 220)
        self.assertEqual(self.plan["metadata_ready_count"], 220)
        self.assertEqual(self.plan["capability_admittable_count"], EXPECTED_ADMITTABLE_COUNT)
        self.assertEqual(self.plan["capability_unresolved_count"], 11)
        self.assertEqual(
            self.plan["decision_counts"],
            {"admit": 209, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )

    def test_unresolved_exact_set_is_frozen(self) -> None:
        self.assertEqual(
            set(self.plan["capability_unresolved_exact_icpns"]),
            set(EXPECTED_CAPABILITY_UNRESOLVED),
        )
        self.assertEqual(
            self.plan["capability_unresolved_exact_set_sha256"],
            EXPECTED_CAPABILITY_UNRESOLVED_SHA256,
        )
        self.assertEqual(
            self.plan["current_mapping_replay"],
            {"unique": 209, "ambiguous": 0, "unmapped": 11},
        )

    def test_unresolved_remain_identity_and_metadata_ready(self) -> None:
        records = self.plan["capability_unresolved"]
        self.assertEqual(len(records), 11)
        self.assertTrue(all(item["identity_status"] == "manufacturer_verified_active" for item in records))
        self.assertTrue(all(item["metadata_status"] == "metadata_ready" for item in records))
        self.assertTrue(all(item["mapping"]["status"] == "unmapped" for item in records))
        self.assertFalse(self.plan["capability_unresolved_is_identity_rejection"])

    def test_all_admitted_rows_use_unique_c0_route(self) -> None:
        for item in self.plan["candidates"]:
            mapping = item["base_mapping"]
            self.assertEqual(mapping["status"], "unique")
            self.assertEqual(mapping["target_config"], TARGET_CONFIG)
            self.assertTrue(mapping["ordering_pattern"].endswith("x"))
            row = item["proposed_canonical_row"]
            self.assertEqual(row["existing_identifier_kind"], "ordering_pattern")
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
            self.assertEqual(row["openocd_target_config"], TARGET_CONFIG)
            self.assertEqual(row["cmsis_device_name"], "")

    def test_mixed_route_base_devices_are_partially_admitted_not_rejected(self) -> None:
        unresolved_bases = {item["base_device"] for item in self.plan["capability_unresolved"]}
        self.assertEqual(
            unresolved_bases,
            {"STM32C051K8", "STM32C071FB", "STM32C071R8", "STM32C071RB", "STM32C091RB", "STM32C092RB"},
        )
        admitted_bases = {item["base_device"] for item in self.plan["candidates"]}
        self.assertTrue(unresolved_bases.issubset(admitted_bases))

    def test_c071_product_version_metadata_survives_capability_exclusion(self) -> None:
        by_icpn = {item["icpn"]: item for item in build_candidate_inputs()}
        for icpn in ("STM32C071R8I6N", "STM32C071RBI6N"):
            row = build_metadata_row(by_icpn[icpn])
            self.assertEqual(row["option_suffix"], "N")
            self.assertIn(icpn, EXPECTED_CAPABILITY_UNRESOLVED)

    def test_c071_wlcsp_identity_is_metadata_valid_but_unmapped(self) -> None:
        by_icpn = {item["icpn"]: item for item in build_candidate_inputs()}
        row = build_metadata_row(by_icpn["STM32C071FBY6TR"])
        self.assertEqual(row["package"], "WLCSP")
        self.assertEqual(row["pin_count"], "19")
        self.assertEqual(row["option_suffix"], "TR")
        self.assertIn("STM32C071FBY6TR", EXPECTED_CAPABILITY_UNRESOLVED)

    def test_policy_rejects_cmsis_shaped_route_as_manual_review(self) -> None:
        candidate = dict(build_candidate_inputs()[0])
        candidate["base_mapping"] = {
            "status": "unique",
            "ordering_pattern": "STM32C011",
            "target_config": TARGET_CONFIG,
        }
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_unresolved_route_cannot_build_canonical_row(self) -> None:
        by_icpn = {item["icpn"]: item for item in build_candidate_inputs()}
        candidate = dict(by_icpn["STM32C091RBI6"])
        candidate["base_mapping"] = resolve_mapping(candidate["icpn"], read_catalog(DEFAULT_CATALOG))
        self.assertEqual(candidate["base_mapping"]["status"], "unmapped")
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_mapping_catalog_byte_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            altered = Path(tempdir) / "openocd-parts-canonical.csv"
            altered.write_bytes(DEFAULT_CATALOG.read_bytes() + b"\n")
            with self.assertRaisesRegex(STM32C0AdmissionError, "catalog bytes changed"):
                build_admission_plan(mapping_catalog_path=altered)

    def test_production_byte_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            altered = Path(tempdir) / "icpn-v1-manifest.json"
            altered.write_bytes(LIVE_PRODUCTION_MANIFEST.read_bytes() + b"\n")
            with self.assertRaisesRegex(STM32C0AdmissionError, "Production manifest blob drifted"):
                build_admission_plan(production_manifest_path=altered)

    def test_nonempty_canonical_prestate_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "stm32c0-commercial-icpn.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, lineterminator="\n")
                writer.writeheader()
                writer.writerow({field: ("STM32C0" if field == "family" else "x") for field in CANONICAL_FIELDS})
            with self.assertRaisesRegex(STM32C0AdmissionError, "zero-row STM32C0 canonical prestate"):
                build_admission_plan(canonical_path=path)

    def test_frozen_summary_replays_exactly(self) -> None:
        validate_frozen_plan(self.plan)
        summary = admission_summary(self.plan)
        self.assertEqual(summary["canonical_input_sha256"], "a57ec095b1af22963ef5415d7f3cbc1cd4a920dc6e06a9817dca4d029b714971")

    def test_no_programming_hil_runtime_or_write_claim_escapes(self) -> None:
        summary = admission_summary(self.plan)
        self.assertTrue(summary["claims"])
        self.assertEqual(set(summary["claims"].values()), {False})
        self.assertEqual(summary["production_snapshot"]["exact_icpn_count"], 703)
        self.assertEqual(summary["production_snapshot"]["stm32c0_exact_icpn_count"], 0)


if __name__ == "__main__":
    unittest.main()
