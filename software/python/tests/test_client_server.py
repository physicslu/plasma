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
from plasma_core.protocol import Frame
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

    async def test_v32_status_lists_enabled_and_disabled_sites(self) -> None:
        client = await self.start_server(enabled_sites=2)
        response = await client.status()
        self.assertTrue(response["ok"])
        self.assertEqual(len(response["sites"]), 8)
        self.assertEqual([item["site_id"] for item in response["sites"] if item["enabled"]], [1, 2])
        self.assertNotIn("channels", response)

    async def test_program_end_to_end(self) -> None:
        client = await self.start_server(enabled_sites=2)
        response = await client.program(1, b"network-firmware", firmware_name="network.bin")
        result = response["result"]
        self.assertEqual(result["site_id"], 1)
        self.assertNotIn("channel_id", result)
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["firmware_name"], "network.bin")
        self.assertEqual(result["firmware_sha256"], hashlib.sha256(b"network-firmware").hexdigest())

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
        self.assertEqual(first["result"]["error"]["error_type"], "PROGRAM_FAILED")
        self.assertEqual(second["result"]["state"], "success")

    async def test_disabled_site_returns_structured_remote_error(self) -> None:
        client = await self.start_server(enabled_sites=2)
        with self.assertRaises(PlasmaError) as caught:
            await client.erase(8)
        self.assertEqual(caught.exception.code, ErrorCode.SITE_DISABLED)

    async def test_v31_client_maps_channel_zero_to_site_one_and_returns_legacy_shape(self) -> None:
        current = await self.start_server(enabled_sites=1)
        legacy = PlasmaClient(current.host, current.port, protocol_version="3.1", response_timeout_s=2.0)
        response = await legacy.status(site_id=1)
        self.assertEqual(response["protocol_version"], "3.1")
        self.assertEqual(response["channels"][0]["channel_id"], 0)
        self.assertNotIn("sites", response)

        request = JobRequest(site_id=1, operation=Operation.ERASE, job_id="legacy-v31-job")
        result = (await legacy.submit(request))["result"]
        self.assertEqual(result["channel_id"], 0)
        self.assertNotIn("site_id", result)
        self.assertEqual(result["state"], "success")

    async def test_bad_checksum_is_rejected_before_job_creation(self) -> None:
        client = await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": "3.1",
                        "operation": "program",
                        "channel_id": 0,
                        "firmware_size": 4,
                        "firmware_sha256": "0" * 64,
                    },
                    binary=b"data",
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_CHECKSUM_MISMATCH)

    async def test_invalid_retry_number_is_classified_as_invalid_argument(self) -> None:
        client = await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": "3.1",
                        "operation": "erase",
                        "channel_id": 0,
                        "timeout_s": "not-a-number",
                    }
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_boolean_channel_id_is_rejected(self) -> None:
        client = await self.start_server(enabled_sites=2)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": "3.1",
                        "operation": "erase",
                        "channel_id": True,
                    }
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_v32_site_id_requires_json_integer_without_coercion(self) -> None:
        client = await self.start_server(enabled_sites=1)
        for value in (1.0, 1.5, "1"):
            with self.subTest(site_id=value):
                with self.assertRaises(PlasmaError) as caught:
                    await client.send(
                        Frame(
                            metadata={
                                "protocol_version": "3.2",
                                "operation": "erase",
                                "site_id": value,
                            }
                        )
                    )
                self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_v31_channel_id_requires_json_integer_without_coercion(self) -> None:
        client = await self.start_server(enabled_sites=1)
        for value in (0.0, 0.5, "0"):
            with self.subTest(channel_id=value):
                with self.assertRaises(PlasmaError) as caught:
                    await client.send(
                        Frame(
                            metadata={
                                "protocol_version": "3.1",
                                "operation": "erase",
                                "channel_id": value,
                            }
                        )
                    )
                self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_v32_rejects_channel_id_field(self) -> None:
        client = await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": "3.2",
                        "operation": "erase",
                        "channel_id": 0,
                    }
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_v31_rejects_site_id_field(self) -> None:
        client = await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": "3.1",
                        "operation": "erase",
                        "site_id": 1,
                    }
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_invalid_status_channel_is_not_an_internal_error(self) -> None:
        client = await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(
                Frame(
                    metadata={
                        "protocol_version": "3.1",
                        "operation": "status",
                        "channel_id": "CH0",
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
                        "protocol_version": "3.1",
                        "operation": "erase",
                        "channel_id": 0,
                        "wait_for_completion": "false",
                    }
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_unsupported_protocol_version(self) -> None:
        await self.start_server(enabled_sites=1)
        with self.assertRaises(PlasmaError) as caught:
            from plasma_core.protocol import encode_frame
            encode_frame(Frame(metadata={"protocol_version": "2.0", "operation": "status"}))
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
