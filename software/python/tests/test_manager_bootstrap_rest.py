from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from plasma_manager.config import ManagerConfig
from plasma_manager.registry import PPURegistryStore
from plasma_manager.server_bootstrap import BootstrapPlasmaManagerHandler


class FakePoller:
    def __init__(
        self,
        *,
        active: bool = False,
        observation_state: str = "current",
        include_ppu: bool = True,
        identity_conflict: bool = False,
        errors: list[str] | None = None,
    ) -> None:
        self.active = active
        self.observation_state = observation_state
        self.include_ppu = include_ppu
        self.identity_conflict = identity_conflict
        self.errors = [] if errors is None else errors

    def snapshot(self):
        ppus = []
        if self.include_ppu:
            ppus.append(
                {
                    "alias": "z2",
                    "observation": {"state": self.observation_state},
                    "identity_conflict": self.identity_conflict,
                    "errors": self.errors,
                    "sites": [
                        {
                            "state": "running" if self.active else "ready",
                            "current_job_id": "job-1" if self.active else None,
                        }
                    ],
                }
            )
        return {"ok": True, "ppus": ppus}


class FakeBootstrapCoordinator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def status(self, alias: str):
        self.calls.append(("status", alias, None))
        return {
            "ok": True,
            "ppu_alias": alias,
            "pairing": {"paired": False, "device_match": True},
            "bootstrap": {
                "bootstrap": {"state": "bootstrap_ready"},
                "identity": {"device_id": "ppu-device-0123456789abcdef"},
                "runtime": {"state": "runtime_absent"},
                "capabilities": {"runtime_deployment": True, "fpga_update": False},
                "deployment": None,
            },
        }

    def pair(self, alias: str, token: str):
        self.calls.append(("pair", alias, token))
        return {"ok": True, "ppu_alias": alias, "pairing": {"paired": True}}

    def create_upload(self, alias: str, body):
        self.calls.append(("create_upload", alias, dict(body)))
        return 201, {"ok": True, "upload": {"upload_id": "a" * 32}}

    def append_chunk(self, alias: str, upload_id: str, body):
        self.calls.append(("append_chunk", alias, {"upload_id": upload_id, **dict(body)}))
        return 200, {"ok": True, "upload": {"received_bytes": 3}}

    def commit_upload(self, alias: str, upload_id: str):
        self.calls.append(("commit_upload", alias, upload_id))
        return 200, {"ok": True, "upload": {"state": "committed"}}

    def start_deployment(self, alias: str, body):
        self.calls.append(("start_deployment", alias, dict(body)))
        return 202, {"ok": True, "deployment": {"state": "queued"}}


class ManagerBootstrapRestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.registry = PPURegistryStore((), root / "registry.json")
        self.registry.add(alias="z2", endpoint="http://192.168.2.99:18080")
        self.coordinator = FakeBootstrapCoordinator()
        self.previous = (
            BootstrapPlasmaManagerHandler.config,
            BootstrapPlasmaManagerHandler.registry_store,
            BootstrapPlasmaManagerHandler.poller,
            BootstrapPlasmaManagerHandler.bootstrap_coordinator,
        )
        BootstrapPlasmaManagerHandler.config = ManagerConfig(registry_state_path=root / "registry.json")
        BootstrapPlasmaManagerHandler.registry_store = self.registry
        BootstrapPlasmaManagerHandler.poller = FakePoller()
        BootstrapPlasmaManagerHandler.bootstrap_coordinator = self.coordinator
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), BootstrapPlasmaManagerHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        (
            BootstrapPlasmaManagerHandler.config,
            BootstrapPlasmaManagerHandler.registry_store,
            BootstrapPlasmaManagerHandler.poller,
            BootstrapPlasmaManagerHandler.bootstrap_coordinator,
        ) = self.previous
        self.temp.cleanup()

    def request(self, method: str, path: str, body=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        payload = None if body is None else json.dumps(body)
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        connection.close()
        return response.status, data

    def test_pending_ppu_can_read_bootstrap_before_runtime_exists(self) -> None:
        status, payload = self.request("GET", "/api/registry/z2/bootstrap")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["bootstrap"]["runtime"]["state"], "runtime_absent")
        self.assertEqual(self.coordinator.calls, [("status", "z2", None)])

    def test_pending_ppu_can_pair_without_being_commissioned(self) -> None:
        token = "t" * 40
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/pair", {"token": token})
        self.assertEqual(status, 200)
        self.assertTrue(payload["pairing"]["paired"])
        self.assertEqual(self.coordinator.calls[-1], ("pair", "z2", token))

    def test_commissioned_ppu_requires_disable_before_any_runtime_maintenance(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        status, payload = self.request(
            "POST",
            "/api/registry/z2/bootstrap/uploads",
            {"size": 3, "sha256": "0" * 64},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_maintenance_required")
        self.assertEqual(self.coordinator.calls, [])

    def test_disabled_ppu_requires_current_trusted_idle_observation(self) -> None:
        self.registry.set_lifecycle("z2", "disabled")
        cases = [
            FakePoller(include_ppu=False),
            FakePoller(observation_state="stale"),
            FakePoller(identity_conflict=True),
            FakePoller(errors=["gateway_unreachable"]),
            FakePoller(active=True),
        ]
        for poller in cases:
            with self.subTest(poller=poller.__dict__):
                BootstrapPlasmaManagerHandler.poller = poller
                status, payload = self.request(
                    "POST",
                    "/api/registry/z2/bootstrap/uploads",
                    {"size": 3, "sha256": "0" * 64},
                )
                self.assertEqual(status, 409)
                self.assertIn(payload["error"]["code"], {"ppu_idle_state_unproven", "ppu_busy"})
                self.assertEqual(self.coordinator.calls, [])

    def test_disabled_ppu_with_current_trusted_idle_observation_can_upgrade(self) -> None:
        self.registry.set_lifecycle("z2", "disabled")
        BootstrapPlasmaManagerHandler.poller = FakePoller()
        status, payload = self.request(
            "POST",
            "/api/registry/z2/bootstrap/uploads",
            {"size": 3, "sha256": "0" * 64},
        )
        self.assertEqual(status, 201)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.coordinator.calls[-1][0], "create_upload")

    def test_upload_and_deployment_routes_are_explicit(self) -> None:
        status, _ = self.request(
            "POST",
            "/api/registry/z2/bootstrap/uploads",
            {"size": 3, "sha256": "0" * 64},
        )
        self.assertEqual(status, 201)
        upload_id = "a" * 32
        status, _ = self.request(
            "POST",
            f"/api/registry/z2/bootstrap/uploads/{upload_id}/chunks",
            {"offset": 0, "data_base64": "YWJj", "sha256": "0" * 64},
        )
        self.assertEqual(status, 200)
        status, _ = self.request(
            "POST",
            f"/api/registry/z2/bootstrap/uploads/{upload_id}/commit",
            {"action": "commit"},
        )
        self.assertEqual(status, 200)
        status, payload = self.request(
            "POST",
            "/api/registry/z2/bootstrap/deployments",
            {
                "upload_id": upload_id,
                "ppu_id": "z2-dev-01",
                "facility_id": "lab",
                "display_name": "Plasma Z2",
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["deployment"]["state"], "queued")
        self.assertEqual(
            [call[0] for call in self.coordinator.calls],
            ["create_upload", "append_chunk", "commit_upload", "start_deployment"],
        )

    def test_active_execution_blocks_pending_bootstrap_mutations(self) -> None:
        BootstrapPlasmaManagerHandler.poller = FakePoller(active=True)
        status, payload = self.request(
            "POST",
            "/api/registry/z2/bootstrap/uploads",
            {"size": 1, "sha256": "0" * 64},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_busy")
        self.assertEqual(self.coordinator.calls, [])

    def test_unknown_bootstrap_route_fails_closed(self) -> None:
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/shell", {"command": "id"})
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "bootstrap_route_not_allowed")
        self.assertEqual(self.coordinator.calls, [])


if __name__ == "__main__":
    unittest.main()
