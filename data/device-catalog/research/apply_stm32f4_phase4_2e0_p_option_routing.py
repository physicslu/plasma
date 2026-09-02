#!/usr/bin/env python3
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = HERE / "stm32f4_admission_policy.py"
TEST = HERE / "test_stm32f4_phase4_2e0_p_option_routing.py"

old = '''def commercial_core(icpn: str) -> str:
    """Remove packing-only suffixes before matching OpenOCD ordering patterns."""

    for suffix in ("TR", "TT"):
        if icpn.endswith(suffix):
            return icpn[: -len(suffix)]
    return icpn
'''
new = '''def commercial_core(icpn: str) -> str:
    """Build an OpenOCD routing key without changing canonical commercial identity."""

    core = icpn
    for suffix in ("TR", "TT"):
        if core.endswith(suffix):
            core = core[: -len(suffix)]
            break

    # STM32F412xE/G ordering information defines P as a device option
    # (internal regulator disabled), not as packing. OpenOCD ordering
    # patterns do not encode this option. Ignore it only for routing;
    # build_canonical_row() still retains P in option_suffix.
    if core.startswith("STM32F412") and core.endswith("P"):
        core = core[:-1]
    return core
'''

text = POLICY.read_text(encoding="utf-8")
if old not in text:
    raise SystemExit("commercial_core anchor missing or already changed")
POLICY.write_text(text.replace(old, new, 1), encoding="utf-8")

TEST.write_text('''#!/usr/bin/env python3
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
ICPN = "STM32F412RGY6PTR"


class STM32F4Phase42E0POptionRoutingTests(unittest.TestCase):
    def _catalog_rows(self):
        with CATALOG.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _fields(self):
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle).fieldnames or [])

    def test_p_option_is_ignored_only_in_routing_key(self) -> None:
        self.assertEqual(commercial_core(ICPN), "STM32F412RGY6")
        self.assertEqual(commercial_core("STM32F412RGY6TR"), "STM32F412RGY6")
        self.assertEqual(commercial_core("STM32F410CBT6TR"), "STM32F410CBT6")

    def test_ptr_exact_part_routes_uniquely(self) -> None:
        mapping = resolve_ordering_pattern_mapping(ICPN, self._catalog_rows())
        self.assertEqual(mapping["status"], "unique")
        self.assertEqual(mapping["match_count"], 1)
        self.assertEqual(mapping["existing_identifier"], "STM32F412RGYx")
        self.assertEqual(mapping["target_configs"], ["tcl/target/stm32f4x.cfg"])

    def test_canonical_identity_retains_p_option(self) -> None:
        mapping = resolve_ordering_pattern_mapping(ICPN, self._catalog_rows())
        candidate = {
            "manufacturer": "STMicroelectronics",
            "base_device": "STM32F412RG",
            "icpn": ICPN,
            "authoritative_evidence": {
                "evidence_id": "phase4.2e0-routing-contract",
                "source_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32f412rg.html",
            },
            "base_mapping": mapping,
        }
        row = build_canonical_row(candidate, self._fields())
        self.assertEqual(row["package"], "WLCSP")
        self.assertEqual(row["pin_count"], "64")
        self.assertEqual(row["flash_size"], "1024 KiB")
        self.assertEqual(row["option_suffix"], "PTR")


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")
