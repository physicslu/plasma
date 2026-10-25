"""Host-only Blue Pill REST -> real Protocol v3.3 PS server -> exact OpenOCD
route admission. This is a safety/WEB integration regression, NOT Flash HIL.

Use actual network listeners on loopback with ordinary PlasmaWebHandler and
PlasmaServer, not a fake REST client. Neither server opens PL or SWD hardware.
"""
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

from plasma_client.client import PlasmaClient
from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.errors import ErrorCode
from plasma_server.server import PlasmaServer
from plasma_web.gateway import PlasmaWebHandler


class BluePillWebPsRouteAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="plasma-bb-web-")
        root = Path(self.temporary.name)
        config = PlasmaConfig(
            server=ServerConfig(
                host="127.0.0.1",
                port=0,
                max_supported_sites=1,
                max_concurrent_jobs=1,
                output_root=root / "output",
                log_root=root / "logs",
            ),
            sites=[SiteConfig(
                id=1, enabled=True, interface="openocd",
                target="STM32F103C8T6",
                openocd={
                    "interface_cfg": "interface/remote_bitbang.cfg",
                    "target_cfg": "target/stm32f1x.cfg",
                },
            )],
        )
        self.ps = PlasmaServer(config)
        await self.ps.start()
        host, port = self.ps.address

        # Per-test subclass prevents global Gateway handler mutation.
        class Gateway(PlasmaWebHandler):
            client_factory = staticmethod(
                lambda: PlasmaClient(host, port, response_timeout_s=3.0)
            )
            output_root = config.server.output_root
            engineering_provider = None
            batch_runtime = None

        self.gateway = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
        self.thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
        self.thread.start()

    async def asyncTearDown(self):
        self.gateway.shutdown()
        self.gateway.server_close()
        self.thread.join(timeout=3)
        await self.ps.close()
        self.temporary.cleanup()

    def _post(self, path, body):
        conn = HTTPConnection("127.0.0.1", self.gateway.server_port, timeout=4)
        payload = json.dumps(body).encode("utf-8")
        conn.request("POST", path, payload, {"Content-Type": "application/json"})
        response = conn.getresponse()
        data = json.loads(response.read())
        code = response.status
        conn.close()
        return code, data

    async def test_program_image_crosses_web_and_ps_but_unadmitted_openocd_is_rejected(self):
        image = bytes(range(32))
        sha = hashlib.sha256(image).hexdigest()
        status, response = await asyncio.to_thread(
            self._post, "/api/jobs",
            {
                "site_id": 1,
                "operation": "program",
                "asset_name": "bluepill-test.bin",
                "asset_type": "image",
                "asset_format": "binary",
                "asset_size": len(image),
                "asset_sha256": sha,
                "asset_base64": base64.b64encode(image).decode("ascii"),
            },
        )
        self.assertEqual(status, 400)
        self.assertFalse(response["ok"])
        self.assertEqual(
            response["error"]["error_code"],
            ErrorCode.INTERFACE_NOT_CONFIGURED.value,
        )
        self.assertIn("runtime-ready", response["error"]["message"])
        self.assertEqual(self.ps.manager.registry.all(), [])
        self.assertFalse(self.ps.manager.execution_lease_snapshot()["busy"])
        self.assertEqual(self.ps.manager.workers[1].queue.qsize(), 0)

    async def test_erase_also_refuses_without_a_registered_runtime(self):
        status, response = await asyncio.to_thread(
            self._post, "/api/jobs", {"site_id": 1, "operation": "erase"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(
            response["error"]["error_code"],
            ErrorCode.INTERFACE_NOT_CONFIGURED.value,
        )
        self.assertEqual(self.ps.manager.registry.all(), [])
        self.assertFalse(self.ps.manager.execution_lease_snapshot()["busy"])

    async def test_web_cannot_supply_server_owned_runtime_admission(self):
        status, response = await asyncio.to_thread(
            self._post, "/api/jobs",
            {
                "site_id": 1,
                "operation": "erase",
                "resolved_ic_support": {"hardware_runtime_ready": True},
            },
        )
        self.assertEqual(status, 400)
        self.assertFalse(response["ok"])
        self.assertEqual(self.ps.manager.registry.all(), [])


if __name__ == "__main__":
    unittest.main()
