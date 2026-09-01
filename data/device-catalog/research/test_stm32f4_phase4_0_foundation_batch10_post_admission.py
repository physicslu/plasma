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

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch10-live-2026-09-01"
BASELINE = HERE / "stm32f4-phase4.0-foundation-batch10-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
AUDIT = HERE / "stm32f4-phase4.0-foundation-batch10-admission-audit.json"
NEW_BASES = {
    "STM32F469ZG",
    "STM32F469ZI",
    "STM32F479VG",
    "STM32F479VI",
    "STM32F479ZG",
}
EXPECTED_CANONICAL_SHA256 = "9a5c90fd0b1b326a073fa7d88d7d76962716872505a5f856b6b8f5ba0b2d3a41"
EXPECTED_PREWRITE_PLAN_SHA256 = "1613d2a0ee774ae34d246feb713cc253f1d1a21717f723d2aa1f20b18754de81"
EXPECTED_CANONICAL_GIT_BLOB = "8a6740da10a312612b047b1dd65e79dae8deef56"
POST_BATCH11_CANONICAL_SHA256 = "6a3150e356511dfed679b747515d1ae1380d3da101b11edd3322f27cd936c948"
POST_BATCH11_CANONICAL_GIT_BLOB = "21ad3fee8b780949e8184cdb56b5601fe6a48c03"
CONTROL_ICPNS = {"STM32F469ZET6"}
PREVIEW_AUDIT_ONLY_ICPN = "STM32F401CCF6TR"
PRE_BATCH10_EVIDENCE_IDS = {
    "stm32f4-phase3.1-bounded-pilot-2026-08-30-retained-20260830T023035Z-b42d460",
    "stm32f4-phase3.3-scaleout-batch1-2026-08-30-retained-20260830T040319Z-db7f090",
    "stm32f4-phase3.3-scaleout-batch2-2026-08-30-retained-20260830T063333Z-cb883bb",
    "stm32f4-phase4.0-f446-batch1-2026-08-30-retained-20260830T134444Z-e9e8e60",
    "stm32f4-phase4.0-foundation-batch2-2026-08-31-retained-20260831T013557Z-8979938",
    "stm32f4-phase4.0-foundation-batch3-2026-08-31-retained-20260831T035207Z-42fa641",
    "stm32f4-phase4.0-foundation-batch4-2026-08-31-retained-20260831T044040Z-226ad4d",
    "stm32f4-phase4.0-foundation-batch5-2026-08-31-retained-20260831T053303Z-5f76683",
    "stm32f4-phase4.0-foundation-batch6-2026-08-31-retained-20260831T063818Z-c3edb20",
    "stm32f4-phase4.0-foundation-batch7-2026-08-31-retained-20260831T080025Z-feef382",
    "stm32f4-phase4.0-foundation-batch8-2026-08-31-retained-20260831T121653Z-5299281",
    "stm32f4-phase4.0-foundation-batch9-2026-08-31-retained-20260831T125555Z-4e5cc1b",
}


def _row_evidence_id(row: dict[str, str]) -> str:
    marker = "#plasma-evidence="
    reference = row.get("source_reference", "")
    return reference.split(marker, 1)[1] if marker in reference else ""


class STM32F4Phase40FoundationBatch10PostAdmissionTests(unittest.TestCase):
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
            rows = [row for row in reader if _row_evidence_id(row) in PRE_BATCH10_EVIDENCE_IDS]
        self.assertEqual(len(rows), 151)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_admission_audit_binds_read_only_proposal(self) -> None:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["pre_rows"], 151)
        self.assertEqual(audit["new_exact_icpns"], 6)
        self.assertEqual(audit["post_rows"], 157)
        self.assertEqual(
            audit["decision_counts"],
            {"admit": 6, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(audit["admission_plan_sha256"], EXPECTED_PREWRITE_PLAN_SHA256)
        self.assertEqual(audit["final_csv_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(audit["final_git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(audit["proposal_workflow_run_id"], "33461938201")
        self.assertEqual(audit["proposal_artifact_id"], "9783458088")
        self.assertTrue(audit["canonical_dataset_written"])

    def test_retained_evidence_is_scale_ready_and_preserves_bounded_retry(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 6)
        self.assertEqual(report["exact_icpn_candidates"], 7)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])
        provenance = json.loads((EVIDENCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["live_acquisition_attempts"], 2)
        self.assertFalse(provenance["live_acquisition_attempt_outcomes"][0]["clean"])
        self.assertTrue(provenance["live_acquisition_attempt_outcomes"][1]["clean"])
        self.assertEqual(provenance["excluded_non_active_observations"], [])

    def test_current_state_replans_batch10_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 6)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 0, "already_present": 6, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_materialization_replays_151_to_157_and_matches_historical_hash(self) -> None:
        new_icpns = self._baseline_new_icpns()
        self.assertEqual(len(new_icpns), 6)
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
            self.assertEqual(plan["canonical_rows_before"], 151)
            self.assertEqual(plan["candidate_count"], 6)
            self.assertEqual(plan["decision_counts"]["admit"], 6)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 151)
            self.assertEqual(first["rows_after"], 157)
            self.assertEqual(set(first["added"]), new_icpns)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 157)
            self.assertEqual(second["rows_after"], 157)
            self.assertEqual(second["added"], [])
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)

    def test_new_control_and_preview_audit_only_icpns_remain_present(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertTrue(self._baseline_new_icpns() <= set(rows))
        self.assertTrue(CONTROL_ICPNS <= set(rows))
        self.assertIn(PREVIEW_AUDIT_ONLY_ICPN, rows)
        self.assertEqual(rows[PREVIEW_AUDIT_ONLY_ICPN]["base_device"], "STM32F401CC")

    def test_production_manifest_retains_batch10_after_later_growth(self) -> None:
        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        sources = {source["family"]: source for source in manifest["sources"]}
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        payload = CANONICAL.read_bytes()
        current_sha = hashlib.sha256(payload).hexdigest()
        current_blob = hashlib.sha1(f"blob {len(payload)}".encode() + bytes([0]) + payload).hexdigest()
        self.assertTrue(self._baseline_new_icpns() <= {row["icpn"] for row in rows})
        self.assertGreaterEqual(len(rows), 158)
        self.assertEqual(sources["STM32F4"]["row_count"], len(rows))
        self.assertEqual(sources["STM32F4"]["sha256"], current_sha)
        self.assertEqual(sources["STM32F4"]["git_blob_sha"], current_blob)
        self.assertEqual(sum(source["row_count"] for source in sources.values()), 75 + len(rows))


if __name__ == "__main__":
    unittest.main()
