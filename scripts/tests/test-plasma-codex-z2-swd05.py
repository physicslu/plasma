#!/usr/bin/env python3
"""No real SSH, sudo, MMIO, FPGA, JTAG or UART. Only fake contracts."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

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
                "sudo_password": "PRIVATE_DO_NOT_PRINT",
            }
            command = subject.fixed_remote_cmd(route)
        self.assertNotIn("PRIVATE_DO_NOT_PRINT", command)
        self.assertIn("sha256sum", command)
        self.assertIn("sudo -S", command)
        self.assertIn("pl.hil.swd04.one_shot", command)
        self.assertNotIn("uhubctl", command)
        self.assertNotIn("openocd", command)


if __name__ == "__main__":
    unittest.main()
