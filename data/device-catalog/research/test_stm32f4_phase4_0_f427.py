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

BASELINE = HERE / "stm32f4-phase4.0-f427-batch2-baseline.json"
MANIFEST = HERE / "stm32f4-phase4.0-f427-batch2-manifest.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CONTROL_BASE = "STM32F401CC"
F427_BASES = {"STM32F427VG", "STM32F427VI", "STM32F427ZG", "STM32F427ZI"}
EXPECTED_NEW_ICPNS = 11


class STM32F4Phase40F427Tests(unittest.TestCase):
    def _baseline(self) -> dict[str, object]:
        return json.loads(BASELINE.read_text(encoding="utf-8"))

    def _catalog_rows(self) -> list[dict[str, str]]:
        with CATALOG.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _canonical_fields(self) -> list[str]:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle).fieldnames or [])

    def test_baseline_is_bounded_active_only_and_records_non_active_rows(self) -> None:
        baseline = self._baseline()
        self.assertEqual(baseline["pilot_id"], "stm32f4-phase4.0-f427-batch2-2026-08-31")
        self.assertFalse(baseline["canonical_dataset_admission"])
        targets = baseline["targets"]
        self.assertEqual({target["base_device"] for target in targets}, {CONTROL_BASE, *F427_BASES})

        new_values = [
            icpn
            for target in targets
            if target["base_device"] in F427_BASES
            for icpn in target["exact_icpns"]
        ]
        self.assertEqual(len(new_values), EXPECTED_NEW_ICPNS)
        self.assertEqual(len(set(new_values)), EXPECTED_NEW_ICPNS)
        self.assertNotIn("STM32F427VIT7", new_values)

        excluded = baseline["excluded_non_active_observations"]
        self.assertEqual(
            excluded,
            [
                {
                    "base_device": "STM32F401CC",
                    "icpn": "STM32F401CCF6TR",
                    "marketing_status": "Preview",
                    "admission": False,
                    "lifecycle_note": (
                        "previously admitted production identity; retained pending explicit "
                        "de-admission policy"
                    ),
                },
                {
                    "base_device": "STM32F427VI",
                    "icpn": "STM32F427VIT7",
                    "marketing_status": "Proposal",
                    "admission": False,
                },
            ],
        )

    def test_manifest_matches_control_plus_four_f427_base_devices(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(pilot_id, "stm32f4-phase4.0-f427-batch2-2026-08-31")
        self.assertEqual(len(targets), 5)
        self.assertEqual({target.base_device for target in targets}, {CONTROL_BASE, *F427_BASES})

    def test_all_11_f427_exact_icpns_have_unique_ordering_pattern_mapping(self) -> None:
        catalog_rows = self._catalog_rows()
        failures: list[str] = []
        mapped = 0
        for target in self._baseline()["targets"]:
            if target["base_device"] not in F427_BASES:
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

    def test_f427_package_pin_and_flash_semantics_are_already_deterministic(self) -> None:
        catalog_rows = self._catalog_rows()
        fields = self._canonical_fields()
        cases = {
            "STM32F427VGT6": ("STM32F427VG", "LQFP", "100", "1024 KiB"),
            "STM32F427VIT7TR": ("STM32F427VI", "LQFP", "100", "2048 KiB"),
            "STM32F427ZGT6TR": ("STM32F427ZG", "LQFP", "144", "1024 KiB"),
            "STM32F427ZIT7": ("STM32F427ZI", "LQFP", "144", "2048 KiB"),
        }
        for icpn, (base, package, pins, flash) in cases.items():
            with self.subTest(icpn=icpn):
                candidate = {
                    "manufacturer": "STMicroelectronics",
                    "base_device": base,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": "phase4.0-f427-package-policy-contract",
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


if __name__ == "__main__":
    unittest.main()
