from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.gateway_settings import GatewaySettingsController


class GatewaySettingsControllerTests(unittest.TestCase):
    def test_defaults_and_immutable_snapshots(self) -> None:
        controller = GatewaySettingsController()
        frozen = controller.snapshot()
        self.assertEqual(
            controller.current(),
            {"revision": 1, "ppu_request_timeout_ms": 10_000, "ppu_retry_count": 3},
        )

        updated = controller.update({"ppu_request_timeout_ms": 20_000, "ppu_retry_count": 5})
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(frozen.ppu_request_timeout_ms, 10_000)
        self.assertEqual(frozen.ppu_retry_count, 3)

    def test_invalid_values_and_fields_fail_closed(self) -> None:
        controller = GatewaySettingsController()
        candidates = (
            {"ppu_request_timeout_ms": 999, "ppu_retry_count": 3},
            {"ppu_request_timeout_ms": 120_001, "ppu_retry_count": 3},
            {"ppu_request_timeout_ms": True, "ppu_retry_count": 3},
            {"ppu_request_timeout_ms": 10_000, "ppu_retry_count": -1},
            {"ppu_request_timeout_ms": 10_000, "ppu_retry_count": 11},
            {"ppu_request_timeout_ms": 10_000},
            {"ppu_request_timeout_ms": 10_000, "ppu_retry_count": 3, "revision": 9},
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(PlasmaError) as caught:
                controller.update(candidate)
            self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
        self.assertEqual(controller.current()["revision"], 1)

    def test_persistence_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway-settings.yaml"
            first = GatewaySettingsController(path)
            saved = first.update({"ppu_request_timeout_ms": 30_000, "ppu_retry_count": 2})
            self.assertEqual(GatewaySettingsController(path).current(), saved)

    def test_persistence_failure_does_not_apply_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = GatewaySettingsController(Path(directory) / "gateway-settings.yaml")
            before = controller.current()
            with mock.patch.object(controller, "_write_atomic", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    controller.update({"ppu_request_timeout_ms": 15_000, "ppu_retry_count": 1})
            self.assertEqual(controller.current(), before)


if __name__ == "__main__":
    unittest.main()
