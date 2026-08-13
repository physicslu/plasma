from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from pathlib import Path

from plasma_client.cli import ProgressRenderer, _run_work
from plasma_client.client import PlasmaClient
from plasma_core.enums import JobState, Operation
from plasma_core.errors import PlasmaError
from plasma_core.models import JobRequest
from plasma_interfaces.mock import MockInterface
from plasma_server.channel_manager import ChannelManager
from plasma_server.server import PlasmaServer

from tests.helpers import make_config


class ProgressAndCliTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.servers: list[PlasmaServer] = []

    async def asyncTearDown(self) -> None:
        for server in reversed(self.servers):
            await server.close()

    async def start_server(self, delays: dict[str, float]) -> tuple[PlasmaClient, PlasmaServer]:
        config = make_config(
            self.root,
            enabled_channels=1,
            channel_options={
                0: {
                    "operation_timeout_s": 3.0,
                    "mock": {"delays": delays, "progress_steps": 12},
                }
            },
        )
        server = PlasmaServer(config, ChannelManager(config))
        await server.start()
        self.servers.append(server)
        return PlasmaClient(*server.address, response_timeout_s=2.0), server

    async def test_detached_program_reports_all_stages_and_monotonic_progress(self) -> None:
        client, _server = await self.start_server(
            {"erase": 0.12, "program": 0.18, "verify": 0.12}
        )
        request = JobRequest(
            channel_id=0,
            operation=Operation.PROGRAM,
            firmware=bytes(range(64)),
            job_id="progress-stages",
            timeout_s=2.0,
        )
        accepted = await client.start(request)
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["job"]["job_id"], request.job_id)

        updates: list[dict[str, object]] = []
        result = await client.wait_for_job(
            request.job_id,
            poll_interval_s=0.01,
            timeout_s=2.0,
            on_update=lambda job: updates.append(dict(job)),
        )

        observed_stages = {str(item["stage"]) for item in updates if item.get("stage")}
        percentages = [float(item["progress_percent"]) for item in updates]
        self.assertEqual(result["result"]["state"], "success")
        self.assertEqual(observed_stages, {"erase", "program", "verify"})
        self.assertTrue(any(0.0 < value < 100.0 for value in percentages))
        self.assertEqual(percentages, sorted(percentages))
        self.assertEqual(percentages[-1], 100.0)
        self.assertTrue(any(item.get("bytes_total") == 64 for item in updates))

    async def test_cli_progress_renderer_shows_erase_program_verify(self) -> None:
        client, _server = await self.start_server(
            {"erase": 0.09, "program": 0.12, "verify": 0.09}
        )
        stream = io.StringIO()
        renderer = ProgressRenderer(stream=stream, width=12)
        result = await _run_work(
            client,
            JobRequest(
                channel_id=0,
                operation=Operation.PROGRAM,
                firmware=b"progress-bar-firmware",
                job_id="cli-progress",
                timeout_s=2.0,
            ),
            poll_interval_s=0.01,
            renderer=renderer,
        )
        rendered = stream.getvalue()
        self.assertEqual(result["result"]["state"], "success")
        self.assertIn("ERASE", rendered)
        self.assertIn("PROGRAM", rendered)
        self.assertIn("VERIFY", rendered)
        self.assertIn("100.0%", rendered)
        self.assertIn("█", rendered)

    async def test_cancelling_cli_wait_cancels_server_operation(self) -> None:
        client, server = await self.start_server(
            {"erase": 0.05, "program": 0.8, "verify": 0.05}
        )
        stream = io.StringIO()
        request = JobRequest(
            channel_id=0,
            operation=Operation.PROGRAM,
            firmware=b"cancel-me" * 32,
            job_id="cli-cancel",
            timeout_s=2.0,
        )
        task = asyncio.create_task(
            _run_work(
                client,
                request,
                poll_interval_s=0.01,
                renderer=ProgressRenderer(stream=stream, width=12),
            )
        )

        for _ in range(200):
            try:
                snapshot = server.manager.registry.get(request.job_id).snapshot()
            except PlasmaError:
                await asyncio.sleep(0.005)
                continue
            if snapshot["stage"] == "program" and snapshot["stage_progress_percent"] > 0:
                break
            await asyncio.sleep(0.005)
        else:
            self.fail("program stage was not reached")

        task.cancel()
        result = await task
        snapshot = server.manager.registry.get(request.job_id).snapshot()
        interface = server.manager.interfaces[0]
        self.assertIsInstance(interface, MockInterface)
        self.assertEqual(result["result"]["state"], "cancelled")
        self.assertEqual(snapshot["state"], JobState.CANCELLED.value)
        self.assertTrue(snapshot["cancel_requested"])
        self.assertEqual(snapshot["stage_state"], "cancelled")
        self.assertGreaterEqual(interface.shutdown_count, 1)
        self.assertIn("Cancellation requested", stream.getvalue())

        follow_up = await client.erase(0, timeout_s=1.0)
        self.assertEqual(follow_up["result"]["state"], "success")

    async def test_explicit_cancel_command_stops_detached_job(self) -> None:
        client, _server = await self.start_server({"erase": 0.6})
        request = JobRequest(
            channel_id=0,
            operation=Operation.ERASE,
            job_id="explicit-cancel",
            timeout_s=2.0,
        )
        await client.start(request)
        for _ in range(100):
            status = await client.status(job_id=request.job_id)
            if status["job"]["state"] == "running":
                break
            await asyncio.sleep(0.005)
        cancel = await client.cancel(request.job_id)
        result = await client.wait_for_job(request.job_id, poll_interval_s=0.01, timeout_s=1.0)
        self.assertTrue(cancel["accepted"])
        self.assertTrue(cancel["cancel_requested"])
        self.assertEqual(result["result"]["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
