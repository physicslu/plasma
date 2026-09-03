#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import read_json, write_canonical_dataset
from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CATALOG = HERE / "openocd-parts-canonical.csv"
EVIDENCE = HERE / "evidence" / "stm32f4-phase4.2l-f427-f429-i-admission-live-2026-09-03"
PLAN = HERE / "stm32f4-phase4.2l-f427-f429-i-admission-plan.json"
SUMMARY = HERE / "stm32f4-phase4.2l-f427-f429-i-admission-audit.json"
EVALUATION = EVIDENCE / "evaluation.json"
PLAN_SHA = "f777a8170b6579ee8f6d4b50e159d8269ac203bbadceeaed512392e0dbac0f8b"
EXPECTED = {
    "STM32F427IGH6", "STM32F427IGH6TR", "STM32F427IGH7", "STM32F427IGT6",
    "STM32F427IIH6", "STM32F427IIH6TR", "STM32F427IIH7", "STM32F427IIT6", "STM32F427IIT7",
    "STM32F429IEH6", "STM32F429IET6",
    "STM32F429IGH6", "STM32F429IGT6",
    "STM32F429IIH6", "STM32F429IIH6TR", "STM32F429IIT6",
}
ADMISSION_BASES = {"STM32F427IG", "STM32F427II", "STM32F429IE", "STM32F429IG", "STM32F429II"}
FLASH_BY_SUFFIX = {"IE": "512 KiB", "IG": "1024 KiB", "II": "2048 KiB"}


class STM32F4Phase42LPostAdmissionTests(unittest.TestCase):
    def _rows(self) -> list[dict[str, str]]:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_retained_evidence_and_publish_binding_are_immutable(self) -> None:
        evaluation = read_json(EVALUATION)
        self.assertTrue(evaluation["candidate_baseline_match"])
        self.assertEqual(evaluation["candidate_drift"], [])
        self.assertTrue(evaluation["scale_ready"])
        self.assertEqual(evaluation["target_count"], 6)
        self.assertEqual(evaluation["expected_exact_icpn_candidates"], 17)
        self.assertEqual(evaluation["observed_exact_icpn_candidates"], 17)

        self.assertEqual(hashlib.sha256(PLAN.read_bytes()).hexdigest(), PLAN_SHA)
        plan = read_json(PLAN)
        self.assertEqual(plan["candidate_count"], 16)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 16, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual({item["icpn"] for item in plan["candidates"]}, EXPECTED)
        self.assertTrue(all(item["decision"] == "admit" for item in plan["candidates"]))

        summary = read_json(SUMMARY)
        self.assertEqual(summary["status"], "published")
        self.assertEqual(summary["admission_plan_sha256"], PLAN_SHA)
        self.assertEqual(summary["proposal_run_id"], 33720156815)
        self.assertEqual(summary["proposal_artifact_id"], 9879921022)
        self.assertEqual(
            summary["proposal_artifact_zip_sha256"],
            "dd5db25420960caadcb56e7676a89c2ebde9cbaf6ac6ac4947aa167c8985b533",
        )
        self.assertEqual((summary["production_rows_before"], summary["production_rows_after"]), (226, 242))
        self.assertEqual((summary["production_base_devices_before"], summary["production_base_devices_after"]), (77, 82))
        self.assertEqual(set(summary["added_exact_icpns"]), EXPECTED)
        self.assertEqual(summary["lifecycle_exclusions"], [])

    def test_production_contains_only_the_active_exact_candidate_set(self) -> None:
        rows = self._rows()
        self.assertGreaterEqual(len(rows), 242)
        self.assertEqual(len(rows), len({row["icpn"] for row in rows}))
        by_icpn = {row["icpn"]: row for row in rows}
        self.assertTrue(EXPECTED <= set(by_icpn))

        for icpn in EXPECTED:
            row = by_icpn[icpn]
            self.assertEqual(row["openocd_target_config"], "tcl/target/stm32f4x.cfg")
            self.assertEqual(row["pin_count"], "176")
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
            self.assertEqual(row["verification_status"], "verified_direct_st_retained_browser_exact_icpn")
            self.assertEqual(row["package"], "UFBGA" if "H" in icpn[len(row["base_device"]):] else "LQFP")
            self.assertEqual(row["flash_size"], FLASH_BY_SUFFIX[row["base_device"][-2:]])

    def test_inventory_closes_five_admitted_bases_without_freezing_future_growth(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertGreaterEqual(inventory["production"]["exact_icpn_rows"], 242)
        self.assertGreaterEqual(inventory["production"]["base_device_count"], 82)
        gap_bases = {
            item["base_device"]
            for item in inventory["gap"]["policy_ready"] + inventory["gap"]["policy_blocked"]
        }
        self.assertTrue(ADMISSION_BASES.isdisjoint(gap_bases))
        self.assertTrue(ADMISSION_BASES <= set(inventory["production"]["base_devices"]))

    def test_stored_plan_is_idempotent_against_current_and_future_supersets(self) -> None:
        plan = read_json(PLAN)
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / CANONICAL.name
            shutil.copyfile(CANONICAL, copy)
            before = copy.read_bytes()
            result = write_canonical_dataset(plan=plan, canonical_path=copy)
            self.assertEqual(result["status"], "no_op")
            self.assertEqual(result["added"], [])
            self.assertEqual(copy.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
