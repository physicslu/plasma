#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import file_sha256, read_json
from stm32g0_phase4_8c_policy import (
    DEFAULT_POLICY_BASELINE,
    DEFAULT_PRODUCTION_MANIFEST,
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    EXPECTED_PRODUCTION_FAMILY_COUNTS,
    STM32G0PolicyError,
    build_policy_plan,
    policy_plan_is_clean,
    policy_summary,
    production_snapshot,
)

EXPECTED_POLICY_BASELINE_SHA256 = "953df55b097ad58c93738e2aeecc7c762cb464f882493bf622fefbb61fc3a787"
EXPECTED_PRODUCTION_PRESTATE_SHA256 = "4b05b3e3e7cb8e9b8cc426f9358d758f04d5bc4944b23e44ee0cad1d3bea1cd3"
EXPECTED_DISCOVERY_BASELINE_SHA256 = "ef059c3226b506aa0ff739abf8c6bf3e0f525ceaefb571693458dad6b706f10a"
EXPECTED_RETAINED_MANIFEST_SHA256 = "ff90c6ab4b3adb8bf9c87d5b0321ec3b29eab32f9854b38e566c09d7ffb39469"
EXPECTED_N_ICPNS = {"STM32G0B1CBT6N", "STM32G0B1CBU6N"}


class STM32G0Phase48CPolicyPlanTests(unittest.TestCase):
    def test_frozen_production_prestate_is_exact_563_state(self) -> None:
        self.assertEqual(file_sha256(DEFAULT_PRODUCTION_MANIFEST), EXPECTED_PRODUCTION_PRESTATE_SHA256)
        snapshot = production_snapshot()
        self.assertEqual(snapshot["exact_icpn_count"], EXPECTED_PRODUCTION_EXACT_COUNT)
        self.assertEqual(snapshot["base_device_count"], EXPECTED_PRODUCTION_BASE_DEVICE_COUNT)
        self.assertEqual(snapshot["family_exact_icpn_counts"], EXPECTED_PRODUCTION_FAMILY_COUNTS)
        self.assertEqual(snapshot["stm32g0_exact_icpn_count"], 0)

    def test_policy_plan_is_clean_and_admission_remains_deferred(self) -> None:
        plan = build_policy_plan()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 49)
        self.assertEqual(plan["decision_counts"], {
            "metadata_ready": 49, "manual_review_required": 0, "reject": 0,
        })
        self.assertEqual(plan["issues"], [])
        self.assertEqual(plan["canonical_dataset_admission"], "deferred")
        self.assertFalse(plan["production_write_applied"])
        self.assertTrue(plan["exact_icpn_admission_deferred"])
        self.assertFalse(plan["openocd_routing_gate_applied"])
        self.assertFalse(plan["cmsis_alias_gate_applied"])
        self.assertTrue(plan["capability_mapping_deferred"])
        self.assertFalse(plan["runtime_support_claimed"])

    def test_policy_baseline_is_byte_locked_and_exact_deterministic_replay(self) -> None:
        self.assertEqual(file_sha256(DEFAULT_POLICY_BASELINE), EXPECTED_POLICY_BASELINE_SHA256)
        plan = build_policy_plan()
        summary = policy_summary(plan)
        baseline = read_json(DEFAULT_POLICY_BASELINE)
        self.assertEqual(summary, baseline)
        self.assertEqual(summary["retained_discovery_baseline_sha256"], EXPECTED_DISCOVERY_BASELINE_SHA256)
        self.assertEqual(summary["retained_evidence_manifest_sha256"], EXPECTED_RETAINED_MANIFEST_SHA256)
        self.assertEqual(summary["production_manifest_sha256"], EXPECTED_PRODUCTION_PRESTATE_SHA256)
        self.assertEqual(len(summary["policy_ready_exact_icpns"]), 49)
        self.assertTrue(EXPECTED_N_ICPNS.issubset(set(summary["policy_ready_exact_icpns"])))

    def test_metadata_distribution_and_n_semantics_are_frozen(self) -> None:
        baseline = read_json(DEFAULT_POLICY_BASELINE)
        self.assertEqual(baseline["metadata_distribution"], {
            "flash_size": {
                "128 KiB": 21, "16 KiB": 2, "256 KiB": 2,
                "32 KiB": 11, "512 KiB": 2, "64 KiB": 11,
            },
            "option_suffix": {"": 27, "N": 2, "TR": 20},
            "package": {"LQFP": 26, "UFQFPN": 23},
            "pin_count": {"48": 49},
            "temperature_grade": {"-40 to 105 C": 8, "-40 to 125 C": 12, "-40 to 85 C": 29},
        })
        contract = baseline["metadata_contract"]
        self.assertTrue(contract["n_product_version_preserved"])
        self.assertFalse(contract["openocd_routing_gates_metadata"])
        self.assertFalse(contract["cmsis_alias_gates_metadata"])
        self.assertFalse(contract["production_write_authorized"])
        self.assertEqual(contract["capability_mapping_deferred_to"], "4.8D")

    def test_frozen_prestate_rejects_g0_publication(self) -> None:
        manifest = read_json(DEFAULT_PRODUCTION_MANIFEST)
        mutated = json.loads(json.dumps(manifest))
        mutated["sources"].append({
            "manufacturer": "STMicroelectronics", "family": "STM32G0",
            "path": "../research/stm32g0-commercial-icpn.csv", "row_count": 49,
            "git_blob_sha": "0" * 40, "sha256": "0" * 64,
        })
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json",
            prefix="stm32g0-phase4.8c-mutated-prestate-",
            dir=DEFAULT_PRODUCTION_MANIFEST.parent, delete=False,
        ) as handle:
            json.dump(mutated, handle)
            path = Path(handle.name)
        try:
            with self.assertRaises(STM32G0PolicyError):
                production_snapshot(path)
        finally:
            path.unlink(missing_ok=True)

    def test_summary_contains_no_production_programming_or_runtime_authorization(self) -> None:
        summary = policy_summary(build_policy_plan())
        self.assertFalse(summary["production_write_applied"])
        self.assertTrue(summary["exact_icpn_admission_deferred"])
        self.assertFalse(summary["openocd_routing_gate_applied"])
        self.assertFalse(summary["cmsis_alias_gate_applied"])
        self.assertTrue(summary["capability_mapping_deferred"])
        self.assertFalse(summary["programming_algorithm_equivalence_claimed"])
        self.assertFalse(summary["runtime_support_claimed"])
        self.assertFalse(summary["full_stm32g0_surface_covered"])
        self.assertTrue(summary["fail_closed"])


if __name__ == "__main__":
    unittest.main()
