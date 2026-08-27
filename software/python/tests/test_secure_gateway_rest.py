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


class FakeLocalClient:
    def __init__(self) -> None:
        self.status_calls = 0
        self.start_calls = 0

    async def status(self, *, job_id=None, site_id=None):
        self.status_calls += 1
        if job_id is not None:
            return {
                "ok": True,
                "job": {
                    "job_id": job_id,
                    "site_id": 1,
                    "operation": "read",
                    "state": "running",
                },
            }
        sites = [
            {
                "site_id": current,
                "enabled": True,
                "state": "idle",
                "current_job_id": None,
            }
            for current in (1, 2, 3)
            if site_id is None or current == site_id
        ]
        return {
            "ok": True,
            "ppu": {
                "ppu_id": "ppu-1",
                "facility_id": "facility-1",
                "model": "TEST",
                "display_name": "Test PPU",
                "site_count": 3,
                "enabled_site_count": 3,
                "execution": {"busy": False},
                "capabilities": {"max_supported_sites": 3, "operations": ["erase", "program", "verify", "read"]},
            },
            "sites": sites,
        }

    async def start(self, request):
        self.start_calls += 1
        return {"ok": True, "job": {"job_id": request.job_id, "site_id": request.site_id, "state": "queued"}}

    async def cancel(self, job_id):
        return {"ok": True, "job_id": job_id, "accepted": True}


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
        cls.local_client = FakeLocalClient()
        SecurePlasmaWebHandler.security_controller = cls.security
        SecurePlasmaWebHandler.batch_runtime = cls.runtime
        SecurePlasmaWebHandler.gateway_settings = cls.runtime.gateway_settings
        SecurePlasmaWebHandler.client_factory = staticmethod(lambda: cls.local_client)
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

    def test_unauthenticated_status_is_rejected_before_ppu_lookup(self):
        before = self.local_client.status_calls
        status, payload = self.request("GET", "/api/status")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["error_code"], "E4101")
        self.assertEqual(self.local_client.status_calls, before)

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

    def test_viewer_cannot_execute_ic_read(self):
        before = self.local_client.start_calls
        status, payload = self.request(
            "POST",
            "/api/jobs",
            {"site_id": 1, "operation": "read", "offset": 0, "length": 16},
            token=self.tokens["viewer"],
            command_id="cmd-viewer-read-0001",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["error_code"], "E4102")
        self.assertEqual(self.local_client.start_calls, before)

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

    def test_site_scoped_operator_cannot_cancel_ppu_batch_containing_other_site(self):
        body = {
            "targets": [{"facility_id": "facility-1", "ppu_id": "ppu-1", "site_ids": [1, 3]}],
            "operations": ["erase"],
            "execution_policy": {
                "repeat_count": 1,
                "site_retry_limit": 0,
                "failed_site_stop_threshold": None,
            },
        }
        status, created = self.request(
            "POST",
            "/api/batches",
            body,
            token=self.tokens["admin"],
            command_id="cmd-admin-wide-batch-0001",
        )
        self.assertEqual(status, 202)
        batch_id = created["batch"]["batch_id"]
        status, payload = self.request(
            "POST",
            f"/api/batches/{batch_id}/targets/facility-1/ppu-1/cancel",
            {},
            token=self.tokens["operator"],
            command_id="cmd-operator-wide-cancel-0001",
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
