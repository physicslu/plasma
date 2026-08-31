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

BASELINE = HERE / "stm32f4-phase4.0-foundation-batch3-baseline.json"
MANIFEST = HERE / "stm32f4-phase4.0-foundation-batch3-manifest.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CONTROL_BASE = "STM32F401CC"
NEW_BASES = {
    "STM32F401CD",
    "STM32F401CE",
    "STM32F412CE",
    "STM32F412CG",
    "STM32F412ZE",
}
EXPECTED_NEW_ICPNS = 16


class STM32F4Phase40FoundationBatch3Tests(unittest.TestCase):
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
            "stm32f4-phase4.0-foundation-batch3-2026-08-31",
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

        excluded = {
            (item["base_device"], item["icpn"], item["marketing_status"])
            for item in baseline["excluded_non_active_observations"]
        }
        self.assertEqual(
            excluded,
            {(CONTROL_BASE, "STM32F401CCF6TR", "Preview")},
        )

    def test_manifest_matches_control_plus_five_new_base_devices(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(
            pilot_id,
            "stm32f4-phase4.0-foundation-batch3-2026-08-31",
        )
        self.assertEqual(len(targets), 6)
        self.assertEqual(
            {target.base_device for target in targets},
            {CONTROL_BASE, *NEW_BASES},
        )

    def test_all_16_new_exact_icpns_have_unique_ordering_pattern_mapping(self) -> None:
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

    def test_existing_policy_builds_expected_batch3_rows(self) -> None:
        catalog_rows = self._catalog_rows()
        fields = self._canonical_fields()
        cases = {
            "STM32F401CDU6": ("STM32F401CD", "UFQFPN", "48", "384 KiB"),
            "STM32F401CEU6": ("STM32F401CE", "UFQFPN", "48", "512 KiB"),
            "STM32F412CEU7TR": ("STM32F412CE", "UFQFPN", "48", "512 KiB"),
            "STM32F412CGU6TR": ("STM32F412CG", "UFQFPN", "48", "1024 KiB"),
            "STM32F412ZEJ3": ("STM32F412ZE", "UFBGA", "144", "512 KiB"),
            "STM32F412ZET7TR": ("STM32F412ZE", "LQFP", "144", "512 KiB"),
        }
        for icpn, (base, package, pins, flash) in cases.items():
            with self.subTest(icpn=icpn):
                candidate = {
                    "manufacturer": "STMicroelectronics",
                    "base_device": base,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": "phase4.0-foundation-batch3-policy-contract",
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
