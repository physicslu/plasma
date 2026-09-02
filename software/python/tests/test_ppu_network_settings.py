from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.ppu_network_settings import PPUNetworkSettingsController


class PPUNetworkSettingsControllerTests(unittest.TestCase):
    def test_default_is_unapplied_dhcp_desired_state(self) -> None:
        controller = PPUNetworkSettingsController()
        self.assertEqual(
            controller.current(),
            {
                "revision": 1,
                "interface": "eth0",
                "mode": "dhcp",
                "address": None,
                "prefix_length": None,
                "gateway": None,
                "dns_servers": [],
            },
        )

    def test_static_configuration_is_normalized_and_revisioned(self) -> None:
        controller = PPUNetworkSettingsController()
        saved = controller.update(
            {
                "mode": "static",
                "address": "192.168.10.21",
                "prefix_length": 24,
                "gateway": "192.168.10.1",
                "dns_servers": ["192.168.10.1", "8.8.8.8"],
            }
        )
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(saved["interface"], "eth0")
        self.assertEqual(saved["mode"], "static")
        self.assertEqual(saved["address"], "192.168.10.21")
        self.assertEqual(saved["prefix_length"], 24)
        self.assertEqual(saved["gateway"], "192.168.10.1")
        self.assertEqual(saved["dns_servers"], ["192.168.10.1", "8.8.8.8"])

    def test_dhcp_requires_static_fields_to_be_empty(self) -> None:
        controller = PPUNetworkSettingsController()
        invalid = (
            {
                "mode": "dhcp",
                "address": "192.168.10.21",
                "prefix_length": None,
                "gateway": None,
                "dns_servers": [],
            },
            {
                "mode": "dhcp",
                "address": None,
                "prefix_length": None,
                "gateway": None,
                "dns_servers": ["8.8.8.8"],
            },
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(PlasmaError) as caught:
                controller.update(candidate)
            self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_static_validation_fails_closed(self) -> None:
        controller = PPUNetworkSettingsController()
        invalid = (
            {
                "mode": "static",
                "address": "192.168.10.0",
                "prefix_length": 24,
                "gateway": "192.168.10.1",
                "dns_servers": [],
            },
            {
                "mode": "static",
                "address": "192.168.10.21",
                "prefix_length": 24,
                "gateway": "192.168.11.1",
                "dns_servers": [],
            },
            {
                "mode": "static",
                "address": "192.168.10.21",
                "prefix_length": 24,
                "gateway": "192.168.10.21",
                "dns_servers": [],
            },
            {
                "mode": "static",
                "address": "192.168.10.21",
                "prefix_length": 33,
                "gateway": None,
                "dns_servers": [],
            },
            {
                "mode": "static",
                "address": "not-an-ip",
                "prefix_length": 24,
                "gateway": None,
                "dns_servers": [],
            },
            {
                "mode": "static",
                "address": "192.168.10.21",
                "prefix_length": 24,
                "gateway": None,
                "dns_servers": ["8.8.8.8", "8.8.8.8"],
            },
            {
                "mode": "static",
                "address": "192.168.10.21",
                "prefix_length": 24,
                "gateway": None,
                "dns_servers": ["1.1.1.1", "8.8.8.8", "9.9.9.9", "4.4.4.4"],
            },
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(PlasmaError) as caught:
                controller.update(candidate)
            self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
        self.assertEqual(controller.current()["revision"], 1)

    def test_unknown_or_missing_fields_are_rejected(self) -> None:
        controller = PPUNetworkSettingsController()
        with self.assertRaises(PlasmaError) as caught:
            controller.update(
                {
                    "mode": "static",
                    "address": "192.168.10.21",
                    "prefix_length": 24,
                    "gateway": None,
                    "dns_servers": [],
                    "interface": "eth1",
                }
            )
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_persistence_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ppu-network-settings.yaml"
            first = PPUNetworkSettingsController(path)
            saved = first.update(
                {
                    "mode": "static",
                    "address": "10.20.30.40",
                    "prefix_length": 24,
                    "gateway": "10.20.30.1",
                    "dns_servers": ["1.1.1.1"],
                }
            )
            self.assertEqual(PPUNetworkSettingsController(path).current(), saved)

    def test_persistence_failure_does_not_apply_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = PPUNetworkSettingsController(Path(directory) / "ppu-network-settings.yaml")
            before = controller.current()
            with mock.patch.object(controller, "_write_atomic", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    controller.update(
                        {
                            "mode": "static",
                            "address": "192.168.10.21",
                            "prefix_length": 24,
                            "gateway": "192.168.10.1",
                            "dns_servers": [],
                        }
                    )
            self.assertEqual(controller.current(), before)

    def test_corrupt_persistence_fails_startup_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ppu-network-settings.yaml"
            path.write_text("mode: static\naddress: 192.168.10.21\n", encoding="utf-8")
            with self.assertRaises(PlasmaError) as caught:
                PPUNetworkSettingsController(path)
            self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)


if __name__ == "__main__":
    unittest.main()
