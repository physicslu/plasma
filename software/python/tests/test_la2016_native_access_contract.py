#!/usr/bin/env python3
"""Document-level LA2016 direct Sigrok access contract (host-only; no USB)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
LA = ROOT / "docs/development/la2016-tool-operations.md"
ST = ROOT / "docs/development/stlink-swd-tool-operations.md"
AGENTS = ROOT / "AGENTS.md"
DIRECT = ROOT / "docs/development/plasma-path3-direct-hardware-tools.md"
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

    def test_direct_codex_uses_native_busy_without_extra_probe(self):
        runbook = LA.read_text(encoding="utf-8")
        direct = DIRECT.read_text(encoding="utf-8")
        for content in (runbook, direct):
            self.assertIn("DEVICE_BUSY", content)
            self.assertIn("RUNTIME_FAIL", content)
            self.assertNotIn("LA_LOCK_PATH=", content)
            self.assertNotIn("LA_LOCK_FD", content)
            self.assertNotIn("flock -x -n", content)
            self.assertNotIn("subprocess.run(['fuser'", content)
            self.assertNotIn("LA_USB_BUSY_OR_OWNER_UNCERTAIN", content)
        self.assertIn("native Driver Open/Claim", direct)
        self.assertIn("No intermediary hardware JSON command translation", direct)
        self.assertNotIn("and existing `SIGROK_FIRMWARE_PATH`/firmware resources", direct)

    def test_usb_identity_acl_and_safe_close_are_still_required(self):
        runbook = LA.read_text(encoding="utf-8")
        direct = DIRECT.read_text(encoding="utf-8")
        for text in ("77a1", "01a2", "LA_USB_DAC_DENIED",
                     "os.access(node, os.R_OK | os.W_OK)"):
            self.assertIn(text, runbook)
        self.assertIn("SHA256", direct)
        self.assertIn("RW DAC/ACL", direct)
        self.assertIn("normal USB close", direct)
        self.assertIn("Native concurrency rejection has **not** been physically requalified", direct)


    def test_native_busy_coexists_with_reusable_owner_electrical_evidence(self):
        """PR #1192 must preserve PR #1194's passive-input safety contract."""
        for path in (LA, DIRECT):
            with self.subTest(path=path.name):
                doc = path.read_text(encoding="utf-8")
                self.assertIn("DEVICE_BUSY", doc)
                self.assertIn("OWNER_ELECTRICAL_ATTESTATION_REUSE", doc)
                self.assertIn("不要求每次", doc)
                self.assertIn("Linux DAC/ACL", doc)
                self.assertNotIn("LA_LOCK_PATH=", doc)
                self.assertNotIn("flock -x -n", doc)
        self.assertIn("真實電氣危險", DIRECT.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
