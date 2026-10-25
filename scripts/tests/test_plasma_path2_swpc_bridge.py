#!/usr/bin/env python3
"""SWPC bridge: offline-only negative contract checks, no SSH or device."""
from __future__ import annotations

from contextlib import ExitStack
import errno
import json
import os
import subprocess

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
PROJECT = "pl/projects/z2-fixed-unified-site1"
FILE = ROOT / "scripts/plasma_development_stage_transport.py"
loader = SourceFileLoader("path2_swpc_fixed_bridge_test", str(FILE))
spec = spec_from_loader(loader.name, loader)
bridge = module_from_spec(spec)
loader.exec_module(bridge)


class BridgeContracts(unittest.TestCase):
    def test_invalid_stage_name_blocks_before_enrollment(self):
        # Transport checks syntax, not the business-specific stage catalogue.
        for stage in ("", "--help", "download;id", "audit && id",
                      "../audit", "Audit", "a" * 33, None, 7):
            with self.subTest(stage=stage), patch.object(
                    bridge, "enrollment") as creds:
                with self.assertRaisesRegex(bridge.Blocked, "STAGE_INVALID"):
                    bridge.execute(stage, "a" * 40, PROJECT)
                creds.assert_not_called()

    def test_valid_new_stage_name_passes_transport_format_check(self):
        # Reaching enrollment does not authorize a remote root operation.
        for stage in ("audit", "probe", "diagnostics", "download"):
            with self.subTest(stage=stage), patch.object(
                    bridge, "enrollment",
                    side_effect=bridge.Blocked("LOCAL_ENROLLMENT_DENIED")) as creds:
                with self.assertRaisesRegex(bridge.Blocked,
                                            "LOCAL_ENROLLMENT_DENIED"):
                    bridge.execute(stage, "a" * 40, PROJECT)
                creds.assert_called_once()

    def test_invalid_sha_before_secrets(self):
        with patch.object(bridge, "enrollment") as credentials:
            with self.assertRaisesRegex(bridge.Blocked, "SOURCE_SHA_INVALID"):
                bridge.execute("test", "invalid", PROJECT)
            credentials.assert_not_called()

    def test_transport_has_only_fixed_target_and_root_stage_command(self):
        s = FILE.read_text()
        self.assertIn('STAGE_NAME = re.compile(', s)
        self.assertNotIn('STAGES = ("download", "test", "restore")', s)
        self.assertIn('ROOT_ENTRY = "/usr/local/libexec/plasma/z2-path2-root-entry"', s)
        self.assertIn('"StrictHostKeyChecking=yes"', s)
        self.assertIn('"SOURCE_SHA_INVALID"', s)
        self.assertNotIn("shell=True", s)
        self.assertNotIn("eval(", s)
        self.assertIn("REMOTE_EXIT_OR_PRIVILEGE_FAILED", s)


    @staticmethod
    def _receipt(result="LOADED_AND_HELD", stage="download"):
        return (bridge.MARK + json.dumps({
            "stage": stage, "result": result, "project": PROJECT,
            "boot_id": "fe723a58-621e-444a-9171-0c81d35a3b0a",
        }) + "\n").encode()

    def _fake_ssh(self, chunks, *, exit_code=0, eio=False, stage="download"):
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
                outcome = bridge.execute(stage, "a" * 40, PROJECT)
            finally:
                args = popen.call_args.args[0]
                self.assertEqual(args[0], "/usr/bin/ssh")
                self.assertIn("StrictHostKeyChecking=yes", args)
                self.assertIn("xilinx@z2.example", args)
        return outcome, writes

    def test_new_audit_receipt_is_explicitly_not_hardware_authority(self):
        # Root still controls which verbs exist. Transport must never
        # interpret an unfamiliar verb's receipt as FPGA load/restore PASS.
        def payload(result, write=False, stage="audit"):
            return (bridge.MARK + json.dumps({
                "stage": stage, "result": result, "project": PROJECT,
                "boot_id": "fe723a58-621e-444a-9171-0c81d35a3b0a",
                "hardware_write_authorized": write,
            }) + "\\n").encode()

        receipt = payload("READ_ONLY_AUDIT_NOT_HARDWARE_ADMISSION")
        observed = bridge.parse_receipt("audit", "a" * 40, receipt, PROJECT)
        self.assertEqual(observed["stage"], "audit")
        self.assertEqual(observed["result"],
                         "READ_ONLY_AUDIT_NOT_HARDWARE_ADMISSION")
        for denied in (
                payload("LOADED_AND_HELD"),
                payload("IDENTITY_PASS"),
                payload("READ_ONLY_AUDIT_NOT_HARDWARE_ADMISSION", True),
                payload("READ_ONLY_AUDIT_NOT_HARDWARE_ADMISSION",
                        False, stage="download"),
        ):
            with self.subTest(denied=denied[:75]), self.assertRaises(
                    bridge.Blocked):
                bridge.parse_receipt("audit", "a" * 40, denied, PROJECT)

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

    def test_no_identity_or_restore_pass_without_successful_root_receipt(self):
        for stage, result in (("test", "IDENTITY_PASS"),
                              ("restore", "RESTORED_VERIFIED"),
                              ("restore", "ALREADY_RESTORED")):
            with self.subTest(stage=stage, result=result):
                with self.assertRaisesRegex(bridge.Blocked,
                                            "EXACTLY_ONE_REMOTE_RECEIPT_REQUIRED"):
                    self._fake_ssh([b"no receipt\n"], stage=stage)
                with self.assertRaisesRegex(bridge.Blocked,
                                            "REMOTE_EXIT_OR_PRIVILEGE_FAILED"):
                    self._fake_ssh([self._receipt(result=result, stage=stage)],
                                   stage=stage, exit_code=1)

    def test_ssh_prompt_not_required_when_exact_root_receipt_is_valid(self):
        receipt, _writes = self._fake_ssh([b"\n" + self._receipt()])
        self.assertEqual(receipt["result"], "LOADED_AND_HELD")
        with self.assertRaises(bridge.Blocked):
            self._fake_ssh([b"\nno root receipt\n"])

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
                bridge.execute("download", "a" * 40, PROJECT)
        self.assertEqual(raised.exception.errno, errno.EPERM)



if __name__ == "__main__":
    unittest.main()
