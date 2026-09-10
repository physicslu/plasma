from __future__ import annotations

import json
import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from plasma_manager.config import ManagerConfig, PPURegistryEntry
from plasma_manager.server import PlasmaManagerHandler


class FakeSiteGatewayHandler(BaseHTTPRequestHandler):
    observed: dict[str, object] = {}

    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).observed = {
            "path": self.path,
            "if_match": self.headers.get("If-Match"),
            "idempotency_key": self.headers.get("Idempotency-Key"),
            "authorization": self.headers.get("Authorization"),
            "forbidden": self.headers.get("X-Do-Not-Forward"),
            "body": body,
        }
        payload = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ManagerSiteCasRelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ppu_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSiteGatewayHandler)
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

    def test_site_if_match_is_forwarded_without_opening_generic_header_proxy(self):
        body = json.dumps(
            {"enabled": True, "interface": "mock", "target": "TARGET-NEW"},
            separators=(",", ":"),
        ).encode("utf-8")
        revision = "sha256:" + "a" * 64
        connection = HTTPConnection("127.0.0.1", self.manager_server.server_port, timeout=3)
        connection.request(
            "POST",
            "/api/ppus/ppu-a/gateway/api/settings/sites/1",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "Authorization": "Bearer test-secret",
                "Idempotency-Key": "site-write-1",
                "If-Match": f'"{revision}"',
                "X-Do-Not-Forward": "private-hop-header",
            },
        )
        response = connection.getresponse()
        response.read()
        connection.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(FakeSiteGatewayHandler.observed["path"], "/api/settings/sites/1")
        self.assertEqual(FakeSiteGatewayHandler.observed["if_match"], f'"{revision}"')
        self.assertEqual(FakeSiteGatewayHandler.observed["idempotency_key"], "site-write-1")
        self.assertEqual(FakeSiteGatewayHandler.observed["authorization"], "Bearer test-secret")
        self.assertIsNone(FakeSiteGatewayHandler.observed["forbidden"])
        self.assertEqual(FakeSiteGatewayHandler.observed["body"], body)


if __name__ == "__main__":
    unittest.main()
