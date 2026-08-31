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

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch5-live-2026-08-31"
BASELINE = HERE / "stm32f4-phase4.0-foundation-batch5-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
AUDIT = HERE / "stm32f4-phase4.0-foundation-batch5-admission-audit.json"
NEW_BASES = {
    "STM32F437VI",
    "STM32F437ZG",
    "STM32F437ZI",
    "STM32F439VG",
    "STM32F439VI",
}
EXPECTED_CANONICAL_SHA256 = "22f999adb9627231df7b332650271320d96f1957913481a5cb7a57155d9d1b6b"
EXPECTED_PREWRITE_PLAN_SHA256 = "25fb27441e32ad38cb8fe3148d061c85d8e2b42cf684117d3db9b0ca5968ee29"
EXPECTED_CANONICAL_GIT_BLOB = "c0bb4971fa44eb818f423fc2a85efa1ffc06e81f"
NRND_ONLY = "STM32F437VIT6WTR"
CONTROL_ICPNS = {
    "STM32F437VGT6",
    "STM32F437VGT6TR",
    "STM32F437VGT7",
    "STM32F437VGT7TR",
}
PRE_BATCH5_EVIDENCE_IDS = {
    "stm32f4-phase3.1-bounded-pilot-2026-08-30-retained-20260830T023035Z-b42d460",
    "stm32f4-phase3.3-scaleout-batch1-2026-08-30-retained-20260830T040319Z-db7f090",
    "stm32f4-phase3.3-scaleout-batch2-2026-08-30-retained-20260830T063333Z-cb883bb",
    "stm32f4-phase4.0-f446-batch1-2026-08-30-retained-20260830T134444Z-e9e8e60",
    "stm32f4-phase4.0-foundation-batch2-2026-08-31-retained-20260831T013557Z-8979938",
    "stm32f4-phase4.0-foundation-batch3-2026-08-31-retained-20260831T035207Z-42fa641",
    "stm32f4-phase4.0-foundation-batch4-2026-08-31-retained-20260831T044040Z-226ad4d",
}


def _row_evidence_id(row: dict[str, str]) -> str:
    marker = "#plasma-evidence="
    reference = row.get("source_reference", "")
    return reference.split(marker, 1)[1] if marker in reference else ""


class STM32F4Phase40FoundationBatch5PostAdmissionTests(unittest.TestCase):
    def _baseline_new_icpns(self) -> set[str]:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        return {
            icpn
            for target in baseline["targets"]
            if target["base_device"] in NEW_BASES
            for icpn in target["exact_icpns"]
        }

    def _prewrite_canonical(self, output: Path) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if _row_evidence_id(row) in PRE_BATCH5_EVIDENCE_IDS]
        self.assertEqual(len(rows), 114)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_admission_audit_binds_read_only_proposal(self) -> None:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["source_rows"], 114)
        self.assertEqual(audit["admitted_rows"], 10)
        self.assertEqual(audit["production_rows_after"], 124)
        self.assertEqual(
            audit["decision_counts"],
            {"admit": 10, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(audit["plan_sha256"], EXPECTED_PREWRITE_PLAN_SHA256)
        self.assertEqual(audit["canonical_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(audit["canonical_git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(audit["proposal_workflow_run_id"], "33361381534")
        self.assertEqual(audit["proposal_artifact_id"], "9746791945")
        self.assertTrue(audit["canonical_dataset_written"])

    def test_retained_evidence_is_scale_ready(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 6)
        self.assertEqual(report["exact_icpn_candidates"], 14)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_current_state_replans_batch5_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 10)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 0, "already_present": 10, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_materialization_replays_114_to_124_and_matches_historical_hash(self) -> None:
        new_icpns = self._baseline_new_icpns()
        self.assertEqual(len(new_icpns), 10)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "stm32f4-commercial-icpn.csv"
            named_evidence = root / EVIDENCE.name
            self._prewrite_canonical(canonical)
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
            self.assertEqual(plan["canonical_rows_before"], 114)
            self.assertEqual(plan["candidate_count"], 10)
            self.assertEqual(plan["decision_counts"]["admit"], 10)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 114)
            self.assertEqual(first["rows_after"], 124)
            self.assertEqual(len(first["added"]), 10)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 124)
            self.assertEqual(second["rows_after"], 124)
            self.assertEqual(second["added"], [])
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)

    def test_nrnd_is_not_admitted_and_control_stays_present(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertNotIn(NRND_ONLY, rows)
        self.assertTrue(CONTROL_ICPNS <= set(rows))
        self.assertEqual(rows["STM32F437VGT6"]["base_device"], "STM32F437VG")


if __name__ == "__main__":
    unittest.main()
