#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import write_canonical_dataset  # noqa: E402
from device_catalog_pipeline_framework import pipeline_plan_is_clean  # noqa: E402
from stm32f4_admission import build_admission_plan  # noqa: E402
from validate_stm32f4_retained_evidence import validate_retained_evidence  # noqa: E402

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-f446-batch1-live-2026-08-30"
BASELINE = HERE / "stm32f4-phase4.0-f446-batch1-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
NEW_BASES = {"STM32F446VC", "STM32F446VE", "STM32F446ZC", "STM32F446ZE"}
EXPECTED_POST_F446_SHA256 = "9ccab9f4de5c447410b2d649ce933fddcc569746431bf9cb0431fa8246676308"
EXPECTED_PREWRITE_PLAN_SHA256 = "df3dbe713b05bc7c7ef7bc6640655cd4808321eaf4bf756b75005097fa823b89"
PRE_F446_EVIDENCE_IDS = {
    "stm32f4-phase3.1-bounded-pilot-2026-08-30-retained-20260830T023035Z-b42d460",
    "stm32f4-phase3.3-scaleout-batch1-2026-08-30-retained-20260830T040319Z-db7f090",
    "stm32f4-phase3.3-scaleout-batch2-2026-08-30-retained-20260830T063333Z-cb883bb",
}
POST_F446_EVIDENCE_IDS = {
    *PRE_F446_EVIDENCE_IDS,
    "stm32f4-phase4.0-f446-batch1-2026-08-30-retained-20260830T134444Z-e9e8e60",
}


class STM32F4Phase40F446PostAdmissionTests(unittest.TestCase):
    def _historical_canonical(
        self,
        output: Path,
        *,
        evidence_ids: set[str],
        expected_rows: int,
    ) -> None:
        """Reconstruct a historical canonical state from immutable provenance cohorts.

        Current production may contain later admissions. Historical replay therefore
        selects rows by the retained-evidence cohorts that existed at the milestone,
        rather than assuming today's total row count is still the milestone row count.
        """
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [
                row
                for row in reader
                if any(evidence_id in row["source_reference"] for evidence_id in evidence_ids)
            ]
        self.assertEqual(len(rows), expected_rows)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_retained_evidence_is_scale_ready(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 5)
        self.assertEqual(report["exact_icpn_candidates"], 27)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_current_state_replans_f446_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 23)
        self.assertEqual(plan["decision_counts"]["admit"], 0)
        self.assertEqual(plan["decision_counts"]["already_present"], 23)
        self.assertEqual(plan["decision_counts"]["manual_review_required"], 0)
        self.assertEqual(plan["decision_counts"]["reject"], 0)
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_materialization_replays_49_to_72_and_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "stm32f4-commercial-icpn.csv"
            expected_post_f446 = root / "stm32f4-post-f446.csv"
            named_evidence = root / EVIDENCE.name
            self._historical_canonical(
                canonical,
                evidence_ids=PRE_F446_EVIDENCE_IDS,
                expected_rows=49,
            )
            self._historical_canonical(
                expected_post_f446,
                evidence_ids=POST_F446_EVIDENCE_IDS,
                expected_rows=72,
            )
            self.assertEqual(
                hashlib.sha256(expected_post_f446.read_bytes()).hexdigest(),
                EXPECTED_POST_F446_SHA256,
            )
            shutil.copytree(EVIDENCE, named_evidence)

            plan = build_admission_plan(
                evidence_dir=named_evidence,
                baseline_path=BASELINE,
                catalog_path=CATALOG,
                canonical_path=canonical,
                admission_base_devices=NEW_BASES,
            )
            serialized = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode("utf-8")
            self.assertEqual(hashlib.sha256(serialized).hexdigest(), EXPECTED_PREWRITE_PLAN_SHA256)
            self.assertEqual(plan["canonical_rows_before"], 49)
            self.assertEqual(plan["candidate_count"], 23)
            self.assertEqual(plan["decision_counts"]["admit"], 23)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 49)
            self.assertEqual(first["rows_after"], 72)
            self.assertEqual(len(first["added"]), 23)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 72)
            self.assertEqual(second["rows_after"], 72)
            self.assertEqual(second["added"], [])
            self.assertEqual(canonical.read_bytes(), expected_post_f446.read_bytes())
            self.assertEqual(
                hashlib.sha256(canonical.read_bytes()).hexdigest(),
                EXPECTED_POST_F446_SHA256,
            )


if __name__ == "__main__":
    unittest.main()
