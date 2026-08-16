from __future__ import annotations

import asyncio
import base64
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from plasma_client.client import PlasmaClient
from plasma_server.server import PlasmaServer
from plasma_web.gateway import PlasmaWebHandler
from tests.helpers import make_config


class WebMockEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        config = make_config(
            self.root,
            enabled_channels=2,
            channel_options={
                0: {
                    "operation_timeout_s": 3.0,
                    "mock": {
                        "delays": {"erase": 0.4, "program": 0.15, "verify": 0.1},
                        "progress_steps": 20,
                    },
                },
                1: {
                    "operation_timeout_s": 3.0,
                    "mock": {
                        "delays": {"erase": 0.1, "program": 0.15, "verify": 0.1},
                        "progress_steps": 20,
                    },
                },
            },
        )
        self.plasma = PlasmaServer(config)
        await self.plasma.start()

        self.original_factory = PlasmaWebHandler.client_factory
        self.original_origins = PlasmaWebHandler.allowed_origins
        self.original_output_root = PlasmaWebHandler.output_root
        self.addCleanup(setattr, PlasmaWebHandler, "output_root", self.original_output_root)
        self.addCleanup(setattr, PlasmaWebHandler, "allowed_origins", self.original_origins)
        self.addCleanup(setattr, PlasmaWebHandler, "client_factory", self.original_factory)
        PlasmaWebHandler.client_factory = staticmethod(
            lambda: PlasmaClient(*self.plasma.address, response_timeout_s=3.0)
        )
        PlasmaWebHandler.allowed_origins = frozenset({"http://localhost:4173"})
        PlasmaWebHandler.output_root = config.server.output_root
        self.gateway = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        self.gateway_thread = threading.Thread(
            target=self.gateway.serve_forever,
            daemon=True,
        )
        self.gateway_thread.start()

    async def asyncTearDown(self) -> None:
        self.gateway.shutdown()
        self.gateway.server_close()
        self.gateway_thread.join()
        await self.plasma.close()
        self.temporary.cleanup()

    def _request_sync(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        connection = HTTPConnection("127.0.0.1", self.gateway.server_port, timeout=3)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Origin": "http://localhost:4173"}
        if raw:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        response_headers = dict(response.getheaders())
        response_body = response.read()
        payload = json.loads(response_body) if response_headers.get("Content-Type", "").startswith("application/json") else response_body
        status = response.status
        connection.close()
        return status, payload, response_headers

    async def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        return await asyncio.to_thread(self._request_sync, method, path, body)

    async def wait_for_terminal(
        self,
        job_id: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        updates: list[dict[str, Any]] = []
        for _ in range(300):
            status, payload, _ = await self.request("GET", f"/api/status?job={job_id}")
            self.assertEqual(status, 200)
            job = payload["job"]
            updates.append(job)
            if job["state"] in {"success", "failed", "cancelled", "timeout", "aborted"}:
                return job, updates
            await asyncio.sleep(0.01)
        self.fail(f"job did not reach a terminal state: {job_id}")

    async def test_web_gateway_programs_mock_and_reports_real_progress(self) -> None:
        status, channels, headers = await self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://localhost:4173")
        self.assertEqual(
            [item["channel_id"] for item in channels["channels"] if item["enabled"]],
            [0, 1],
        )

        firmware = bytes(range(64))
        status, accepted, _ = await self.request(
            "POST",
            "/api/jobs",
            {
                "channel_id": 1,
                "operation": "program",
                "firmware_name": "web-e2e.bin",
                "firmware_base64": base64.b64encode(firmware).decode(),
                "timeout_s": 2,
            },
        )
        self.assertEqual(status, 202)
        job_id = accepted["job"]["job_id"]

        final, updates = await self.wait_for_terminal(job_id)
        self.assertEqual(final["state"], "success")
        self.assertEqual(final["progress_percent"], 100.0)
        self.assertEqual(
            {item["stage"] for item in updates if item["stage"]},
            {"erase", "program", "verify"},
        )
        self.assertTrue(any(0 < item["progress_percent"] < 100 for item in updates))

    async def test_web_gateway_cancel_reaches_mock_worker(self) -> None:
        status, accepted, _ = await self.request(
            "POST",
            "/api/jobs",
            {"channel_id": 0, "operation": "erase"},
        )
        self.assertEqual(status, 202)
        job_id = accepted["job"]["job_id"]

        for _ in range(100):
            _, payload, _ = await self.request("GET", f"/api/status?job={job_id}")
            if payload["job"]["state"] == "running":
                break
            await asyncio.sleep(0.005)
        else:
            self.fail("erase job did not start")

        status, cancelled, _ = await self.request(
            "POST",
            f"/api/jobs/{job_id}/cancel",
            {},
        )
        self.assertEqual(status, 200)
        self.assertTrue(cancelled["cancel_requested"])

        final, _ = await self.wait_for_terminal(job_id)
        self.assertEqual(final["state"], "cancelled")
        self.assertTrue(final["cancel_requested"])

    async def test_program_then_read_and_download_exact_mock_bytes(self) -> None:
        firmware = bytes(range(64))
        status, accepted, _ = await self.request("POST", "/api/jobs", {
            "channel_id": 1, "operation": "program", "firmware_name": "known.bin",
            "firmware_base64": base64.b64encode(firmware).decode(),
        })
        self.assertEqual(status, 202)
        programmed, _ = await self.wait_for_terminal(accepted["job"]["job_id"])
        self.assertEqual(programmed["state"], "success")

        status, accepted, _ = await self.request("POST", "/api/jobs", {
            "channel_id": 1, "operation": "read", "offset": 7, "length": 29,
        })
        self.assertEqual(status, 202)
        read_job, updates = await self.wait_for_terminal(accepted["job"]["job_id"])
        self.assertEqual(read_job["state"], "success")
        self.assertTrue(any(item["stage"] == "read_flash" for item in updates))
        output_file = Path(read_job["result"]["output_files"][0])
        self.assertTrue(output_file.is_file())
        self.assertEqual(output_file.read_bytes(), firmware[7:36])

        status, downloaded, headers = await self.request(
            "GET", f"/api/jobs/{read_job['job_id']}/files/{output_file.name}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(downloaded, firmware[7:36])


if __name__ == "__main__":
    unittest.main()
