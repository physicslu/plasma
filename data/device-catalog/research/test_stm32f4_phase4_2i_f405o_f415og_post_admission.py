#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
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
BASELINE = HERE / "stm32f4-phase4.2i-f405o-f415og-admission-baseline.json"
EVIDENCE = HERE / "evidence" / "stm32f4-phase4.2i-f405o-f415og-admission-live-2026-09-02"
PRE_SHA = "22419b078f1c6436f0aa6dd3b410791170a1976be59a03a814469acc54690f09"
FINAL_SHA = "2b3e7aaf50e855957af2072815fd536ac8e4374f7a4326f035e344f2c1abc19b"
PLAN_SHA = "58d5a9c10b82bd13325e04a9931a42a6bf554304b006b797e9cc46b7014c08db"
EXPECTED = {"STM32F405OEY6TR", "STM32F405OGY6TR", "STM32F415OGY6TR"}
EXCLUDED_NRND = {"STM32F405OGY6VTR", "STM32F405OGY6WTR"}
ADMISSION_BASES = {"STM32F405OE", "STM32F405OG", "STM32F415OG"}


class STM32F4Phase42IPostAdmissionTests(unittest.TestCase):
    def _rows(self, path: Path = CANONICAL) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_retained_evidence_remains_scale_ready_and_lifecycle_locked(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertTrue(report["scale_ready"])
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertEqual(report["targets"], 4)
        self.assertEqual(report["exact_icpn_candidates"], 4)
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        excluded = {
            row["icpn"]: row["marketing_status"]
            for row in baseline["excluded_non_active_observations"]
        }
        self.assertEqual(set(excluded), EXCLUDED_NRND)
        self.assertTrue(all(status.startswith("NRND") for status in excluded.values()))

    def test_production_contains_only_active_bounded_admission(self) -> None:
        rows = self._rows()
        self.assertEqual(len(rows), 211)
        by_icpn = {row["icpn"]: row for row in rows}
        self.assertTrue(EXPECTED <= set(by_icpn))
        self.assertTrue(EXCLUDED_NRND.isdisjoint(by_icpn))
        oe = by_icpn["STM32F405OEY6TR"]
        self.assertEqual(
            (oe["package"], oe["pin_count"], oe["flash_size"]),
            ("WLCSP", "90", "512 KiB"),
        )
        self.assertEqual(oe["openocd_target_config"], "tcl/target/stm32f4x.cfg")
        og = by_icpn["STM32F405OGY6TR"]
        self.assertEqual(
            (og["package"], og["pin_count"], og["flash_size"]),
            ("WLCSP", "90", "1024 KiB"),
        )
        self.assertEqual(hashlib.sha256(CANONICAL.read_bytes()).hexdigest(), FINAL_SHA)

    def test_gap_lifecycle_closes_all_three_admitted_bases(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 211)
        self.assertEqual(inventory["production"]["base_device_count"], 73)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["gap"]["base_device_count"], 76)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 0)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 76)
        gap_bases = {
            item["base_device"]
            for item in inventory["gap"]["policy_ready"] + inventory["gap"]["policy_blocked"]
        }
        self.assertTrue(ADMISSION_BASES.isdisjoint(gap_bases))

    def test_historical_208_to_211_replay_matches_immutable_proposal(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if row["icpn"] not in EXPECTED]
        self.assertEqual(len(rows), 208)
        with tempfile.TemporaryDirectory() as tmp:
            historical = Path(tmp) / "stm32f4-commercial-icpn.csv"
            with historical.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            self.assertEqual(hashlib.sha256(historical.read_bytes()).hexdigest(), PRE_SHA)
            plan = build_admission_plan(
                evidence_dir=EVIDENCE,
                baseline_path=BASELINE,
                catalog_path=CATALOG,
                canonical_path=historical,
                admission_base_devices=ADMISSION_BASES,
            )
            self.assertTrue(pipeline_plan_is_clean(plan))
            self.assertEqual(plan["candidate_count"], 3)
            self.assertEqual(plan["decision_counts"]["admit"], 3)
            serialized = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode()
            self.assertEqual(hashlib.sha256(serialized).hexdigest(), PLAN_SHA)
            first = write_canonical_dataset(plan=plan, canonical_path=historical)
            self.assertEqual((first["rows_before"], first["rows_after"]), (208, 211))
            self.assertEqual(set(first["added"]), EXPECTED)
            self.assertEqual(hashlib.sha256(historical.read_bytes()).hexdigest(), FINAL_SHA)
            self.assertEqual(historical.read_bytes(), CANONICAL.read_bytes())
            second = write_canonical_dataset(plan=plan, canonical_path=historical)
            self.assertEqual(second["status"], "no_op")

    def test_current_replan_is_three_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=ADMISSION_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 3)
        self.assertEqual(
            plan["decision_counts"],
            {
                "admit": 0,
                "already_present": 3,
                "manual_review_required": 0,
                "reject": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
