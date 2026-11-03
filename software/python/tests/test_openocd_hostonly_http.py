"""Host-only HTTP-to-Site Flash flow; no Z2, FPGA, C driver or DUT."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_client.client import PlasmaClient
from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.ic_support import get_default_ic_support_resolver
from plasma_interfaces.openocd import OpenOCDInterface
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager
from plasma_web.gateway import PlasmaWebHandler


FLASH_BASE = 0x08000000
FLASH_BYTES = 64 * 1024
TERMINAL = {"success", "failed", "error", "timeout", "cancelled", "aborted"}


class FakeProcess:
    def __init__(self, returncode: int):
        self.returncode = returncode

    async def communicate(self):
        return b"host-only-openocd", b""


class FlashSimulator:
    """Fake process launcher used only through the explicit test injection."""

    def __init__(self) -> None:
        self.memory = bytearray(bytes([0xFF]) * FLASH_BYTES)
        self.commands: list[str] = []

    async def launch(self, *argv, **_kwargs):
        commands = [argv[i + 1] for i, item in enumerate(argv[:-1]) if item == "-c"]
        self.commands.extend(commands)
        rc = 0
        for command in commands:
            if command.startswith("flash erase_address "):
                _, _, start, length = command.split()
                if int(start, 0) != FLASH_BASE or int(length, 0) != FLASH_BYTES:
                    rc = 2
                    break
                self.memory[:] = bytes([0xFF]) * FLASH_BYTES
            elif command.startswith(("flash write_image ", "flash verify_image ")):
                staged = re.search(r"\\{([^{}]+)\\}", command)
                if staged is None:
                    rc = 3
                    break
                image = Path(staged.group(1)).read_bytes()
                if not image or len(image) > FLASH_BYTES:
                    rc = 4
                    break
                if command.startswith("flash write_image "):
                    self.memory[:len(image)] = image
                elif self.memory[:len(image)] != image:
                    rc = 5
                    break
            elif command.startswith("dump_image "):
                staged = re.search(r"\\{([^{}]+)\\}", command)
                if staged is None:
                    rc = 6
                    break
                _, output, start, length = command.split()
                position = int(start, 0) - FLASH_BASE
                size = int(length, 0)
                if position < 0 or position + size > FLASH_BYTES:
                    rc = 7
                    break
                Path(staged.group(1)).write_bytes(self.memory[position:position + size])
        return FakeProcess(rc)


class HostOnlyFlashHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_rest_flash_cycle_site2_and_readback_download(self) -> None:
        image = b"PLASMA-HOST-ONLY-SITE2"
        sha256 = hashlib.sha256(image).hexdigest()
        simulator = FlashSimulator()
        resolver = get_default_ic_support_resolver()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = PlasmaConfig(
                server=ServerConfig(
                    host="127.0.0.1",
                    port=0,
                    output_root=root / "output",
                    log_root=root / "logs",
                    max_supported_sites=2,
                    max_concurrent_jobs=1,
                ),
                sites=[SiteConfig(
                    id=2,
                    enabled=True,
                    interface="openocd",
                    target="STM32F103C8T6",
                    openocd={
                        "executable": "fake-openocd",
                        "interface_cfg": "interface/cmsis-dap.cfg",
                        "target_cfg": "target/stm32f1x.cfg",
                        "work_dir": str(root),
                    },
                )],
            )
            manager = SiteManager(
                config,
                interface_factory=lambda site: OpenOCDInterface(
                    site.openocd,
                    process_launcher=simulator.launch,
                    resolver=resolver,
                ),
                ic_support_resolver=resolver,
            )
            ps = PlasmaServer(config, manager)
            await ps.start()
            ps_host, ps_port = ps.address

            class TestGateway(PlasmaWebHandler):
                pass

            TestGateway.client_factory = staticmethod(
                lambda: PlasmaClient(ps_host, ps_port)
            )
            TestGateway.output_root = root / "output"
            TestGateway.engineering_provider = None
            TestGateway.batch_runtime = None
            TestGateway.static_root = None
            http = ThreadingHTTPServer(("127.0.0.1", 0), TestGateway)
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()

            async def api(method: str, endpoint: str, payload=None):
                def request():
                    conn = HTTPConnection("127.0.0.1", http.server_port, timeout=10)
                    try:
                        data = json.dumps(payload).encode() if payload is not None else None
                        headers = {"Content-Type": "application/json"} if data else {}
                        conn.request(method, endpoint, data, headers)
                        response = conn.getresponse()
                        raw = response.read()
                        content_type = response.getheader("Content-Type", "")
                        value = json.loads(raw) if "application/json" in content_type else raw
                        return response.status, value
                    finally:
                        conn.close()

                return await asyncio.to_thread(request)

            async def submit_and_wait(body: dict):
                status, payload = await api("POST", "/api/jobs", body)
                self.assertEqual(status, 202, payload)
                job_id = payload["job"]["job_id"]
                for _ in range(150):
                    status, observation = await api("GET", "/api/status?job=" + job_id)
                    self.assertEqual(status, 200, observation)
                    job = observation["job"]
                    if job["state"] in TERMINAL:
                        return job_id, job
                    await asyncio.sleep(0.02)
                self.fail("Host-only Site Job never became terminal")

            try:
                _, erased = await submit_and_wait({"site_id": 2, "operation": "erase"})
                self.assertEqual(erased["state"], "success", erased)

                def asset(op: str, data: bytes):
                    return {
                        "site_id": 2,
                        "operation": op,
                        "asset_name": "test.bin",
                        "asset_type": "image",
                        "asset_format": "binary",
                        "asset_size": len(data),
                        "asset_sha256": hashlib.sha256(data).hexdigest(),
                        "asset_base64": base64.b64encode(data).decode(),
                    }

                _, programmed = await submit_and_wait(asset("program", image))
                self.assertEqual(programmed["state"], "success", programmed)
                _, verified = await submit_and_wait(asset("verify", image))
                self.assertEqual(verified["state"], "success", verified)

                read_id, read = await submit_and_wait({
                    "site_id": 2, "operation": "read",
                    "offset": 0, "length": len(image),
                })
                self.assertEqual(read["state"], "success", read)
                status, downloaded = await api(
                    "GET", f"/api/jobs/{read_id}/files/read_SITE2_flash.bin"
                )
                self.assertEqual(status, 200)
                self.assertEqual(downloaded, image)
                self.assertEqual(hashlib.sha256(downloaded).hexdigest(), sha256)

                # A mismatching image must never be reported as Verify PASS.
                _, rejected = await submit_and_wait(asset("verify", b"WRONG-IMAGE"))
                self.assertNotEqual(rejected["state"], "success")
                self.assertEqual(bytes(simulator.memory[:len(image)]), image)
                self.assertTrue(any(x.startswith("flash erase_address ") for x in simulator.commands))
                self.assertTrue(any(x.startswith("flash write_image ") for x in simulator.commands))
                self.assertTrue(any(x.startswith("flash verify_image ") for x in simulator.commands))
                self.assertTrue(any(x.startswith("dump_image ") for x in simulator.commands))
            finally:
                await asyncio.to_thread(http.shutdown)
                http.server_close()
                thread.join(timeout=5)
                await ps.close()


if __name__ == "__main__":
    unittest.main()
