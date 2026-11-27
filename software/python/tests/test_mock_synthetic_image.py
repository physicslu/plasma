from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_core.assets import ProgrammingAsset
from plasma_core.enums import Operation
from plasma_core.models import JobRequest
from plasma_web.gateway import PlasmaWebHandler
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


class NonSyntheticEngineeringProvider:
    def job_timeout_s(self, facility_id: str, ppu_id: str) -> float:
        return 30.0

    async def start_job(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
        *,
        session_id: str | None = None,
        asset_sha256: str | None = None,
    ) -> dict[str, object]:
        raise AssertionError("non-synthetic provider must not receive an Image-less Program job")


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
        self.session_id = self.provider.begin_session()["session"]["session_id"]

    def tearDown(self) -> None:
        self.provider.close()
        self.temporary.cleanup()

    def request_gateway_job(self, provider: object, body: dict[str, object]) -> tuple[int, dict[str, object]]:
        previous_provider = PlasmaWebHandler.engineering_provider
        server = None
        thread = None
        try:
            PlasmaWebHandler.engineering_provider = provider  # type: ignore[assignment]
            server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            conn = HTTPConnection("127.0.0.1", server.server_port)
            raw = json.dumps(body).encode("utf-8")
            conn.request(
                "POST",
                "/api/engineering/targets/mock-facility-01/mock-facility-01-ppu-01/api/jobs",
                raw,
                {"Content-Type": "application/json"},
            )
            response = conn.getresponse()
            payload = json.loads(response.read())
            status = response.status
            conn.close()
            return status, payload
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join()
            PlasmaWebHandler.engineering_provider = previous_provider

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

    def test_gateway_accepts_image_less_program_only_for_shared_image_mock_provider(self) -> None:
        status, payload = self.request_gateway_job(
            self.provider,
            {
                "site_id": 1,
                "operation": "program",
                "session_id": self.session_id,
            },
        )
        self.assertEqual(status, 202)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["job"]["operation"], "program")

    def test_gateway_keeps_non_synthetic_provider_fail_closed(self) -> None:
        status, payload = self.request_gateway_job(
            NonSyntheticEngineeringProvider(),
            {
                "site_id": 1,
                "operation": "program",
                "session_id": self.session_id,
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("asset_sha256", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
