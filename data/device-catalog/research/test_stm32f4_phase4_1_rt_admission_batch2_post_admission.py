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

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.1-rt-admission-batch2-live-2026-09-01"
BASELINE = HERE / "stm32f4-phase4.1-rt-admission-batch2-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
AUDIT = HERE / "stm32f4-phase4.1-rt-admission-batch2-admission-audit.json"
NEW_BASES = {"STM32F401RB", "STM32F401RC", "STM32F401RD", "STM32F401RE", "STM32F405RG"}
EXPECTED_EVIDENCE_ID = "stm32f4-phase4.1-rt-admission-batch2-2026-09-01-retained-20260901T125059Z-4e0435d"
EXPECTED_PLAN_SHA256 = "6f5344b46564f38a7d5b7eadd64ecaeff8d0807209005253f7b79985f7dd7c9e"
EXPECTED_CANONICAL_SHA256 = "6d096c2129a2a3f520c049c0eaab1749cec05f163a773be7db10ec82472c8e58"
EXPECTED_CANONICAL_GIT_BLOB = "614e81313b69c27d8306b22df68a5a20b031e20d"
NRND_AUDIT_ONLY = {"STM32F405RGT6V", "STM32F405RGT6W"}


def _evidence_id(row: dict[str, str]) -> str:
    marker = "#plasma-evidence="
    value = row.get("source_reference", "")
    return value.split(marker, 1)[1] if marker in value else ""


def _git_blob(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


class STM32F4Phase41RTBatch2PostAdmissionTests(unittest.TestCase):
    def _prewrite_canonical(self, output: Path) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if _evidence_id(row) != EXPECTED_EVIDENCE_ID]
        self.assertEqual(len(rows), 158)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_retained_evidence_is_scale_ready_and_lifecycle_safe(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 6)
        self.assertEqual(report["exact_icpn_candidates"], 18)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])
        provenance = json.loads((EVIDENCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["live_acquisition_attempts"], 1)
        self.assertTrue(provenance["live_acquisition_attempt_outcomes"][0]["clean"])
        self.assertEqual(
            {item["icpn"] for item in provenance["excluded_non_active_observations"]},
            NRND_AUDIT_ONLY,
        )

    def test_admission_audit_binds_immutable_transaction(self) -> None:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["evidence_id"], EXPECTED_EVIDENCE_ID)
        self.assertEqual(audit["pre_rows"], 158)
        self.assertEqual(audit["post_rows"], 175)
        self.assertEqual(audit["new_exact_icpns"], 17)
        self.assertEqual(
            audit["decision_counts"],
            {"admit": 17, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(audit["conflicts"], 0)
        self.assertEqual(audit["issues"], [])
        self.assertEqual(audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(audit["proposal_workflow_run_id"], "33510466747")
        self.assertEqual(audit["proposal_artifact_id"], "9801403104")
        self.assertEqual(
            audit["proposal_zip_sha256"],
            "3f0ad3b5c9437cf51fb41ba06b532fd2c54bd896dc776de9d18e927d080e727b",
        )
        self.assertEqual(audit["final_csv_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(audit["final_git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertTrue(audit["canonical_dataset_written"])
        self.assertEqual(len(audit["added"]), 17)
        self.assertTrue(all(icpn.startswith(tuple(NEW_BASES)) for icpn in audit["added"]))

    def test_current_state_replans_all_17_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 17)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 0, "already_present": 17, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_historical_materialization_replays_158_to_175_byte_identically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "stm32f4-commercial-icpn.csv"
            catalog = root / "openocd-parts-canonical.csv"
            evidence = root / EVIDENCE.name
            self._prewrite_canonical(canonical)
            catalog.write_bytes(CATALOG.read_bytes().replace(b"\r\n", b"\n"))
            shutil.copytree(EVIDENCE, evidence)
            plan = build_admission_plan(
                evidence_dir=evidence,
                baseline_path=BASELINE,
                catalog_path=catalog,
                canonical_path=canonical,
                admission_base_devices=NEW_BASES,
            )
            serialized = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode("utf-8")
            self.assertEqual(hashlib.sha256(serialized).hexdigest(), EXPECTED_PLAN_SHA256)
            self.assertEqual(plan["canonical_rows_before"], 158)
            self.assertEqual(plan["decision_counts"]["admit"], 17)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 158)
            self.assertEqual(first["rows_after"], 175)
            self.assertEqual(len(first["added"]), 17)
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)
            self.assertEqual(_git_blob(canonical), EXPECTED_CANONICAL_GIT_BLOB)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 175)
            self.assertEqual(second["rows_after"], 175)
            self.assertEqual(second["added"], [])

    def test_production_manifest_and_remaining_rt_inventory(self) -> None:
        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        sources = {source["family"]: source for source in manifest["sources"]}
        f4 = sources["STM32F4"]
        self.assertEqual(f4["row_count"], 175)
        self.assertEqual(f4["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(f4["git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(sum(source["row_count"] for source in sources.values()), 250)

        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertFalse(inventory["algorithm_equivalence_claimed"])
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["production"]["base_device_count"], 61)
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 175)
        self.assertEqual(inventory["gap"]["base_device_count"], 88)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 6)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 82)
        self.assertEqual(
            {item["base_device"] for item in inventory["gap"]["policy_ready"]},
            {"STM32F411RC", "STM32F411RE", "STM32F413RG", "STM32F415RG", "STM32F446RC", "STM32F446RE"},
        )

    def test_nrnd_observations_remain_audit_only(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            icpns = {row["icpn"] for row in csv.DictReader(handle)}
        self.assertTrue(NRND_AUDIT_ONLY.isdisjoint(icpns))


if __name__ == "__main__":
    unittest.main()
