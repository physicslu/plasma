from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from plasma_manager.config import ManagerConfig, PPURegistryEntry
from plasma_manager.network_commissioning import NetworkCommissioningRecord
from plasma_manager.registry import PPURegistryStore
from plasma_manager.server import PlasmaManagerHandler


class FakePoller:
    def __init__(self, *, active: bool = False, trusted: bool = True) -> None:
        site = {"state": "running" if active else "ready", "current_job_id": "job-1" if active else None}
        self.payload = {
            "ok": True,
            "ppus": [
                {
                    "alias": "ppu-a",
                    "gateway_live": trusted,
                    "execution_ready": trusted,
                    "contract_compatible": trusted,
                    "identity_conflict": False,
                    "ppu": {"ppu_id": "ppu-static-1"},
                    "sites": [site],
                    "errors": [],
                    "observation": {"state": "current" if trusted else "stale"},
                }
            ],
        }

    def snapshot(self):
        return self.payload


class FakeCoordinator:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.record = NetworkCommissioningRecord(
            transaction_id="tx-1",
            request_key="request-1",
            request_fingerprint="f" * 64,
            alias="ppu-a",
            state="completed",
            old_endpoint="http://192.168.77.10:18080",
            candidate_endpoint="http://192.168.77.21:18080",
            ppu_id="ppu-static-1",
            desired_revision=2,
            activation_id="activation-1",
            rollback_timeout_s=20,
            rollback_deadline_epoch_s=100.0,
            started_at="2026-09-03T00:00:00+00:00",
            updated_at="2026-09-03T00:00:01+00:00",
        )

    def get(self, alias: str):
        return self.record if alias == "ppu-a" else None

    def start(self, alias, desired, *, rollback_timeout_s, request_key, authorization):
        self.calls.append(
            {
                "alias": alias,
                "desired": desired,
                "rollback_timeout_s": rollback_timeout_s,
                "request_key": request_key,
                "authorization": authorization,
            }
        )
        return self.record


class ManagerNetworkCommissioningRestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.registry = PPURegistryStore(
            (PPURegistryEntry(endpoint="http://192.168.77.10:18080", alias="ppu-a"),),
            root / "registry.json",
        )
        self.coordinator = FakeCoordinator()
        self.previous = (
            PlasmaManagerHandler.config,
            PlasmaManagerHandler.registry_store,
            PlasmaManagerHandler.poller,
            PlasmaManagerHandler.network_commissioning,
        )
        PlasmaManagerHandler.config = ManagerConfig(
            ppus=(PPURegistryEntry(endpoint="http://192.168.77.10:18080", alias="ppu-a"),),
            registry_state_path=root / "registry.json",
        )
        PlasmaManagerHandler.registry_store = self.registry
        PlasmaManagerHandler.poller = FakePoller()
        PlasmaManagerHandler.network_commissioning = self.coordinator
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaManagerHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        (
            PlasmaManagerHandler.config,
            PlasmaManagerHandler.registry_store,
            PlasmaManagerHandler.poller,
            PlasmaManagerHandler.network_commissioning,
        ) = self.previous
        self.temp.cleanup()

    def request(self, method: str, path: str, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        payload = None if body is None else json.dumps(body)
        request_headers = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=payload, headers=request_headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        connection.close()
        return response.status, data

    def desired(self):
        return {
            "mode": "static",
            "address": "192.168.77.21",
            "prefix_length": 24,
            "gateway": None,
            "dns_servers": [],
        }

    def test_post_is_manager_owned_and_preserves_in_memory_auth_evidence(self) -> None:
        status, payload = self.request(
            "POST",
            "/api/registry/ppu-a/network-commissioning",
            {"desired": self.desired(), "rollback_timeout_s": 20},
            {
                "Idempotency-Key": "request-1",
                "Authorization": "Bearer admin-token",
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["commissioning"]["state"], "completed")
        self.assertEqual(self.coordinator.calls[0]["request_key"], "request-1")
        self.assertEqual(self.coordinator.calls[0]["authorization"], "Bearer admin-token")
        self.assertEqual(self.coordinator.calls[0]["desired"], self.desired())

    def test_get_returns_latest_durable_transaction_without_contacting_ppu(self) -> None:
        status, payload = self.request("GET", "/api/registry/ppu-a/network-commissioning")
        self.assertEqual(status, 200)
        self.assertEqual(payload["commissioning"]["transaction_id"], "tx-1")

    def test_active_execution_fails_closed_before_coordinator_start(self) -> None:
        PlasmaManagerHandler.poller = FakePoller(active=True)
        status, payload = self.request(
            "POST",
            "/api/registry/ppu-a/network-commissioning",
            {"desired": self.desired()},
            {"Idempotency-Key": "request-busy"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_busy")
        self.assertEqual(self.coordinator.calls, [])

    def test_stale_identity_observation_fails_closed(self) -> None:
        PlasmaManagerHandler.poller = FakePoller(trusted=False)
        status, payload = self.request(
            "POST",
            "/api/registry/ppu-a/network-commissioning",
            {"desired": self.desired()},
            {"Idempotency-Key": "request-stale"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_validation_incomplete")
        self.assertEqual(self.coordinator.calls, [])


if __name__ == "__main__":
    unittest.main()
