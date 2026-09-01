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
from stm32f4_coverage_gap_inventory import build_inventory  # noqa: E402
from validate_stm32f4_retained_evidence import validate_retained_evidence  # noqa: E402

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch11-live-2026-09-01"
BASELINE = HERE / "stm32f4-phase4.0-foundation-batch11-baseline.json"
F446_BASELINE = HERE / "stm32f4-phase4.0-f446-batch1-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
AUDIT = HERE / "stm32f4-phase4.0-foundation-batch11-admission-audit.json"
NEW_BASES = {"STM32F479ZI"}
NEW_ICPN = "STM32F479ZIT6"
CONTROL_ICPN = "STM32F479ZGT6"
PREVIEW_AUDIT_ONLY_ICPN = "STM32F401CCF6TR"
EXPECTED_CANONICAL_SHA256 = "6a3150e356511dfed679b747515d1ae1380d3da101b11edd3322f27cd936c948"
EXPECTED_PREWRITE_PLAN_SHA256 = "2c024e80102919ff9be2213d48809c0dde07d8a8e5d7ad7dbdd83fab54f433fe"
EXPECTED_CANONICAL_GIT_BLOB = "21ad3fee8b780949e8184cdb56b5601fe6a48c03"
EXPECTED_EVIDENCE_ID = (
    "stm32f4-phase4.0-foundation-batch11-2026-09-01-"
    "retained-20260901T030509Z-4fb6652"
)


def _row_evidence_id(row: dict[str, str]) -> str:
    marker = "#plasma-evidence="
    reference = row.get("source_reference", "")
    return reference.split(marker, 1)[1] if marker in reference else ""


class STM32F4Phase40FoundationBatch11PostAdmissionTests(unittest.TestCase):
    def _prewrite_canonical(self, output: Path) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if _row_evidence_id(row) != EXPECTED_EVIDENCE_ID]
        self.assertEqual(len(rows), 157)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def _catalog_rows(self) -> dict[str, dict[str, str]]:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return {row["icpn"]: row for row in csv.DictReader(handle)}

    def test_admission_audit_binds_read_only_proposal(self) -> None:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["pre_rows"], 157)
        self.assertEqual(audit["new_exact_icpns"], 1)
        self.assertEqual(audit["post_rows"], 158)
        self.assertEqual(
            audit["decision_counts"],
            {"admit": 1, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(audit["added"], [NEW_ICPN])
        self.assertEqual(audit["admission_plan_sha256"], EXPECTED_PREWRITE_PLAN_SHA256)
        self.assertEqual(audit["final_csv_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(audit["final_git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(audit["proposal_workflow_run_id"], "33465207580")
        self.assertEqual(audit["proposal_artifact_id"], "9784588327")
        self.assertEqual(
            audit["proposal_zip_sha256"],
            "906ae4219072b29b5f83b40c3e8f587e948758cbfbc4a0e681adb3001993e92f",
        )
        self.assertTrue(audit["canonical_dataset_written"])

    def test_retained_evidence_is_scale_ready_and_preserves_bounded_retry(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 2)
        self.assertEqual(report["exact_icpn_candidates"], 2)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])
        provenance = json.loads((EVIDENCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["live_acquisition_attempts"], 2)
        self.assertFalse(provenance["live_acquisition_attempt_outcomes"][0]["clean"])
        self.assertTrue(provenance["live_acquisition_attempt_outcomes"][1]["clean"])
        self.assertEqual(provenance["excluded_non_active_observations"], [])

    def test_current_state_replans_batch11_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 1)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 0, "already_present": 1, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_materialization_replays_157_to_158_and_matches_immutable_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "stm32f4-commercial-icpn.csv"
            normalized_catalog = root / "openocd-parts-canonical.csv"
            named_evidence = root / EVIDENCE.name
            self._prewrite_canonical(canonical)
            normalized_catalog.write_bytes(CATALOG.read_bytes().replace(b"\r\n", b"\n"))
            shutil.copytree(EVIDENCE, named_evidence)
            plan = build_admission_plan(
                evidence_dir=named_evidence,
                baseline_path=BASELINE,
                catalog_path=normalized_catalog,
                canonical_path=canonical,
                admission_base_devices=NEW_BASES,
            )
            serialized = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode("utf-8")
            self.assertEqual(hashlib.sha256(serialized).hexdigest(), EXPECTED_PREWRITE_PLAN_SHA256)
            self.assertEqual(plan["canonical_rows_before"], 157)
            self.assertEqual(plan["candidate_count"], 1)
            self.assertEqual(plan["decision_counts"]["admit"], 1)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 157)
            self.assertEqual(first["rows_after"], 158)
            self.assertEqual(first["added"], [NEW_ICPN])

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 158)
            self.assertEqual(second["rows_after"], 158)
            self.assertEqual(second["added"], [])
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)

    def test_preview_lifecycle_drift_is_audit_only_and_does_not_de_admit(self) -> None:
        f446_baseline = json.loads(F446_BASELINE.read_text(encoding="utf-8"))
        preview = next(
            item
            for item in f446_baseline["excluded_non_active_observations"]
            if item["icpn"] == PREVIEW_AUDIT_ONLY_ICPN
        )
        self.assertEqual(preview["marketing_status"], "Preview")
        self.assertFalse(preview["admission"])
        self.assertIn("pending explicit de-admission policy", preview["lifecycle_note"])

        rows = self._catalog_rows()
        self.assertIn(PREVIEW_AUDIT_ONLY_ICPN, rows)
        self.assertEqual(rows[PREVIEW_AUDIT_ONLY_ICPN]["base_device"], "STM32F401CC")
        self.assertIn(CONTROL_ICPN, rows)
        self.assertIn(NEW_ICPN, rows)
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["added"], [NEW_ICPN])

    def test_production_manifest_binds_158_f4_rows_and_233_total_rows(self) -> None:
        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        sources = {source["family"]: source for source in manifest["sources"]}
        self.assertEqual(sources["STM32F4"]["row_count"], 158)
        self.assertEqual(sources["STM32F4"]["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(sources["STM32F4"]["git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(sum(source["row_count"] for source in sources.values()), 233)

    def test_phase41_rt_policy_preserves_batch11_production_and_unlocks_only_rt(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertFalse(inventory["algorithm_equivalence_claimed"])
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["production"]["base_device_count"], 56)
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 158)
        self.assertEqual(inventory["gap"]["base_device_count"], 93)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 11)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 82)
        self.assertEqual(
            {item["base_device"] for item in inventory["gap"]["policy_ready"]},
            {
                "STM32F401RB",
                "STM32F401RC",
                "STM32F401RD",
                "STM32F401RE",
                "STM32F405RG",
                "STM32F411RC",
                "STM32F411RE",
                "STM32F413RG",
                "STM32F415RG",
                "STM32F446RC",
                "STM32F446RE",
            },
        )


if __name__ == "__main__":
    unittest.main()
