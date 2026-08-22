from __future__ import annotations

import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from plasma_core.assets import ProgrammingAsset
from plasma_core.batch import BatchExecutionPolicy, BatchTarget
from plasma_core.enums import Operation
from plasma_core.models import JobRequest
from plasma_web.mock_batch_runtime import MockAwareBatchRuntimeManager
from plasma_web.mock_synthetic_image import build_synthetic_mock_asset
from plasma_web.shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


def zero_error_settings(size_bytes: int) -> dict[str, object]:
    return {
        "enabled": True,
        "default_image_size_bytes": size_bytes,
        "operations": {
            operation: {
                "error_rate_per_mille": 0,
                "base_time_ms": 0,
                "throughput_bytes_per_second": 64 * 1024 * 1024,
                "jitter_ms": 0,
            }
            for operation in ("erase", "program", "verify", "read")
        },
        "seed": {"mode": "fixed", "fixed_seed": 424242},
    }


def user_asset(data: bytes) -> ProgrammingAsset:
    return ProgrammingAsset.from_upload(
        name="user-image.bin",
        asset_type="image",
        asset_format="binary",
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
    )


class MockSyntheticImageTests(unittest.TestCase):
    def test_builder_is_deterministic_and_size_exact(self) -> None:
        first = build_synthetic_mock_asset(64 * 1024)
        second = build_synthetic_mock_asset(64 * 1024)
        self.assertEqual(first.name, "mock-synthetic-64KiB.bin")
        self.assertEqual(first.size, 64 * 1024)
        self.assertEqual(first.data[:260], bytes(range(256)) + bytes(range(4)))
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.data, second.data)


class MockSyntheticRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.provider = SharedImageMockEngineeringPPUProvider(
            self.root,
            flash_size_bytes=256 * 1024,
        )
        self.provider.start()
        self.provider.update_mock_runtime_settings(zero_error_settings(64 * 1024))
        self.manager = MockAwareBatchRuntimeManager(self.provider, poll_interval_s=0.005)
        self.session_id = self.provider.begin_session()["session"]["session_id"]

    def tearDown(self) -> None:
        self.manager.close()
        self.provider.close()
        self.temporary.cleanup()

    def wait_terminal(self, batch_id: str, timeout_s: float = 8.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            snapshot = self.manager.get(batch_id)
            if snapshot["state"] in {"success", "partial", "error", "cancelled"}:
                return snapshot
            time.sleep(0.01)
        self.fail(f"Batch {batch_id} did not reach terminal state")

    def test_batch_without_uploaded_image_uses_frozen_profile_size(self) -> None:
        started = self.manager.create_batch(
            targets=(
                BatchTarget("mock-facility-01", "mock-facility-01-ppu-01", 1),
                BatchTarget("mock-facility-01", "mock-facility-01-ppu-01", 2),
            ),
            operations=["program", "verify"],
            policy=BatchExecutionPolicy(repeat_count=1, site_retry_limit=0),
            session_id=self.session_id,
            asset=None,
        )
        self.provider.update_mock_runtime_settings(zero_error_settings(128 * 1024))

        self.assertEqual(started["asset"]["name"], "mock-synthetic-64KiB.bin")
        self.assertEqual(started["asset"]["size_bytes"], 64 * 1024)
        self.assertEqual(started["mock_runtime"]["profile"]["default_image_size_bytes"], 64 * 1024)

        final = self.wait_terminal(str(started["batch_id"]))
        self.assertEqual(final["state"], "success")
        self.assertEqual(final["site_counts"]["success"], 2)
        self.assertEqual(final["asset"]["size_bytes"], 64 * 1024)

    def test_user_image_overrides_synthetic_image(self) -> None:
        asset = user_asset(b"user-image" * 1024)
        started = self.manager.create_batch(
            targets=(BatchTarget("mock-facility-01", "mock-facility-01-ppu-01", 1),),
            operations=["program", "verify"],
            policy=BatchExecutionPolicy(),
            session_id=self.session_id,
            asset=asset,
        )
        self.assertEqual(started["asset"]["name"], asset.name)
        self.assertEqual(started["asset"]["sha256"], asset.sha256)
        final = self.wait_terminal(str(started["batch_id"]))
        self.assertEqual(final["state"], "success")

    def test_direct_mock_job_can_use_synthetic_image_without_asset_sha(self) -> None:
        request = JobRequest(
            site_id=1,
            operation=Operation.PROGRAM,
            client_id="synthetic-test",
        )
        accepted = __import__("asyncio").run(
            self.provider.start_job(
                "mock-facility-01",
                "mock-facility-01-ppu-01",
                request,
                session_id=self.session_id,
                asset_sha256=None,
            )
        )
        self.assertTrue(accepted["ok"])
        self.assertTrue(accepted["job"]["job_id"])


if __name__ == "__main__":
    unittest.main()
