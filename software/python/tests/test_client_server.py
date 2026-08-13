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
from plasma_server.channel_manager import ChannelManager
from plasma_server.server import PlasmaServer

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
        manager = ChannelManager(config)
        self.server = PlasmaServer(config, manager)
        await self.server.start()
        return PlasmaClient(*self.server.address, response_timeout_s=2.0)

    async def test_status_lists_enabled_and_disabled_channels(self) -> None:
        client = await self.start_server(enabled_channels=2)
        response = await client.status()
        self.assertTrue(response["ok"])
        self.assertEqual(len(response["channels"]), 8)
        self.assertEqual([item["channel_id"] for item in response["channels"] if item["enabled"]], [0, 1])

    async def test_program_end_to_end(self) -> None:
        client = await self.start_server(enabled_channels=2)
        response = await client.program(0, b"network-firmware", firmware_name="network.bin")
        result = response["result"]
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["firmware_name"], "network.bin")
        self.assertEqual(result["firmware_sha256"], hashlib.sha256(b"network-firmware").hexdigest())

    async def test_two_network_jobs_are_isolated_and_parallel(self) -> None:
        client = await self.start_server(
            enabled_channels=2,
            max_concurrent_jobs=2,
            channel_options={
                0: {
                    "mock": {
                        "failures": {"program": 1},
                        "failure_recoverable": False,
                        "default_delay_s": 0.01,
                    }
                },
                1: {"mock": {"default_delay_s": 0.01}},
            },
        )
        first, second = await asyncio.gather(
            client.program(0, b"A" * 16),
            client.program(1, b"B" * 16),
        )
        self.assertEqual(first["result"]["state"], "failed")
        self.assertEqual(first["result"]["error"]["error_code"], ErrorCode.PROGRAM_FAILED.value)
        self.assertEqual(second["result"]["state"], "success")

    async def test_disabled_channel_returns_structured_remote_error(self) -> None:
        client = await self.start_server(enabled_channels=2)
        with self.assertRaises(PlasmaError) as caught:
            await client.erase(7)
        self.assertEqual(caught.exception.code, ErrorCode.CHANNEL_DISABLED)

    async def test_bad_checksum_is_rejected_before_job_creation(self) -> None:
        client = await self.start_server(enabled_channels=1)
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
        client = await self.start_server(enabled_channels=1)
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
        client = await self.start_server(enabled_channels=2)
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

    async def test_invalid_status_channel_is_not_an_internal_error(self) -> None:
        client = await self.start_server(enabled_channels=1)
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
        client = await self.start_server(enabled_channels=1)
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
        client = await self.start_server(enabled_channels=1)
        with self.assertRaises(PlasmaError) as caught:
            await client.send(Frame(metadata={"protocol_version": "2.0", "operation": "status"}))
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_VERSION_UNSUPPORTED)

    async def test_server_survives_truncated_connection(self) -> None:
        client = await self.start_server(enabled_channels=1)
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
            enabled_channels=1,
            channel_options={0: {"mock": {"default_delay_s": 0.2}}},
        )
        assert self.server is not None
        request = JobRequest(
            channel_id=0,
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
        client = await self.start_server(enabled_channels=1)
        request = JobRequest(channel_id=0, operation=Operation.ERASE, job_id="status-job")
        await client.submit(request)
        response = await client.status(job_id="status-job")
        self.assertEqual(response["job"]["job_id"], "status-job")
        self.assertEqual(response["job"]["state"], "success")

    async def test_connection_failure_is_classified(self) -> None:
        client = await self.start_server(enabled_channels=1)
        host, port = client.host, client.port
        assert self.server is not None
        await self.server.close()
        self.server = None
        disconnected = PlasmaClient(host, port, connect_timeout_s=0.1)
        with self.assertRaises(PlasmaError) as caught:
            await disconnected.status()
        self.assertEqual(caught.exception.code, ErrorCode.CONNECTION_FAILED)
