"""Host-only WEB -> real PS -> SiteWorker -> opt-in PoC adapter Job test.

The injected executor records compiled-plan calls only. This MUST NOT be
reported as SWD, flash programming, FPGA or real hardware qualification.
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
from plasma_core.ic_support import get_default_ic_support_resolver
from plasma_core.errors import ErrorCode
from plasma_interfaces.bluepill_openocd_job import BluepillPoCOpenOCDInterface
from plasma_interfaces.openocd_executor import OpenOCDExecutionResult
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager
from plasma_web.gateway import PlasmaWebHandler


class SyntheticExecutor:
    """Captures canonical plans; never launches OpenOCD or touches any DUT."""

    def __init__(self):
        self.calls = []

    async def execute(self, plan, support, request):
        self.calls.append((plan, support, request))
        return OpenOCDExecutionResult(stdout="HOST_SYNTHETIC_ONLY", stderr="", read_sections={})


class BluePillWebPsCandidateJobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="plasma-bb-job-")
        root = Path(self.temp.name)
        self.resolver = get_default_ic_support_resolver()
        config = PlasmaConfig(
            server=ServerConfig(
                host="127.0.0.1", port=0, max_supported_sites=1,
                max_concurrent_jobs=1, output_root=root / "out",
                log_root=root / "log",
            ),
            sites=[SiteConfig(id=1, enabled=True, interface="openocd",
                target="STM32F103C8T6",
                openocd={
                    "interface_cfg": "interface/remote_bitbang.cfg",
                    "target_cfg": "target/stm32f1x.cfg",
                })],
        )
        self.executor = SyntheticExecutor()
        self.shutdowns = 0
        self.owner_valid = True

        async def shutdown():
            self.shutdowns += 1

        def factory(site):
            return BluepillPoCOpenOCDInterface(
                site.openocd, self.resolver, executor=self.executor,
                admission_check=lambda request, route: self.owner_valid
                    and request.site_id == 1
                    and request.target == "STM32F103C8T6",
                shutdown=shutdown,
            )

        manager = SiteManager(config, interface_factory=factory,
                              ic_support_resolver=self.resolver)
        self.ps = PlasmaServer(config, manager=manager)
        await self.ps.start()
        host, port = self.ps.address

        class Gateway(PlasmaWebHandler):
            client_factory = staticmethod(lambda: PlasmaClient(
                host, port, response_timeout_s=3.0))
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
        self.temp.cleanup()

    def _request_sync(self, method, path, body=None):
        c = HTTPConnection("127.0.0.1", self.gateway.server_port, timeout=4)
        raw = json.dumps(body).encode() if body is not None else None
        c.request(method, path, raw,
                  {"Content-Type": "application/json"} if raw else {})
        resp = c.getresponse()
        status = resp.status
        payload = json.loads(resp.read())
        c.close()
        return status, payload

    async def request(self, method, path, body=None):
        return await asyncio.to_thread(self._request_sync, method, path, body)

    async def test_injected_candidate_receives_canonical_sha_bound_program_job(self):
        image = bytes(range(32))
        digest = hashlib.sha256(image).hexdigest()
        status, response = await self.request("POST", "/api/jobs", {
            "site_id": 1, "operation": "program",
            "asset_name": "disposable-bluepill.bin", "asset_type": "image",
            "asset_format": "binary", "asset_size": len(image),
            "asset_sha256": digest,
            "asset_base64": base64.b64encode(image).decode(),
        })
        self.assertEqual(status, 202)
        job = response["job"]
        self.assertEqual(job["site_id"], 1)
        for _ in range(200):
            status, payload = await self.request("GET",
                                                  f"/api/status?job={job['job_id']}")
            self.assertEqual(status, 200)
            if payload["job"]["state"] in ("success", "failed", "timeout", "aborted"):
                break
            await asyncio.sleep(0.01)
        else:
            self.fail("Synthetic job did not complete")

        self.assertEqual(payload["job"]["state"], "success")
        self.assertEqual(len(self.executor.calls), 1)
        plan, support, captured = self.executor.calls[0]
        self.assertEqual(support.icpn, "STM32F103C8T6")
        self.assertEqual(captured.image_sha256, digest)
        self.assertEqual(captured.image, image)
        self.assertEqual(captured.site_id, 1)
        self.assertEqual(plan.main_flash_size_bytes, 64 * 1024)
        self.assertIn("flash write_image", " ".join(plan.commands))
        self.assertGreaterEqual(self.shutdowns, 1)

    async def test_hardware_admission_revocation_rejects_before_job_queue(self):
        self.owner_valid = False
        status, data = await self.request("POST", "/api/jobs", {
            "site_id": 1, "operation": "erase",
        })
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["error_code"], ErrorCode.INTERFACE_NOT_CONFIGURED.value)
        self.assertEqual(self.executor.calls, [])
        self.assertFalse(self.ps.manager.execution_lease_snapshot()["busy"])
        self.assertEqual(self.ps.manager.registry.all(), [])


if __name__ == "__main__":
    unittest.main()
