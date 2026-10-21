#!/usr/bin/env python3
"""SWPC bridge: offline-only negative contract checks, no SSH or device."""
from __future__ import annotations

from contextlib import ExitStack
import errno
import json

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


    @staticmethod
    def _receipt(result="LOADED_AND_HELD", stage="download"):
        return (bridge.MARK + json.dumps({
            "stage": stage, "result": result,
            "boot_id": "fe723a58-621e-444a-9171-0c81d35a3b0a",
        }) + "\n").encode()

    def _fake_ssh(self, chunks, *, exit_code=0, eio=False):
        """Drive actual Bridge parsing without sockets, SSH, sudo or hardware.

        poll() reports that SSH has exited *before* its buffered PTY data is
        drained, making the old read-loop race deterministic.
        """
        class CompletedSSH:
            pid = 515151
            def poll(self):
                return exit_code
            def wait(self, timeout=None):
                return exit_code

        stream = list(chunks)
        writes = []

        def read(_fd, _count):
            if stream:
                return stream.pop(0)
            if eio:
                raise OSError(errno.EIO, "closed PTY")
            return b""

        def write(_fd, data):
            writes.append(data)
            return len(data)

        with ExitStack() as stack:
            def replace(obj, attr, **kwargs):
                return stack.enter_context(patch.object(obj, attr, **kwargs))

            replace(bridge, "approved_sha")
            replace(bridge, "enrollment",
                    return_value=("z2.example", "fake-ssh", "fake-sudo"))
            popen = replace(bridge.subprocess, "Popen",
                            return_value=CompletedSSH())
            replace(bridge.os, "openpty", return_value=(910, 911))
            replace(bridge.os, "read", side_effect=read)
            replace(bridge.os, "write", side_effect=write)
            replace(bridge.os, "close")
            replace(bridge.select, "select",
                    return_value=([910], [], []))
            replace(bridge.tty, "setraw")
            try:
                outcome = bridge.execute("download", "a" * 40)
            finally:
                args = popen.call_args.args[0]
                self.assertEqual(args[0], "/usr/bin/ssh")
                self.assertIn("StrictHostKeyChecking=yes", args)
                self.assertIn("xilinx@z2.example", args)
        return outcome, writes

    def test_prompt_and_receipt_same_line_after_ssh_exit(self):
        # Exact failure shape: sudo -p omits newline; the receipt follows
        # directly after the sudo prompt, potentially in later PTY reads.
        outcome, writes = self._fake_ssh([
            b"xilinx@z2.example's password:",
            bridge.PROMPT.encode(),
            self._receipt(),
        ], eio=True)
        self.assertEqual(outcome["result"], "LOADED_AND_HELD")
        self.assertEqual(outcome["stage"], "download")
        self.assertTrue(outcome["real_z2"])
        self.assertEqual(writes, [b"fake-ssh\n", b"fake-sudo\n"])

    def test_root_receipt_accepted_without_cached_sudo_prompt(self):
        # A cached or NOPASSWD sudo may legitimately omit the password
        # prompt; success still requires SSH authentication and exact receipt.
        outcome, writes = self._fake_ssh([
            b"xilinx@z2.example's password:",
            b"\n" + self._receipt(),
        ])
        self.assertEqual(outcome["result"], "LOADED_AND_HELD")
        self.assertEqual(writes, [b"fake-ssh\n"])

    def test_root_receipt_with_separate_sudo_prompt_line(self):
        outcome, writes = self._fake_ssh([
            b"password:", bridge.PROMPT.encode() + b"\n",
            self._receipt(),
        ])
        self.assertEqual(outcome["stage"], "download")
        self.assertEqual(len(writes), 1)  # sudo prompt did not end tail

    def test_reject_duplicate_wrong_and_missing_root_receipts(self):
        receipt = self._receipt()
        for payload in (
            b"\n" + receipt + receipt,
            b"\n" + self._receipt(result="UNVERIFIED"),
            b"\n" + self._receipt(stage="test"),
            b"\n" + bridge.MARK.encode() + b"not-json\n",
            b"\nno root receipt\n",
        ):
            with self.subTest(payload=payload[:60]), self.assertRaises(
                    (bridge.Blocked, ValueError, json.JSONDecodeError)):
                self._fake_ssh([
                    b"xilinx@z2.example's password:", payload,
                ])

    def test_reject_nonzero_ssh_exit_despite_success_marker(self):
        with self.assertRaisesRegex(
                bridge.Blocked, "REMOTE_EXIT_OR_PRIVILEGE_FAILED"):
            self._fake_ssh([
                b"xilinx@z2.example's password:",
                b"\n" + self._receipt(),
            ], exit_code=1)

    def test_reject_missing_ssh_password_prompt_even_with_receipt(self):
        with self.assertRaisesRegex(
                bridge.Blocked, "REMOTE_EXIT_OR_PRIVILEGE_FAILED"):
            self._fake_ssh([b"\n" + self._receipt()])

    def test_reject_unexpected_pty_error(self):
        with self.assertRaises(OSError) as raised:
            class Done:
                pid = 4141
                def poll(self):
                    return 0
                def wait(self, timeout=None):
                    return 0

            with ExitStack() as stack:
                def patcher(obj, attr, **kw):
                    return stack.enter_context(patch.object(obj, attr, **kw))
                patcher(bridge, "approved_sha")
                patcher(bridge, "enrollment",
                        return_value=("z2.example", "fake-ssh", "fake-sudo"))
                patcher(bridge.subprocess, "Popen", return_value=Done())
                patcher(bridge.os, "openpty", return_value=(910, 911))
                patcher(bridge.os, "close")
                patcher(bridge.select, "select",
                        return_value=([910], [], []))
                patcher(bridge.tty, "setraw")
                patcher(bridge.os, "read",
                        side_effect=OSError(errno.EPERM, "unexpected"))
                bridge.execute("download", "a" * 40)
        self.assertEqual(raised.exception.errno, errno.EPERM)


if __name__ == "__main__":
    unittest.main()
