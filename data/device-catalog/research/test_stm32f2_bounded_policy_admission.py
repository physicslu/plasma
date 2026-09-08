#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import (  # noqa: E402
    AdmissionError,
    write_canonical_dataset,
)
from stm32f2_admission_policy import CANONICAL_FIELDS  # noqa: E402
from stm32f2_bounded_admission import (  # noqa: E402
    admission_plan_is_clean,
    build_admission_plan,
    load_admission_spec,
)
from stm32f2_bounded_policy import (  # noqa: E402
    DEFAULT_CANONICAL,
    build_policy_plan,
    load_policy_spec,
    policy_plan_is_clean,
    policy_summary,
)

EXPECTED_43I = {
    "STM32F205RET6",
    "STM32F205RET6TR",
    "STM32F205RET7",
    "STM32F205RET7TR",
    "STM32F205REY6TR",
    "STM32F207IFH6",
    "STM32F207IFH6TR",
    "STM32F207IFT6",
    "STM32F215VET6",
    "STM32F217VET6",
    "STM32F217VET6TR",
}


class STM32F2BoundedPolicyAdmissionTests(unittest.TestCase):
    def _phase_4_3j_historical_canonical(self, path: Path) -> None:
        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = [row for row in reader if row["icpn"] not in EXPECTED_43I]
        self.assertEqual(len(rows), 22)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_historical_policy_replay_matches_checked_in_baselines(self) -> None:
        for phase in ("4.3C", "4.3F"):
            with self.subTest(phase=phase):
                spec = load_policy_spec(phase)
                plan = build_policy_plan(phase=phase)
                self.assertTrue(policy_plan_is_clean(plan, spec=spec))
                self.assertEqual(
                    policy_summary(plan, spec=spec),
                    json.loads(spec.policy_baseline_path.read_text(encoding="utf-8")),
                )

    def test_phase_4_3i_policy_is_exact_clean_and_closed(self) -> None:
        spec = load_policy_spec("4.3I")
        plan = build_policy_plan(phase="4.3I")
        summary = policy_summary(plan, spec=spec)
        self.assertTrue(policy_plan_is_clean(plan, spec=spec))
        self.assertEqual(summary, json.loads(spec.policy_baseline_path.read_text(encoding="utf-8")))
        self.assertEqual(set(summary["policy_ready_exact_icpns"]), EXPECTED_43I)
        self.assertEqual(summary["candidate_count"], 11)
        self.assertEqual(summary["production_snapshot"]["exact_icpn_count"], 481)
        self.assertEqual(summary["production_snapshot"]["stm32f2_exact_icpn_count"], 22)
        self.assertFalse(summary["production_write_applied"])
        self.assertFalse(summary["programming_algorithm_equivalence_claimed"])
        self.assertFalse(summary["runtime_support_claimed"])

    def test_phase_4_3i_metadata_semantics_are_deterministic(self) -> None:
        plan = build_policy_plan(phase="4.3I")
        rows = {
            item["icpn"]: item["proposed_canonical_row"]
            for item in plan["candidates"]
        }
        self.assertEqual(rows["STM32F205REY6TR"]["package"], "WLCSP")
        self.assertEqual(rows["STM32F205REY6TR"]["pin_count"], "66")
        self.assertEqual(rows["STM32F205REY6TR"]["flash_size"], "512 KiB")
        self.assertEqual(rows["STM32F207IFH6"]["package"], "UFBGA")
        self.assertEqual(rows["STM32F207IFH6"]["pin_count"], "176")
        self.assertEqual(rows["STM32F207IFH6"]["flash_size"], "768 KiB")
        self.assertEqual(rows["STM32F215VET6"]["package"], "LQFP")
        self.assertEqual(rows["STM32F215VET6"]["pin_count"], "100")
        self.assertEqual(rows["STM32F217VET6TR"]["pin_count"], "100")

    def test_phase_4_3i_fails_closed_on_historical_canonical_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / DEFAULT_CANONICAL.name
            with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                fields = list(reader.fieldnames or [])
            rows = [row for row in rows if row["icpn"] != "STM32F205RBT6"]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(AdmissionError, "historical canonical"):
                build_policy_plan(phase="4.3I", canonical_path=path)

    def test_phase_4_3j_admission_plan_replays_from_historical_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            self._phase_4_3j_historical_canonical(canonical)
            spec = load_admission_spec("4.3J")
            plan = build_admission_plan(phase="4.3J", canonical_path=canonical)
            self.assertTrue(admission_plan_is_clean(plan, spec=spec))
            self.assertEqual(plan["candidate_count"], 11)
            self.assertEqual(plan["canonical_rows_before"], 22)
            self.assertEqual(
                plan["decision_counts"],
                {"admit": 11, "already_present": 0, "manual_review_required": 0, "reject": 0},
            )
            self.assertEqual({item["icpn"] for item in plan["candidates"]}, EXPECTED_43I)
            self.assertFalse(plan["production_write_applied"])
            self.assertFalse(plan["programming_algorithm_equivalence_claimed"])
            self.assertFalse(plan["runtime_programming_support_claimed"])

    def test_generic_writer_is_exact_and_idempotent_in_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            self._phase_4_3j_historical_canonical(canonical)
            plan = build_admission_plan(phase="4.3J", canonical_path=canonical)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 22)
            self.assertEqual(first["rows_after"], 33)
            self.assertEqual(set(first["added"]), EXPECTED_43I)
            self.assertEqual(second["status"], "no_op")
            with canonical.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 33)
            self.assertEqual({row["base_device"] for row in rows} & {
                "STM32F205RE", "STM32F207IF", "STM32F215VE", "STM32F217VE"
            }, {"STM32F205RE", "STM32F207IF", "STM32F215VE", "STM32F217VE"})

    def test_generic_writer_rejects_unbound_canonical_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            self._phase_4_3j_historical_canonical(canonical)
            plan = build_admission_plan(phase="4.3J", canonical_path=canonical)
            with canonical.open("a", encoding="utf-8") as handle:
                handle.write("unexpected\n")
            with self.assertRaisesRegex(AdmissionError, "changed after admission planning"):
                write_canonical_dataset(plan=plan, canonical_path=canonical)


if __name__ == "__main__":
    unittest.main()
