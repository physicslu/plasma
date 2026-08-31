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

EVIDENCE = HERE / "evidence" / "stm32f4-phase3.3-scaleout-batch2-live-2026-08-30"
BASELINE = HERE / "stm32f4-phase3.3-scaleout-batch2-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
AUDIT = HERE / "stm32f4-phase3.3-scaleout-batch2-admission-audit.json"
NEW_BASES = {"STM32F407ZE", "STM32F415VG", "STM32F427VG", "STM32F427ZG", "STM32F437VG"}
HISTORICAL_POST_BATCH2_EVIDENCE_IDS = {
    "stm32f4-phase3.1-bounded-pilot-2026-08-30-retained-20260830T023035Z-b42d460",
    "stm32f4-phase3.3-scaleout-batch1-2026-08-30-retained-20260830T040319Z-db7f090",
    "stm32f4-phase3.3-scaleout-batch2-2026-08-30-retained-20260830T063333Z-cb883bb",
}


class STM32F4Phase33ScaleoutBatch2Tests(unittest.TestCase):
    def _audit(self) -> dict[str, object]:
        return json.loads(AUDIT.read_text(encoding="utf-8"))

    def _historical_post_batch2_canonical(self, output: Path) -> None:
        """Reconstruct the immutable 49-row catalog state at Phase 3.3 batch2 close.

        Reconstruction is provenance-cohort based rather than current-row-count based,
        so later STM32F4 admissions cannot change this historical replay fixture.
        """
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [
                row
                for row in reader
                if any(
                    evidence_id in row["source_reference"]
                    for evidence_id in HISTORICAL_POST_BATCH2_EVIDENCE_IDS
                )
            ]
        self.assertEqual(len(rows), 49)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def _prewrite_canonical(self, output: Path, historical_after: Path, new_icpns: set[str]) -> None:
        with historical_after.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if row["icpn"] not in new_icpns]
        self.assertEqual(len(rows), 34)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_retained_evidence_is_scale_ready(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 6)
        self.assertEqual(report["exact_icpn_candidates"], 20)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_current_state_replans_new_batch_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 15)
        self.assertEqual(plan["decision_counts"]["admit"], 0)
        self.assertEqual(plan["decision_counts"]["already_present"], 15)
        self.assertEqual(plan["decision_counts"]["manual_review_required"], 0)
        self.assertEqual(plan["decision_counts"]["reject"], 0)
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_materialization_plan_replays_34_to_49_and_writer_is_idempotent(self) -> None:
        audit = self._audit()
        new_icpns = set(audit["icpns"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "stm32f4-commercial-icpn.csv"
            historical_after = root / "stm32f4-phase3.3-after.csv"
            materialized_named_evidence = root / EVIDENCE.name
            self._historical_post_batch2_canonical(historical_after)
            self.assertEqual(
                hashlib.sha256(historical_after.read_bytes()).hexdigest(),
                audit["canonical_sha256_after"],
            )
            self._prewrite_canonical(canonical, historical_after, new_icpns)
            shutil.copytree(EVIDENCE, materialized_named_evidence)

            # The retained audit binds the materialization plan, whose input contract
            # includes evidence_dir.name. Recreate that logical basename exactly rather
            # than recomputing or replacing the immutable admission-plan digest.
            plan = build_admission_plan(
                evidence_dir=materialized_named_evidence,
                baseline_path=BASELINE,
                catalog_path=CATALOG,
                canonical_path=canonical,
                admission_base_devices=NEW_BASES,
            )
            serialized = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode("utf-8")
            self.assertEqual(hashlib.sha256(serialized).hexdigest(), audit["admission_plan_sha256"])
            self.assertEqual(plan["canonical_rows_before"], 34)
            self.assertEqual(plan["candidate_count"], 15)
            self.assertEqual(plan["decision_counts"]["admit"], 15)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 34)
            self.assertEqual(first["rows_after"], 49)
            self.assertEqual(len(first["added"]), 15)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 49)
            self.assertEqual(second["rows_after"], 49)
            self.assertEqual(second["added"], [])
            self.assertEqual(canonical.read_bytes(), historical_after.read_bytes())
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), audit["canonical_sha256_after"])


if __name__ == "__main__":
    unittest.main()
