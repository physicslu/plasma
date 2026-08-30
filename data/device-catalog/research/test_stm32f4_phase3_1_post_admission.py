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

EVIDENCE = HERE / "evidence" / "stm32f4-phase3.1-bounded-pilot-live-2026-08-30"
BASELINE = HERE / "stm32f4-phase3.1-pilot-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
AUDIT = HERE / "stm32f4-phase3.1-admission-audit.json"
EXPECTED_COUNT = 18


class STM32F4Phase31PostAdmissionTests(unittest.TestCase):
    def _audit(self) -> dict[str, object]:
        return json.loads(AUDIT.read_text(encoding="utf-8"))

    def _empty_canonical(self, path: Path) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            fields = list(csv.DictReader(handle).fieldnames or [])
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle, lineterminator="\n").writerow(fields)

    def test_retained_live_evidence_is_byte_integrity_valid_and_scale_ready(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 4)
        self.assertEqual(report["exact_icpn_candidates"], EXPECTED_COUNT)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_current_state_replans_all_18_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], EXPECTED_COUNT)
        self.assertEqual(plan["decision_counts"]["admit"], 0)
        self.assertEqual(plan["decision_counts"]["already_present"], EXPECTED_COUNT)
        self.assertEqual(plan["decision_counts"]["manual_review_required"], 0)
        self.assertEqual(plan["decision_counts"]["reject"], 0)
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_prewrite_plan_reconstructs_live_artifact_byte_for_byte_and_writer_is_idempotent(self) -> None:
        audit = self._audit()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "stm32f4-commercial-icpn.csv"
            live_named_evidence = root / "evidence"
            self._empty_canonical(canonical)
            shutil.copytree(EVIDENCE, live_named_evidence)

            # The live admission artifact binds the logical evidence directory basename
            # (`evidence`). Recreate that path identity while keeping the retained files
            # byte-identical; do not normalize or replace the immutable live-plan digest.
            plan = build_admission_plan(
                evidence_dir=live_named_evidence,
                baseline_path=BASELINE,
                catalog_path=CATALOG,
                canonical_path=canonical,
            )
            serialized = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode("utf-8")
            self.assertEqual(hashlib.sha256(serialized).hexdigest(), audit["admission_plan_sha256"])
            self.assertEqual(plan["candidate_count"], audit["candidate_count"])
            self.assertEqual(plan["decision_counts"], audit["decision_counts"])
            self.assertEqual(plan["canonical_rows_before"], audit["canonical_rows_before"])
            self.assertEqual(plan["inputs"]["canonical_input_sha256"], audit["canonical_input_sha256"])
            self.assertEqual(plan["inputs"]["baseline_sha256"], audit["baseline_sha256"])
            self.assertEqual(plan["inputs"]["mapping_catalog_sha256"], audit["mapping_catalog_sha256"])
            self.assertEqual(plan["source_provenance"]["evidence_manifest_sha256"], audit["evidence_manifest_sha256"])
            self.assertEqual([item["icpn"] for item in plan["candidates"]], audit["icpns"])
            self.assertEqual(plan["decision_counts"]["admit"], EXPECTED_COUNT)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 0)
            self.assertEqual(first["rows_after"], EXPECTED_COUNT)
            self.assertEqual(len(first["added"]), EXPECTED_COUNT)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], EXPECTED_COUNT)
            self.assertEqual(second["rows_after"], EXPECTED_COUNT)
            self.assertEqual(second["added"], [])

            self.assertEqual(canonical.read_bytes(), CANONICAL.read_bytes())


if __name__ == "__main__":
    unittest.main()
