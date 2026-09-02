from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from plasma_web.gateway import PlasmaWebHandler
from plasma_web.ppu_network_settings import PPUNetworkSettingsController


class PPUNetworkSettingsRestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = TemporaryDirectory()
        cls.root = Path(cls.temp.name)

        class Handler(PlasmaWebHandler):
            pass

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
        cls.temp.cleanup()

    def request(self, method: str, path: str, body=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def test_get_exposes_desired_dhcp_state_without_claiming_os_activation(self) -> None:
        status, payload = self.request("GET", "/api/settings/ppu-network")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["ppu_network_settings"],
            {
                "revision": 1,
                "interface": "eth0",
                "mode": "dhcp",
                "address": None,
                "prefix_length": None,
                "gateway": None,
                "dns_servers": [],
            },
        )
        self.assertEqual(
            payload["activation"],
            {"supported": False, "state": "not_implemented"},
        )

    def test_post_persists_static_desired_state_and_restart_loads_it(self) -> None:
        body = {
            "mode": "static",
            "address": "192.168.10.21",
            "prefix_length": 24,
            "gateway": "192.168.10.1",
            "dns_servers": ["192.168.10.1", "8.8.8.8"],
        }
        status, payload = self.request("POST", "/api/settings/ppu-network", body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["ppu_network_settings"]["revision"], 2)
        self.assertEqual(payload["ppu_network_settings"]["mode"], "static")
        self.assertFalse(payload["activation"]["supported"])

        persisted = PPUNetworkSettingsController(self.root / "ppu-network-settings.yaml")
        self.assertEqual(persisted.current(), payload["ppu_network_settings"])

        status, current = self.request("GET", "/api/settings/ppu-network")
        self.assertEqual(status, 200)
        self.assertEqual(current["ppu_network_settings"], payload["ppu_network_settings"])

    def test_invalid_static_configuration_returns_400_and_does_not_advance_revision(self) -> None:
        before = self.handler.ppu_network_settings.current()
        status, payload = self.request(
            "POST",
            "/api/settings/ppu-network",
            {
                "mode": "static",
                "address": "192.168.10.21",
                "prefix_length": 24,
                "gateway": "192.168.11.1",
                "dns_servers": [],
            },
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(self.handler.ppu_network_settings.current(), before)


if __name__ == "__main__":
    unittest.main()
