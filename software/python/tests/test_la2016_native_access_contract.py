#!/usr/bin/env python3
"""Document-level LA2016 direct Sigrok access contract (host-only; no USB)."""
import fcntl
import os
from pathlib import Path
import tempfile
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

    def test_direct_codex_lock_uses_read_only_fd_without_acl_change(self):
        runbook = LA.read_text(encoding="utf-8")
        direct = DIRECT.read_text(encoding="utf-8")
        for text in ('exec {LA_LOCK_FD}< "$LA_LOCK_PATH"',
                     'flock -x -n "$LA_LOCK_FD"',
                     'exec {LA_LOCK_FD}<&-'):
            self.assertIn(text, runbook)
        self.assertIn("read-only file descriptor", direct)
        self.assertIn("native USB/fuser checks", direct)
        self.assertIn("no Host Supervisor", direct)
        self.assertNotIn("and existing `SIGROK_FIRMWARE_PATH`/firmware resources", direct)

    @unittest.skipUnless(os.name == "posix", "Linux flock semantics")
    def test_exclusive_flock_can_be_held_on_read_only_descriptor(self):
        # Host-only Linux semantics; no LA/USB and no /run/lock access.
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "la.lock"
            lock.write_bytes(b"")
            lock.chmod(0o444)
            with lock.open("rb") as holder:
                fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with lock.open("rb") as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with lock.open("rb") as new_holder:
                fcntl.flock(new_holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(lock.stat().st_mode & 0o777, 0o444)


if __name__ == "__main__":
    unittest.main()
