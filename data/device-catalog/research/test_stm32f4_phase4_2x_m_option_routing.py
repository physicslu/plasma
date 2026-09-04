#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from stm32f4_admission_policy import build_canonical_row, commercial_core, resolve_ordering_pattern_mapping

CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
ICPN = "STM32F446MEY6MTR"


class STM32F4Phase42XMOptionRoutingTests(unittest.TestCase):
    def _catalog_rows(self):
        with CATALOG.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _fields(self):
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle).fieldnames or [])

    def test_m_option_is_ignored_only_for_exact_f446_mey6m_routing_key(self) -> None:
        self.assertEqual(commercial_core(ICPN), "STM32F446MEY6")
        self.assertEqual(commercial_core("STM32F446MEY6TR"), "STM32F446MEY6")
        self.assertEqual(commercial_core("STM32F446MCY6MTR"), "STM32F446MCY6M")

    def test_m_option_exact_part_routes_uniquely(self) -> None:
        mapping = resolve_ordering_pattern_mapping(ICPN, self._catalog_rows())
        self.assertEqual(mapping["status"], "unique")
        self.assertEqual(mapping["match_count"], 1)
        self.assertEqual(mapping["existing_identifier"], "STM32F446MEYx")
        self.assertEqual(mapping["target_configs"], ["tcl/target/stm32f4x.cfg"])

    def test_canonical_identity_retains_m_option(self) -> None:
        mapping = resolve_ordering_pattern_mapping(ICPN, self._catalog_rows())
        candidate = {
            "manufacturer": "STMicroelectronics",
            "base_device": "STM32F446ME",
            "icpn": ICPN,
            "authoritative_evidence": {
                "evidence_id": "phase4.2x-m-option-routing-contract",
                "source_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32f446me.html",
            },
            "base_mapping": mapping,
        }
        row = build_canonical_row(candidate, self._fields())
        self.assertEqual(row["package"], "WLCSP")
        self.assertEqual(row["pin_count"], "81")
        self.assertEqual(row["flash_size"], "512 KiB")
        self.assertEqual(row["temperature_grade"], "-40 to 85 C")
        self.assertEqual(row["option_suffix"], "MTR")


if __name__ == "__main__":
    unittest.main()
