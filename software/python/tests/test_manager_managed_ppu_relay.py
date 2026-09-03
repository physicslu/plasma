from __future__ import annotations

import json
import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from plasma_manager.config import ManagerConfig, PPURegistryEntry
from plasma_manager.server import PlasmaManagerHandler


class FakeManagedPPUGatewayHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, format, *args):
        return

    def _record(self, body: bytes = b"") -> None:
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "idempotency_key": self.headers.get("Idempotency-Key"),
                "content_type": self.headers.get("Content-Type"),
                "body": body,
            }
        )

    def do_GET(self):
        self._record()
        if "/files/" in self.path:
            data = b"readback-bytes"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="readback.bin"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        data = json.dumps({"ok": True, "path": self.path}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._record(body)
        if self.path == "/api/engineering/diagnostics/loopback":
            request = json.loads(body)
            payload = {
                "ok": True,
                "diagnostic_protocol_version": "1",
                "loopback": {
                    "endpoint": "ps",
                    "source": "ps",
                    "test_id": request["test_id"],
                    "sequence": request["sequence"],
                    "transform": "echo",
                    "pattern": request["pattern"],
                    "seed": request["seed"],
                    "payload_length": request["payload_length"],
                    "tx_crc32": request["tx_crc32"],
                    "rx_crc32": request["tx_crc32"],
                    "ppu_rtt_ms": 0.5,
                },
                "payload_base64": request["payload_base64"],
            }
            status = HTTPStatus.OK
        else:
            payload = {"ok": True, "path": self.path, "size": len(body)}
            status = HTTPStatus.CREATED if "programming-assets" in self.path else HTTPStatus.OK
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ManagerManagedPPURelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FakeManagedPPUGatewayHandler.requests.clear()
        cls.ppu_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeManagedPPUGatewayHandler)
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

    def relay(self, method: str, target: str, *, body: bytes | None = None, headers: dict | None = None):
        conn = HTTPConnection("127.0.0.1", self.manager_server.server_port, timeout=3)
        request_headers = dict(headers or {})
        if body is not None:
            request_headers.setdefault("Content-Length", str(len(body)))
        conn.request(method, f"/api/ppus/ppu-a/gateway{target}", body=body, headers=request_headers)
        response = conn.getresponse()
        data = response.read()
        result = (response.status, dict(response.getheaders()), data)
        conn.close()
        return result

    def test_json_command_preserves_security_headers(self):
        body = b"{}"
        status, _, data = self.relay(
            "POST",
            "/api/engineering/session",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test-secret",
                "Idempotency-Key": "command-123",
                "X-Do-Not-Forward": "private-hop-header",
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])
        observed = FakeManagedPPUGatewayHandler.requests[-1]
        self.assertEqual(observed["authorization"], "Bearer test-secret")
        self.assertEqual(observed["idempotency_key"], "command-123")
        self.assertEqual(observed["content_type"], "application/json")
        self.assertEqual(observed["body"], body)

    def test_binary_programming_asset_is_relayed_byte_for_byte(self):
        asset = bytes(range(256)) * 8
        path = (
            "/api/engineering/targets/fac-a/ppu-01/api/programming-assets"
            "?session_id=s1&name=image.bin&type=image&format=binary&sha256=abc"
        )
        status, _, data = self.relay(
            "POST",
            path,
            body=asset,
            headers={"Content-Type": "application/octet-stream", "Idempotency-Key": "asset-1"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(data)["size"], len(asset))
        observed = FakeManagedPPUGatewayHandler.requests[-1]
        self.assertEqual(observed["body"], asset)
        self.assertIn("session_id=s1", observed["path"])

    def test_batch_asset_envelope_is_relayed_byte_for_byte(self):
        body = json.dumps(
            {
                "session_id": "session-1",
                "targets": [{"facility_id": "fac-a", "ppu_id": "ppu-01", "site_ids": [1]}],
                "operations": ["program", "verify"],
                "execution_policy": {
                    "repeat_count": 1,
                    "site_retry_limit": 0,
                    "failed_site_stop_threshold": None,
                },
                "asset": {
                    "asset_name": "image.bin",
                    "asset_type": "image",
                    "asset_format": "binary",
                    "asset_size": 3,
                    "asset_sha256": "0" * 64,
                    "asset_base64": "AAEC",
                },
                "read": {"offset": 0, "length": 256},
            },
            separators=(",", ":"),
        ).encode("utf-8")
        status, _, data = self.relay(
            "POST",
            "/api/batches",
            body=body,
            headers={"Content-Type": "application/json", "Idempotency-Key": "batch-1"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])
        observed = FakeManagedPPUGatewayHandler.requests[-1]
        self.assertEqual(observed["path"], "/api/batches")
        self.assertEqual(observed["body"], body)
        self.assertEqual(observed["idempotency_key"], "batch-1")

    def test_managed_workspace_settings_routes_preserve_security_headers(self):
        for path in ("/api/settings/gateway", "/api/settings/ppu-network", "/api/mock/runtime"):
            status, _, data = self.relay("GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)["path"], path)

            body = b'{"enabled":true}'
            status, _, data = self.relay(
                "POST",
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer settings-secret",
                    "Idempotency-Key": f"settings-{path.rsplit('/', 1)[-1]}",
                },
            )
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(data)["ok"])
            observed = FakeManagedPPUGatewayHandler.requests[-1]
            self.assertEqual(observed["path"], path)
            self.assertEqual(observed["authorization"], "Bearer settings-secret")
            self.assertIsNotNone(observed["idempotency_key"])
            self.assertEqual(observed["body"], body)

    def test_status_query_is_preserved(self):
        status, _, data = self.relay(
            "GET",
            "/api/engineering/targets/fac-a/ppu-01/api/status?job=job-7",
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["path"], "/api/engineering/targets/fac-a/ppu-01/api/status?job=job-7")

    def test_readback_binary_and_content_disposition_pass_through(self):
        status, headers, data = self.relay(
            "GET",
            "/api/engineering/targets/fac-a/ppu-01/api/jobs/job-7/files/readback.bin",
        )
        self.assertEqual(status, 200)
        self.assertEqual(data, b"readback-bytes")
        self.assertEqual(headers.get("Content-Disposition"), 'attachment; filename="readback.bin"')

    def test_loopback_uses_same_managed_relay_and_adds_manager_proof(self):
        body = json.dumps(
            {
                "endpoint": "ps",
                "test_id": "managed-route",
                "sequence": 1,
                "pattern": "zero",
                "seed": "",
                "payload_length": 1,
                "payload_base64": "AA==",
                "tx_crc32": "d202ef8d",
                "timeout_ms": 5000,
            }
        ).encode("utf-8")
        status, _, data = self.relay(
            "POST",
            "/api/engineering/diagnostics/loopback",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        payload = json.loads(data)
        self.assertEqual(payload["manager"]["relay"], "pass-through")
        self.assertEqual(payload["manager"]["ppu_alias"], "ppu-a")
        self.assertEqual(payload["loopback"]["source"], "ps")

    def test_non_allowlisted_route_is_rejected_before_ppu_contact(self):
        before = len(FakeManagedPPUGatewayHandler.requests)
        status, _, data = self.relay("GET", "/api/internal/debug")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(data)["error"]["code"], "managed_route_not_allowed")
        self.assertEqual(len(FakeManagedPPUGatewayHandler.requests), before)

    def test_caller_cannot_supply_arbitrary_destination_url(self):
        before = len(FakeManagedPPUGatewayHandler.requests)
        status, _, data = self.relay("GET", "/api/http://example.invalid/anything")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(data)["error"]["code"], "managed_route_not_allowed")
        self.assertEqual(len(FakeManagedPPUGatewayHandler.requests), before)


if __name__ == "__main__":
    unittest.main()
