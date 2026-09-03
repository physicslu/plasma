#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import read_json, write_canonical_dataset
from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CATALOG = HERE / "openocd-parts-canonical.csv"
EVIDENCE = HERE / "evidence" / "stm32f4-phase4.2k-f407-f417-i-admission-live-2026-09-03"
PLAN = HERE / "stm32f4-phase4.2k-f407-f417-i-admission-plan.json"
SUMMARY = HERE / "stm32f4-phase4.2k-f407-f417-i-admission-audit.json"
EVALUATION = EVIDENCE / "evaluation.json"
PLAN_SHA = "5bf84e7ebbac8808e6ef3f1cc072bc55ac380e0ba64a59b23a0684db0b76764f"
EXPECTED = {
    "STM32F407IEH6", "STM32F407IEH6TR", "STM32F407IEH7", "STM32F407IET6",
    "STM32F407IGH6", "STM32F407IGH6TR", "STM32F407IGH7", "STM32F407IGT6", "STM32F407IGT7",
    "STM32F417IEH6", "STM32F417IET6",
    "STM32F417IGH6", "STM32F417IGH6TR", "STM32F417IGT6", "STM32F417IGT7",
}
EXCLUDED_NRND = {"STM32F417IGH6W"}
ADMISSION_BASES = {"STM32F407IE", "STM32F407IG", "STM32F417IE", "STM32F417IG"}


class STM32F4Phase42KPostAdmissionTests(unittest.TestCase):
    def _rows(self) -> list[dict[str, str]]:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_retained_evidence_and_publish_binding_are_immutable(self) -> None:
        evaluation = read_json(EVALUATION)
        self.assertTrue(evaluation["candidate_baseline_match"])
        self.assertEqual(evaluation["candidate_drift"], [])
        self.assertTrue(evaluation["scale_ready"])
        self.assertEqual(evaluation["target_count"], 5)
        self.assertEqual(evaluation["expected_exact_icpn_candidates"], 16)
        self.assertEqual(evaluation["observed_exact_icpn_candidates"], 16)

        self.assertEqual(hashlib.sha256(PLAN.read_bytes()).hexdigest(), PLAN_SHA)
        plan = read_json(PLAN)
        self.assertEqual(plan["candidate_count"], 15)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 15, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual({item["icpn"] for item in plan["candidates"]}, EXPECTED)
        self.assertTrue(all(item["decision"] == "admit" for item in plan["candidates"]))

        summary = read_json(SUMMARY)
        self.assertEqual(summary["status"], "published")
        self.assertEqual(summary["admission_plan_sha256"], PLAN_SHA)
        self.assertEqual(summary["proposal_run_id"], 33711328905)
        self.assertEqual(summary["proposal_artifact_id"], 9876998587)
        self.assertEqual(
            summary["proposal_artifact_zip_sha256"],
            "427727ceecb8f1ec6f1ce3ea3ece58660ceef6c7fb14f8f2e67fe8398dd12356",
        )
        self.assertEqual((summary["production_rows_before"], summary["production_rows_after"]), (211, 226))
        self.assertEqual((summary["production_base_devices_before"], summary["production_base_devices_after"]), (73, 77))
        self.assertEqual(set(summary["added_exact_icpns"]), EXPECTED)
        self.assertEqual(set(summary["lifecycle_exclusions"]), EXCLUDED_NRND)

    def test_production_contains_active_exact_rows_and_excludes_nrnd(self) -> None:
        rows = self._rows()
        self.assertGreaterEqual(len(rows), 226)
        self.assertEqual(len(rows), len({row["icpn"] for row in rows}))
        by_icpn = {row["icpn"]: row for row in rows}
        self.assertTrue(EXPECTED <= set(by_icpn))
        self.assertTrue(EXCLUDED_NRND.isdisjoint(by_icpn))

        for icpn in EXPECTED:
            row = by_icpn[icpn]
            self.assertEqual(row["openocd_target_config"], "tcl/target/stm32f4x.cfg")
            self.assertEqual(row["pin_count"], "176")
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
            self.assertEqual(row["verification_status"], "verified_direct_st_retained_browser_exact_icpn")
            if "H" in icpn[len(row["base_device"]):]:
                self.assertEqual(row["package"], "UFBGA")
            else:
                self.assertEqual(row["package"], "LQFP")
            expected_flash = "512 KiB" if row["base_device"].endswith("IE") else "1024 KiB"
            self.assertEqual(row["flash_size"], expected_flash)

    def test_inventory_closes_four_admitted_bases_without_freezing_future_growth(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertGreaterEqual(inventory["production"]["exact_icpn_rows"], 226)
        self.assertGreaterEqual(inventory["production"]["base_device_count"], 77)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(
            inventory["gap"]["base_device_count"],
            inventory["gap"]["policy_ready_count"] + inventory["gap"]["policy_blocked_count"],
        )
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
