#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import file_sha256, read_json
from stm32f7_phase4_6c_policy import (
    DEFAULT_POLICY_BASELINE,
    DEFAULT_PRODUCTION_MANIFEST,
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    EXPECTED_PRODUCTION_FAMILY_COUNTS,
    STM32F7PolicyError,
    build_policy_plan,
    policy_plan_is_clean,
    policy_summary,
    production_snapshot,
    validate_policy,
)

EXPECTED_PRODUCTION_PRESTATE_SHA256 = "a13f9eac404261bff406fe3d2a6922cf4fe07345563fb0f18b08a6670f598fe2"
EXPECTED_DISCOVERY_BASELINE_SHA256 = "6e93a1b2ef0a91396bed08f6f3e6e87a427537bc6eb7b4bde5385e8191696e14"
EXPECTED_RETAINED_MANIFEST_SHA256 = "b45459347eaaaf16409f6ca12c75aa99696dbdacec260a387708a96725c0c9ca"
EXPECTED_ICPNS = {
    "STM32F722ICK6", "STM32F722ICT6",
    "STM32F723ICK6", "STM32F723ICT6",
    "STM32F730I8K6", "STM32F730I8K6TR",
    "STM32F732IEK6", "STM32F732IET6",
    "STM32F733IEK6", "STM32F733IET6",
    "STM32F745IEK6", "STM32F745IEK6TR", "STM32F745IEK7",
    "STM32F745IEK7TR", "STM32F745IET6", "STM32F745IET7",
    "STM32F750N8H6", "STM32F778AIY6TR", "STM32F779AIY6TR",
}


class STM32F7Phase46CPolicyPlanTests(unittest.TestCase):
    def test_frozen_production_prestate_is_exact_544_state(self) -> None:
        self.assertEqual(file_sha256(DEFAULT_PRODUCTION_MANIFEST), EXPECTED_PRODUCTION_PRESTATE_SHA256)
        snapshot = production_snapshot()
        self.assertEqual(snapshot["exact_icpn_count"], EXPECTED_PRODUCTION_EXACT_COUNT)
        self.assertEqual(snapshot["base_device_count"], EXPECTED_PRODUCTION_BASE_DEVICE_COUNT)
        self.assertEqual(snapshot["family_exact_icpn_counts"], EXPECTED_PRODUCTION_FAMILY_COUNTS)
        self.assertEqual(snapshot["stm32f7_exact_icpn_count"], 0)

    def test_policy_plan_is_clean_and_admission_is_still_deferred(self) -> None:
        plan = build_policy_plan()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 19)
        self.assertEqual(plan["decision_counts"], {
            "metadata_ready": 19,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["issues"], [])
        self.assertEqual(plan["canonical_dataset_admission"], "deferred")
        self.assertFalse(plan["production_write_applied"])
        self.assertTrue(plan["exact_icpn_admission_deferred"])
        self.assertFalse(plan["openocd_routing_gate_applied"])
        self.assertTrue(plan["capability_mapping_deferred"])
        self.assertFalse(plan["runtime_support_claimed"])

    def test_policy_baseline_is_exact_deterministic_replay(self) -> None:
        plan, summary = validate_policy()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(summary, read_json(DEFAULT_POLICY_BASELINE))
        self.assertEqual(set(summary["policy_ready_exact_icpns"]), EXPECTED_ICPNS)
        self.assertEqual(summary["retained_discovery_baseline_sha256"], EXPECTED_DISCOVERY_BASELINE_SHA256)
        self.assertEqual(summary["retained_evidence_manifest_sha256"], EXPECTED_RETAINED_MANIFEST_SHA256)
        self.assertEqual(summary["production_manifest_sha256"], EXPECTED_PRODUCTION_PRESTATE_SHA256)

    def test_metadata_distribution_is_frozen_in_policy_baseline(self) -> None:
        baseline = read_json(DEFAULT_POLICY_BASELINE)
        self.assertEqual(baseline["metadata_distribution"], {
            "flash_size": {"2048 KiB": 2, "256 KiB": 4, "512 KiB": 10, "64 KiB": 3},
            "option_suffix": {"": 14, "TR": 5},
            "package": {"LQFP": 6, "TFBGA": 1, "UFBGA": 10, "WLCSP": 2},
            "pin_count": {"176": 16, "180": 2, "216": 1},
            "temperature_grade": {"-40 to 105 C": 3, "-40 to 85 C": 16},
        })
        self.assertFalse(baseline["metadata_contract"]["f750_generalized_decode_allowed"])
        self.assertFalse(baseline["metadata_contract"]["openocd_routing_gates_metadata"])
        self.assertEqual(baseline["metadata_contract"]["capability_mapping_deferred_to"], "4.6D")

    def test_frozen_prestate_rejects_f7_publication_or_count_mutation(self) -> None:
        manifest = read_json(DEFAULT_PRODUCTION_MANIFEST)
        mutated = json.loads(json.dumps(manifest))
        mutated["sources"].append({
            "manufacturer": "STMicroelectronics",
            "family": "STM32F7",
            "path": "../research/stm32f7-commercial-icpn.csv",
            "row_count": 19,
            "git_blob_sha": "0" * 40,
            "sha256": "0" * 64,
        })
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "prestate.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            with self.assertRaises(STM32F7PolicyError):
                production_snapshot(path)

    def test_baseline_drift_fails_closed(self) -> None:
        baseline = read_json(DEFAULT_POLICY_BASELINE)
        baseline["metadata_rows"][0]["flash_size"] = "512 KiB"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "baseline.json"
            path.write_text(json.dumps(baseline), encoding="utf-8")
            with self.assertRaises(STM32F7PolicyError):
                validate_policy(path)

    def test_summary_contains_no_production_or_runtime_authorization(self) -> None:
        summary = policy_summary(build_policy_plan())
        self.assertFalse(summary["production_write_applied"])
        self.assertTrue(summary["exact_icpn_admission_deferred"])
        self.assertFalse(summary["openocd_routing_gate_applied"])
        self.assertTrue(summary["capability_mapping_deferred"])
        self.assertFalse(summary["programming_algorithm_equivalence_claimed"])
        self.assertFalse(summary["runtime_support_claimed"])
        self.assertFalse(summary["full_stm32f7_surface_covered"])
        self.assertTrue(summary["fail_closed"])


if __name__ == "__main__":
    unittest.main()
