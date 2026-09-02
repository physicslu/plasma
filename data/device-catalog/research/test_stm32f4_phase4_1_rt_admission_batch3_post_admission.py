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

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.1-rt-admission-batch3-live-2026-09-01"
BASELINE = HERE / "stm32f4-phase4.1-rt-admission-batch3-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
AUDIT = HERE / "stm32f4-phase4.1-rt-admission-batch3-admission-audit.json"
NEW_BASES = {"STM32F411RC", "STM32F411RE", "STM32F413RG", "STM32F415RG"}
EXPECTED_EVIDENCE_ID = "stm32f4-phase4.1-rt-admission-batch3-2026-09-01-retained-20260901T152600Z-1e04e9e"
EXPECTED_PLAN_SHA256 = "e7f8092c8eab3f446a845d474b6c272d80d48066597e9f0406a11415a817b8af"
EXPECTED_CANONICAL_SHA256 = "c9f7709994c4894f335c9c07264149ffa25b1cbe11343eb667ec41dbc84be6d8"
EXPECTED_CANONICAL_GIT_BLOB = "02af1f1557b2f2c1bb5429edeb09837111225d73"
PROPOSAL_AUDIT_ONLY = {"STM32F413RGT3"}

PRE_BATCH3_EVIDENCE_IDS = {
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
    "stm32f4-phase4.0-foundation-batch10-2026-09-01-retained-20260901T015746Z-6ecf759",
    "stm32f4-phase4.0-foundation-batch11-2026-09-01-retained-20260901T030509Z-4fb6652",
    "stm32f4-phase4.1-rt-admission-batch2-2026-09-01-retained-20260901T125059Z-4e0435d",
}


def _evidence_id(row: dict[str, str]) -> str:
    marker = "#plasma-evidence="
    value = row.get("source_reference", "")
    return value.split(marker, 1)[1] if marker in value else ""


def _git_blob(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


class STM32F4Phase41RTBatch3PostAdmissionTests(unittest.TestCase):
    def _prewrite_canonical(self, output: Path) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if _evidence_id(row) in PRE_BATCH3_EVIDENCE_IDS]
        self.assertEqual(len(rows), 175)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_retained_evidence_is_scale_ready_and_lifecycle_safe(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 5)
        self.assertEqual(report["exact_icpn_candidates"], 12)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])
        provenance = json.loads((EVIDENCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["live_acquisition_attempts"], 1)
        self.assertTrue(provenance["live_acquisition_attempt_outcomes"][0]["clean"])
        self.assertEqual(
            {item["icpn"] for item in provenance["excluded_non_active_observations"]},
            PROPOSAL_AUDIT_ONLY,
        )

    def test_admission_audit_binds_immutable_transaction(self) -> None:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["evidence_id"], EXPECTED_EVIDENCE_ID)
        self.assertEqual(audit["evidence_artifact_id"], "9807572561")
        self.assertEqual(
            audit["evidence_zip_sha256"],
            "2c2629936db0b6fe3104f6757c2599d6c65554644070cdd8b757621c936702fb",
        )
        self.assertEqual(audit["pre_rows"], 175)
        self.assertEqual(audit["post_rows"], 186)
        self.assertEqual(audit["new_exact_icpns"], 11)
        self.assertEqual(
            audit["decision_counts"],
            {"admit": 11, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(audit["conflicts"], 0)
        self.assertEqual(audit["issues"], [])
        self.assertEqual(audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(audit["proposal_workflow_run_id"], "33526423227")
        self.assertEqual(audit["proposal_artifact_id"], "9807861106")
        self.assertEqual(
            audit["proposal_zip_sha256"],
            "d696a30a06ecdc9d43aa65214df485f00f91dabb19b666de1ae6e42e980bbdd2",
        )
        self.assertEqual(audit["final_csv_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(audit["final_git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(set(audit["excluded_non_active"]), PROPOSAL_AUDIT_ONLY)
        self.assertTrue(audit["canonical_dataset_written"])
        self.assertEqual(len(audit["added"]), 11)
        self.assertTrue(all(icpn.startswith(tuple(NEW_BASES)) for icpn in audit["added"]))

    def test_current_state_replans_all_11_as_already_present(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            baseline_path=BASELINE,
            catalog_path=CATALOG,
            canonical_path=CANONICAL,
            admission_base_devices=NEW_BASES,
        )
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 11)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 0, "already_present": 11, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["conflicts"], 0)
        self.assertEqual(plan["issues"], [])

    def test_historical_materialization_replays_175_to_186_byte_identically(self) -> None:
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
            self.assertEqual(plan["canonical_rows_before"], 175)
            self.assertEqual(plan["decision_counts"]["admit"], 11)
            self.assertTrue(pipeline_plan_is_clean(plan))

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 175)
            self.assertEqual(first["rows_after"], 186)
            self.assertEqual(len(first["added"]), 11)
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)
            self.assertEqual(_git_blob(canonical), EXPECTED_CANONICAL_GIT_BLOB)

            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(second["rows_before"], 186)
            self.assertEqual(second["rows_after"], 186)
            self.assertEqual(second["added"], [])

    def test_current_manifest_and_inventory_remain_consistent_after_later_growth(self) -> None:
        payload = CANONICAL.read_bytes()
        current_sha = hashlib.sha256(payload).hexdigest()
        current_blob = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        production_bases = {row["base_device"] for row in rows}

        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        sources = {source["family"]: source for source in manifest["sources"]}
        f4 = sources["STM32F4"]
        self.assertEqual(f4["row_count"], len(rows))
        self.assertEqual(f4["sha256"], current_sha)
        self.assertEqual(f4["git_blob_sha"], current_blob)
        self.assertEqual(sum(source["row_count"] for source in sources.values()), 75 + len(rows))
        self.assertTrue(NEW_BASES <= production_bases)

        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertFalse(inventory["algorithm_equivalence_claimed"])
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["production"]["exact_icpn_rows"], len(rows))
        self.assertEqual(inventory["production"]["base_device_count"], len(production_bases))
        self.assertEqual(
            inventory["gap"]["base_device_count"],
            149 - inventory["production"]["base_device_count"],
        )
        self.assertEqual(
            inventory["gap"]["base_device_count"],
            inventory["gap"]["policy_ready_count"] + inventory["gap"]["policy_blocked_count"],
        )
        ready = {item["base_device"] for item in inventory["gap"]["policy_ready"]}
        blocked = {item["base_device"] for item in inventory["gap"]["policy_blocked"]}
        self.assertTrue(NEW_BASES.isdisjoint(ready))
        self.assertTrue(NEW_BASES.isdisjoint(blocked))

    def test_proposal_observation_remains_audit_only(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            icpns = {row["icpn"] for row in csv.DictReader(handle)}
        self.assertTrue(PROPOSAL_AUDIT_ONLY.isdisjoint(icpns))


if __name__ == "__main__":
    unittest.main()
