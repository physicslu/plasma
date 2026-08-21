from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_client.client import PlasmaClient
from plasma_core.enums import JobState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_image_store import default_mock_image_store
from plasma_core.models import (
    LOCAL_MOCK_BLOB_SCHEME,
    ErrorDetail,
    ExecutionImageRef,
    JobRequest,
)
from plasma_interfaces.mock import MockInterface
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager

from tests.helpers import make_config


class ShutdownFailureMock(MockInterface):
    async def safe_shutdown(self) -> None:
        raise PlasmaError(
            ErrorCode.INTERFACE_FAILURE,
            "injected safe-shutdown infrastructure failure",
        )


class FailureSourceContractTests(unittest.TestCase):
    def test_failure_sources_are_distinct(self) -> None:
        injected = ErrorDetail.from_exception(
            PlasmaError(
                ErrorCode.PROGRAM_FAILED,
                "injected",
                context={"failure_source": "injected"},
            )
        )
        mismatch = ErrorDetail.from_exception(
            PlasmaError(
                ErrorCode.VERIFY_FAILED,
                "mismatch",
                context={"failure_source": "mismatch"},
            )
        )
        infrastructure = ErrorDetail.from_exception(
            PlasmaError(ErrorCode.INTERNAL_ERROR, "internal")
        )
        cancelled = ErrorDetail.from_exception(
            PlasmaError(ErrorCode.OPERATION_CANCELLED, "cancelled")
        )
        self.assertEqual(injected.failure_source, "injected")
        self.assertEqual(mismatch.failure_source, "mismatch")
        self.assertEqual(infrastructure.failure_source, "infrastructure")
        self.assertEqual(cancelled.failure_source, "cancelled")

    def test_error_state_is_terminal(self) -> None:
        self.assertTrue(JobState.ERROR.terminal)


class ExecutionImageReferenceContractTests(unittest.TestCase):
    def test_reference_and_inline_bytes_are_mutually_exclusive(self) -> None:
        ref = ExecutionImageRef(
            scheme=LOCAL_MOCK_BLOB_SCHEME,
            sha256="0" * 64,
            size_bytes=4,
        )
        with self.assertRaises(PlasmaError) as caught:
            JobRequest(
                site_id=1,
                operation=Operation.PROGRAM,
                image=b"data",
                image_ref=ref,
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_reference_is_serialized_without_a_path(self) -> None:
        ref = ExecutionImageRef(
            scheme=LOCAL_MOCK_BLOB_SCHEME,
            sha256="a" * 64,
            size_bytes=4096,
        )
        request = JobRequest(site_id=1, operation=Operation.PROGRAM, image_ref=ref)
        metadata = request.protocol_metadata()
        self.assertEqual(metadata["image_size"], 4096)
        self.assertEqual(metadata["image_sha256"], "a" * 64)
        self.assertEqual(
            metadata["execution_image_ref"],
            {
                "scheme": LOCAL_MOCK_BLOB_SCHEME,
                "sha256": "a" * 64,
                "size_bytes": 4096,
            },
        )
        self.assertNotIn("path", metadata["execution_image_ref"])


class ExecutionContractServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.server: PlasmaServer | None = None

    async def asyncTearDown(self) -> None:
        if self.server is not None:
            await self.server.close()

    async def start_server(
        self,
        *,
        site_options: dict[int, dict[str, object]] | None = None,
        interface_factory=None,
    ) -> PlasmaClient:
        config = make_config(
            self.root,
            enabled_sites=1,
            site_options=site_options,
        )
        manager = SiteManager(config, interface_factory=interface_factory)
        self.server = PlasmaServer(config, manager)
        await self.server.start()
        return PlasmaClient(*self.server.address, response_timeout_s=3.0)

    async def test_mock_server_drops_inline_image_from_job_registry(self) -> None:
        client = await self.start_server()
        image = b"shared-job-image" * 1024
        request = JobRequest(
            site_id=1,
            operation=Operation.PROGRAM,
            image=image,
            job_id="shared-registry-image",
        )
        accepted = await client.start(request)
        self.assertTrue(accepted["accepted"])
        assert self.server is not None
        runtime = self.server.manager.registry.get(request.job_id)
        self.assertEqual(runtime.request.image, b"")
        self.assertIsNotNone(runtime.request.image_ref)
        assert runtime.request.image_ref is not None
        self.assertEqual(runtime.request.image_ref.size_bytes, len(image))
        self.assertEqual(runtime.request.image_ref.sha256, request.image_sha256)
        completed = await client.wait_for_job(request.job_id, timeout_s=3.0)
        self.assertEqual(completed["result"]["state"], "success")

    async def test_explicit_shared_reference_program_and_verify(self) -> None:
        client = await self.start_server()
        image = b"reference-image" * 2048
        shared = default_mock_image_store().put(image)
        image_ref = ExecutionImageRef(
            scheme=LOCAL_MOCK_BLOB_SCHEME,
            sha256=shared.sha256,
            size_bytes=shared.size_bytes,
        )
        programmed = await client.submit(
            JobRequest(site_id=1, operation=Operation.PROGRAM, image_ref=image_ref)
        )
        verified = await client.submit(
            JobRequest(site_id=1, operation=Operation.VERIFY, image_ref=image_ref)
        )
        self.assertEqual(programmed["result"]["state"], "success")
        self.assertEqual(verified["result"]["state"], "success")
        self.assertEqual(verified["result"]["image_sha256"], shared.sha256)

    async def test_retry_history_records_recovered_failures(self) -> None:
        client = await self.start_server(
            site_options={
                1: {
                    "mock": {
                        "failures": {"program": 2},
                        "failure_recoverable": True,
                    }
                }
            }
        )
        result = (
            await client.submit(
                JobRequest(
                    site_id=1,
                    operation=Operation.PROGRAM,
                    image=b"retry-image",
                    max_retries=2,
                    retry_backoff_s=0,
                )
            )
        )["result"]
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["attempts"], 3)
        self.assertFalse(result["retry_exhausted"])
        self.assertEqual(
            [item["state"] for item in result["attempt_history"]],
            ["failed", "failed", "success"],
        )
        self.assertTrue(result["attempt_history"][0]["retry_scheduled"])
        self.assertEqual(
            result["attempt_history"][0]["error"]["failure_source"],
            "injected",
        )

    async def test_retry_exhaustion_is_explicit(self) -> None:
        client = await self.start_server(
            site_options={
                1: {
                    "mock": {
                        "failures": {"program": 3},
                        "failure_recoverable": True,
                    }
                }
            }
        )
        result = (
            await client.submit(
                JobRequest(
                    site_id=1,
                    operation=Operation.PROGRAM,
                    image=b"retry-exhausted",
                    max_retries=2,
                    retry_backoff_s=0,
                )
            )
        )["result"]
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["attempts"], 3)
        self.assertTrue(result["retry_exhausted"])
        self.assertEqual(len(result["attempt_history"]), 3)
        self.assertFalse(result["attempt_history"][-1]["retry_scheduled"])

    async def test_interface_shutdown_failure_is_job_error(self) -> None:
        client = await self.start_server(
            interface_factory=lambda _site: ShutdownFailureMock()
        )
        result = (await client.erase(1))["result"]
        self.assertEqual(result["state"], "error")
        self.assertEqual(result["error"]["error_code"], ErrorCode.INTERFACE_FAILURE.value)
        self.assertEqual(result["error"]["failure_source"], "infrastructure")


if __name__ == "__main__":
    unittest.main()
