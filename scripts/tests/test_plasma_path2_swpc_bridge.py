#!/usr/bin/env python3
"""SWPC bridge: offline-only negative contract checks, no SSH or device."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from pathlib import Path
from types import SimpleNamespace
import stat
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

    def test_root_owned_0644_approval_readable_by_unprivileged_worker(self):
        # A hosted non-root test cannot chown(2). Simulate only st_uid=0,
        # while reading a real 0644 file as the current unprivileged user.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "approved"
            p.write_text("a" * 40 + "\n")
            p.chmod(0o644)
            actual_lstat = Path.lstat

            def root_owned_lstat(path):
                observed = actual_lstat(path)
                if path == p:
                    return SimpleNamespace(
                        st_mode=observed.st_mode, st_uid=0,
                        st_size=observed.st_size)
                return observed

            with patch.object(Path, "lstat", root_owned_lstat), patch.object(
                    bridge, "APPROVAL", p):
                bridge.approved_sha("a" * 40)
                with self.assertRaisesRegex(
                        bridge.Blocked, "SWPC_APPROVED_SOURCE_SHA_MISMATCH"):
                    bridge.approved_sha("b" * 40)

    def test_approval_denies_bad_ownership_type_mode_and_size(self):
        rejected = (
            ("root_only_unreadable", stat.S_IFREG | 0o600, 0, 41),
            ("group_writable", stat.S_IFREG | 0o664, 0, 41),
            ("world_writable", stat.S_IFREG | 0o666, 0, 41),
            ("worker_owned", stat.S_IFREG | 0o644, 1000, 41),
            ("symlink", stat.S_IFLNK | 0o644, 0, 41),
            ("oversized", stat.S_IFREG | 0o644, 0, 65),
        )
        with patch.object(bridge, "APPROVAL") as approved:
            for name, mode, uid, size in rejected:
                with self.subTest(name=name):
                    approved.lstat.return_value = SimpleNamespace(
                        st_mode=mode, st_uid=uid, st_size=size)
                    approved.read_text.reset_mock()
                    with self.assertRaisesRegex(
                            bridge.Blocked, "SWPC_APPROVED_SOURCE_NOT_INSTALLED"):
                        bridge.approved_sha("a" * 40)
                    approved.read_text.assert_not_called()
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
