from __future__ import annotations

import json
import threading
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from plasma_manager.client import PPUHTTPError, PPUHttpClient


class FakePPUGatewayHandler(BaseHTTPRequestHandler):
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
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "ok": False,
                    "gateway": "alive",
                    "execution": "unavailable",
                    "error": {"message": "local Plasma Server is unavailable"},
                },
            )
            return
        if self.path == "/api/node":
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"not-json")


class ManagerPPUHttpClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakePPUGatewayHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.client = PPUHttpClient(
            f"http://127.0.0.1:{cls.server.server_port}",
            timeout_s=1.0,
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_liveness_uses_real_http_transport(self):
        status, payload = self.client.liveness()
        self.assertEqual(status, 200)
        self.assertEqual(payload["gateway"], "alive")

    def test_readiness_preserves_expected_503_payload(self):
        status, payload = self.client.readiness()
        self.assertEqual(status, 503)
        self.assertEqual(payload["execution"], "unavailable")
        self.assertEqual(payload["error"]["message"], "local Plasma Server is unavailable")

    def test_unexpected_http_status_and_invalid_json_are_errors(self):
        with self.assertRaises(PPUHTTPError):
            self.client.node()
        with self.assertRaises(PPUHTTPError):
            self.client.status()


if __name__ == "__main__":
    unittest.main()
