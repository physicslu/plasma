#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from stm32f4_acquisition_pilot import read_manifest  # noqa: E402
from stm32f4_admission_policy import (  # noqa: E402
    TARGET_CONFIG,
    build_canonical_row,
    resolve_ordering_pattern_mapping,
)
from validate_stm32f4_retained_evidence import validate_retained_evidence  # noqa: E402

BASELINE = HERE / "stm32f4-phase4.0-foundation-batch11-baseline.json"
MANIFEST = HERE / "stm32f4-phase4.0-foundation-batch11-manifest.json"
EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch11-live-2026-09-01"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CONTROL_BASE = "STM32F479ZG"
NEW_BASE = "STM32F479ZI"
NEW_ICPN = "STM32F479ZIT6"
EXPECTED_EVIDENCE_ID = (
    "stm32f4-phase4.0-foundation-batch11-2026-09-01-"
    "retained-20260901T030509Z-4fb6652"
)
DISCOVERY_ZIP_SHA256 = "db546ac3dc9477fc02daaa9d0fb9114dbad436af5597c644dde5150536502950"


class STM32F4Phase40FoundationBatch11Tests(unittest.TestCase):
    def _baseline(self) -> dict[str, object]:
        return json.loads(BASELINE.read_text(encoding="utf-8"))

    def _catalog_rows(self) -> list[dict[str, str]]:
        with CATALOG.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _canonical_fields(self) -> list[str]:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle).fieldnames or [])

    def test_baseline_is_discovery_artifact_locked_and_denies_admission(self) -> None:
        baseline = self._baseline()
        self.assertEqual(
            baseline["pilot_id"],
            "stm32f4-phase4.0-foundation-batch11-2026-09-01",
        )
        self.assertFalse(baseline["canonical_dataset_admission"])
        self.assertEqual(baseline["source_workflow_run_id"], "33464522226")
        self.assertEqual(baseline["source_artifact_id"], "9784377080")
        self.assertEqual(baseline["source_artifact_sha256"], DISCOVERY_ZIP_SHA256)
        self.assertEqual(
            baseline["targets"],
            [
                {
                    "base_device": CONTROL_BASE,
                    "role": "lifecycle_control",
                    "marketing_status": "Active",
                    "exact_icpns": ["STM32F479ZGT6"],
                },
                {
                    "base_device": NEW_BASE,
                    "role": "candidate",
                    "marketing_status": "Active",
                    "exact_icpns": [NEW_ICPN],
                },
            ],
        )
        self.assertEqual(baseline["excluded_non_active_observations"], [])

    def test_manifest_matches_control_plus_sole_policy_ready_base_device(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(
            pilot_id,
            "stm32f4-phase4.0-foundation-batch11-2026-09-01",
        )
        self.assertEqual(
            [target.base_device for target in targets],
            [CONTROL_BASE, NEW_BASE],
        )

    def test_new_exact_icpn_has_unique_ordering_pattern_mapping(self) -> None:
        mapping = resolve_ordering_pattern_mapping(NEW_ICPN, self._catalog_rows())
        self.assertEqual(mapping["status"], "unique")
        self.assertEqual(mapping["match_count"], 1)
        self.assertEqual(mapping["identifier_kind"], "ordering_pattern")
        self.assertEqual(mapping["target_configs"], [TARGET_CONFIG])

    def test_existing_policy_builds_expected_batch11_row(self) -> None:
        candidate = {
            "manufacturer": "STMicroelectronics",
            "base_device": NEW_BASE,
            "icpn": NEW_ICPN,
            "authoritative_evidence": {
                "evidence_id": "phase4.0-foundation-batch11-policy-contract",
                "source_url": (
                    "https://www.st.com/en/microcontrollers-microprocessors/"
                    "stm32f479zi.html"
                ),
            },
            "base_mapping": resolve_ordering_pattern_mapping(
                NEW_ICPN,
                self._catalog_rows(),
            ),
        }
        row = build_canonical_row(candidate, self._canonical_fields())
        self.assertEqual(row["base_device"], NEW_BASE)
        self.assertEqual(row["package"], "LQFP")
        self.assertEqual(row["pin_count"], "144")
        self.assertEqual(row["flash_size"], "2048 KiB")

    def test_retained_evidence_is_offline_scale_ready_and_baseline_locked(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 2)
        self.assertEqual(report["exact_icpn_candidates"], 2)
        self.assertEqual(report["acquisition_success"], 2)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_retained_provenance_preserves_bounded_retry_and_source_binding(self) -> None:
        provenance = json.loads((EVIDENCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["evidence_id"], EXPECTED_EVIDENCE_ID)
        self.assertEqual(provenance["workflow_run_id"], "33464822120")
        self.assertEqual(
            provenance["locked_discovery_source"],
            {
                "workflow_run_id": "33464522226",
                "artifact_id": "9784377080",
                "artifact_sha256": DISCOVERY_ZIP_SHA256,
            },
        )
        self.assertEqual(provenance["live_acquisition_attempts"], 2)
        attempts = provenance["live_acquisition_attempt_outcomes"]
        self.assertEqual(len(attempts), 2)
        self.assertFalse(attempts[0]["clean"])
        self.assertEqual(attempts[0]["acquisition_success"], 1)
        self.assertEqual(attempts[0]["acquisition_failure"], 1)
        self.assertEqual(
            [failure["base_device"] for failure in attempts[0]["failed_targets"]],
            [NEW_BASE],
        )
        self.assertTrue(attempts[1]["clean"])
        self.assertEqual(attempts[1]["acquisition_success"], 2)
        self.assertEqual(attempts[1]["acquisition_failure"], 0)
        self.assertEqual(attempts[1]["failed_targets"], [])
        self.assertEqual(provenance["evaluator_result"], "scale_ready")
        self.assertEqual(provenance["excluded_non_active_observations"], [])


if __name__ == "__main__":
    unittest.main()
