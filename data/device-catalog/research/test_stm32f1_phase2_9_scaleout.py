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

from evaluate_stm32f1_live_pilot import read_baseline  # noqa: E402
from stm32f1_acquisition_pilot import catalog_mapping, read_catalog, read_manifest  # noqa: E402
from stm32f1_admission_policy import MANUFACTURER, build_canonical_row  # noqa: E402

MANIFEST = HERE / "stm32f1-phase2.9-scaleout-manifest.json"
BASELINE = HERE / "stm32f1-phase2.9-scaleout-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
EXPECTED_BASES = [
    "STM32F100CB",
    "STM32F100VE",
    "STM32F101RE",
    "STM32F101ZE",
    "STM32F102CB",
    "STM32F103RC",
    "STM32F105VB",
    "STM32F107RC",
]
EXPECTED_CANDIDATE_COUNT = 26


class Phase29ScaleoutTests(unittest.TestCase):
    def _baseline_by_base(self) -> dict[str, list[str]]:
        baseline = read_baseline(BASELINE)
        return {
            item["base_device"]: item["exact_icpns"]
            for item in baseline["targets"]
        }

    def test_manifest_is_bounded_and_matches_expected_batch(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(pilot_id, "stm32f1-phase2.9-scaleout-batch1-2026-08-29")
        self.assertEqual([target.base_device for target in targets], EXPECTED_BASES)
        self.assertEqual(len(targets), 8)
        self.assertLessEqual(len(targets), 10)

    def test_research_baseline_matches_manifest_and_has_26_unique_candidates(self) -> None:
        _, targets = read_manifest(MANIFEST)
        baseline = read_baseline(BASELINE)
        self.assertFalse(baseline["canonical_dataset_admission"])
        self.assertEqual(baseline["pilot_id"], "stm32f1-phase2.9-scaleout-batch1-2026-08-29")
        baseline_by_base = self._baseline_by_base()
        self.assertEqual(set(baseline_by_base), {target.base_device for target in targets})
        candidates = [icpn for values in baseline_by_base.values() for icpn in values]
        self.assertEqual(len(candidates), EXPECTED_CANDIDATE_COUNT)
        self.assertEqual(len(set(candidates)), EXPECTED_CANDIDATE_COUNT)
        for base_device, icpns in baseline_by_base.items():
            self.assertTrue(icpns)
            self.assertTrue(all(icpn.startswith(base_device) and icpn != base_device for icpn in icpns))

    def test_batch_has_unique_openocd_mapping_for_every_base(self) -> None:
        catalog_rows = read_catalog(CATALOG)
        for base_device in EXPECTED_BASES:
            mapping = catalog_mapping(base_device, catalog_rows)
            self.assertEqual(mapping["status"], "unique", base_device)
            self.assertEqual(mapping["match_count"], 1, base_device)
            self.assertEqual(mapping["target_configs"], ["tcl/target/stm32f1x.cfg"], base_device)

    def test_scaleout_candidates_are_not_already_canonical(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            canonical_icpns = {row["icpn"] for row in csv.DictReader(handle)}
        scaleout_icpns = {
            icpn for values in self._baseline_by_base().values() for icpn in values
        }
        self.assertTrue(scaleout_icpns.isdisjoint(canonical_icpns))

    def test_existing_stm32f1_policy_can_construct_all_26_candidate_rows(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            fields = list(csv.DictReader(handle).fieldnames or [])
        catalog_rows = read_catalog(CATALOG)
        _, targets = read_manifest(MANIFEST)
        source_by_base = {target.base_device: target.source_url for target in targets}
        built: list[dict[str, str]] = []
        for base_device, icpns in self._baseline_by_base().items():
            mapping = catalog_mapping(base_device, catalog_rows)
            for icpn in icpns:
                candidate = {
                    "manufacturer": MANUFACTURER,
                    "base_device": base_device,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": "phase2.9-contract-only-not-admission",
                        "source_url": source_by_base[base_device],
                    },
                    "base_mapping": mapping,
                }
                built.append(build_canonical_row(candidate, fields))
        self.assertEqual(len(built), EXPECTED_CANDIDATE_COUNT)
        self.assertEqual(len({row["icpn"] for row in built}), EXPECTED_CANDIDATE_COUNT)
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32f1x.cfg" for row in built))
        self.assertEqual(next(row for row in built if row["icpn"] == "STM32F103RCY6TR")["package"], "WLCSP64")
        self.assertEqual(next(row for row in built if row["icpn"] == "STM32F105VBH6")["package"], "LFBGA")

    def test_baseline_is_not_misrepresented_as_retained_browser_evidence(self) -> None:
        payload = json.loads(BASELINE.read_text(encoding="utf-8"))
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn("rendered_dom_sha256", serialized)
        self.assertNotIn("evidence_section_sha256", serialized)
        self.assertNotIn("scale_ready", serialized)


if __name__ == "__main__":
    unittest.main()
