from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_web.gateway_phase2 import Phase2PlasmaWebHandler
from plasma_web.ppu_network_activation import PPUNetworkActivationController
from plasma_web.ppu_network_settings import PPUNetworkSettingsController


class FakeHelper:
    def __init__(self) -> None:
        self.current = {"interface": "eth0", "address": "192.168.77.10", "prefix_length": 24}

    def snapshot(self):
        return dict(self.current)

    def apply(self, settings):
        self.current = {
            "interface": "eth0",
            "address": settings["address"],
            "prefix_length": settings["prefix_length"],
        }
        return dict(self.current)

    def restore(self, snapshot):
        self.current = dict(snapshot)
        return dict(self.current)


class PPUNetworkActivationRestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.settings = PPUNetworkSettingsController(cls.root / "ppu-network-settings.yaml")
        cls.helper = FakeHelper()
        cls.ppu_id = "ppu-phase2-rest"
        cls.activation = PPUNetworkActivationController(
            cls.settings,
            cls.helper,
            cls.root / "ppu-network-activation.json",
            lambda: cls.ppu_id,
            apply_delay_s=0.01,
        )

        class Handler(Phase2PlasmaWebHandler):
            pass

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
        cls.temp.cleanup()

    def request(self, method: str, path: str, body=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def wait_state(self, state: str, timeout: float = 3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, payload = self.request("GET", "/api/settings/ppu-network/activation")
            self.assertEqual(status, 200)
            if payload["activation"]["state"] == state:
                return payload["activation"]
            time.sleep(0.02)
        self.fail(f"activation did not reach {state}")

    @staticmethod
    def static(address: str):
        return {
            "mode": "static",
            "address": address,
            "prefix_length": 24,
            "gateway": "192.168.77.1",
            "dns_servers": ["192.168.77.1"],
        }

    def test_apply_ack_commit_and_busy_settings_guard(self) -> None:
        status, initial = self.request("GET", "/api/settings/ppu-network")
        self.assertEqual(status, 200)
        self.assertTrue(initial["activation"]["supported"])
        self.assertEqual(initial["activation"]["state"], "idle")

        status, desired = self.request("POST", "/api/settings/ppu-network", self.static("192.168.77.21"))
        self.assertEqual(status, 200)
        revision = desired["ppu_network_settings"]["revision"]

        status, scheduled = self.request(
            "POST",
            "/api/settings/ppu-network/activation",
            {
                "action": "apply",
                "expected_revision": revision,
                "expected_ppu_id": self.ppu_id,
                "rollback_timeout_s": 2,
            },
        )
        self.assertEqual(status, 202)
        activation_id = scheduled["activation"]["activation_id"]
        waiting = self.wait_state("applied_waiting_commit")
        self.assertEqual(waiting["ppu_id"], self.ppu_id)

        status, busy = self.request("POST", "/api/settings/ppu-network", self.static("192.168.77.22"))
        self.assertEqual(status, 409)
        self.assertEqual(busy["error"]["error_type"], "PPU_NETWORK_ACTIVATION_BUSY")

        status, committed = self.request(
            "POST",
            f"/api/settings/ppu-network/activation/{activation_id}/commit",
            {"expected_revision": revision, "expected_ppu_id": self.ppu_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(committed["activation"]["state"], "committed")
        self.assertEqual(committed["activation"]["committed_revision"], revision)

    def test_stale_revision_and_wrong_identity_are_conflicts(self) -> None:
        status, desired = self.request("POST", "/api/settings/ppu-network", self.static("192.168.77.23"))
        self.assertEqual(status, 200)
        revision = desired["ppu_network_settings"]["revision"]

        status, stale = self.request(
            "POST",
            "/api/settings/ppu-network/activation",
            {
                "action": "apply",
                "expected_revision": revision - 1,
                "expected_ppu_id": self.ppu_id,
                "rollback_timeout_s": 2,
            },
        )
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"]["error_type"], "PPU_NETWORK_REVISION_CONFLICT")

        status, wrong = self.request(
            "POST",
            "/api/settings/ppu-network/activation",
            {
                "action": "apply",
                "expected_revision": revision,
                "expected_ppu_id": "wrong-ppu",
                "rollback_timeout_s": 2,
            },
        )
        self.assertEqual(status, 409)
        self.assertEqual(wrong["error"]["error_type"], "PPU_NETWORK_IDENTITY_CONFLICT")


if __name__ == "__main__":
    unittest.main()
