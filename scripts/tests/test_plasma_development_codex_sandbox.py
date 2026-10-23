#!/usr/bin/env python3
"""Host-only negatives for existing Path 3 USB/TTY namespace; NO hardware opens."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_development_codex_sandbox as sandbox
import plasma_development_dispatch as dispatcher


class Path3UsbTtySandboxContracts(unittest.TestCase):
    def roots(self, temp: str):
        root = Path(temp)
        home = root / "home"
        (home / ".codex").mkdir(parents=True)
        (home / ".ssh").mkdir()
        work = root / "candidate"
        work.mkdir()
        usb = root / "usb"
        usb.mkdir()
        dev = root / "dev"
        dev.mkdir()
        (dev / "ttyACM2").write_bytes(b"")
        (dev / "ttyUSB7").write_bytes(b"")
        (dev / "disk0").write_bytes(b"")
        return work, home, usb, dev

    def test_existing_path3_exposes_usb_and_tty_not_all_dev(self):
        with tempfile.TemporaryDirectory() as temp:
            work, home, usb, dev = self.roots(temp)
            with patch.object(sandbox.os, "geteuid", return_value=1000), \
                 patch.object(sandbox.shutil, "which", return_value=sys.executable), \
                 patch.object(Path, "is_char_device",
                              lambda self: self.name in {"ttyACM2", "ttyUSB7"}):
                args = sandbox.codex_command(work, home=home,
                                             usb_root=usb, dev_root=dev)
        self.assertIn("--dev", args)
        self.assertIn("--dev-bind", args)
        self.assertIn(str(usb), args)
        self.assertIn("/dev/bus/usb", args)
        self.assertIn("/dev/ttyACM2", args)
        self.assertIn("/dev/ttyUSB7", args)
        self.assertNotIn("/dev/disk0", args)
        self.assertNotIn("/dev/mem", args)
        self.assertNotIn("/dev/uio0", args)
        self.assertIn("--ro-bind", args)
        self.assertEqual(args[args.index("--tmpfs") + 1], "/run")
        self.assertIn("--unsetenv", args)
        self.assertIn("--sandbox", args)
        self.assertEqual(args[args.index("--sandbox") + 1],
                         "danger-full-access")
        self.assertIn(str(home / ".ssh"), args)
        self.assertEqual(args.count("--dev-bind"), 3)
        self.assertEqual(args[-1], "-")

    def test_no_root_no_bwrap_no_auth_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            work, home, usb, dev = self.roots(temp)
            with patch.object(sandbox.os, "geteuid", return_value=0):
                with self.assertRaisesRegex(
                    sandbox.CodexSandboxDenied, "ROOT_DENIED"
                ):
                    sandbox.codex_command(work, home=home,
                                          usb_root=usb, dev_root=dev)
            with patch.object(sandbox.os, "geteuid", return_value=1000), \
                 patch.object(sandbox.shutil, "which", return_value=None):
                with self.assertRaisesRegex(
                    sandbox.CodexSandboxDenied, "BWRAP_UNAVAILABLE"
                ):
                    sandbox.codex_command(work, home=home,
                                          usb_root=usb, dev_root=dev)
            (home / ".codex").rename(home / "not-codex")
            with patch.object(sandbox.os, "geteuid", return_value=1000), \
                 patch.object(sandbox.shutil, "which", return_value=sys.executable):
                with self.assertRaisesRegex(
                    sandbox.CodexSandboxDenied, "AUTH_DENIED"
                ):
                    sandbox.codex_command(work, home=home,
                                          usb_root=usb, dev_root=dev)

    def test_symlink_tty_or_private_credential_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            work, home, usb, dev = self.roots(temp)
            (dev / "ttyACM2").unlink()
            (dev / "ttyACM2").symlink_to("/dev/null")
            with patch.object(sandbox.os, "geteuid", return_value=1000), \
                 patch.object(sandbox.shutil, "which", return_value=sys.executable):
                with self.assertRaisesRegex(
                    sandbox.CodexSandboxDenied, "TTY_NODE_DENIED"
                ):
                    sandbox.codex_command(work, home=home,
                                          usb_root=usb, dev_root=dev)

    def test_real_runner_launch_calls_outer_namespace_not_raw_codex(self):
        # Production path selection is selected by the actual subprocess.run
        # identity, not by a prompt or a new Work Order/Session field.
        class Result:
            returncode = 0
            stdout = b""
            stderr = b""
        with tempfile.TemporaryDirectory() as temp:
            work, _, _, _ = self.roots(temp)
            with patch.object(dispatcher.subprocess, "run",
                              return_value=Result()) as run, \
                 patch.object(sandbox, "codex_command",
                              return_value=["bwrap", "--", "codex", "-"]) as outer:
                receipt = dispatcher.run_codex_task(
                    {"objective": "Owner approved development work."},
                    workspace=work, executor=run)
            outer.assert_called_once_with(work)
            self.assertEqual(run.call_args.args[0],
                             ["bwrap", "--", "codex", "-"])
            self.assertEqual(receipt["codex_exit_code"], 0)

    def test_normal_path3_has_no_new_capability_or_session(self):
        import inspect
        source = inspect.getsource(dispatcher.parse_dynamic_work_order)
        self.assertNotIn("codex-lab-usb", source)
        self.assertNotIn("lab-session", source)
        self.assertNotIn("program_limit", source)
        run = inspect.getsource(dispatcher.run_codex_task)
        self.assertIn("plasma_development_codex_sandbox", run)
        self.assertIn("codex_sandbox.codex_command(root)", run)
        self.assertIn("minimum sufficient experiment", run.lower())
        self.assertNotIn("bluepill_flash", run)


if __name__ == "__main__":
    unittest.main()
