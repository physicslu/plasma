#!/usr/bin/env python3
"""No real network or serial IO. Offline owner-provisioning and mapping tests."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

HERE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "plasma_codex_z2_login", HERE / "scripts/plasma-codex-z2-login.py")
assert SPEC and SPEC.loader
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class Z2LoginContracts(unittest.TestCase):
    def test_uses_only_ft2232_channel_b(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            usb = base / "usb"
            usb.mkdir()
            (usb / "idVendor").write_text("0403")
            (usb / "idProduct").write_text("6010")
            interface = usb / "1-1.2:1.1"
            interface.mkdir()
            (interface / "bInterfaceNumber").write_text("01")
            dev = interface / "ttyUSB23"
            dev.mkdir()
            tty_root = base / "ttys"
            (tty_root / "ttyUSB23").mkdir(parents=True)
            (tty_root / "ttyUSB23" / "device").symlink_to(dev)
            self.assertEqual(subject.uart_candidates(tty_root),
                             [Path("/dev/ttyUSB23")])
            (interface / "bInterfaceNumber").write_text("00")
            self.assertEqual(subject.uart_candidates(tty_root), [])
            (interface / "bInterfaceNumber").write_text("01")
            (usb / "idProduct").write_text("9999")
            self.assertEqual(subject.uart_candidates(tty_root), [])

    def test_uart_wake_requires_two_separate_enter_keypresses(self) -> None:
        # Owner's picocom evidence: two Enter presses produce the
        # interactive 'xilinx@pynq:~$' prompt. CRLF is not two CR keys.
        with patch.object(subject.os, "write") as sender:
            with patch.object(subject.time, "sleep") as pause:
                subject.wake_uart_console(17, pause_seconds=0.35)
        self.assertEqual(sender.call_args_list, [
            call(17, b"\r"), call(17, b"\r"),
        ])
        pause.assert_called_once_with(0.35)

    def test_z2_interactive_shell_prompt_format(self) -> None:
        # A preauthenticated UART shell must not be asked for a password.
        prompt = "\r\nxilinx@pynq:~$ "
        self.assertRegex(
            prompt,
            r"(?m)(?:^|[\r\n])[\w.-]+@[\w.-]+:[^\r\n]{0,70}\$\s*$",
        )

    def test_missing_private_credentials_never_guess_host(self) -> None:
        with patch.object(subject, "private_file", side_effect=ValueError("no file")):
            with self.assertRaisesRegex(ValueError, "PRIVATE_CREDENTIAL_OR_HOST_KEY_NOT_READY"):
                subject.creds()

    def test_atomic_secret_creation_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "private.json"
            subject.atomic_private_create(target, b"secret")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                subject.atomic_private_create(target, b"new secret")
            self.assertEqual(target.read_bytes(), b"secret")

    def test_consolidation_ignores_retired_swd05_route(self) -> None:
        """An obsolete/malformed SWD-05 path file must not block SSH consolidation."""
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            base.chmod(0o700)
            login = base / "z2-login-smoke.json"
            pinned = base / "z2-login-known_hosts"
            legacy = base / "z2-dev-credentials.json"
            retired = base / "z2-swd05-oneshot.json"
            current = {"ssh_host": "z2.example", "ssh_username": "xilinx",
                       "ssh_password": "fake-ssh"}
            for path, data in (
                (login, json.dumps(current)),
                (pinned, "z2.example ssh-ed25519 TEST-ONLY-KEY\\n"),
                (legacy, json.dumps(dict(current, sudo_password="fake-sudo"))),
                (retired, '{"legacy-swd05":"not-a-valid-route"}'),
            ):
                path.write_text(data)
                path.chmod(0o600)
            with patch.object(subject, "FILE", login), \
                 patch.object(subject, "KNOWN_HOSTS", pinned), \
                 patch.object(subject, "expect_worker"), \
                 patch.object(subject.sys, "stdin", Mock(isatty=lambda: True)), \
                 patch.dict(os.environ, {"GITHUB_ACTIONS": "", "RUNNER_NAME": ""}), \
                 patch.object(subject.pwd, "getpwnam", return_value=Mock(pw_uid=os.geteuid())), \
                 patch.object(subject.subprocess, "Popen") as ssh_key:
                ssh_key.return_value.__enter__.return_value.wait.return_value = 0
                subject.consolidate_credentials()
                self.assertFalse(legacy.exists())
                self.assertEqual(json.loads(login.read_text())["sudo_password"],
                                 "fake-sudo")
                self.assertEqual(retired.read_text(),
                                 '{"legacy-swd05":"not-a-valid-route"}')

    def test_conflicting_legacy_login_does_not_delete_anything(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            base.chmod(0o700)
            login = base / "z2-login-smoke.json"
            pinned = base / "z2-login-known_hosts"
            legacy = base / "z2-dev-credentials.json"
            original = {"ssh_host": "z2.example", "ssh_username": "xilinx",
                        "ssh_password": "fake-ssh"}
            login.write_text(json.dumps(original))
            legacy.write_text(json.dumps(dict(original, ssh_host="different.example",
                                              sudo_password="fake-sudo")))
            pinned.write_text("z2.example ssh-ed25519 TEST-ONLY-KEY\\n")
            for p in (login, pinned, legacy):
                p.chmod(0o600)
            with patch.object(subject, "FILE", login), \
                 patch.object(subject, "KNOWN_HOSTS", pinned), \
                 patch.object(subject, "expect_worker"), \
                 patch.object(subject.sys, "stdin", Mock(isatty=lambda: True)), \
                 patch.dict(os.environ, {"GITHUB_ACTIONS": "", "RUNNER_NAME": ""}), \
                 patch.object(subject.pwd, "getpwnam", return_value=Mock(pw_uid=os.geteuid())), \
                 patch.object(subject.subprocess, "Popen") as ssh_key:
                ssh_key.return_value.__enter__.return_value.wait.return_value = 0
                before = legacy.read_bytes()
                with self.assertRaisesRegex(ValueError, "LEGACY_Z2_CREDENTIAL_CONFLICT"):
                    subject.consolidate_credentials()
                self.assertEqual(legacy.read_bytes(), before)
                self.assertNotIn("sudo_password", json.loads(login.read_text()))

    def test_retired_dedicated_workflow_cannot_be_redispatched(self) -> None:
        # GitHub-hosted offline only: preserve protected shared source, retire
        # only the historical owner-triggered SWD-05 dispatch path.
        retired = (
            ".github/workflows/plasma-codex-z2-swd05.yml",
            "scripts/plasma-codex-z2-swd05-contract.py",
            "scripts/plasma-codex-z2-swd05.py",
            "scripts/plasma-codex-z2-swd05.sh",
            "scripts/plasma-codex-z2-swd05-inner.sh",
            "scripts/tests/test-plasma-codex-z2-swd05.py",
        )
        for path in retired:
            with self.subTest(path=path):
                self.assertFalse((HERE / path).exists())
        for needed in (
            "pl/hil/swd04/one_shot.py",
            "pl/hil/path2_z2_target_guard.py",
            "scripts/z2/plasma-path2-root-entry",
            "scripts/plasma_development_stage_transport.py",
            "software/python/plasma_interfaces/swd_transaction.py",
            ".github/workflows/pl-swd05-linux-driver.yml",
        ):
            with self.subTest(needed=needed):
                self.assertTrue((HERE / needed).is_file())
        for wf in (HERE / ".github/workflows").glob("*.yml"):
            with self.subTest(workflow=wf.name):
                self.assertNotIn("/plasma-codex z2-swd05 981", wf.read_text())
        self.assertNotIn("z2-swd05-oneshot.json",
                         (HERE / "scripts/plasma-codex-z2-login.py").read_text())

    def test_no_hardware_activity_during_self_test(self) -> None:
        with patch.object(subject, "ssh_login", side_effect=AssertionError):
            with patch.object(subject, "uart_login", side_effect=AssertionError):
                subject.self_test()


if __name__ == "__main__":
    unittest.main()
