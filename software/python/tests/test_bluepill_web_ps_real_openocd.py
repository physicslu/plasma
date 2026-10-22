"""Host-only canonical WEB -> real OpenOCD -> socket -> virtual SWD target.

This fixture deliberately has only a DP IDR responder and cannot emulate
Flash. A WEB erase/program Job MUST be terminal *failure*, not fake success.
The real upstream executable is injected from the pinned build CI artifact.
No Z2, Blue Pill, FPGA reconfiguration, USB or network outside loopback.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_client.client import PlasmaClient
from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.ic_support import get_default_ic_support_resolver
from plasma_interfaces.bluepill_openocd_job import BluepillPoCOpenOCDInterface
from plasma_interfaces.bluepill_openocd_session import BluepillOpenOCDSessionExecutor
from plasma_server.site_manager import SiteManager
from plasma_server.server import PlasmaServer
from plasma_web.gateway import PlasmaWebHandler
from tests.test_bluepill_openocd_virtual_target import VirtualWordPort


ROOT = Path(__file__).resolve().parents[3]
ADAPTER_CFG = ROOT / "specs/bluepill-poc/openocd-remote-bitbang-adapter-only.cfg"


@unittest.skipUnless(os.environ.get("PLASMA_BLUEPILL_OPENOCD"),
                     "requires real explicitly pinned OpenOCD binary built by Host CI")
class RealOpenOCDWebPsJobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="plasma-real-bb-web-")
        root = Path(self.temp.name)
        config = PlasmaConfig(
            server=ServerConfig(
                host="127.0.0.1", port=0, max_supported_sites=1,
                max_concurrent_jobs=1, output_root=root / "out",
                log_root=root / "logs",
            ),
            sites=[SiteConfig(id=1, enabled=True, interface="openocd",
                target="STM32F103C8T6",
                openocd={"interface_cfg": str(ADAPTER_CFG),
                         "target_cfg": "target/stm32f1x.cfg"})],
        )
        self.port = VirtualWordPort()
        self.resolver = get_default_ic_support_resolver()
        binary = Path(os.environ["PLASMA_BLUEPILL_OPENOCD"]).resolve()
        scripts = binary.parent.parent / "share/openocd/scripts"
        self.session = BluepillOpenOCDSessionExecutor(
            executable=binary,
            scripts_root=scripts,
            adapter_config=ADAPTER_CFG,
            work_dir=ROOT,
            word_port_factory=lambda: self.port,
            command_timeout_s=12.0,
            socket_timeout_s=6.0,
        )
        self.shutdowns = 0

        async def shutdown():
            self.shutdowns += 1

        def make_interface(site):
            return BluepillPoCOpenOCDInterface(
                site.openocd, self.resolver,
                executor=self.session,
                admission_check=lambda req, route: (
                    req.site_id == 1
                    and req.target == "STM32F103C8T6"
                    and self.session is not None
                ),
                shutdown=shutdown,
            )

        manager = SiteManager(config, interface_factory=make_interface,
                              ic_support_resolver=self.resolver)
        self.server = PlasmaServer(config, manager=manager)
        await self.server.start()
        host, port = self.server.address

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
        await self.server.close()
        self.temp.cleanup()

    def _request_sync(self, method, path, body=None):
        conn = HTTPConnection("127.0.0.1", self.gateway.server_port, timeout=15)
        data = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, data, {"Content-Type": "application/json"} if data else {})
        response = conn.getresponse()
        code = response.status
        payload = json.loads(response.read())
        conn.close()
        return code, payload

    async def request(self, method, path, body=None):
        return await asyncio.to_thread(self._request_sync, method, path, body)

    async def test_real_openocd_process_cannot_fake_flash_erase_success(self):
        http_code, response = await self.request("POST", "/api/jobs",
                                                 {"site_id": 1, "operation": "erase"})
        self.assertEqual(http_code, 202)
        job_id = response["job"]["job_id"]
        for _ in range(300):
            code, status = await self.request("GET", f"/api/status?job={job_id}")
            self.assertEqual(code, 200)
            if status["job"]["state"] in {
                "success", "failed", "error", "timeout", "aborted", "cancelled"
            }:
                break
            await asyncio.sleep(0.025)
        else:
            self.fail("Real OpenOCD Job did not reach a terminal state")
        self.assertNotEqual(status["job"]["state"], "success",
                            "Virtual IDR-only target must never pass Flash Erase")
        self.assertGreater(self.session.last_command_count, 0,
                           "Real OpenOCD never sent remote_bitbang commands")
        self.assertGreaterEqual(self.port.dpidr_reads, 1,
                                "Real OpenOCD never reached virtual DP IDR")
        self.assertTrue(self.session.last_process_argv)
        self.assertEqual(self.session.last_process_argv[0],
                         str(Path(os.environ["PLASMA_BLUEPILL_OPENOCD"]).resolve()))
        self.assertIn("-s", self.session.last_process_argv)
        self.assertIn("-f", self.session.last_process_argv)
        self.assertGreaterEqual(self.shutdowns, 1)
        self.assertFalse(self.session.last_socket_path.exists())
        self.assertFalse(self.server.manager.execution_lease_snapshot()["busy"])


if __name__ == "__main__":
    unittest.main()
