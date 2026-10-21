#!/usr/bin/env python3
"""SWPC bridge: offline-only negative contract checks, no SSH or device."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "scripts/swpc/z2-path2-f1b-bridge"
loader = SourceFileLoader("path2_swpc_fixed_bridge_test", str(FILE))
spec = spec_from_loader(loader.name, loader)
bridge = module_from_spec(spec)
loader.exec_module(bridge)


class BridgeContracts(unittest.TestCase):
    def test_stage_allowlist_blocks_any_remote_call(self):
        for stage in ("full", "build", "reset", "download;id", "", "--help"):
            with self.subTest(stage=stage), patch.object(
                    bridge, "approved_sha") as approve, patch.object(
                    bridge, "enrollment") as creds:
                with self.assertRaisesRegex(bridge.Blocked,
                                            "STAGE_NOT_ALLOWLISTED"):
                    bridge.execute(stage, "a" * 40)
                approve.assert_not_called()
                creds.assert_not_called()

    def test_exact_reviewed_sha_checked_before_reading_secrets(self):
        with patch.object(bridge, "approved_sha",
                          side_effect=bridge.Blocked("SOURCE_NOT_APPROVED")):
            with patch.object(bridge, "enrollment") as creds:
                with self.assertRaisesRegex(bridge.Blocked,
                                            "SOURCE_NOT_APPROVED"):
                    bridge.execute("download", "a" * 40)
                creds.assert_not_called()

    def test_root_owned_approval_file_required(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "approved"
            p.write_text("a" * 40 + "\n")
            p.chmod(0o644)  # publicly-readable file not valid
            with patch.object(bridge, "APPROVAL", p):
                with self.assertRaisesRegex(bridge.Blocked,
                                            "SWPC_APPROVED_SOURCE_NOT_INSTALLED"):
                    bridge.approved_sha("a" * 40)
            with self.assertRaisesRegex(bridge.Blocked, "SOURCE_SHA_INVALID"):
                bridge.approved_sha("not-a-sha")

    def test_transport_has_only_fixed_target_and_root_stage_command(self):
        s = FILE.read_text()
        self.assertIn('STAGES = ("download", "test", "restore")', s)
        self.assertIn('ROOT_ENTRY = "/usr/local/libexec/plasma/z2-path2-f1b-root-entry"', s)
        self.assertIn('"StrictHostKeyChecking=yes"', s)
        self.assertIn('"SOURCE_SHA_INVALID"', s)
        self.assertNotIn("shell=True", s)
        self.assertNotIn("eval(", s)
        self.assertIn("REMOTE_EXIT_OR_PRIVILEGE_FAILED", s)


if __name__ == "__main__":
    unittest.main()
