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
from stm32f4_admission_policy import TARGET_CONFIG, resolve_ordering_pattern_mapping  # noqa: E402

BASELINE = HERE / "stm32f4-phase4.0-f446-batch1-baseline.json"
MANIFEST = HERE / "stm32f4-phase4.0-f446-batch1-manifest.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CONTROL_BASE = "STM32F401CC"
F446_BASES = {"STM32F446VC", "STM32F446VE", "STM32F446ZC", "STM32F446ZE"}
EXPECTED_NEW_ICPNS = 23


class STM32F4Phase40F446Tests(unittest.TestCase):
    def _baseline(self) -> dict[str, object]:
        return json.loads(BASELINE.read_text(encoding="utf-8"))

    def _catalog_rows(self) -> list[dict[str, str]]:
        with CATALOG.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_baseline_is_bounded_active_only_and_excludes_proposal(self) -> None:
        baseline = self._baseline()
        self.assertEqual(baseline["pilot_id"], "stm32f4-phase4.0-f446-batch1-2026-08-30")
        self.assertFalse(baseline["canonical_dataset_admission"])
        targets = baseline["targets"]
        self.assertEqual({target["base_device"] for target in targets}, {CONTROL_BASE, *F446_BASES})

        new_values = [
            icpn
            for target in targets
            if target["base_device"] in F446_BASES
            for icpn in target["exact_icpns"]
        ]
        self.assertEqual(len(new_values), EXPECTED_NEW_ICPNS)
        self.assertEqual(len(set(new_values)), EXPECTED_NEW_ICPNS)
        self.assertNotIn("STM32F446ZCT7", new_values)

        excluded = baseline["excluded_non_active_observations"]
        self.assertEqual(
            excluded,
            [
                {
                    "base_device": "STM32F446ZC",
                    "icpn": "STM32F446ZCT7",
                    "marketing_status": "Proposal",
                    "admission": False,
                }
            ],
        )

    def test_manifest_matches_control_plus_four_f446_base_devices(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(pilot_id, "stm32f4-phase4.0-f446-batch1-2026-08-30")
        self.assertEqual(len(targets), 5)
        self.assertEqual({target.base_device for target in targets}, {CONTROL_BASE, *F446_BASES})

    def test_all_23_f446_exact_icpns_have_unique_ordering_pattern_mapping(self) -> None:
        catalog_rows = self._catalog_rows()
        failures: list[str] = []
        mapped = 0
        for target in self._baseline()["targets"]:
            if target["base_device"] not in F446_BASES:
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


if __name__ == "__main__":
    unittest.main()
