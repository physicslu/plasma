from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_manager.config import ManagerConfig, PPURegistryEntry
from plasma_manager.server import PlasmaManagerHandler


class ReadOnlyAggregator:
    def registry_snapshot(self):
        return {"ok": True, "ppus": []}

    def fleet_snapshot(self):
        return {"ok": True, "degraded": False, "ppus": []}


class ManagerReadOnlyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_aggregator = PlasmaManagerHandler.aggregator
        cls.original_config = PlasmaManagerHandler.config
        PlasmaManagerHandler.aggregator = ReadOnlyAggregator()
        PlasmaManagerHandler.config = ManagerConfig(
            ppus=(PPURegistryEntry(endpoint="http://127.0.0.1:9", alias="ppu-a"),),
        )
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaManagerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        PlasmaManagerHandler.aggregator = cls.original_aggregator
        PlasmaManagerHandler.config = cls.original_config

    def request(self, method: str, path: str = "/api/fleet"):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request(method, path)
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        content_type = response.getheader("Content-Type")
        conn.close()
        return status, payload, content_type

    def test_mutating_http_methods_remain_rejected_outside_approved_loopback_route(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, payload, content_type = self.request(method)
                self.assertEqual(status, 405)
                self.assertFalse(payload["ok"])
                self.assertIn("PS loopback", payload["error"]["message"])
                self.assertTrue(content_type.startswith("application/json"))

    def test_unknown_ppu_alias_is_not_an_open_proxy(self):
        status, payload, _ = self.request(
            "POST",
            "/api/ppus/not-enrolled/diagnostics/loopback",
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "ppu_not_found")

    def test_cli_requires_an_explicit_manager_config(self):
        server_source = (
            Path(__file__).resolve().parents[1] / "plasma_manager" / "server.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"--config"', server_source)
        self.assertIn("required=True", server_source)
        self.assertNotIn('default=Path("config/manager.yaml")', server_source)


if __name__ == "__main__":
    unittest.main()
