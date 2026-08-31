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

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch3-live-2026-08-31"
BASELINE = HERE / "stm32f4-phase4.0-foundation-batch3-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
AUDIT = HERE / "stm32f4-phase4.0-foundation-batch3-admission-audit.json"
NEW_BASES = {
    "STM32F401CD",
    "STM32F401CE",
    "STM32F412CE",
    "STM32F412CG",
    "STM32F412ZE",
}
EXPECTED_CANONICAL_SHA256 = "affa1b94e569a771eb7b5672fadf3ad17c8914f0d5adab27bbe23386cb88364e"
EXPECTED_PREWRITE_PLAN_SHA256 = "05cbd105b923f1b363dedf59f0d2348a70e2daee88915206f929c31ba1821de0"
EXPECTED_CANONICAL_GIT_BLOB = "b13f219a2496184ee4443d44164e9e449fb77529"
PREVIEW_CONTROL = "STM32F401CCF6TR"


class STM32F4Phase40FoundationBatch3PostAdmissionTests(unittest.TestCase):
    def _baseline_new_icpns(self) -> set[str]:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        return {
            icpn
            for target in baseline["targets"]
            if target["base_device"] in NEW_BASES
            for icpn in target["exact_icpns"]
        }

    def _prewrite_canonical(self, output: Path, new_icpns: set[str]) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if row["icpn"] not in new_icpns]
        self.assertEqual(len(rows), 85)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_admission_audit_binds_read_only_proposal(self) -> None:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["source_rows"], 85)
        self.assertEqual(audit["admitted_rows"], 16)
        self.assertEqual(audit["production_rows_after"], 101)
        self.assertEqual(
            audit["decision_counts"],
            {
                "admit": 16,
                "already_present": 0,
                "manual_review_required": 0,
                "reject": 0,
            },
        )
        self.assertEqual(audit["plan_sha256"], EXPECTED_PREWRITE_PLAN_SHA256)
        self.assertEqual(audit["canonical_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(audit["canonical_git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(audit["proposal_workflow_run_id"], "33355504707")
        self.assertEqual(audit["proposal_artifact_id"], "9744988636")
        self.assertTrue(audit["canonical_dataset_written"])

    def test_retained_evidence_is_scale_ready(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 6)
        self.assertEqual(report["exact_icpn_candidates"], 20)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_current_state_replans_batch3_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 16)
        self.assertEqual(plan["decision_counts"]["admit"], 0)
        self.assertEqual(plan["decision_counts"]["already_present"], 16)
        self.assertEqual(plan["decision_counts"]["manual_review_required"], 0)
        self.assertEqual(plan["decision_counts"]["reject"], 0)
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])
        self.assertEqual(hashlib.sha256(CANONICAL.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)

    def test_materialization_replays_85_to_101_and_is_byte_identical(self) -> None:
        new_icpns = self._baseline_new_icpns()
        self.assertEqual(len(new_icpns), 16)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "stm32f4-commercial-icpn.csv"
            named_evidence = root / EVIDENCE.name
            self._prewrite_canonical(canonical, new_icpns)
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
            self.assertEqual(plan["canonical_rows_before"], 85)
            self.assertEqual(plan["candidate_count"], 16)
            self.assertEqual(plan["decision_counts"]["admit"], 16)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 85)
            self.assertEqual(first["rows_after"], 101)
            self.assertEqual(len(first["added"]), 16)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 101)
            self.assertEqual(second["rows_after"], 101)
            self.assertEqual(second["added"], [])
            self.assertEqual(canonical.read_bytes(), CANONICAL.read_bytes())
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)

    def test_preview_control_remains_in_production(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertIn(PREVIEW_CONTROL, rows)
        self.assertEqual(rows[PREVIEW_CONTROL]["base_device"], "STM32F401CC")


if __name__ == "__main__":
    unittest.main()
