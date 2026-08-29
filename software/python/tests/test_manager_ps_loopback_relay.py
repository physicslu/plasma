from __future__ import annotations

import json
import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from plasma_manager.config import ManagerConfig, PPURegistryEntry
from plasma_manager.server import PlasmaManagerHandler


class FakePPUGatewayHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, format, *args):
        return

    def do_POST(self):
        if self.path != "/api/engineering/diagnostics/loopback":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(content_length))
        self.__class__.requests.append(body)
        payload = {
            "ok": True,
            "diagnostic_protocol_version": "1",
            "loopback": {
                "endpoint": "ps",
                "source": "ps",
                "test_id": body["test_id"],
                "sequence": body["sequence"],
                "transform": "echo",
                "pattern": body.get("pattern", "prbs"),
                "seed": body.get("seed", ""),
                "payload_length": body.get("payload_length", 1),
                "tx_crc32": body.get("tx_crc32", "00000000"),
                "rx_crc32": body.get("tx_crc32", "00000000"),
                "ppu_rtt_ms": 1.25,
            },
            "payload_base64": body.get("payload_base64", "AA=="),
        }
        data = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ManagerPsLoopbackRelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ppu_server = ThreadingHTTPServer(("127.0.0.1", 0), FakePPUGatewayHandler)
        cls.ppu_thread = threading.Thread(target=cls.ppu_server.serve_forever, daemon=True)
        cls.ppu_thread.start()

        cls.original_config = PlasmaManagerHandler.config
        cls.config = ManagerConfig(
            request_timeout_s=1.0,
            ppus=(
                PPURegistryEntry(
                    endpoint=f"http://127.0.0.1:{cls.ppu_server.server_port}",
                    alias="ppu-a",
                ),
            ),
        )
        PlasmaManagerHandler.config = cls.config
        cls.manager_server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaManagerHandler)
        cls.manager_thread = threading.Thread(target=cls.manager_server.serve_forever, daemon=True)
        cls.manager_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.manager_server.shutdown()
        cls.manager_server.server_close()
        cls.manager_thread.join()
        cls.ppu_server.shutdown()
        cls.ppu_server.server_close()
        cls.ppu_thread.join()
        PlasmaManagerHandler.config = cls.original_config

    def relay(self, alias: str, body: dict):
        conn = HTTPConnection("127.0.0.1", self.manager_server.server_port, timeout=2)
        encoded = json.dumps(body)
        conn.request(
            "POST",
            f"/api/ppus/{alias}/diagnostics/loopback",
            body=encoded,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        conn.close()
        return status, payload

    def test_manager_relay_crosses_real_http_boundary_and_preserves_ppu_response(self):
        request = {
            "endpoint": "ps",
            "test_id": "manager-relay-test",
            "sequence": 3,
            "pattern": "prbs",
            "seed": "0x12345678",
            "payload_length": 1,
            "payload_base64": "AA==",
            "tx_crc32": "d202ef8d",
            "timeout_ms": 5000,
        }
        status, payload = self.relay("ppu-a", request)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["loopback"]["source"], "ps")
        self.assertEqual(payload["loopback"]["test_id"], request["test_id"])
        self.assertEqual(payload["manager"]["relay"], "pass-through")
        self.assertEqual(payload["manager"]["ppu_alias"], "ppu-a")
        self.assertGreaterEqual(payload["manager"]["manager_rtt_ms"], 0)
        self.assertEqual(FakePPUGatewayHandler.requests[-1], request)

    def test_manager_rejects_non_ps_endpoint_before_contacting_ppu(self):
        before = len(FakePPUGatewayHandler.requests)
        status, payload = self.relay("ppu-a", {"endpoint": "pl", "timeout_ms": 5000})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "unsupported_endpoint")
        self.assertEqual(len(FakePPUGatewayHandler.requests), before)


if __name__ == "__main__":
    unittest.main()
