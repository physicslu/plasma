from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_profile import DEFAULT_MOCK_PROFILE
from plasma_core.mock_profile_io import mock_profile_to_dict
from plasma_core.models import JobRequest
from plasma_interfaces.mock import MockInterface
from plasma_web.mock_runtime_settings import MockRuntimeSettingsController


def editable_settings(*, error_rate_per_mille: int = 0, seed_mode: str = "fixed", fixed_seed: int | None = 1234):
    profile = mock_profile_to_dict(DEFAULT_MOCK_PROFILE)
    operations = {
        name: {
            **values,
            "error_rate_per_mille": error_rate_per_mille,
            "base_time_ms": 0,
            "throughput_bytes_per_second": 64 * 1024 * 1024,
            "jitter_ms": 0,
        }
        for name, values in profile["operations"].items()
    }
    return {
        "enabled": True,
        "default_image_size_bytes": 64 * 1024,
        "operations": operations,
        "seed": {"mode": seed_mode, "fixed_seed": fixed_seed},
    }


class MockRuntimeSettingsControllerTests(unittest.TestCase):
    def test_default_contract_matches_foundation_profile(self) -> None:
        controller = MockRuntimeSettingsController()
        current = controller.current()
        self.assertEqual(current["profile_id"], DEFAULT_MOCK_PROFILE.profile_id)
        self.assertEqual(current["revision"], DEFAULT_MOCK_PROFILE.revision)
        self.assertEqual(current["operations"]["erase"]["error_rate_per_mille"], 1)
        self.assertEqual(current["operations"]["program"]["error_rate_per_mille"], 50)
        self.assertEqual(current["seed"], {"mode": "auto", "fixed_seed": None})

    def test_update_increments_revision_and_fixed_seed_is_stable(self) -> None:
        controller = MockRuntimeSettingsController()
        updated = controller.update(editable_settings(error_rate_per_mille=75, fixed_seed=987654))
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["operations"]["program"]["error_rate_per_mille"], 75)
        first = controller.execution_snapshot("batch-a")
        second = controller.execution_snapshot("batch-b")
        self.assertEqual(first["resolved_seed"], 987654)
        self.assertEqual(second["resolved_seed"], 987654)
        self.assertEqual(first["profile"]["revision"], 2)

    def test_invalid_image_step_and_seed_fail_closed(self) -> None:
        controller = MockRuntimeSettingsController()
        invalid = editable_settings()
        invalid["default_image_size_bytes"] = 65 * 1024
        with self.assertRaises(PlasmaError) as caught:
            controller.update(invalid)
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

        invalid = editable_settings(seed_mode="fixed", fixed_seed=None)
        with self.assertRaises(PlasmaError) as caught:
            controller.update(invalid)
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_persistence_round_trip_keeps_revision_and_seed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mock-runtime.yaml"
            first = MockRuntimeSettingsController(path)
            saved = first.update(editable_settings(error_rate_per_mille=10, fixed_seed=77))
            second = MockRuntimeSettingsController(path)
            self.assertEqual(second.current(), saved)


class MockInterfaceProfileExecutionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def request_metadata(*, error_rate_per_mille: int, batch_seed: int = 1234) -> dict[str, object]:
        editable = editable_settings(error_rate_per_mille=error_rate_per_mille, fixed_seed=batch_seed)
        controller = MockRuntimeSettingsController()
        profile = controller.update(editable)
        profile.pop("seed")
        return {
            "mock_runtime": {
                "profile": profile,
                "resolved_seed": batch_seed,
                "batch_id": "batch-deterministic",
                "facility_id": "mock-facility-01",
                "ppu_id": "mock-facility-01-ppu-01",
                "site_id": 1,
                "round_index": 1,
            }
        }

    async def test_profile_failure_is_injected_and_attempt_specific(self) -> None:
        interface = MockInterface(flash_size=64 * 1024, progress_steps=1)
        request = JobRequest(
            site_id=1,
            operation=Operation.ERASE,
            metadata=self.request_metadata(error_rate_per_mille=1000),
        )
        interface.prepare_request(request)
        with self.assertRaises(PlasmaError) as first:
            await interface.erase()
        self.assertEqual(first.exception.context["failure_source"], "injected")
        self.assertEqual(first.exception.context["attempt"], 1)
        self.assertEqual(first.exception.context["profile_revision"], 2)

        interface.prepare_request(request)
        with self.assertRaises(PlasmaError) as retry:
            await interface.erase()
        self.assertEqual(retry.exception.context["attempt"], 2)

    async def test_zero_error_profile_executes_without_injected_failure(self) -> None:
        interface = MockInterface(flash_size=64 * 1024, progress_steps=1)
        request = JobRequest(
            site_id=1,
            operation=Operation.ERASE,
            metadata=self.request_metadata(error_rate_per_mille=0),
        )
        interface.prepare_request(request)
        await interface.erase()
        self.assertEqual(interface.calls["erase"], 1)


if __name__ == "__main__":
    unittest.main()
