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

from plasma_web.gateway_security import GatewaySecurityController
from plasma_web.ppu_network_settings import PPUNetworkSettingsController
from plasma_web.secure_gateway import SecurePlasmaWebHandler


class PPUNetworkSettingsSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.tokens = {
            "viewer": "viewer-network-token-0123456789abcdef0123456789abcdef",
            "operator": "operator-network-token-0123456789abcdef0123456789abcdef",
            "admin": "admin-network-token-0123456789abcdef0123456789abcdef",
        }
        config = {
            "version": 1,
            "principals": [
                {
                    "id": role,
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "roles": [role],
                    "scopes": [{"facility_id": "*", "ppu_id": "*", "site_ids": "*"}],
                }
                for role, token in cls.tokens.items()
            ],
        }
        config_path = cls.root / "security.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        cls.security = GatewaySecurityController.from_paths(
            config_path,
            cls.root / "security-state.sqlite3",
        )

        class Handler(SecurePlasmaWebHandler):
            pass

        Handler.security_controller = cls.security
        Handler.batch_runtime = None
        Handler.ppu_network_settings = PPUNetworkSettingsController(cls.root / "ppu-network-settings.yaml")
        Handler.allowed_origins = frozenset({"*"})
        cls.handler = Handler
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.security.close()
        cls.temp.cleanup()

    def request(
        self,
        method: str,
        path: str,
        body=None,
        *,
        token: str | None = None,
        command_id: str | None = None,
    ):
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
    def static_body() -> dict[str, object]:
        return {
            "mode": "static",
            "address": "192.168.10.21",
            "prefix_length": 24,
            "gateway": "192.168.10.1",
            "dns_servers": ["192.168.10.1"],
        }

    def test_viewer_can_read_network_settings(self) -> None:
        status, payload = self.request(
            "GET",
            "/api/settings/ppu-network",
            token=self.tokens["viewer"],
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["ppu_network_settings"]["interface"], "eth0")

    def test_operator_cannot_write_network_settings(self) -> None:
        before = self.handler.ppu_network_settings.current()
        status, payload = self.request(
            "POST",
            "/api/settings/ppu-network",
            self.static_body(),
            token=self.tokens["operator"],
            command_id="ppu-net-operator-0001",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["error_code"], "E4102")
        self.assertEqual(self.handler.ppu_network_settings.current(), before)

    def test_admin_write_requires_idempotency_key(self) -> None:
        before = self.handler.ppu_network_settings.current()
        status, payload = self.request(
            "POST",
            "/api/settings/ppu-network",
            self.static_body(),
            token=self.tokens["admin"],
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(self.handler.ppu_network_settings.current(), before)

    def test_admin_write_is_idempotent(self) -> None:
        body = self.static_body()
        first_status, first = self.request(
            "POST",
            "/api/settings/ppu-network",
            body,
            token=self.tokens["admin"],
            command_id="ppu-net-admin-0001",
        )
        self.assertEqual(first_status, 200)
        revision = first["ppu_network_settings"]["revision"]

        replay_status, replay = self.request(
            "POST",
            "/api/settings/ppu-network",
            body,
            token=self.tokens["admin"],
            command_id="ppu-net-admin-0001",
        )
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay, first)
        self.assertEqual(self.handler.ppu_network_settings.current()["revision"], revision)


if __name__ == "__main__":
    unittest.main()
