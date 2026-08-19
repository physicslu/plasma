from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.gateway import PlasmaWebHandler


class FakeFleetClient:
    fail_status = False
    status_calls = 0

    async def status(self, **kwargs):
        FakeFleetClient.status_calls += 1
        if FakeFleetClient.fail_status:
            raise OSError("simulated local Plasma Server outage")
        return {
            "ok": True,
            "protocol_version": "3.2",
            "ppu": {
                "ppu_id": "ppu-test",
                "facility_id": "facility-test",
                "model": "test-model",
                "display_name": "Test PPU",
                "site_count": 4,
                "enabled_site_count": 2,
                "capabilities": {
                    "max_supported_sites": 8,
                    "operations": ["erase", "program", "verify", "read"],
                },
            },
            "sites": [
                {"site_id": 1, "enabled": True, "state": "idle"},
                {"site_id": 2, "enabled": True, "state": "idle"},
            ],
        }


class FleetContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_client_factory = PlasmaWebHandler.client_factory
        PlasmaWebHandler.client_factory = staticmethod(FakeFleetClient)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        PlasmaWebHandler.client_factory = cls.original_client_factory

    def setUp(self):
        FakeFleetClient.fail_status = False
        FakeFleetClient.status_calls = 0

    def request(self, path):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("GET", path)
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        conn.close()
        return status, payload

    def test_liveness_does_not_depend_on_local_plasma_server(self):
        FakeFleetClient.fail_status = True

        status, payload = self.request("/api/health/live")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["gateway"], "alive")
        self.assertEqual(FakeFleetClient.status_calls, 0)

    def test_readiness_reports_local_execution_ready(self):
        status, payload = self.request("/api/health/ready")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["execution"], "ready")
        self.assertEqual(payload["ppu_id"], "ppu-test")
        self.assertEqual(FakeFleetClient.status_calls, 1)

    def test_readiness_returns_503_when_local_execution_is_unavailable(self):
        FakeFleetClient.fail_status = True

        status, payload = self.request("/api/health/ready")

        self.assertEqual(status, 503)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["gateway"], "alive")
        self.assertEqual(payload["execution"], "unavailable")

    def test_node_descriptor_declares_manager_optional(self):
        status, payload = self.request("/api/node")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["contract_version"], "1")
        self.assertEqual(payload["node_role"], "ppu")
        self.assertFalse(payload["manager_required"])
        self.assertEqual(payload["ppu"]["ppu_id"], "ppu-test")
        self.assertEqual(payload["ppu"]["site_count"], 4)
        self.assertEqual(payload["links"]["status"], "/api/status")
        self.assertEqual(payload["links"]["jobs"], "/api/jobs")

    def test_existing_standalone_status_path_remains_available(self):
        status, payload = self.request("/api/status")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["ppu"]["ppu_id"], "ppu-test")


if __name__ == "__main__":
    unittest.main()
