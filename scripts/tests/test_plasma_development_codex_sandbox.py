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
    def test_z2_sources_readonly_after_mask_and_invalid_sources_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            work, home, usb, dev = self.roots(temp)
            for p in dev.glob('tty*'):
                p.unlink()
            plasma = home / '.config/plasma'
            plasma.mkdir(parents=True, mode=0o700)
            sources = [plasma / name for name in (
                'z2-login-smoke.json', 'z2-login-known_hosts')]
            for source in sources:
                source.touch(mode=0o600)
            unrelated = plasma / 'unrelated-secret'
            unrelated.touch(mode=0o600)
            with patch.object(sandbox.shutil, 'which', return_value=sys.executable):
                args = sandbox.codex_command(work, home=home,
                                             usb_root=usb, dev_root=dev)
                mask = next(i for i in range(len(args)-1)
                            if args[i:i+2] == ['--tmpfs', str(plasma)])
                # The mounted Z2 credential directory must satisfy the same
                # 0700 parent requirement as Path 2 enrollment().
                self.assertEqual(args[mask-2:mask], ['--perms', '0700'])
                self.assertEqual(args.count('--perms'), 1)
                self.assertEqual(plasma.stat().st_mode & 0o777, 0o700)
                # Only this private mask changes; other directories retain
                # their existing tmpfs operations and isolation.
                ssh = home / '.ssh'
                self.assertIn(['--tmpfs', str(ssh)],
                              [args[j:j+2] for j in range(len(args)-1)])
                for source in sources:
                    mount = next(i for i in range(len(args)-2)
                                 if args[i:i+3] == ['--ro-bind', str(source), str(source)])
                    self.assertGreater(mount, mask)
                self.assertNotIn(str(unrelated), args)
                self.assertIn('SSH_AUTH_SOCK', args)
                sources[0].chmod(0o644)
                with self.assertRaisesRegex(sandbox.CodexSandboxDenied, 'Z2_SOURCE_DENIED'):
                    sandbox.codex_command(work, home=home, usb_root=usb, dev_root=dev)
                sources[0].unlink()
                sources[0].symlink_to(unrelated)
                with self.assertRaisesRegex(sandbox.CodexSandboxDenied, 'Z2_SOURCE_DENIED'):
                    sandbox.codex_command(work, home=home, usb_root=usb, dev_root=dev)
                sources[0].unlink()
                plasma.chmod(0o755)
                with self.assertRaisesRegex(sandbox.CodexSandboxDenied, 'Z2_DIRECTORY_DENIED'):
                    sandbox.codex_command(work, home=home, usb_root=usb, dev_root=dev)

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
        self.assertNotIn("--sandbox", args)
        self.assertNotIn("--ask-for-approval", args)
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

    def test_real_runner_launch_pins_workspace_write(self):
        class Result:
            returncode = 0
            stdout = b""
            stderr = b""
        with tempfile.TemporaryDirectory() as temp:
            work, _, _, _ = self.roots(temp)
            with patch.object(dispatcher.subprocess, "run",
                              return_value=Result()) as run, \
                 patch.object(sandbox, "codex_command",
                              side_effect=AssertionError("unexpected sandbox")) as outer:
                receipt = dispatcher.run_codex_task(
                    {"objective": "Owner approved development work."},
                    workspace=work, executor=run)
            outer.assert_not_called()
            self.assertEqual(run.call_args.args[0],
                             ["codex", "exec", "--json", "--sandbox", "workspace-write", "-"])
            self.assertEqual(receipt["codex_exit_code"], 0)

    def test_sandbox_error_receipt_is_constant_not_a_host_path(self):
        safe = dispatcher.safe_error_reason(
            sandbox.CodexSandboxDenied("CODEX_SANDBOX_BWRAP_UNAVAILABLE"))
        self.assertEqual(safe, "CODEX_SANDBOX_BWRAP_UNAVAILABLE")
        unsafe = dispatcher.safe_error_reason(
            sandbox.CodexSandboxDenied("CODEX_SANDBOX_ERROR /home/private"))
        self.assertEqual(unsafe, "EXECUTION_ERROR")

    def test_readonly_probe_launches_namespace_not_codex_or_device_operation(self):
        import subprocess
        from unittest.mock import call
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with patch.object(sandbox, "codex_command", return_value=[
                "bwrap", "--dev", "/dev", "--dev-bind",
                "/dev/bus/usb", "/dev/bus/usb", "--chdir", str(work),
                "--", "codex", "exec", "-"
            ]) as builder, patch.object(subprocess, "run",
                return_value=subprocess.CompletedProcess(
                    ["bwrap"], 0, b"PATH3_NAMESPACE_VISIBLE\n", b"")
            ) as runner:
                result = sandbox.readonly_probe(work)
            builder.assert_called_once_with(work)
            self.assertEqual(result["status"], "NAMESPACE_VISIBLE_ONLY")
            self.assertEqual(result["hardware_io"], "NOT_RUN")
            self.assertEqual(result["codex_model"], "NOT_RUN")
            args = runner.call_args.args[0]
            self.assertEqual(args[0], "bwrap")
            self.assertEqual(args[args.index("--") + 1], sys.executable)
            self.assertNotIn("codex", args)
            self.assertEqual(runner.call_args.kwargs["timeout"], 20)
            self.assertEqual(runner.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_readonly_probe_rejects_bad_exit_and_omits_stderr(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with patch.object(sandbox, "codex_command",
                              return_value=["bwrap", "--", "codex"]), \
                 patch.object(subprocess, "run",
                              return_value=subprocess.CompletedProcess(
                                  ["bwrap"], 1, b"", b"secret /home/operator")):
                result = sandbox.readonly_probe(work)
            self.assertEqual(result["status"], "NOT_RUN_OR_FAIL")
            self.assertEqual(result["reason"], "CODEX_SANDBOX_PROBE_FAILED")
            self.assertNotIn("secret", str(result))
            with patch.object(sandbox, "codex_command",
                              side_effect=sandbox.CodexSandboxDenied(
                                  "CODEX_SANDBOX_BWRAP_UNAVAILABLE")):
                denied = sandbox.readonly_probe(work)
            self.assertEqual(denied["reason"],
                             "CODEX_SANDBOX_BWRAP_UNAVAILABLE")
            self.assertEqual(sandbox.main(["--unknown"]), 2)

    def test_normal_path3_has_no_new_capability_or_session(self):
        import inspect
        source = inspect.getsource(dispatcher.parse_dynamic_work_order)
        self.assertNotIn("codex-lab-usb", source)
        self.assertNotIn("lab-session", source)
        self.assertNotIn("program_limit", source)
        run = inspect.getsource(dispatcher.run_codex_task)
        self.assertNotIn("plasma_development_codex_sandbox", run)
        self.assertIn('["codex", "exec", "--json", "--sandbox", "workspace-write", "-"]', run)
        self.assertNotIn("bluepill_flash", run)


if __name__ == "__main__":
    unittest.main()
