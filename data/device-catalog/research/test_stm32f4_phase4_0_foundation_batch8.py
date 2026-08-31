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

BASELINE = HERE / "stm32f4-phase4.0-foundation-batch8-baseline.json"
MANIFEST = HERE / "stm32f4-phase4.0-foundation-batch8-manifest.json"
EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch8-live-2026-08-31"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CONTROL_BASE = "STM32F417VG"
NEW_BASES = {"STM32F417VE", "STM32F417ZE"}
EXPECTED_NEW_ICPNS = 3
EXPECTED_EVIDENCE_ID = "stm32f4-phase4.0-foundation-batch8-2026-08-31-retained-20260831T121653Z-5299281"


class STM32F4Phase40FoundationBatch8Tests(unittest.TestCase):
    def _baseline(self) -> dict[str, object]:
        return json.loads(BASELINE.read_text(encoding="utf-8"))

    def _catalog_rows(self) -> list[dict[str, str]]:
        with CATALOG.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _canonical_fields(self) -> list[str]:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle).fieldnames or [])

    def test_baseline_is_discovery_locked_active_only_and_denies_admission(self) -> None:
        baseline = self._baseline()
        self.assertEqual(
            baseline["pilot_id"],
            "stm32f4-phase4.0-foundation-batch8-2026-08-31",
        )
        self.assertFalse(baseline["canonical_dataset_admission"])
        self.assertEqual(baseline["source_workflow_run_id"], "33390363041")
        self.assertEqual(baseline["source_artifact_id"], "9757212311")
        targets = baseline["targets"]
        self.assertEqual(
            {target["base_device"] for target in targets},
            {CONTROL_BASE, *NEW_BASES},
        )
        new_icpns = [
            icpn
            for target in targets
            if target["base_device"] in NEW_BASES
            for icpn in target["exact_icpns"]
        ]
        self.assertEqual(len(new_icpns), EXPECTED_NEW_ICPNS)
        self.assertEqual(len(set(new_icpns)), EXPECTED_NEW_ICPNS)
        self.assertEqual(baseline["excluded_non_active_observations"], [])

    def test_manifest_matches_control_plus_two_new_base_devices(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(
            pilot_id,
            "stm32f4-phase4.0-foundation-batch8-2026-08-31",
        )
        self.assertEqual(len(targets), 3)
        self.assertEqual(
            {target.base_device for target in targets},
            {CONTROL_BASE, *NEW_BASES},
        )

    def test_all_3_new_exact_icpns_have_unique_ordering_pattern_mapping(self) -> None:
        catalog_rows = self._catalog_rows()
        failures: list[str] = []
        mapped = 0
        for target in self._baseline()["targets"]:
            if target["base_device"] not in NEW_BASES:
                continue
            for icpn in target["exact_icpns"]:
                mapping = resolve_ordering_pattern_mapping(icpn, catalog_rows)
                if (
                    mapping.get("status") != "unique"
                    or mapping.get("match_count") != 1
                    or mapping.get("identifier_kind") != "ordering_pattern"
                    or mapping.get("target_configs") != [TARGET_CONFIG]
                ):
                    failures.append(f"{icpn}: {mapping}")
                else:
                    mapped += 1
        self.assertEqual(failures, [], "\n" + "\n".join(failures))
        self.assertEqual(mapped, EXPECTED_NEW_ICPNS)

    def test_existing_policy_builds_expected_batch8_rows(self) -> None:
        catalog_rows = self._catalog_rows()
        fields = self._canonical_fields()
        cases = {
            "STM32F417VET6": ("STM32F417VE", "LQFP", "100", "512 KiB"),
            "STM32F417VET6TR": ("STM32F417VE", "LQFP", "100", "512 KiB"),
            "STM32F417ZET6": ("STM32F417ZE", "LQFP", "144", "512 KiB"),
        }
        for icpn, (base, package, pins, flash) in cases.items():
            with self.subTest(icpn=icpn):
                candidate = {
                    "manufacturer": "STMicroelectronics",
                    "base_device": base,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": "phase4.0-foundation-batch8-policy-contract",
                        "source_url": (
                            "https://www.st.com/en/microcontrollers-microprocessors/"
                            f"{base.lower()}.html"
                        ),
                    },
                    "base_mapping": resolve_ordering_pattern_mapping(icpn, catalog_rows),
                }
                row = build_canonical_row(candidate, fields)
                self.assertEqual(row["package"], package)
                self.assertEqual(row["pin_count"], pins)
                self.assertEqual(row["flash_size"], flash)

    def test_retained_evidence_is_offline_scale_ready_and_baseline_locked(self) -> None:
        report = validate_retained_evidence(EVIDENCE, baseline_path=BASELINE)
        self.assertEqual(report["targets"], 3)
        self.assertEqual(report["exact_icpn_candidates"], 6)
        self.assertEqual(report["acquisition_success"], 3)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_retained_provenance_preserves_clean_first_attempt_and_empty_lifecycle_audit(self) -> None:
        provenance = json.loads((EVIDENCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["evidence_id"], EXPECTED_EVIDENCE_ID)
        self.assertEqual(provenance["live_acquisition_attempts"], 1)
        attempts = provenance["live_acquisition_attempt_outcomes"]
        self.assertEqual(len(attempts), 1)
        self.assertTrue(attempts[0]["clean"])
        self.assertEqual(attempts[0]["acquisition_success"], 3)
        self.assertEqual(attempts[0]["acquisition_failure"], 0)
        self.assertEqual(attempts[0]["failed_targets"], [])
        self.assertEqual(provenance["evaluator_result"], "scale_ready")
        self.assertEqual(provenance["excluded_non_active_observations"], [])


if __name__ == "__main__":
    unittest.main()
