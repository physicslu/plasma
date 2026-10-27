#!/usr/bin/env python3
"""Document-level LA2016 direct Sigrok access contract (host-only; no USB)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
LA = ROOT / "docs/development/la2016-tool-operations.md"
ST = ROOT / "docs/development/stlink-swd-tool-operations.md"
AGENTS = ROOT / "AGENTS.md"
PIN = "b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475"


class La2016NativeAccessContracts(unittest.TestCase):
    def test_runbook_has_no_firmware_gate_or_auto_firmware_repair(self):
        doc = LA.read_text(encoding="utf-8")
        for banned in ("LA_FIRMWARE_MISSING_OR_AMBIGUOUS",
                       "LA_FIRMWARE_RESOURCE_NOT_READABLE",
                       'find "$root" -type f -name kingst-la-01a2.fw',
                       'export SIGROK_FIRMWARE_PATH='):
            with self.subTest(text=banned):
                self.assertNotIn(banned, doc)
        self.assertIn("NOT_REQUIRED_BY_OWNER", doc)
        self.assertIn("RUNTIME_FAIL", doc)
        self.assertIn(PIN, doc)
        self.assertIn("--appimage-extract-and-run", doc)
        self.assertIn("--driver \"kingst-la2016:conn=$LA_CONN\"", doc)

    def test_stlink_runbook_no_longer_requires_la_firmware_path(self):
        doc = ST.read_text(encoding="utf-8")
        self.assertNotIn('SIGROK_FIRMWARE_PATH:?', doc)
        self.assertIn("--channels CH0,CH1,CH2", doc)
        self.assertIn("--samples 50000000", doc)
        self.assertIn(PIN, doc)

    def test_scope_excludes_fpga_dut_firmware_and_retains_image_admission(self):
        doc = AGENTS.read_text(encoding="utf-8")
        self.assertIn("LA2016 native Sigrok access contract", doc)
        self.assertIn("kingst-la-01a2.fw", doc)
        self.assertIn("kingst-la2016a2-fpga.bitstream", doc)
        self.assertIn("Root Guard", doc)
        self.assertIn("Z2 FPGA Image/Manifest", doc)


if __name__ == "__main__":
    unittest.main()
