from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

from plasma_web.gateway_security import GatewaySecurityController
from plasma_web.ppu_network_activation import PPUNetworkActivationController
from plasma_web.ppu_network_settings import PPUNetworkSettingsController
from plasma_web.secure_gateway_app import DeployedSecurePlasmaWebHandler


class FakeHelper:
    def __init__(self) -> None:
        self.current = {"interface": "eth0", "address": "192.168.77.10", "prefix_length": 24}
        self.apply_calls = 0

    def snapshot(self):
        return dict(self.current)

    def apply(self, settings):
        self.apply_calls += 1
        self.current = {"interface": "eth0", "address": settings["address"], "prefix_length": settings["prefix_length"]}
        return dict(self.current)

    def restore(self, snapshot):
        self.current = dict(snapshot)
        return dict(self.current)


class PPUNetworkActivationSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.tokens = {
            "viewer": "viewer-phase2-token-0123456789abcdef0123456789abcdef",
            "operator": "operator-phase2-token-0123456789abcdef0123456789abcdef",
            "admin": "admin-phase2-token-0123456789abcdef0123456789abcdef",
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
        cls.security = GatewaySecurityController.from_paths(config_path, cls.root / "security-state.sqlite3")
        cls.settings = PPUNetworkSettingsController(cls.root / "ppu-network-settings.yaml")
        cls.settings.update(
            {
                "mode": "static",
                "address": "192.168.77.21",
                "prefix_length": 24,
                "gateway": "192.168.77.1",
                "dns_servers": ["192.168.77.1"],
            }
        )
        cls.ppu_id = "ppu-phase2-secure"
        cls.helper = FakeHelper()
        cls.activation = PPUNetworkActivationController(
            cls.settings,
            cls.helper,
            cls.root / "ppu-network-activation.json",
            lambda: cls.ppu_id,
            apply_delay_s=0.05,
        )

        class Handler(DeployedSecurePlasmaWebHandler):
            pass

        Handler.security_controller = cls.security
        Handler.ppu_network_settings = cls.settings
        Handler._network_activation_socket = cls.root / "fake-helper.sock"
        Handler._network_activation_instance = cls.activation
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
        cls.activation.close()
        cls.handler._network_activation_instance = None
        cls.security.close()
        cls.temp.cleanup()

    def request(self, method: str, path: str, body=None, *, role: str | None = None, command_id: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        if role is not None:
            headers["Authorization"] = f"Bearer {self.tokens[role]}"
        if command_id is not None:
            headers["Idempotency-Key"] = command_id
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def wait_state(self, state: str, timeout: float = 3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, payload = self.request("GET", "/api/settings/ppu-network/activation", role="viewer")
            self.assertEqual(status, 200)
            if payload["activation"]["state"] == state:
                return payload["activation"]
            time.sleep(0.02)
        self.fail(f"activation did not reach {state}")

    def activation_body(self):
        return {
            "action": "apply",
            "expected_revision": self.settings.current()["revision"],
            "expected_ppu_id": self.ppu_id,
            "rollback_timeout_s": 2,
        }

    def test_viewer_can_read_activation_status(self) -> None:
        status, payload = self.request("GET", "/api/settings/ppu-network/activation", role="viewer")
        self.assertEqual(status, 200)
        self.assertTrue(payload["activation"]["supported"])

    def test_operator_cannot_activate_network(self) -> None:
        status, payload = self.request(
            "POST",
            "/api/settings/ppu-network/activation",
            self.activation_body(),
            role="operator",
            command_id="phase2-operator-0001",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["error_code"], "E4102")
        self.assertEqual(self.helper.apply_calls, 0)

    def test_admin_activation_requires_idempotency_and_replays(self) -> None:
        body = self.activation_body()
        status, payload = self.request(
            "POST",
            "/api/settings/ppu-network/activation",
            body,
            role="admin",
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

        status, first = self.request(
            "POST",
            "/api/settings/ppu-network/activation",
            body,
            role="admin",
            command_id="phase2-admin-apply-0001",
        )
        self.assertEqual(status, 202)
        activation_id = first["activation"]["activation_id"]

        replay_status, replay = self.request(
            "POST",
            "/api/settings/ppu-network/activation",
            body,
            role="admin",
            command_id="phase2-admin-apply-0001",
        )
        self.assertEqual(replay_status, 202)
        self.assertEqual(replay, first)

        waiting = self.wait_state("applied_waiting_commit")
        self.assertEqual(self.helper.apply_calls, 1)
        revision = waiting["revision"]
        status, committed = self.request(
            "POST",
            f"/api/settings/ppu-network/activation/{activation_id}/commit",
            {"expected_revision": revision, "expected_ppu_id": self.ppu_id},
            role="admin",
            command_id="phase2-admin-commit-0001",
        )
        self.assertEqual(status, 200)
        self.assertEqual(committed["activation"]["state"], "committed")


if __name__ == "__main__":
    unittest.main()
