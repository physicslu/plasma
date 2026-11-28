from __future__ import annotations

import asyncio
import base64
import hashlib
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
            enabled_sites=2,
            site_options={
                1: {
                    "operation_timeout_s": 3.0,
                    "mock": {
                        "delays": {"erase": 0.4, "program": 0.15, "verify": 0.1},
                        "progress_steps": 20,
                    },
                },
                2: {
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
        self.gateway_thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
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

    @staticmethod
    def asset_body(image: bytes, name: str) -> dict[str, Any]:
        return {
            "asset_name": name,
            "asset_type": "image",
            "asset_format": "binary",
            "asset_size": len(image),
            "asset_sha256": hashlib.sha256(image).hexdigest(),
            "asset_base64": base64.b64encode(image).decode(),
        }

    async def test_web_gateway_refuses_a_direct_mock_job_without_a_reservation(self) -> None:
        # U7: the Mock PPU admits a Programming Job only under its ACTIVE
        # Resource Reservation (the Manager Batch path), exactly like a
        # physical PPU. Progress, STOP and Read download are covered by the
        # Managed Mock-CD browser acceptance.
        status, topology, headers = await self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://localhost:4173")
        self.assertEqual([item["site_id"] for item in topology["sites"] if item["enabled"]], [1, 2])

        image = bytes(range(64))
        status, refused, _ = await self.request(
            "POST",
            "/api/jobs",
            {"site_id": 2, "operation": "program", **self.asset_body(image, "web-e2e.bin")},
        )
        self.assertEqual(status, 409)
        self.assertIn("Reservation required", refused["error"]["message"])
        status, after, _ = await self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertFalse(after["ppu"]["execution"]["busy"])


if __name__ == "__main__":
    unittest.main()
