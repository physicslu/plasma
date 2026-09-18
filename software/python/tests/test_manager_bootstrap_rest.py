from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from plasma_manager.bootstrap_server import BootstrapPlasmaManagerHandler
from plasma_manager.config import ManagerConfig
from plasma_manager.registry import PPURegistryStore
from plasma_manager.server import PPUOperationGate


class FakePoller:
    def __init__(
        self,
        *,
        active: bool = False,
        observation_state: str = "current",
        include_ppu: bool = True,
        gateway_live: bool = True,
        identity_conflict: bool = False,
        errors: list[str] | None = None,
    ) -> None:
        self.active = active
        self.observation_state = observation_state
        self.include_ppu = include_ppu
        self.gateway_live = gateway_live
        self.identity_conflict = identity_conflict
        self.errors = [] if errors is None else errors

    def snapshot(self):
        ppus = []
        if self.include_ppu:
            ppus.append({
                "alias": "z2",
                "gateway_live": self.gateway_live,
                "observation": {"state": self.observation_state},
                "identity_conflict": self.identity_conflict,
                "errors": self.errors,
                "sites": [{
                    "state": "running" if self.active else "ready",
                    "current_job_id": "job-1" if self.active else None,
                }],
            })
        return {"ok": True, "ppus": ppus}


class FakeBootstrapCoordinator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.paired = False
        self.runtime_state = "runtime_active"
        self.deployment_state: str | None = None

    def status(self, alias: str):
        self.calls.append(("status", alias, None))
        return {
            "ok": True,
            "ppu_alias": alias,
            "pairing": {"paired": self.paired, "device_match": True},
            "bootstrap": {
                "bootstrap": {"state": "bootstrap_ready"},
                "identity": {"device_id": "ppu-device-0123456789abcdef"},
                "runtime": {"state": self.runtime_state},
                "capabilities": {"runtime_deployment": True, "fpga_update": False},
                "deployment": (
                    {"state": self.deployment_state}
                    if self.deployment_state is not None
                    else None
                ),
            },
        }

    def pair(self, alias: str, token: str):
        self.calls.append(("pair", alias, token))
        self.paired = True
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
        self.deployment_state = "queued"
        return 202, {"ok": True, "deployment": {"state": "queued"}}


class FakeRuntimeClient:
    calls: list[dict] = []

    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s

    def ps_loopback(self, body: dict, *, timeout_s: float):
        self.__class__.calls.append({"endpoint": self.endpoint, "body": dict(body), "timeout_s": timeout_s})
        return 200, {
            "ok": True,
            "diagnostic_protocol_version": "1",
            "loopback": {
                "endpoint": "ps",
                "source": "ps",
                "test_id": body["test_id"],
                "sequence": body["sequence"],
                "transform": "echo",
                "pattern": body["pattern"],
                "seed": body["seed"],
                "payload_length": body["payload_length"],
                "tx_crc32": body["tx_crc32"],
                "rx_crc32": body["tx_crc32"],
                "ppu_rtt_ms": 1.25,
            },
            "payload_base64": body["payload_base64"],
        }


class ManagerBootstrapRestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.registry = PPURegistryStore((), root / "registry.json")
        self.registry.add(alias="z2", endpoint="http://192.168.2.99:18080")
        self.coordinator = FakeBootstrapCoordinator()
        FakeRuntimeClient.calls.clear()
        self.previous = (
            BootstrapPlasmaManagerHandler.config,
            BootstrapPlasmaManagerHandler.registry_store,
            BootstrapPlasmaManagerHandler.poller,
            BootstrapPlasmaManagerHandler.bootstrap_coordinator,
            BootstrapPlasmaManagerHandler.runtime_client_factory,
            BootstrapPlasmaManagerHandler.operation_gate,
        )
        BootstrapPlasmaManagerHandler.config = ManagerConfig(registry_state_path=root / "registry.json")
        BootstrapPlasmaManagerHandler.registry_store = self.registry
        BootstrapPlasmaManagerHandler.poller = FakePoller()
        BootstrapPlasmaManagerHandler.bootstrap_coordinator = self.coordinator
        BootstrapPlasmaManagerHandler.runtime_client_factory = FakeRuntimeClient
        BootstrapPlasmaManagerHandler.operation_gate = PPUOperationGate()
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
            BootstrapPlasmaManagerHandler.runtime_client_factory,
            BootstrapPlasmaManagerHandler.operation_gate,
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

    @staticmethod
    def loopback_body(endpoint: str = "ps") -> dict:
        return {
            "endpoint": endpoint,
            "test_id": "platform-loopback",
            "sequence": 1,
            "pattern": "zero",
            "seed": "",
            "payload_length": 1,
            "payload_base64": "AA==",
            "tx_crc32": "d202ef8d",
            "timeout_ms": 5000,
        }

    def assert_platform_loopback_passes(self) -> None:
        self.coordinator.paired = True
        status, payload = self.request(
            "POST",
            "/api/registry/z2/bootstrap/ps-loopback",
            self.loopback_body(),
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["loopback"]["source"], "ps")
        self.assertEqual(payload["manager"]["context"], "platform")
        self.assertEqual(payload["manager"]["relay"], "platform-maintenance")
        self.assertEqual(payload["manager"]["ppu_alias"], "z2")
        self.assertEqual(FakeRuntimeClient.calls[-1]["body"], self.loopback_body())

    def test_pending_ppu_can_read_bootstrap_before_runtime_exists(self) -> None:
        status, payload = self.request("GET", "/api/registry/z2/bootstrap")
        self.assertEqual(status, 200)
        self.assertEqual(payload["bootstrap"]["runtime"]["state"], "runtime_active")
        self.assertEqual(self.coordinator.calls, [("status", "z2", None)])

    def test_pending_ppu_can_pair_without_being_commissioned(self) -> None:
        token = "t" * 40
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/pair", {"token": token})
        self.assertEqual(status, 200)
        self.assertTrue(payload["pairing"]["paired"])
        self.assertEqual(self.coordinator.calls[-1], ("pair", "z2", token))

    def test_commissioned_ppu_can_pair_before_entering_maintenance(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        token = "t" * 40
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/pair", {"token": token})
        self.assertEqual(status, 200)
        self.assertTrue(payload["pairing"]["paired"])
        self.assertEqual(self.coordinator.calls[-1], ("pair", "z2", token))

    def test_pairing_is_not_blocked_by_active_execution_because_it_does_not_mutate_runtime(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        BootstrapPlasmaManagerHandler.poller = FakePoller(active=True)
        token = "t" * 40
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/pair", {"token": token})
        self.assertEqual(status, 200)
        self.assertTrue(payload["pairing"]["paired"])
        self.assertEqual(self.coordinator.calls[-1], ("pair", "z2", token))

    def test_platform_ps_loopback_requires_platform_pairing(self) -> None:
        status, payload = self.request(
            "POST",
            "/api/registry/z2/bootstrap/ps-loopback",
            self.loopback_body(),
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "bootstrap_pairing_required")
        self.assertEqual(FakeRuntimeClient.calls, [])

    def test_pending_ppu_can_run_platform_ps_loopback(self) -> None:
        self.assert_platform_loopback_passes()

    def test_disabled_ppu_can_run_platform_ps_loopback(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        self.registry.set_lifecycle("z2", "disabled")
        self.assert_platform_loopback_passes()

    def test_commissioned_ppu_can_run_platform_ps_loopback(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        self.assert_platform_loopback_passes()

    def test_platform_ps_loopback_is_not_blocked_by_active_execution(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        BootstrapPlasmaManagerHandler.poller = FakePoller(active=True)
        self.assert_platform_loopback_passes()

    def test_platform_ps_loopback_rejects_non_ps_endpoint(self) -> None:
        self.coordinator.paired = True
        status, payload = self.request(
            "POST",
            "/api/registry/z2/bootstrap/ps-loopback",
            self.loopback_body("pl"),
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "unsupported_endpoint")
        self.assertEqual(FakeRuntimeClient.calls, [])

    def test_runtime_absent_first_install_does_not_require_programming_registration_or_fleet_idle(self) -> None:
        self.coordinator.runtime_state = "runtime_absent"
        BootstrapPlasmaManagerHandler.poller = FakePoller(include_ppu=False)
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/uploads", {"size": 3, "sha256": "0" * 64})
        self.assertEqual(status, 201)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.coordinator.calls[-1][0], "create_upload")

    def test_runtime_active_requires_current_trusted_idle_independent_of_registration(self) -> None:
        cases = [
            FakePoller(include_ppu=False),
            FakePoller(observation_state="stale"),
            FakePoller(gateway_live=False),
            FakePoller(identity_conflict=True),
            FakePoller(errors=["gateway_unreachable"]),
            FakePoller(active=True),
        ]
        for lifecycle in ("pending", "commissioned", "disabled"):
            if lifecycle == "commissioned":
                self.registry.set_lifecycle("z2", "commissioned")
            elif lifecycle == "disabled":
                if self.registry.record_by_alias("z2").lifecycle != "commissioned":
                    self.registry.set_lifecycle("z2", "commissioned")
                self.registry.set_lifecycle("z2", "disabled")
            else:
                # Each subtest needs pending; reset through a fresh registry record.
                self.registry.remove("z2")
                self.registry.add(alias="z2", endpoint="http://192.168.2.99:18080")
            for poller in cases:
                with self.subTest(lifecycle=lifecycle, poller=poller.__dict__):
                    BootstrapPlasmaManagerHandler.poller = poller
                    before = len(self.coordinator.calls)
                    status, payload = self.request("POST", "/api/registry/z2/bootstrap/uploads", {"size": 3, "sha256": "0" * 64})
                    self.assertEqual(status, 409)
                    self.assertIn(payload["error"]["code"], {"ppu_idle_state_unproven", "ppu_busy"})
                    self.assertNotIn("create_upload", [call[0] for call in self.coordinator.calls[before:]])

    def test_commissioned_ppu_with_current_trusted_idle_observation_can_upgrade(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        BootstrapPlasmaManagerHandler.poller = FakePoller()
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/uploads", {"size": 3, "sha256": "0" * 64})
        self.assertEqual(status, 201)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.coordinator.calls[-1][0], "create_upload")

    def test_disabled_ppu_with_current_trusted_idle_observation_can_upgrade(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        self.registry.set_lifecycle("z2", "disabled")
        BootstrapPlasmaManagerHandler.poller = FakePoller()
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/uploads", {"size": 3, "sha256": "0" * 64})
        self.assertEqual(status, 201)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.coordinator.calls[-1][0], "create_upload")

    def test_recovery_required_blocks_platform_mutation_independent_of_registration(self) -> None:
        for lifecycle in ("pending", "commissioned"):
            if lifecycle == "commissioned":
                self.registry.set_lifecycle("z2", "commissioned")
            self.coordinator.runtime_state = "recovery_required"
            status, payload = self.request("POST", "/api/registry/z2/bootstrap/uploads", {"size": 3, "sha256": "0" * 64})
            self.assertEqual(status, 409)
            self.assertEqual(payload["error"]["code"], "ppu_recovery_required")
            self.coordinator.runtime_state = "runtime_active"

    def test_explicit_upload_commit_and_deployment_routes(self) -> None:
        status, _ = self.request("POST", "/api/registry/z2/bootstrap/uploads", {"size": 3, "sha256": "0" * 64})
        self.assertEqual(status, 201)
        upload_id = "a" * 32
        status, _ = self.request("POST", f"/api/registry/z2/bootstrap/uploads/{upload_id}/chunks", {"offset": 0, "data_base64": "YWJj", "sha256": "0" * 64})
        self.assertEqual(status, 200)
        status, _ = self.request("POST", f"/api/registry/z2/bootstrap/uploads/{upload_id}/commit", {"action": "commit"})
        self.assertEqual(status, 200)
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/deployments", {
            "upload_id": upload_id,
            "ppu_id": "z2-dev-01",
            "facility_id": "lab",
            "display_name": "Plasma Z2",
        })
        self.assertEqual(status, 202)
        self.assertEqual(payload["deployment"]["state"], "queued")

    def test_platform_deployment_launch_is_serialized_against_managed_write(self) -> None:
        gate = BootstrapPlasmaManagerHandler.operation_gate
        self.assertTrue(gate.try_begin_managed_write("z2"))
        try:
            status, payload = self.request(
                "POST",
                "/api/registry/z2/bootstrap/deployments",
                {
                    "upload_id": "a" * 32,
                    "ppu_id": "z2-dev-01",
                    "facility_id": "lab",
                    "display_name": "Plasma Z2",
                },
            )
        finally:
            gate.end_managed_write("z2")
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_control_plane_busy")
        self.assertNotIn("start_deployment", [call[0] for call in self.coordinator.calls])

    def test_durable_platform_deployment_state_blocks_registration_changes_until_terminal(self) -> None:
        self.registry.set_lifecycle("z2", "commissioned")
        status, payload = self.request(
            "POST",
            "/api/registry/z2/bootstrap/deployments",
            {
                "upload_id": "a" * 32,
                "ppu_id": "z2-dev-01",
                "facility_id": "lab",
                "display_name": "Plasma Z2",
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["deployment"]["state"], "queued")

        status, payload = self.request(
            "PATCH",
            "/api/registry/z2",
            {"lifecycle": "disabled"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_platform_maintenance_active")
        self.assertEqual(self.registry.record_by_alias("z2").lifecycle, "commissioned")

        self.coordinator.deployment_state = "succeeded"
        status, payload = self.request(
            "PATCH",
            "/api/registry/z2",
            {"lifecycle": "disabled"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["entry"]["lifecycle"], "disabled")

    def test_active_execution_blocks_pending_mutations(self) -> None:
        BootstrapPlasmaManagerHandler.poller = FakePoller(active=True)
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/uploads", {"size": 1, "sha256": "0" * 64})
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_busy")

    def test_unknown_bootstrap_route_fails_closed(self) -> None:
        status, payload = self.request("POST", "/api/registry/z2/bootstrap/shell", {"command": "id"})
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "bootstrap_route_not_allowed")


if __name__ == "__main__":
    unittest.main()
