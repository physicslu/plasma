from __future__ import annotations

import asyncio
import contextlib
import hashlib
import tempfile
import unittest
from pathlib import Path

from plasma_client.client import PlasmaClient
from plasma_core.enums import JobState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_core.protocol import PROTOCOL_VERSION, Frame, encode_frame
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager

from tests.helpers import make_config


class ClientServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.server: PlasmaServer | None = None

    async def asyncTearDown(self) -> None:
        if self.server:
            await self.server.close()

    async def start_server(self, **options: object) -> PlasmaClient:
        config = make_config(self.root, **options)
        manager = SiteManager(config)
        self.server = PlasmaServer(config, manager)
        await self.server.start()
        return PlasmaClient(*self.server.address, response_timeout_s=2.0)

    async def test_status_lists_enabled_and_disabled_sites(self) -> None:
        client = await self.start_server(enabled_sites=2)
        response = await client.status()
        self.assertTrue(response["ok"])
        self.assertEqual(response["protocol_version"], PROTOCOL_VERSION)
        self.assertEqual(len(response["sites"]), 8)
        self.assertEqual([item["site_id"] for item in response["sites"] if item["enabled"]], [1, 2])

    async def test_program_end_to_end_uses_image_fields(self) -> None:
        client = await self.start_server(enabled_sites=2)
        image = b"network-image"
        response = await client.program(1, image, image_name="network.bin")
        result = response["result"]
        self.assertEqual(result["site_id"], 1)
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["image_name"], "network.bin")
        self.assertEqual(result["image_sha256"], hashlib.sha256(image).hexdigest())
        self.assertEqual(result["image_size"], len(image))

    async def test_two_network_jobs_are_isolated_and_parallel(self) -> None:
        client = await self.start_server(
            enabled_sites=2,
            max_concurrent_jobs=2,
            site_options={
                1: {
                    "mock": {
                        "failures": {"program": 1},
                        "failure_recoverable": False,
                        "default_delay_s": 0.01,
                    }
                },
                2: {"mock": {"default_delay_s": 0.01}},
            },
        )
        first, second = await asyncio.gather(
            client.program(1, b"A" * 16),
            client.program(2, b"B" * 16),
        )
        self.assertEqual(first["result"]["state"], "failed")
        self.assertEqual(first["result"]["error"]["error_code"], ErrorCode.PROGRAM_FAILED.value)
        self.assertEqual(second["result"]["state"], "success")

    async def test_disabled_site_returns_structured_remote_error(self) -> None:
        client = await self.start_server(enabled_sites=2)
        with self.assertRaises(PlasmaError) as caught:
            await client.erase(8)
        self.assertEqual(caught.exception.code, ErrorCode.SITE_DISABLED)

    async def test_bad_image_checksum_is_rejected_before_job_creation(self) -> None:
        client = await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": PROTOCOL_VERSION,
                        "operation": "program",
                        "site_id": 1,
                        "image_size": 4,
                        "image_sha256": "0" * 64,
                    },
                    binary=b"data",
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_CHECKSUM_MISMATCH)

    async def test_invalid_retry_number_is_invalid_argument(self) -> None:
        client = await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": PROTOCOL_VERSION,
                        "operation": "erase",
                        "site_id": 1,
                        "timeout_s": "not-a-number",
                    }
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_site_id_requires_json_integer_without_coercion(self) -> None:
        client = await self.start_server(enabled_sites=1)
        for value in (True, 1.0, 1.5, "1"):
            with self.subTest(site_id=value):
                with self.assertRaises(PlasmaError) as caught:
                    await client.send(
                        Frame(
                            metadata={
                                "protocol_version": PROTOCOL_VERSION,
                                "operation": "erase",
                                "site_id": value,
                            }
                        )
                    )
                self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_wait_for_completion_must_be_boolean(self) -> None:
        client = await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": PROTOCOL_VERSION,
                        "operation": "erase",
                        "site_id": 1,
                        "wait_for_completion": "false",
                    }
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_retired_protocol_versions_are_not_supported(self) -> None:
        for version in ("3.1", "3.2"):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    PlasmaClient(protocol_version=version)
                with self.assertRaises(PlasmaError) as caught:
                    encode_frame(Frame(metadata={"protocol_version": version, "operation": "status"}))
                self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_VERSION_UNSUPPORTED)

    async def test_server_survives_truncated_connection(self) -> None:
        client = await self.start_server(enabled_sites=1)
        assert self.server is not None
        _reader, writer = await asyncio.open_connection(*self.server.address)
        writer.write(b"PLAS")
        await writer.drain()
        writer.close()
        with contextlib.suppress(ConnectionError):
            await writer.wait_closed()
        await asyncio.sleep(0.02)
        response = await client.status()
        self.assertTrue(response["ok"])

    async def test_cancel_through_second_connection(self) -> None:
        client = await self.start_server(
            enabled_sites=1,
            site_options={1: {"mock": {"default_delay_s": 0.2}}},
        )
        assert self.server is not None
        request = JobRequest(
            site_id=1,
            operation=Operation.ERASE,
            job_id="network-cancel-job",
        )
        submission = asyncio.create_task(client.submit(request))
        for _ in range(100):
            try:
                runtime = self.server.manager.registry.get(request.job_id)
            except PlasmaError:
                await asyncio.sleep(0.002)
                continue
            if runtime.state is JobState.RUNNING:
                break
            await asyncio.sleep(0.002)
        cancel_response = await client.cancel(request.job_id)
        completed = await submission
        self.assertTrue(cancel_response["accepted"])
        self.assertEqual(completed["result"]["state"], "cancelled")

    async def test_job_status_by_id(self) -> None:
        client = await self.start_server(enabled_sites=1)
        request = JobRequest(site_id=1, operation=Operation.ERASE, job_id="status-job")
        await client.submit(request)
        response = await client.status(job_id="status-job")
        self.assertEqual(response["job"]["job_id"], "status-job")
        self.assertEqual(response["job"]["site_id"], 1)
        self.assertEqual(response["job"]["state"], "success")

    async def test_connection_failure_is_classified(self) -> None:
        client = await self.start_server(enabled_sites=1)
        host, port = client.host, client.port
        assert self.server is not None
        await self.server.close()
        self.server = None
        disconnected = PlasmaClient(host, port, connect_timeout_s=0.1)
        with self.assertRaises(PlasmaError) as caught:
            await disconnected.status()
        self.assertEqual(caught.exception.code, ErrorCode.CONNECTION_FAILED)
