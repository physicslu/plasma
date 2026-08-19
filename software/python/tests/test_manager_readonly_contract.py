from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

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
        PlasmaManagerHandler.aggregator = ReadOnlyAggregator()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaManagerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        PlasmaManagerHandler.aggregator = cls.original_aggregator

    def request(self, method: str):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request(method, "/api/fleet")
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        content_type = response.getheader("Content-Type")
        conn.close()
        return status, payload, content_type

    def test_all_mutating_http_methods_are_explicitly_rejected_as_json(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, payload, content_type = self.request(method)
                self.assertEqual(status, 405)
                self.assertFalse(payload["ok"])
                self.assertIn("read-only", payload["error"]["message"])
                self.assertTrue(content_type.startswith("application/json"))

    def test_cli_requires_an_explicit_manager_config(self):
        server_source = (
            Path(__file__).resolve().parents[1] / "plasma_manager" / "server.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"--config"', server_source)
        self.assertIn("required=True", server_source)
        self.assertNotIn('default=Path("config/manager.yaml")', server_source)


if __name__ == "__main__":
    unittest.main()
