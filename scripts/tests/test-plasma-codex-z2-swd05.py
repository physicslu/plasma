#!/usr/bin/env python3
"""No real SSH, sudo, MMIO, FPGA, JTAG or UART. Only fake contracts."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

HERE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("swd05_host",
    HERE / "scripts/plasma-codex-z2-swd05.py")
assert SPEC and SPEC.loader
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class SWD05HostContracts(unittest.TestCase):
    def test_path_canonical_and_no_issue_command_input(self):
        for bad in ("relative", "/", "/root/../etc", "/root/\nsecret", "\0",
                    "../artifacts", ""):
            self.assertFalse(subject.valid_target_path(bad))
        self.assertTrue(subject.valid_target_path("/lib/firmware/candidate.bin"))

    def test_missing_route_blocks_without_ssh(self):
        with patch.object(subject.LOGIN, "private_file", side_effect=ValueError):
            with self.assertRaisesRegex(ValueError, "PRIVATE_ROUTE_NOT_READY"):
                subject.load_route()
        with patch.object(subject, "ssh_execute", side_effect=AssertionError):
            self.assertTrue(subject.valid_target_path("/root/evidence/unique"))

    def test_fake_positive_receipt_requires_all_stages(self):
        from pl.hil.swd04 import contract as c
        states = {k: "PASS" for k in subject.STAGES[:-1]}
        states["overall"] = "PASS_DEVELOPMENT_INTERNAL_FIXTURE"
        receipt = {
            "schema": "plasma.z2.swd05.oneshot.v1",
            "stages": states, "site": 1,
            "candidate_source": c.SOURCE_SHA,
            "candidate_bin_sha256": c.CANDIDATE_BIN_SHA256,
            "recovery_bin_sha256": c.RECOVERY_BIN_SHA256,
            "external_dut": "NOT_RUN", "physical_swd": "NOT_RUN",
        }
        self.assertEqual(subject.sanitize_report(receipt, 0)["site"], 1)
        with self.assertRaises(ValueError):
            subject.sanitize_report(receipt, 2)
        receipt["stages"]["restoration_verified"] = "NOT_RUN"
        with self.assertRaises(ValueError):
            subject.sanitize_report(receipt, 0)
        receipt["stages"]["restoration_verified"] = "PASS"
        receipt["external_dut"] = "PASS"
        with self.assertRaises(ValueError):
            subject.sanitize_report(receipt, 0)

    def test_strict_sudo_adjacent_marker(self):
        import json
        payload = json.dumps({"root": True, "no_hardware_writes": True})
        marker = subject.MARKER + payload
        self.assertEqual(subject.extract_receipt_payload(marker + "\n")["root"], True)
        self.assertEqual(
            subject.extract_receipt_payload(
                "\rPLASMA_SWD05_SUDO_PROMPT:" + marker + "\r\n"),
            {"root": True, "no_hardware_writes": True})
        for invalid in (
            "untrusted:" + marker + "\n",
            "PLASMA_SWD05_SUDO_PROMPT:noise:" + marker + "\n",
            marker + "\n" + marker + "\n",
            "PLASMA_SWD05_SUDO_PROMPT:" + subject.MARKER + "not-json\n",
            marker + "trailing\n",
        ):
            with self.subTest(invalid=invalid[:32]), self.assertRaises(
                    (ValueError, json.JSONDecodeError)):
                subject.extract_receipt_payload(invalid)

    def test_remote_command_only_fixed_exec_and_pins(self):
        with patch.object(subject.Path, "read_bytes", autospec=True) as reader:
            reader.return_value = b"reviewed-test-source"
            route = {
                "source_root": "/opt/plasma/swd05-reviewed",
                "candidate_bit": "/root/reviewed/candidate.bit",
                "candidate_hwh": "/root/reviewed/candidate.hwh",
                "manifest": "/root/reviewed/manifest.json",
                "candidate_bin": "/lib/firmware/approved-swd03.bin",
                "recovery_bin": "/lib/firmware/base.bin",
                "recovery_hwh": "/root/reviewed/base.hwh",
                "output": "/root/evidence/fresh",
            }
            command = subject.fixed_remote_cmd(route)
        self.assertNotIn("PRIVATE_DO_NOT_PRINT", command)
        self.assertIn("sha256sum", command)
        self.assertIn("sudo -S", command)
        self.assertIn("pl.hil.swd04.one_shot", command)
        self.assertNotIn("uhubctl", command)
        self.assertNotIn("openocd", command)


class SingleLoginCredentialContracts(unittest.TestCase):
    """No SSH/network: exercise local credential consolidation and denial."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "plasma"
        self.directory.mkdir(mode=0o700)
        self.login = self.directory / "z2-login-smoke.json"
        self.known = self.directory / "z2-login-known_hosts"
        self.legacy = self.directory / "z2-dev-credentials.json"
        self.route = self.directory / "z2-swd05-oneshot.json"
        self.save(self.known, "z2.example ssh-ed25519 TEST-ONLY-KEY\\n")

    def save(self, path, content):
        path.write_text(content if isinstance(content, str) else
                        json.dumps(content, sort_keys=True))
        path.chmod(0o600)

    def mocked_local(self):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(subject.LOGIN, "FILE", self.login))
        stack.enter_context(patch.object(subject.LOGIN, "KNOWN_HOSTS", self.known))
        stack.enter_context(patch.object(subject, "ROUTE", self.route))
        stack.enter_context(patch.object(subject.LOGIN, "expect_worker"))
        stack.enter_context(patch.object(subject.LOGIN.sys, "stdin",
                                         Mock(isatty=lambda: True)))
        stack.enter_context(patch.dict(os.environ, {"GITHUB_ACTIONS": "", "RUNNER_NAME": ""}))
        stack.enter_context(patch.object(subject.LOGIN.pwd, "getpwnam",
                                         return_value=Mock(pw_uid=os.geteuid())))
        ssh = stack.enter_context(patch.object(subject.LOGIN.subprocess, "Popen"))
        ssh.return_value.__enter__.return_value.wait.return_value = 0

    def test_migrate_distinct_sudo_without_second_credential_file(self):
        login = {"ssh_host": "z2.example", "ssh_username": "xilinx",
                 "ssh_password": "fake-ssh"}
        self.save(self.login, login)
        self.save(self.legacy, dict(login, sudo_password="fake-sudo"))
        route = {"source_root": "/opt/plasma/reviewed",
                 "candidate_bit": "/root/r.bit",
                 "candidate_hwh": "/root/r.hwh",
                 "manifest": "/root/m.json",
                 "candidate_bin": "/lib/firmware/c.bin",
                 "recovery_bin": "/lib/firmware/base.bin",
                 "recovery_hwh": "/root/base.hwh",
                 "output": "/root/evidence",
                 "sudo_password": "fake-sudo"}
        self.save(self.route, route)
        self.mocked_local()
        subject.LOGIN.consolidate_credentials()
        self.assertFalse(self.legacy.exists())
        single = json.loads(self.login.read_text())
        self.assertEqual(single["sudo_password"], "fake-sudo")
        self.assertNotIn("sudo_password", json.loads(self.route.read_text()))
        self.assertEqual(subject.load_route()["source_root"], route["source_root"])
        self.assertEqual(subject.LOGIN.creds()["ssh_host"], "z2.example")
        self.assertTrue(self.known.exists())

    def test_different_legacy_host_rejects_without_deleting_anything(self):
        login = {"ssh_host": "z2.example", "ssh_username": "xilinx",
                 "ssh_password": "fake-ssh"}
        self.save(self.login, login)
        self.save(self.legacy, dict(login, ssh_host="different.example",
                                    sudo_password="fake-sudo"))
        self.mocked_local()
        before = self.login.read_bytes()
        with self.assertRaisesRegex(ValueError, "LEGACY_Z2_CREDENTIAL_CONFLICT"):
            subject.LOGIN.consolidate_credentials()
        self.assertTrue(self.legacy.exists())
        self.assertEqual(self.login.read_bytes(), before)

    def test_conflicting_sudo_secrets_abort_without_credential_changes(self):
        login = {"ssh_host": "z2.example", "ssh_username": "xilinx",
                 "ssh_password": "fake-ssh"}
        self.save(self.login, login)
        self.save(self.legacy, dict(login, sudo_password="sudo-from-old-login"))
        self.save(self.route, {"source_root": "/opt/plasma/reviewed",
                 "candidate_bit": "/root/r.bit", "candidate_hwh": "/root/r.hwh",
                 "manifest": "/root/m.json", "candidate_bin": "/lib/firmware/c.bin",
                 "recovery_bin": "/lib/firmware/base.bin", "recovery_hwh": "/root/base.hwh",
                 "output": "/root/evidence", "sudo_password": "different-sudo"})
        self.mocked_local()
        original = self.route.read_bytes()
        with self.assertRaisesRegex(ValueError, "LEGACY_SUDO_CREDENTIAL_CONFLICT"):
            subject.LOGIN.consolidate_credentials()
        self.assertTrue(self.legacy.exists())
        self.assertEqual(self.route.read_bytes(), original)
        self.assertNotIn("sudo_password", json.loads(self.login.read_text()))


if __name__ == "__main__":
    unittest.main()
