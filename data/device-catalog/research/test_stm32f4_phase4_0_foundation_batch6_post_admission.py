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

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch6-live-2026-08-31"
BASELINE = HERE / "stm32f4-phase4.0-foundation-batch6-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
AUDIT = HERE / "stm32f4-phase4.0-foundation-batch6-admission-audit.json"
NEW_BASES = {"STM32F412ZG", "STM32F413CG", "STM32F413ZG"}
EXPECTED_CANONICAL_SHA256 = "4a6bf6ffbf384ce3d9c91d318b6793c710d621d6f9e11f0a6c5b50206a5acb2a"
EXPECTED_PREWRITE_PLAN_SHA256 = "37591f9e8375329ab06169ccddf567259939ea2cc38ed4f6aca79044e6bdbc27"
EXPECTED_CANONICAL_GIT_BLOB = "434443479cd8a7d5b87b723a9fde93806c4faddd"
PROPOSAL_ONLY_ICPNS = {"STM32F413CGU3", "STM32F413ZGJ3", "STM32F413ZGT3"}
CONTROL_ICPNS = {"STM32F412CGU6", "STM32F412CGU6TR"}
PRE_BATCH6_EVIDENCE_IDS = {
    "stm32f4-phase3.1-bounded-pilot-2026-08-30-retained-20260830T023035Z-b42d460",
    "stm32f4-phase3.3-scaleout-batch1-2026-08-30-retained-20260830T040319Z-db7f090",
    "stm32f4-phase3.3-scaleout-batch2-2026-08-30-retained-20260830T063333Z-cb883bb",
    "stm32f4-phase4.0-f446-batch1-2026-08-30-retained-20260830T134444Z-e9e8e60",
    "stm32f4-phase4.0-foundation-batch2-2026-08-31-retained-20260831T013557Z-8979938",
    "stm32f4-phase4.0-foundation-batch3-2026-08-31-retained-20260831T035207Z-42fa641",
    "stm32f4-phase4.0-foundation-batch4-2026-08-31-retained-20260831T044040Z-226ad4d",
    "stm32f4-phase4.0-foundation-batch5-2026-08-31-retained-20260831T053303Z-5f76683",
}


def _row_evidence_id(row: dict[str, str]) -> str:
    marker = "#plasma-evidence="
    reference = row.get("source_reference", "")
    return reference.split(marker, 1)[1] if marker in reference else ""


class STM32F4Phase40FoundationBatch6PostAdmissionTests(unittest.TestCase):
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
            rows = [row for row in reader if _row_evidence_id(row) in PRE_BATCH6_EVIDENCE_IDS]
        self.assertEqual(len(rows), 124)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_admission_audit_binds_read_only_proposal_and_recovery(self) -> None:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["pre_rows"], 124)
        self.assertEqual(audit["new_exact_icpns"], 9)
        self.assertEqual(audit["post_rows"], 133)
        self.assertEqual(
            audit["decision_counts"],
            {"admit": 9, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(audit["admission_plan_sha256"], EXPECTED_PREWRITE_PLAN_SHA256)
        self.assertEqual(audit["final_csv_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(audit["final_git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(audit["proposal_workflow_run_id"], "33365292387")
        self.assertEqual(audit["proposal_artifact_id"], "9748055114")
        self.assertTrue(audit["canonical_dataset_written"])
        recovery = audit["publish_recovery"]
        self.assertEqual(recovery["failed_run_id"], "33365419968")
        self.assertEqual(recovery["failure_stage"], "audit serialization before commit")
        self.assertFalse(recovery["repository_write_occurred"])

    def test_retained_evidence_is_scale_ready(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 4)
        self.assertEqual(report["exact_icpn_candidates"], 11)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_current_state_replans_batch6_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 9)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 0, "already_present": 9, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_materialization_replays_124_to_133_and_matches_historical_hash(self) -> None:
        new_icpns = self._baseline_new_icpns()
        self.assertEqual(len(new_icpns), 9)
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
            self.assertEqual(plan["canonical_rows_before"], 124)
            self.assertEqual(plan["candidate_count"], 9)
            self.assertEqual(plan["decision_counts"]["admit"], 9)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 124)
            self.assertEqual(first["rows_after"], 133)
            self.assertEqual(set(first["added"]), new_icpns)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 133)
            self.assertEqual(second["rows_after"], 133)
            self.assertEqual(second["added"], [])
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)

    def test_proposal_only_parts_are_not_admitted_and_control_stays_present(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertTrue(PROPOSAL_ONLY_ICPNS.isdisjoint(rows))
        self.assertTrue(CONTROL_ICPNS <= set(rows))
        self.assertEqual(rows["STM32F412CGU6"]["base_device"], "STM32F412CG")


if __name__ == "__main__":
    unittest.main()
