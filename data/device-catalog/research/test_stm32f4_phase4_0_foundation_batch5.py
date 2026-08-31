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

BASELINE = HERE / "stm32f4-phase4.0-foundation-batch5-baseline.json"
MANIFEST = HERE / "stm32f4-phase4.0-foundation-batch5-manifest.json"
EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch5-live-2026-08-31"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CONTROL_BASE = "STM32F437VG"
NEW_BASES = {
    "STM32F437VI",
    "STM32F437ZG",
    "STM32F437ZI",
    "STM32F439VG",
    "STM32F439VI",
}
EXPECTED_NEW_ICPNS = 10
NRND_ICPNS = {"STM32F437VIT6WTR"}


class STM32F4Phase40FoundationBatch5Tests(unittest.TestCase):
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
            "stm32f4-phase4.0-foundation-batch5-2026-08-31",
        )
        self.assertFalse(baseline["canonical_dataset_admission"])
        self.assertEqual(baseline["source_workflow_run_id"], "33360590983")
        self.assertEqual(baseline["source_artifact_id"], "9746559475")
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
        self.assertTrue(NRND_ICPNS.isdisjoint(new_icpns))
        excluded = {
            (item["base_device"], item["icpn"], item["marketing_status"])
            for item in baseline["excluded_non_active_observations"]
        }
        self.assertEqual(
            excluded,
            {("STM32F437VI", "STM32F437VIT6WTR", "NRND")},
        )

    def test_manifest_matches_control_plus_five_new_base_devices(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(
            pilot_id,
            "stm32f4-phase4.0-foundation-batch5-2026-08-31",
        )
        self.assertEqual(len(targets), 6)
        self.assertEqual(
            {target.base_device for target in targets},
            {CONTROL_BASE, *NEW_BASES},
        )

    def test_all_10_new_exact_icpns_have_unique_ordering_pattern_mapping(self) -> None:
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

    def test_existing_policy_builds_expected_batch5_rows(self) -> None:
        catalog_rows = self._catalog_rows()
        fields = self._canonical_fields()
        cases = {
            "STM32F437VIT6": ("STM32F437VI", "LQFP", "100", "2048 KiB"),
            "STM32F437ZGT6": ("STM32F437ZG", "LQFP", "144", "1024 KiB"),
            "STM32F437ZIT7TR": ("STM32F437ZI", "LQFP", "144", "2048 KiB"),
            "STM32F439VGT6": ("STM32F439VG", "LQFP", "100", "1024 KiB"),
            "STM32F439VIT6": ("STM32F439VI", "LQFP", "100", "2048 KiB"),
        }
        for icpn, (base, package, pins, flash) in cases.items():
            with self.subTest(icpn=icpn):
                candidate = {
                    "manufacturer": "STMicroelectronics",
                    "base_device": base,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": "phase4.0-foundation-batch5-policy-contract",
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
        self.assertEqual(report["targets"], 6)
        self.assertEqual(report["exact_icpn_candidates"], 14)
        self.assertEqual(report["acquisition_success"], 6)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_retained_provenance_preserves_clean_live_run_and_nrnd_audit(self) -> None:
        provenance = json.loads((EVIDENCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(
            provenance["evidence_id"],
            "stm32f4-phase4.0-foundation-batch5-2026-08-31-retained-20260831T053303Z-5f76683",
        )
        self.assertEqual(provenance["live_acquisition_attempts"], 1)
        attempts = provenance["live_acquisition_attempt_outcomes"]
        self.assertEqual(len(attempts), 1)
        self.assertTrue(attempts[0]["clean"])
        self.assertEqual(attempts[0]["acquisition_failure"], 0)
        self.assertEqual(provenance["evaluator_result"], "scale_ready")
        excluded = provenance["excluded_non_active_observations"]
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["icpn"], "STM32F437VIT6WTR")
        self.assertTrue(excluded[0]["marketing_status"].startswith("NRND"))


if __name__ == "__main__":
    unittest.main()
