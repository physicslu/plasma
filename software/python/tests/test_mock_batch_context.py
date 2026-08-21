from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_core.mock_profile import DEFAULT_MOCK_PROFILE
from plasma_core.mock_profile_io import mock_profile_to_dict
from plasma_web.shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


def settings(seed: int, program_error_per_mille: int) -> dict[str, object]:
    profile = mock_profile_to_dict(DEFAULT_MOCK_PROFILE)
    operations = {
        name: {
            **values,
            "error_rate_per_mille": program_error_per_mille if name == "program" else 0,
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
        "seed": {"mode": "fixed", "fixed_seed": seed},
    }


class MockBatchContextTests(unittest.TestCase):
    def test_batch_context_stays_frozen_across_later_settings_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SharedImageMockEngineeringPPUProvider(Path(directory), flash_size_bytes=64 * 1024)
            provider.update_mock_runtime_settings(settings(111, 50))
            first = provider.freeze_batch_context("batch-a")
            self.assertEqual(first["profile"]["revision"], 2)
            self.assertEqual(first["profile"]["operations"]["program"]["error_rate_per_mille"], 50)
            self.assertEqual(first["resolved_seed"], 111)

            provider.update_mock_runtime_settings(settings(222, 75))
            repeated = provider.freeze_batch_context("batch-a")
            second = provider.freeze_batch_context("batch-b")

            self.assertEqual(repeated, first)
            self.assertEqual(second["profile"]["revision"], 3)
            self.assertEqual(second["profile"]["operations"]["program"]["error_rate_per_mille"], 75)
            self.assertEqual(second["resolved_seed"], 222)


if __name__ == "__main__":
    unittest.main()
