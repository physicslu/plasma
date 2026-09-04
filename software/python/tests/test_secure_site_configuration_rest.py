from __future__ import annotations

import hashlib
import json
import tempfile
import textwrap
import threading
import unittest
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

from plasma_web.gateway_security import GatewaySecurityController
from plasma_web.secure_gateway_app import DeployedSecurePlasmaWebHandler
from plasma_web.site_configuration import SiteConfigurationController


OPERATOR_TOKEN = "site-operator-token-0123456789abcdef0123456789abcdef"
ENGINEER_TOKEN = "site-engineer-token-0123456789abcdef0123456789abcdef"

CONFIG = """
ppu:
  id: ppu-secure-site-01
  facility_id: secure-lab
  model: virtual
  display_name: Secure Site Test PPU
server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 2
  max_queue_depth_per_site: 4
  output_root: output
  log_root: logs
  max_metadata_bytes: 65536
  max_map_bytes: 1048576
  max_binary_bytes: 67108864
sites:
  - {id: 1, enabled: true, interface: mock, target: TARGET-A}
  - {id: 2, enabled: false, interface: mock, target: TARGET-B}
"""


class SecureSiteConfigurationRestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config_path = root / "config" / "plasma.yaml"
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text(textwrap.dedent(CONFIG).lstrip(), encoding="utf-8")

        security_path = root / "security.yaml"
        security_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "principals": [
                        {
                            "id": "site-operator",
                            "token_sha256": hashlib.sha256(OPERATOR_TOKEN.encode()).hexdigest(),
                            "roles": ["operator"],
                            "scopes": [
                                {"facility_id": "secure-lab", "ppu_id": "ppu-secure-site-01", "site_ids": [1]}
                            ],
                        },
                        {
                            "id": "site-engineer",
                            "token_sha256": hashlib.sha256(ENGINEER_TOKEN.encode()).hexdigest(),
                            "roles": ["engineer"],
                            "scopes": [
                                {"facility_id": "secure-lab", "ppu_id": "ppu-secure-site-01", "site_ids": [1]}
                            ],
                        },
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self.controller = GatewaySecurityController.from_paths(
            security_path,
            root / "security-state.sqlite3",
        )

        runtime_snapshot = {
            "ok": True,
            "ppu": {
                "ppu_id": "ppu-secure-site-01",
                "facility_id": "secure-lab",
                "execution": {"busy": False, "active_job_count": 0},
            },
            "sites": [
                {
                    "site_id": 1,
                    "enabled": True,
                    "interface": "mock",
                    "target": "TARGET-A",
                    "state": "idle",
                    "current_job_id": None,
                },
                {
                    "site_id": 2,
                    "enabled": False,
                    "interface": None,
                    "target": None,
                    "state": "disabled",
                    "current_job_id": None,
                },
            ],
        }

        class Handler(DeployedSecurePlasmaWebHandler):
            snapshot = deepcopy(runtime_snapshot)

            def _local_snapshot(self):
                return deepcopy(type(self).snapshot)

        Handler.site_configuration = SiteConfigurationController(self.config_path)
        Handler.security_controller = self.controller
        Handler.allowed_origins = frozenset({"*"})
        self.handler = Handler
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown)

    def _shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.controller.close()

    def request(self, method: str, path: str, token: str, body=None, command_id: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        if raw is not None:
            headers["Content-Type"] = "application/json"
        if command_id is not None:
            headers["Idempotency-Key"] = command_id
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def test_operator_can_read_but_cannot_write_site_desired_configuration(self) -> None:
        status, payload = self.request("GET", "/api/settings/sites", OPERATOR_TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

        before = self.config_path.read_text(encoding="utf-8")
        status, denied = self.request(
            "POST",
            "/api/settings/sites/1",
            OPERATOR_TOKEN,
            {"enabled": True, "interface": "mock", "target": "TARGET-NEW"},
            "site-op-denied-0001",
        )
        self.assertEqual(status, 403)
        self.assertEqual(denied["error"]["error_type"], "AUTHORIZATION_DENIED")
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), before)

    def test_engineer_write_is_idempotent_and_site_scoped(self) -> None:
        desired = {"enabled": True, "interface": "mock", "target": "TARGET-NEW"}
        command_id = "site-engineer-write-0001"
        status, first = self.request(
            "POST",
            "/api/settings/sites/1",
            ENGINEER_TOKEN,
            desired,
            command_id,
        )
        self.assertEqual(status, 200)
        self.assertEqual(first["site_configuration"]["sites"][0]["desired"]["target"], "TARGET-NEW")

        status, replay = self.request(
            "POST",
            "/api/settings/sites/1",
            ENGINEER_TOKEN,
            desired,
            command_id,
        )
        self.assertEqual(status, 200)
        self.assertEqual(replay, first)

        before = self.config_path.read_text(encoding="utf-8")
        status, denied = self.request(
            "POST",
            "/api/settings/sites/2",
            ENGINEER_TOKEN,
            {"enabled": True, "interface": "mock", "target": "TARGET-B"},
            "site-engineer-scope-0002",
        )
        self.assertEqual(status, 403)
        self.assertEqual(denied["error"]["error_type"], "AUTHORIZATION_DENIED")
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
