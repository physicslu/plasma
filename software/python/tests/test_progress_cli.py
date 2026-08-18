from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from plasma_client.cli import ProgressRenderer, _run_work
from plasma_client.client import PlasmaClient
from plasma_core.enums import JobState, Operation
from plasma_core.models import JobRequest
from plasma_interfaces.mock import MockInterface
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager

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
            enabled_sites=1,
            site_options={
                0: {
                    "operation_timeout_s": 3.0,
                    "mock": {"delays": delays, "progress_steps": 12},
                }
            },
        )
        server = PlasmaServer(config, SiteManager(config))
        await server.start()
        self.servers.append(server)
        return PlasmaClient(*server.address, response_timeout_s=2.0), server

    async def test_detached_program_reports_program_only_and_monotonic_progress(self) -> None:
        client, server = await self.start_server(
            {"erase": 0.12, "program": 0.18, "verify": 0.12}
        )
        request = JobRequest(
            channel_id=0,
            operation=Operation.PROGRAM,
            firmware=bytes(range(64)),
            job_id="progress-stages",
            timeout_s=10.0,
        )
        accepted = await client.start(request)
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["job"]["job_id"], request.job_id)
        self.assertEqual(accepted["job"]["site_id"], 0)

        updates: list[dict[str, object]] = []
        result = await client.wait_for_job(
            request.job_id,
            poll_interval_s=0.01,
            timeout_s=12.0,
            on_update=lambda job: updates.append(dict(job)),
        )

        observed_stages = {str(item["stage"]) for item in updates if item.get("stage")}
        percentages = [float(item["progress_percent"]) for item in updates]
        self.assertEqual(result["result"]["state"], "success")
        self.assertEqual(observed_stages, {"program"})
        self.assertTrue(any(0.0 < value < 100.0 for value in percentages))
        self.assertEqual(percentages, sorted(percentages))
        self.assertEqual(percentages[-1], 100.0)
        self.assertTrue(any(item.get("bytes_total") == 64 for item in updates))
        interface = server.manager.interfaces[0]
        self.assertIsInstance(interface, MockInterface)
        self.assertEqual(interface.calls["erase"], 0)
        self.assertEqual(interface.calls["program"], 1)
        self.assertEqual(interface.calls["verify"], 0)

    async def test_cli_progress_renderer_shows_site_and_program_only(self) -> None:
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
        self.assertIn("SITE0", rendered)
        self.assertNotIn("CH0", rendered)
        self.assertIn("PROGRAM", rendered)
        self.assertNotIn("ERASE", rendered)
        self.assertNotIn("VERIFY", rendered)
        self.assertIn("100.0%", rendered)
        self.assertIn("█", rendered)

    async def test_cancelling_cli_wait_cancels_server_operation(self) -> None:
        client, server = await self.start_server({"erase": 0.05, "verify": 0.05})
        stream = io.StringIO()
        program_entered = asyncio.Event()
        keep_programming = asyncio.Event()
        cli_observed_program = asyncio.Event()

        class SynchronizedRenderer(ProgressRenderer):
            def update(self, job: dict[str, object]) -> None:
                super().update(job)
                if job.get("stage") == "program":
                    cli_observed_program.set()

        async def gated_program(
            interface: MockInterface,
            firmware: bytes,
            address: int = 0,
            progress=None,
        ) -> None:
            interface._validate_range(address, len(firmware))
            interface.calls["program"] += 1
            if progress:
                await progress(1, len(firmware))
            program_entered.set()
            await keep_programming.wait()

        request = JobRequest(
            channel_id=0,
            operation=Operation.PROGRAM,
            firmware=b"cancel-me" * 32,
            job_id="cli-cancel",
            timeout_s=10.0,
        )
        with mock.patch.object(MockInterface, "program", gated_program):
            task = asyncio.create_task(
                _run_work(
                    client,
                    request,
                    poll_interval_s=0.01,
                    renderer=SynchronizedRenderer(stream=stream, width=12),
                )
            )
            await asyncio.wait_for(program_entered.wait(), timeout=5.0)
            await asyncio.wait_for(cli_observed_program.wait(), timeout=5.0)
            runtime = server.manager.registry.get(request.job_id)
            self.assertEqual(runtime.stage, "program")
            self.assertGreater(runtime.stage_progress_percent, 0)

            task.cancel()
            await asyncio.wait_for(runtime.cancel_event.wait(), timeout=5.0)
            self.assertIn("Cancellation requested", stream.getvalue())
            result = await asyncio.wait_for(task, timeout=5.0)

        snapshot = server.manager.registry.get(request.job_id).snapshot()
        interface = server.manager.interfaces[0]
        self.assertIsInstance(interface, MockInterface)
        self.assertEqual(result["result"]["state"], "cancelled")
        self.assertEqual(snapshot["state"], JobState.CANCELLED.value)
        self.assertTrue(snapshot["cancel_requested"])
        self.assertEqual(snapshot["stage_state"], "cancelled")
        self.assertGreaterEqual(interface.shutdown_count, 1)

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
