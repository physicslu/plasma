#!/usr/bin/env python3
"""No real network or serial IO. Offline owner-provisioning and mapping tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

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
        # Owner's real picocom evidence: two Enter presses produce the
        # interactive 'xilinx@pynq:~        with patch.object(subject, "private_file", side_effect=ValueError("no file")):
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

    def test_no_hardware_activity_during_self_test(self) -> None:
        with patch.object(subject, "ssh_login", side_effect=AssertionError):
            with patch.object(subject, "uart_login", side_effect=AssertionError):
                subject.self_test()


if __name__ == "__main__":
    unittest.main()
 prompt. A single CRLF is not equivalent.
        with patch.object(subject.os, "write") as sender:
            with patch.object(subject.time, "sleep") as pause:
                subject.wake_uart_console(17, pause_seconds=0.35)
        self.assertEqual(sender.call_args_list, [
            call(17, b"\r"), call(17, b"\r"),
        ])
        pause.assert_called_once_with(0.35)

    def test_real_uart_shell_prompt_and_stage_schema(self) -> None:
        # Terminal-ready behavior is prompt-preserving; no password prompt
        # should be required for an already authenticated console.
        import re
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

    def test_no_hardware_activity_during_self_test(self) -> None:
        with patch.object(subject, "ssh_login", side_effect=AssertionError):
            with patch.object(subject, "uart_login", side_effect=AssertionError):
                subject.self_test()


if __name__ == "__main__":
    unittest.main()
