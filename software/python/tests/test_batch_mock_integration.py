from __future__ import annotations

import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from plasma_core.assets import ProgrammingAsset
from plasma_core.batch import BatchExecutionPolicy, BatchTarget
from plasma_interfaces.mock import MockInterface
from plasma_web.batch_runtime import BatchRuntimeManager
from plasma_web.engineering_targets import MockEngineeringPPUProvider


def make_asset(data: bytes) -> ProgrammingAsset:
    return ProgrammingAsset.from_upload(
        name="integration.bin",
        asset_type="image",
        asset_format="binary",
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
    )


class BatchMockIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.provider = MockEngineeringPPUProvider(self.root, flash_size_bytes=64 * 1024)
        self.provider.start()
        self.manager = BatchRuntimeManager(self.provider, poll_interval_s=0.005)
        session = self.provider.begin_session()
        self.session_id = session["session"]["session_id"]

    def tearDown(self) -> None:
        self.manager.close()
        self.provider.close()
        self.temporary.cleanup()

    def wait_terminal(self, batch_id: str, timeout_s: float = 8.0):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            snapshot = self.manager.get(batch_id)
            if snapshot["state"] in {"success", "partial", "error", "cancelled"}:
                return snapshot
            time.sleep(0.01)
        self.fail(f"Batch {batch_id} did not reach terminal state")

    @staticmethod
    def two_site_targets() -> tuple[BatchTarget, ...]:
        return (
            BatchTarget("mock-facility-01", "mock-facility-01-ppu-01", 1),
            BatchTarget("mock-facility-01", "mock-facility-01-ppu-01", 2),
        )

    def test_real_mock_provider_runs_repeat_program_verify_batch(self):
        image = bytes((index * 13) & 0xFF for index in range(4096))
        started = self.manager.create_batch(
            targets=self.two_site_targets(),
            operations=["erase", "program", "verify"],
            policy=BatchExecutionPolicy(repeat_count=2, site_retry_limit=1),
            session_id=self.session_id,
            asset=make_asset(image),
        )
        final = self.wait_terminal(started["batch_id"])
        self.assertEqual(final["state"], "success")
        self.assertEqual(final["site_counts"]["success"], 2)
        self.assertEqual(final["operation_statistics"]["program"]["logical_executions"], 4)
        self.assertEqual(final["operation_statistics"]["verify"]["logical_executions"], 4)
        self.assertTrue(all(site["completed_rounds"] == 2 for site in final["sites"]))

    def test_real_mock_retry_exhaustion_trips_threshold(self):
        key = ("mock-facility-01", "mock-facility-01-ppu-01")
        server = self.provider._servers[key]
        interface = server.manager.interfaces[1]
        self.assertIsInstance(interface, MockInterface)
        interface.failures["program"] = 1
        interface.failure_recoverable = True

        started = self.manager.create_batch(
            targets=self.two_site_targets(),
            operations=["program"],
            policy=BatchExecutionPolicy(
                repeat_count=3,
                site_retry_limit=0,
                failed_site_stop_threshold=1,
            ),
            session_id=self.session_id,
            asset=make_asset(b"fault-me" * 128),
        )
        final = self.wait_terminal(started["batch_id"])
        by_site = {site["site_id"]: site for site in final["sites"]}
        self.assertEqual(final["state"], "error")
        self.assertEqual(final["stop_reason"], "failed_site_threshold")
        self.assertEqual(final["faulted_site_count"], 1)
        self.assertEqual(by_site[1]["state"], "faulted")
        self.assertEqual(by_site[1]["total_attempts"], 1)
        self.assertEqual(by_site[1]["retry_count"], 0)
        self.assertEqual(by_site[1]["last_failure_source"], "injected")
        self.assertIn(by_site[2]["state"], {"success", "stopped", "cancelled"})


if __name__ == "__main__":
    unittest.main()
