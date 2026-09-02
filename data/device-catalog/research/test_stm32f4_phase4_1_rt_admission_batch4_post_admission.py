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

from device_catalog_admission_framework import write_canonical_dataset
from device_catalog_pipeline_framework import pipeline_plan_is_clean
from stm32f4_admission import build_admission_plan
from stm32f4_coverage_gap_inventory import build_inventory
from validate_stm32f4_retained_evidence import validate_retained_evidence

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.1-rt-admission-batch4-live-2026-09-02"
BASELINE = HERE / "stm32f4-phase4.1-rt-admission-batch4-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
AUDIT = HERE / "stm32f4-phase4.1-rt-admission-batch4-admission-audit.json"
NEW_BASES = {"STM32F446RC", "STM32F446RE"}
EXPECTED_EVIDENCE_ID = "stm32f4-phase4.1-rt-admission-batch4-2026-09-02-retained-20260902T005937Z-f2c2198"
EXPECTED_PLAN_SHA256 = "05913c6bf5b1f35998208add33145ed0730a29d1be15480e1f527615b590f06c"
EXPECTED_CANONICAL_SHA256 = "8339390cdafe1aee25cac8f3e371a09fbc01d57a243ad66f012bcb205b322cac"
EXPECTED_CANONICAL_GIT_BLOB = "b6aaef8f8cafd0ad2d26b89dfc17c0f670bf8f77"
PRE_BATCH4_EVIDENCE_IDS = {
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
    "stm32f4-phase4.1-rt-admission-batch3-2026-09-01-retained-20260901T152600Z-1e04e9e",
}


def _evidence_id(row):
    marker = "#plasma-evidence="
    value = row.get("source_reference", "")
    return value.split(marker, 1)[1] if marker in value else ""


def _git_blob(path):
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


class Batch4PostAdmissionTests(unittest.TestCase):
    def _prewrite(self, output):
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if _evidence_id(row) in PRE_BATCH4_EVIDENCE_IDS]
        self.assertEqual(len(rows), 186)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_retained_evidence_and_audit(self):
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 3)
        self.assertEqual(report["exact_icpn_candidates"], 9)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        provenance = json.loads((EVIDENCE / "provenance.json").read_text())
        self.assertEqual(provenance["excluded_non_active_observations"], [])
        audit = json.loads(AUDIT.read_text())
        self.assertEqual(audit["evidence_id"], EXPECTED_EVIDENCE_ID)
        self.assertEqual(audit["evidence_artifact_id"], "9827190036")
        self.assertEqual(audit["proposal_workflow_run_id"], "33577825725")
        self.assertEqual(audit["proposal_artifact_id"], "9827276583")
        self.assertEqual(audit["pre_rows"], 186)
        self.assertEqual(audit["post_rows"], 194)
        self.assertEqual(audit["new_exact_icpns"], 8)
        self.assertEqual(audit["decision_counts"], {"admit": 8, "already_present": 0, "manual_review_required": 0, "reject": 0})
        self.assertEqual(audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(audit["final_csv_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(audit["final_git_blob_sha"], EXPECTED_CANONICAL_GIT_BLOB)
        self.assertEqual(audit["excluded_non_active"], [])

    def test_current_replan_is_already_present(self):
        plan = build_admission_plan(evidence_dir=EVIDENCE, baseline_path=BASELINE, catalog_path=CATALOG, canonical_path=CANONICAL, admission_base_devices=NEW_BASES)
        self.assertTrue(pipeline_plan_is_clean(plan))
        self.assertEqual(plan["decision_counts"], {"admit": 0, "already_present": 8, "manual_review_required": 0, "reject": 0})

    def test_historical_replay_186_to_194_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "stm32f4-commercial-icpn.csv"
            catalog = root / "openocd-parts-canonical.csv"
            evidence = root / EVIDENCE.name
            self._prewrite(canonical)
            catalog.write_bytes(CATALOG.read_bytes().replace(b"\r\n", b"\n"))
            shutil.copytree(EVIDENCE, evidence)
            plan = build_admission_plan(evidence_dir=evidence, baseline_path=BASELINE, catalog_path=catalog, canonical_path=canonical, admission_base_devices=NEW_BASES)
            serialized = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode()
            self.assertEqual(hashlib.sha256(serialized).hexdigest(), EXPECTED_PLAN_SHA256)
            result = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual((result["rows_before"], result["rows_after"], len(result["added"])), (186, 194, 8))
            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)
            self.assertEqual(_git_blob(canonical), EXPECTED_CANONICAL_GIT_BLOB)

    def test_current_manifest_and_inventory_are_growth_safe(self):
        payload = CANONICAL.read_bytes()
        current_sha = hashlib.sha256(payload).hexdigest()
        current_blob = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        bases = {r["base_device"] for r in rows}
        manifest = json.loads(PRODUCTION_MANIFEST.read_text())
        sources = {s["family"]: s for s in manifest["sources"]}
        f4 = sources["STM32F4"]
        self.assertEqual((f4["row_count"], f4["sha256"], f4["git_blob_sha"]), (len(rows), current_sha, current_blob))
        self.assertTrue(NEW_BASES <= bases)
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertFalse(inventory["algorithm_equivalence_claimed"])
        self.assertEqual(inventory["gap"]["base_device_count"], 149 - inventory["production"]["base_device_count"])
        ready = {x["base_device"] for x in inventory["gap"]["policy_ready"]}
        blocked = {x["base_device"] for x in inventory["gap"]["policy_blocked"]}
        self.assertTrue(NEW_BASES.isdisjoint(ready | blocked))


if __name__ == "__main__":
    unittest.main()
