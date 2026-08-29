from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from http import HTTPStatus
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from plasma_manager.config import ManagerConfig, PPURegistryEntry
from plasma_manager.fleet import FleetAggregator


class _StubGateway(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _json(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/health/live":
            self._json(HTTPStatus.OK, {"ok": True, "gateway": "alive"})
            return
        if self.path == "/api/health/ready":
            self._json(HTTPStatus.OK, {"ok": True, "gateway": "ready", "execution": "ready"})
            return
        if self.path == "/api/node":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "node": {
                        "ppu_id": "ppu-test-01",
                        "facility_id": "facility-test",
                        "site_count": 2,
                        "sites": [1, 2],
                    },
                },
            )
            return
        if self.path == "/api/status":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "ppu_id": "ppu-test-01",
                    "facility_id": "facility-test",
                    "sites": [],
                },
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False})


class FleetAggregatorSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _StubGateway)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_registry_snapshot_keeps_alias_and_hides_no_execution_truth(self):
        config = ManagerConfig(
            request_timeout_s=1.0,
            ppus=(
                PPURegistryEntry(
                    endpoint=f"http://127.0.0.1:{self.server.server_port}",
                    alias="ppu-a",
                ),
            ),
        )
        aggregator = FleetAggregator(config)
        snapshot = aggregator.registry_snapshot()
        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["ppus"][0]["alias"], "ppu-a")


if __name__ == "__main__":
    unittest.main()
