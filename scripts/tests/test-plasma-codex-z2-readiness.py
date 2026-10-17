#!/usr/bin/env python3
"""Purely offline contract tests; never open SSH, serial, MMIO or other devices."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "plasma-codex-z2-readiness.py"
SPEC = importlib.util.spec_from_file_location("z2_readiness", SCRIPT)
assert SPEC and SPEC.loader
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


def example() -> dict:
    return {
        "schema": "plasma.z2.readiness.remote.v1",
        "remote_user_is_xilinx": True,
        "os_linux": True,
        "machine_armv7": True,
        "device_tree_zynq7000": True,
        "device_tree_board_model_available": False,
        "fpga_manager_state": "OPERATING",
        "uio": {"count": 2, "fabric_detected": True, "audio_codec_detected": True},
        "fclk0": {"visibility": "NOT_OBSERVED_UNPRIVILEGED", "hz": None},
        "services": {
            name: "ACTIVE" for name in (
                "plasma-bootstrap", "plasma-server", "plasma-web",
                "plasma-runtime-activation",
            )
        },
    }


class ReadinessContracts(unittest.TestCase):
    def test_synthetic_identity_and_operating_fpga_is_partial_only(self):
        report = subject.summarize(subject.validate_remote(example()))
        self.assertEqual(report["baseline_result"], "BASELINE_PASS_PARTIAL")
        self.assertFalse(report["hardware_go"])
        self.assertEqual(report["bitstream_identity"], "NOT_QUALIFIED")
        self.assertEqual(report["board_identity_exact"], "NOT_QUALIFIED")
        self.assertEqual(report["mmio_access"], "NOT_RUN")
        self.assertEqual(report["fpga_reload"], "NOT_RUN")
        self.assertEqual(report["uart"], "NON_BLOCKING_NOT_RUN")

    def test_unavailable_fclk_not_fabricated(self):
        report = subject.summarize(subject.validate_remote(example()))
        self.assertEqual(report["clock_fclk0"]["visibility"], "NOT_OBSERVED_UNPRIVILEGED")
        self.assertIsNone(report["clock_fclk0"]["hz"])

    def test_kernel_or_board_identity_fail_closed(self):
        for field in ("remote_user_is_xilinx", "os_linux", "machine_armv7",
                      "device_tree_zynq7000"):
            case = example()
            case[field] = False
            self.assertEqual(
                subject.summarize(subject.validate_remote(case))["baseline_result"],
                "BASELINE_BLOCKED", field)
        case = example()
        case["fpga_manager_state"] = "NOT_OPERATING"
        self.assertEqual(
            subject.summarize(subject.validate_remote(case))["baseline_result"],
            "BASELINE_BLOCKED")

    def test_untrusted_or_invalid_remote_json_rejected(self):
        for key, value in (
            ("schema", "invalid.schema"),
            ("remote_user_is_xilinx", "true"),
            ("fpga_manager_state", "UNKNOWN_UNVALIDATED"),
            ("uio", {"count": -1}),
            ("fclk0", {"visibility": "OBSERVED", "hz": None}),
            ("services", {"evil": "ACTIVE"}),
        ):
            case = example()
            case[key] = value
            with self.assertRaises(ValueError, msg=key):
                subject.validate_remote(case)
        case = example()
        case["ssh_password"] = "unexpected secret"
        with self.assertRaises(ValueError):
            subject.validate_remote(case)

    def test_remote_observer_does_not_use_hardware_control_paths(self):
        code = subject.REMOTE_PY
        for forbidden in (
            "/dev/", "sudo", "uhubctl", "fpga_manager/flags",
            "fpga_manager/firmware", "mmap", "i2c", "openocd",
            "reboot", "poweroff",
        ):
            self.assertNotIn(forbidden, code, forbidden)
        for required in ("/sys/class/fpga_manager", "/sys/class/uio",
                         "/proc/device-tree/compatible", "systemctl",
                         "clk_rate"):
            self.assertIn(required, code)

    def test_validation_never_uses_ssh_or_devices(self):
        with patch.object(subject, "bounded_ssh_probe", side_effect=AssertionError):
            with patch.object(subject.LOGIN, "creds", side_effect=AssertionError):
                case = example()
                self.assertEqual(
                    subject.summarize(subject.validate_remote(case))["baseline_result"],
                    "BASELINE_PASS_PARTIAL")


if __name__ == "__main__":
    unittest.main()
