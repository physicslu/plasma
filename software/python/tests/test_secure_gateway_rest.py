from __future__ import annotations

import hashlib
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from plasma_web.batch_runtime import BatchRuntimeManager
from plasma_web.gateway_security import GatewaySecurityController
from plasma_web.secure_gateway import SecurePlasmaWebHandler
from tests.test_batch_runtime import FakeBatchProvider


class SecureGatewayRestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.tokens = {
            "viewer": "viewer-token-0123456789abcdef0123456789abcdef",
            "operator": "operator-token-0123456789abcdef0123456789abcdef",
            "admin": "admin-token-0123456789abcdef0123456789abcdef",
        }
        config = {
            "version": 1,
            "principals": [
                {
                    "id": "remote-support",
                    "token_sha256": hashlib.sha256(cls.tokens["viewer"].encode()).hexdigest(),
                    "roles": ["viewer"],
                    "scopes": [{"facility_id": "facility-1", "ppu_id": "ppu-1", "site_ids": "*"}],
                },
                {
                    "id": "operator",
                    "token_sha256": hashlib.sha256(cls.tokens["operator"].encode()).hexdigest(),
                    "roles": ["operator"],
                    "scopes": [{"facility_id": "facility-1", "ppu_id": "ppu-1", "site_ids": [1, 2]}],
                },
                {
                    "id": "admin",
                    "token_sha256": hashlib.sha256(cls.tokens["admin"].encode()).hexdigest(),
                    "roles": ["admin"],
                    "scopes": [{"facility_id": "*", "ppu_id": "*", "site_ids": "*"}],
                },
            ],
        }
        config_path = cls.root / "security.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        cls.security = GatewaySecurityController.from_paths(
            config_path,
            cls.root / "security-state.sqlite3",
        )
        cls.provider = FakeBatchProvider()
        cls.runtime = BatchRuntimeManager(cls.provider, poll_interval_s=0.001)
        SecurePlasmaWebHandler.security_controller = cls.security
        SecurePlasmaWebHandler.batch_runtime = cls.runtime
        SecurePlasmaWebHandler.gateway_settings = cls.runtime.gateway_settings
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SecurePlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.runtime.close()
        cls.security.close()
        SecurePlasmaWebHandler.security_controller = None
        SecurePlasmaWebHandler.batch_runtime = None
        cls.temp.cleanup()

    def request(self, method: str, path: str, body=None, *, token: str | None = None, command_id: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        if command_id is not None:
            headers["Idempotency-Key"] = command_id
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    @staticmethod
    def batch_body(*, site_id: int = 1, repeat_count: int = 1):
        return {
            "targets": [{"facility_id": "facility-1", "ppu_id": "ppu-1", "site_ids": [site_id]}],
            "operations": ["erase"],
            "execution_policy": {
                "repeat_count": repeat_count,
                "site_retry_limit": 0,
                "failed_site_stop_threshold": None,
            },
        }

    def test_missing_authentication_is_401(self):
        status, payload = self.request(
            "POST",
            "/api/batches",
            self.batch_body(),
            command_id="cmd-no-auth-0001",
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["error_code"], "E4101")

    def test_viewer_can_read_settings_but_cannot_start_batch(self):
        status, payload = self.request(
            "GET",
            "/api/settings/gateway",
            token=self.tokens["viewer"],
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

        status, payload = self.request(
            "POST",
            "/api/batches",
            self.batch_body(),
            token=self.tokens["viewer"],
            command_id="cmd-viewer-write-0001",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["error_code"], "E4102")

    def test_operator_scope_blocks_other_site(self):
        status, payload = self.request(
            "POST",
            "/api/batches",
            self.batch_body(site_id=3),
            token=self.tokens["operator"],
            command_id="cmd-out-scope-0001",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["error_code"], "E4102")

    def test_idempotent_batch_replay_returns_same_batch_without_second_execution(self):
        body = self.batch_body()
        before = len(self.runtime._batches)
        status, first = self.request(
            "POST",
            "/api/batches",
            body,
            token=self.tokens["operator"],
            command_id="cmd-batch-replay-0001",
        )
        self.assertEqual(status, 202)
        after_first = len(self.runtime._batches)
        self.assertEqual(after_first, before + 1)

        status, second = self.request(
            "POST",
            "/api/batches",
            body,
            token=self.tokens["operator"],
            command_id="cmd-batch-replay-0001",
        )
        self.assertEqual(status, 202)
        self.assertEqual(second["batch"]["batch_id"], first["batch"]["batch_id"])
        self.assertEqual(len(self.runtime._batches), after_first)

    def test_same_idempotency_key_with_changed_payload_is_409(self):
        status, _ = self.request(
            "POST",
            "/api/batches",
            self.batch_body(repeat_count=1),
            token=self.tokens["operator"],
            command_id="cmd-replay-conflict-0001",
        )
        self.assertEqual(status, 202)
        status, payload = self.request(
            "POST",
            "/api/batches",
            self.batch_body(repeat_count=2),
            token=self.tokens["operator"],
            command_id="cmd-replay-conflict-0001",
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["error_code"], "E4103")

    def test_operator_cannot_change_gateway_settings_but_admin_can(self):
        body = {"ppu_request_timeout_ms": 12_000, "ppu_retry_count": 2}
        status, payload = self.request(
            "POST",
            "/api/settings/gateway",
            body,
            token=self.tokens["operator"],
            command_id="cmd-settings-operator-0001",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["error_code"], "E4102")

        status, payload = self.request(
            "POST",
            "/api/settings/gateway",
            body,
            token=self.tokens["admin"],
            command_id="cmd-settings-admin-0001",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["gateway_settings"]["ppu_request_timeout_ms"], 12_000)
        self.runtime.gateway_settings.update({"ppu_request_timeout_ms": 10_000, "ppu_retry_count": 3})


if __name__ == "__main__":
    unittest.main()
