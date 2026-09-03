#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import write_canonical_dataset
from device_catalog_pipeline_framework import pipeline_plan_is_clean
from stm32f4_admission import build_admission_plan
from stm32f4_coverage_gap_inventory import build_inventory
from validate_stm32f4_retained_evidence import validate_retained_evidence

CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CATALOG = HERE / "openocd-parts-canonical.csv"
BASELINE = HERE / "stm32f4-phase4.2f-f412re-rg-admission-baseline.json"
EVIDENCE = HERE / "evidence" / "stm32f4-phase4.2f-f412re-rg-admission-live-2026-09-02"
FINAL_SHA = "22419b078f1c6436f0aa6dd3b410791170a1976be59a03a814469acc54690f09"
EXPECTED = {
    "STM32F412RET6", "STM32F412RET6TR", "STM32F412RET7", "STM32F412RET7TR", "STM32F412REY6TR",
    "STM32F412RGT6", "STM32F412RGT6TR", "STM32F412RGY6PTR", "STM32F412RGY6TR",
}
# Admissions after Phase 4.2F must be removed when reconstructing the immutable
# historical 199-row pre-state. Otherwise a later legitimate catalog expansion
# would make this historical replay test fail for the wrong reason.
POST_PHASE42F_ADMISSIONS = {
    "STM32F405OEY6TR",
    "STM32F405OGY6TR",
    "STM32F415OGY6TR",
    "STM32F407IEH6",
    "STM32F407IEH6TR",
    "STM32F407IEH7",
    "STM32F407IET6",
    "STM32F407IGH6",
    "STM32F407IGH6TR",
    "STM32F407IGH7",
    "STM32F407IGT6",
    "STM32F407IGT7",
    "STM32F417IEH6",
    "STM32F417IET6",
    "STM32F417IGH6",
    "STM32F417IGH6TR",
    "STM32F417IGT6",
    "STM32F417IGT7",
}


class STM32F4Phase42FPostAdmissionTests(unittest.TestCase):
    def _rows(self, path: Path = CANONICAL) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_retained_evidence_is_still_scale_ready(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertTrue(report["scale_ready"])
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertEqual(report["targets"], 3)
        self.assertEqual(report["exact_icpn_candidates"], 10)

    def test_production_contains_exact_bounded_admission(self) -> None:
        rows = self._rows()
        self.assertGreaterEqual(len(rows), 208)
        by_icpn = {row["icpn"]: row for row in rows}
        self.assertTrue(EXPECTED <= set(by_icpn))
        row = by_icpn["STM32F412RGY6PTR"]
        self.assertEqual(row["base_device"], "STM32F412RG")
        self.assertEqual(row["package"], "WLCSP")
        self.assertEqual(row["pin_count"], "64")
        self.assertEqual(row["flash_size"], "1024 KiB")
        self.assertEqual(row["option_suffix"], "PTR")
        self.assertEqual(row["openocd_target_config"], "tcl/target/stm32f4x.cfg")

    def test_gap_lifecycle_closes_admitted_bases_without_freezing_future_policy(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertGreaterEqual(inventory["production"]["exact_icpn_rows"], 208)
        self.assertGreaterEqual(inventory["production"]["base_device_count"], 70)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(
            inventory["gap"]["base_device_count"],
            inventory["gap"]["policy_ready_count"] + inventory["gap"]["policy_blocked_count"],
        )
        gap_bases = {x["base_device"] for x in inventory["gap"]["policy_ready"] + inventory["gap"]["policy_blocked"]}
        self.assertNotIn("STM32F412RE", gap_bases)
        self.assertNotIn("STM32F412RG", gap_bases)

    def test_historical_199_to_208_replay_is_byte_identical(self) -> None:
        fields: list[str]
        rows: list[dict[str, str]]
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [
                row
                for row in reader
                if row["icpn"] not in EXPECTED and row["icpn"] not in POST_PHASE42F_ADMISSIONS
            ]
        self.assertEqual(len(rows), 199)
        with tempfile.TemporaryDirectory() as tmp:
            historical = Path(tmp) / "stm32f4-commercial-icpn.csv"
            with historical.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            plan = build_admission_plan(
                evidence_dir=EVIDENCE,
                baseline_path=BASELINE,
                catalog_path=CATALOG,
                canonical_path=historical,
                admission_base_devices={"STM32F412RE", "STM32F412RG"},
            )
            self.assertTrue(pipeline_plan_is_clean(plan))
            self.assertEqual(plan["candidate_count"], 9)
            self.assertEqual(plan["decision_counts"]["admit"], 9)
            result = write_canonical_dataset(plan=plan, canonical_path=historical)
            self.assertEqual((result["rows_before"], result["rows_after"], len(result["added"])), (199, 208, 9))
            self.assertEqual(hashlib.sha256(historical.read_bytes()).hexdigest(), FINAL_SHA)


if __name__ == "__main__":
    unittest.main()
