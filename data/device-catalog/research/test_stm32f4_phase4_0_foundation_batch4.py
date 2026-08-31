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

BASELINE = HERE / "stm32f4-phase4.0-foundation-batch4-baseline.json"
MANIFEST = HERE / "stm32f4-phase4.0-foundation-batch4-manifest.json"
EVIDENCE = HERE / "evidence" / "stm32f4-phase4.0-foundation-batch4-live-2026-08-31"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CONTROL_BASE = "STM32F429ZG"
NEW_BASES = {
    "STM32F427VI",
    "STM32F427ZI",
    "STM32F429VE",
    "STM32F429VG",
    "STM32F429VI",
}
EXPECTED_NEW_ICPNS = 13
PROPOSAL_ICPNS = {"STM32F427VIT7"}


class STM32F4Phase40FoundationBatch4Tests(unittest.TestCase):
    def _baseline(self) -> dict[str, object]:
        return json.loads(BASELINE.read_text(encoding="utf-8"))

    def _catalog_rows(self) -> list[dict[str, str]]:
        with CATALOG.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _canonical_fields(self) -> list[str]:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle).fieldnames or [])

    def test_baseline_is_discovery_locked_and_active_only(self) -> None:
        baseline = self._baseline()
        self.assertEqual(
            baseline["pilot_id"],
            "stm32f4-phase4.0-foundation-batch4-2026-08-31",
        )
        self.assertFalse(baseline["canonical_dataset_admission"])
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
        self.assertTrue(PROPOSAL_ICPNS.isdisjoint(new_icpns))

        excluded = {
            (item["base_device"], item["icpn"], item["marketing_status"])
            for item in baseline["excluded_non_active_observations"]
        }
        self.assertEqual(
            excluded,
            {("STM32F427VI", "STM32F427VIT7", "Proposal")},
        )

    def test_manifest_matches_control_plus_five_new_base_devices(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(
            pilot_id,
            "stm32f4-phase4.0-foundation-batch4-2026-08-31",
        )
        self.assertEqual(len(targets), 6)
        self.assertEqual(
            {target.base_device for target in targets},
            {CONTROL_BASE, *NEW_BASES},
        )

    def test_all_13_new_exact_icpns_have_unique_ordering_pattern_mapping(self) -> None:
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

    def test_existing_policy_builds_expected_batch4_rows(self) -> None:
        catalog_rows = self._catalog_rows()
        fields = self._canonical_fields()
        cases = {
            "STM32F427VIT6": ("STM32F427VI", "LQFP", "100", "2048 KiB"),
            "STM32F427ZIT7TR": ("STM32F427ZI", "LQFP", "144", "2048 KiB"),
            "STM32F429VET6": ("STM32F429VE", "LQFP", "100", "512 KiB"),
            "STM32F429VGT6TR": ("STM32F429VG", "LQFP", "100", "1024 KiB"),
            "STM32F429VIT6TR": ("STM32F429VI", "LQFP", "100", "2048 KiB"),
        }
        for icpn, (base, package, pins, flash) in cases.items():
            with self.subTest(icpn=icpn):
                candidate = {
                    "manufacturer": "STMicroelectronics",
                    "base_device": base,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": "phase4.0-foundation-batch4-policy-contract",
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
        self.assertEqual(report["exact_icpn_candidates"], 16)
        self.assertEqual(report["acquisition_success"], 6)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_retained_provenance_preserves_transient_retry_without_weakening_gate(self) -> None:
        provenance = json.loads((EVIDENCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["live_acquisition_attempts"], 2)
        attempts = provenance["live_acquisition_attempt_outcomes"]
        self.assertEqual(len(attempts), 2)
        self.assertFalse(attempts[0]["clean"])
        self.assertEqual(attempts[0]["acquisition_failure"], 2)
        self.assertTrue(attempts[1]["clean"])
        self.assertEqual(attempts[1]["acquisition_failure"], 0)
        self.assertEqual(provenance["evaluator_result"], "scale_ready")
        excluded = provenance["excluded_non_active_observations"]
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["icpn"], "STM32F427VIT7")
        self.assertTrue(excluded[0]["marketing_status"].startswith("Proposal"))


if __name__ == "__main__":
    unittest.main()
