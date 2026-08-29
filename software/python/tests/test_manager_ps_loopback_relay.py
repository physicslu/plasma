from __future__ import annotations

import io
import json
import threading
import unittest
from contextlib import redirect_stdout
from http import HTTPStatus
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from plasma_manager.config import ManagerConfig, ManagerConfigError, PPURegistryEntry, load_manager_config
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
                "pattern": body["pattern"],
                "seed": body["seed"],
                "payload_length": body["payload_length"],
                "tx_crc32": body["tx_crc32"],
                "rx_crc32": body["tx_crc32"],
                "ppu_rtt_ms": 1.25,
            },
            "payload_base64": body["payload_base64"],
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
        FakePPUGatewayHandler.requests.clear()
        cls.ppu_server = ThreadingHTTPServer(("127.0.0.1", 0), FakePPUGatewayHandler)
        cls.ppu_thread = threading.Thread(target=cls.ppu_server.serve_forever, daemon=True)
        cls.ppu_thread.start()

        cls.original_config = PlasmaManagerHandler.config
        PlasmaManagerHandler.config = ManagerConfig(
            request_timeout_s=1.0,
            ppus=(
                PPURegistryEntry(
                    endpoint=f"http://127.0.0.1:{cls.ppu_server.server_port}",
                    alias="ppu-a",
                ),
            ),
        )
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
        conn.request(
            "POST",
            f"/api/ppus/{alias}/diagnostics/loopback",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        conn.close()
        return status, payload

    @staticmethod
    def request_body(endpoint: str = "ps") -> dict:
        return {
            "endpoint": endpoint,
            "test_id": "manager-relay-test",
            "sequence": 3,
            "pattern": "prbs",
            "seed": "0x12345678",
            "payload_length": 1,
            "payload_base64": "AA==",
            "tx_crc32": "d202ef8d",
            "timeout_ms": 5000,
        }

    def test_manager_relay_crosses_real_http_boundary_and_adds_proof(self):
        body = self.request_body()
        output = io.StringIO()
        with redirect_stdout(output):
            status, payload = self.relay("ppu-a", body)

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["loopback"]["source"], "ps")
        self.assertEqual(payload["loopback"]["test_id"], body["test_id"])
        self.assertEqual(payload["manager"]["relay"], "pass-through")
        self.assertEqual(payload["manager"]["ppu_alias"], "ppu-a")
        self.assertGreaterEqual(payload["manager"]["manager_rtt_ms"], 0)
        self.assertEqual(FakePPUGatewayHandler.requests[-1], body)

        log_entry = json.loads(output.getvalue().strip())
        self.assertEqual(log_entry["event"], "manager_ps_loopback_relay")
        self.assertEqual(log_entry["ppu_alias"], "ppu-a")
        self.assertEqual(log_entry["test_id"], body["test_id"])
        self.assertEqual(log_entry["sequence"], body["sequence"])
        self.assertEqual(log_entry["result"], "pass")
        self.assertNotIn("payload_base64", log_entry)

    def test_manager_rejects_non_ps_endpoint_before_contacting_ppu(self):
        before = len(FakePPUGatewayHandler.requests)
        status, payload = self.relay("ppu-a", self.request_body("pl"))
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "unsupported_endpoint")
        self.assertEqual(len(FakePPUGatewayHandler.requests), before)

    def test_manager_resolves_only_enrolled_aliases(self):
        status, payload = self.relay("not-enrolled", self.request_body())
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "ppu_not_found")

    def test_manager_configuration_rejects_ambiguous_command_aliases(self):
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "manager.yaml"
            config_path.write_text(
                """
manager:
  host: 127.0.0.1
ppus:
  - alias: duplicate
    endpoint: http://127.0.0.1:18080
  - alias: duplicate
    endpoint: http://127.0.0.1:18081
""".lstrip(),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ManagerConfigError, "PPU aliases must be unique"):
                load_manager_config(config_path)


if __name__ == "__main__":
    unittest.main()
