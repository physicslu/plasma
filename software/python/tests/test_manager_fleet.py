from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_manager.client import PPUHTTPError, PPUTransportError
from plasma_manager.config import ManagerConfig, ManagerConfigError, PPURegistryEntry, load_manager_config
from plasma_manager.fleet import FleetAggregator
from plasma_manager.observation import FleetObservationStore
from plasma_manager.poller import FleetPoller
from plasma_manager.server import PlasmaManagerHandler


class FakePPUClient:
    scenarios = {}

    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.scenario = self.scenarios[endpoint]

    def liveness(self):
        if self.scenario.get("offline"):
            raise PPUTransportError("simulated PPU offline")
        if self.scenario.get("bad_live"):
            return 200, {"ok": False, "gateway": "alive"}
        return 200, {"ok": True, "service": "plasma-web-rest-gateway", "gateway": "alive"}

    def readiness(self):
        if self.scenario.get("unready"):
            return 503, {
                "ok": False,
                "gateway": "alive",
                "execution": "unavailable",
                "error": {"message": "local Plasma Server is unavailable"},
            }
        return 200, {
            "ok": True,
            "gateway": "alive",
            "execution": "ready",
            "ppu_id": self.scenario.get("readiness_ppu_id", self.scenario["ppu_id"]),
        }

    def node(self):
        site_count = self.scenario["site_count"]
        enabled_site_count = self.scenario.get("enabled_site_count", site_count)
        return 200, {
            "ok": True,
            "contract_version": "1",
            "node_role": "ppu",
            "manager_required": False,
            "ppu": {
                "ppu_id": self.scenario["ppu_id"],
                "facility_id": self.scenario.get("facility_id", "facility-a"),
                "model": self.scenario.get("model", "test-ppu"),
                "display_name": self.scenario["ppu_id"],
                "site_count": site_count,
                "enabled_site_count": enabled_site_count,
                "capabilities": {
                    "max_supported_sites": site_count,
                    "operations": ["erase", "program", "verify", "read"],
                },
            },
            "links": {
                "status": "/api/status",
                "jobs": "/api/jobs",
                "liveness": "/api/health/live",
                "readiness": "/api/health/ready",
            },
        }

    def status(self):
        _, node = self.node()
        site_count = self.scenario["site_count"]
        enabled_site_count = self.scenario.get("enabled_site_count", site_count)
        ppu = dict(node["ppu"])
        if "status_ppu_id" in self.scenario:
            ppu["ppu_id"] = self.scenario["status_ppu_id"]
        return 200, {
            "ok": True,
            "ppu": ppu,
            "sites": [
                {
                    "site_id": site_id,
                    "enabled": site_id <= enabled_site_count,
                    "state": "idle",
                    "current_job_id": None,
                    "queued_jobs": 0,
                }
                for site_id in range(1, site_count + 1)
            ],
        }


class ManagerConfigTests(unittest.TestCase):
    def load(self, text: str) -> ManagerConfig:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manager.yaml"
            path.write_text(text, encoding="utf-8")
            return load_manager_config(path)

    def test_loads_manual_registry_and_normalizes_gateway_root(self):
        config = self.load(
            """
manager:
  host: 0.0.0.0
  port: 18180
  request_timeout_s: 1.5
  poll_interval_s: 3.0
ppus:
  - alias: line-a
    endpoint: https://ppu-a.example.invalid/
  - endpoint: http://ppu-b.example.invalid:18080
"""
        )
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 18180)
        self.assertEqual(config.request_timeout_s, 1.5)
        self.assertEqual(config.poll_interval_s, 3.0)
        self.assertEqual(config.ppus[0].endpoint, "https://ppu-a.example.invalid")
        self.assertEqual(config.ppus[0].alias, "line-a")

    def test_poll_interval_defaults_and_rejects_busy_loop_values(self):
        self.assertEqual(self.load("ppus: []\n").poll_interval_s, 2.0)
        with self.assertRaises(ManagerConfigError):
            self.load("manager:\n  poll_interval_s: 0\nppus: []\n")
        with self.assertRaises(ManagerConfigError):
            self.load("manager:\n  poll_interval_s: 301\nppus: []\n")

    def test_rejects_duplicate_or_credentialed_endpoints(self):
        with self.assertRaises(ManagerConfigError):
            self.load(
                """
ppus:
  - {endpoint: http://ppu-a.example.invalid}
  - {endpoint: http://ppu-a.example.invalid/}
"""
            )
        with self.assertRaises(ManagerConfigError):
            self.load("ppus:\n  - {endpoint: 'https://user:secret@ppu-a.example.invalid'}\n")


class FleetAggregatorTests(unittest.TestCase):
    def setUp(self):
        FakePPUClient.scenarios = {
            "http://ppu-2": {
                "ppu_id": "ppu-2",
                "facility_id": "factory-a",
                "site_count": 2,
                "enabled_site_count": 2,
            },
            "http://ppu-4": {
                "ppu_id": "ppu-4",
                "facility_id": "factory-a",
                "site_count": 4,
                "enabled_site_count": 3,
            },
            "http://ppu-8": {
                "ppu_id": "ppu-8",
                "facility_id": "factory-b",
                "site_count": 8,
                "enabled_site_count": 6,
            },
            "http://offline": {"offline": True},
            "http://unready": {
                "ppu_id": "ppu-unready",
                "site_count": 2,
                "unready": True,
            },
            "http://bad-live": {
                "ppu_id": "ppu-bad-live",
                "site_count": 2,
                "bad_live": True,
            },
        }

    def config(self, endpoints) -> ManagerConfig:
        return ManagerConfig(
            request_timeout_s=0.5,
            ppus=tuple(PPURegistryEntry(endpoint=endpoint) for endpoint in endpoints),
        )

    def test_aggregates_heterogeneous_2_4_8_site_ppus(self):
        snapshot = FleetAggregator(
            self.config(["http://ppu-2", "http://ppu-4", "http://ppu-8"]),
            FakePPUClient,
        ).fleet_snapshot()

        self.assertTrue(snapshot["ok"])
        self.assertFalse(snapshot["degraded"])
        self.assertEqual(snapshot["summary"]["configured_ppus"], 3)
        self.assertEqual(snapshot["summary"]["ready_ppus"], 3)
        self.assertEqual(snapshot["summary"]["identified_ppus"], 3)
        self.assertEqual(snapshot["summary"]["reported_sites"], 14)
        self.assertEqual(snapshot["summary"]["enabled_sites"], 11)
        self.assertEqual([item["ppu"]["site_count"] for item in snapshot["ppus"]], [2, 4, 8])
        self.assertTrue(all(item["transport_state"] == "reachable" for item in snapshot["ppus"]))
        self.assertTrue(all(item["execution_state"] == "ready" for item in snapshot["ppus"]))
        self.assertEqual(
            snapshot["facilities"],
            [
                {
                    "facility_id": "factory-a",
                    "ppu_ids": ["ppu-2", "ppu-4"],
                    "site_count": 6,
                    "enabled_site_count": 5,
                },
                {
                    "facility_id": "factory-b",
                    "ppu_ids": ["ppu-8"],
                    "site_count": 8,
                    "enabled_site_count": 6,
                },
            ],
        )

    def test_one_offline_ppu_does_not_poison_healthy_ppus(self):
        snapshot = FleetAggregator(
            self.config(["http://ppu-2", "http://offline", "http://ppu-8"]),
            FakePPUClient,
        ).fleet_snapshot()

        self.assertTrue(snapshot["ok"])
        self.assertTrue(snapshot["degraded"])
        self.assertEqual(snapshot["summary"]["configured_ppus"], 3)
        self.assertEqual(snapshot["summary"]["reachable_ppus"], 2)
        self.assertEqual(snapshot["summary"]["ready_ppus"], 2)
        self.assertEqual(snapshot["summary"]["identified_ppus"], 2)
        self.assertEqual(snapshot["summary"]["reported_sites"], 10)
        self.assertTrue(snapshot["ppus"][0]["execution_ready"])
        self.assertFalse(snapshot["ppus"][1]["gateway_live"])
        self.assertEqual(snapshot["ppus"][1]["transport_state"], "unreachable")
        self.assertEqual(snapshot["ppus"][1]["execution_state"], "unknown")
        self.assertIn("simulated PPU offline", snapshot["ppus"][1]["errors"][0])
        self.assertTrue(snapshot["ppus"][2]["execution_ready"])

    def test_unready_execution_is_distinct_from_transport_failure(self):
        snapshot = FleetAggregator(
            self.config(["http://unready"]),
            FakePPUClient,
        ).fleet_snapshot()
        item = snapshot["ppus"][0]

        self.assertTrue(item["gateway_live"])
        self.assertEqual(item["transport_state"], "reachable")
        self.assertFalse(item["execution_ready"])
        self.assertEqual(item["execution_state"], "unavailable")

    def test_contract_failure_is_not_misclassified_as_transport_outage(self):
        snapshot = FleetAggregator(
            self.config(["http://bad-live"]),
            FakePPUClient,
        ).fleet_snapshot()
        item = snapshot["ppus"][0]

        self.assertFalse(item["gateway_live"])
        self.assertEqual(item["transport_state"], "reachable")
        self.assertEqual(item["execution_state"], "unknown")
        self.assertIn("liveness payload", item["errors"][0])

    def test_duplicate_ppu_identity_is_excluded_from_trusted_topology_totals(self):
        FakePPUClient.scenarios["http://duplicate"] = {
            "ppu_id": "ppu-2",
            "facility_id": "factory-a",
            "site_count": 2,
            "enabled_site_count": 2,
        }
        snapshot = FleetAggregator(
            self.config(["http://ppu-2", "http://duplicate"]),
            FakePPUClient,
        ).fleet_snapshot()

        self.assertTrue(snapshot["degraded"])
        self.assertEqual(snapshot["summary"]["identity_conflicts"], 1)
        self.assertEqual(snapshot["summary"]["identified_ppus"], 0)
        self.assertEqual(snapshot["summary"]["reported_sites"], 0)
        self.assertEqual(snapshot["facilities"], [])
        self.assertTrue(snapshot["ppus"][0]["identity_conflict"])
        self.assertTrue(snapshot["ppus"][1]["identity_conflict"])

    def test_readiness_node_and_status_identity_must_agree(self):
        FakePPUClient.scenarios["http://ready-mismatch"] = {
            "ppu_id": "ppu-real",
            "readiness_ppu_id": "ppu-other",
            "site_count": 2,
        }
        FakePPUClient.scenarios["http://status-mismatch"] = {
            "ppu_id": "ppu-status-real",
            "status_ppu_id": "ppu-status-other",
            "site_count": 2,
        }

        ready_mismatch = FleetAggregator(
            self.config(["http://ready-mismatch"]),
            FakePPUClient,
        ).fleet_snapshot()
        status_mismatch = FleetAggregator(
            self.config(["http://status-mismatch"]),
            FakePPUClient,
        ).fleet_snapshot()

        self.assertTrue(ready_mismatch["degraded"])
        self.assertEqual(ready_mismatch["summary"]["identified_ppus"], 0)
        self.assertIn("disagree on ppu_id", ready_mismatch["ppus"][0]["errors"][0])
        self.assertTrue(status_mismatch["degraded"])
        self.assertEqual(status_mismatch["summary"]["identified_ppus"], 0)
        self.assertIn("disagree on ppu.ppu_id", status_mismatch["ppus"][0]["errors"][0])


class FleetObservationStoreTests(unittest.TestCase):
    def setUp(self):
        FakePPUClient.scenarios = {
            "http://ppu-a": {
                "ppu_id": "ppu-a",
                "facility_id": "factory-a",
                "site_count": 2,
                "enabled_site_count": 2,
            },
            "http://ppu-b": {
                "ppu_id": "ppu-b",
                "facility_id": "factory-b",
                "site_count": 4,
                "enabled_site_count": 3,
            },
            "http://never-seen": {"offline": True},
        }

    def config(self, endpoints) -> ManagerConfig:
        return ManagerConfig(
            request_timeout_s=0.5,
            ppus=tuple(PPURegistryEntry(endpoint=endpoint) for endpoint in endpoints),
        )

    def observer(self, endpoints) -> FleetObservationStore:
        return FleetObservationStore(FleetAggregator(self.config(endpoints), FakePPUClient))

    def test_success_then_offline_preserves_last_known_without_inflating_current_totals(self):
        observer = self.observer(["http://ppu-a"])
        current = observer.fleet_snapshot()
        current_item = current["ppus"][0]
        first_success = current_item["observation"]["last_success_at"]

        self.assertEqual(current_item["observation"]["state"], "current")
        self.assertFalse(current_item["observation"]["stale"])
        self.assertEqual(current_item["observation"]["stale_age_s"], 0.0)
        self.assertEqual(current_item["last_known"]["ppu"]["ppu_id"], "ppu-a")
        self.assertEqual(current["summary"]["known_ppus"], 1)
        self.assertEqual(current["summary"]["stale_ppus"], 0)
        self.assertEqual(current["summary"]["unknown_ppus"], 0)

        FakePPUClient.scenarios["http://ppu-a"]["offline"] = True
        stale = observer.fleet_snapshot()
        stale_item = stale["ppus"][0]

        self.assertIsNone(stale_item["ppu"])
        self.assertEqual(stale_item["sites"], [])
        self.assertEqual(stale_item["transport_state"], "unreachable")
        self.assertEqual(stale_item["execution_state"], "unknown")
        self.assertEqual(stale_item["observation"]["state"], "stale")
        self.assertTrue(stale_item["observation"]["stale"])
        self.assertEqual(stale_item["observation"]["last_success_at"], first_success)
        self.assertGreaterEqual(stale_item["observation"]["stale_age_s"], 0.0)
        self.assertEqual(stale_item["last_known"]["ppu"]["ppu_id"], "ppu-a")
        self.assertEqual(len(stale_item["last_known"]["sites"]), 2)

        # Existing fleet totals remain current-only; stale topology is explicit metadata,
        # not silently counted as currently identified/available capacity.
        self.assertEqual(stale["summary"]["identified_ppus"], 0)
        self.assertEqual(stale["summary"]["reported_sites"], 0)
        self.assertEqual(stale["summary"]["known_ppus"], 1)
        self.assertEqual(stale["summary"]["stale_ppus"], 1)
        self.assertEqual(stale["summary"]["unknown_ppus"], 0)
        self.assertEqual(stale["facilities"], [])

        FakePPUClient.scenarios["http://ppu-a"]["offline"] = False
        recovered = observer.fleet_snapshot()
        recovered_item = recovered["ppus"][0]
        self.assertEqual(recovered_item["observation"]["state"], "current")
        self.assertFalse(recovered_item["observation"]["stale"])
        self.assertEqual(recovered_item["observation"]["stale_age_s"], 0.0)
        self.assertEqual(recovered["summary"]["identified_ppus"], 1)
        self.assertEqual(recovered["summary"]["stale_ppus"], 0)

    def test_first_observation_failure_is_unknown_not_fake_stale_data(self):
        snapshot = self.observer(["http://never-seen"]).fleet_snapshot()
        item = snapshot["ppus"][0]

        self.assertEqual(item["observation"]["state"], "unknown")
        self.assertFalse(item["observation"]["stale"])
        self.assertIsNone(item["observation"]["last_success_at"])
        self.assertIsNone(item["observation"]["stale_age_s"])
        self.assertIsNone(item["last_known"])
        self.assertEqual(snapshot["summary"]["known_ppus"], 0)
        self.assertEqual(snapshot["summary"]["stale_ppus"], 0)
        self.assertEqual(snapshot["summary"]["unknown_ppus"], 1)

    def test_execution_unavailable_preserves_known_topology_as_stale(self):
        observer = self.observer(["http://ppu-a"])
        observer.fleet_snapshot()
        FakePPUClient.scenarios["http://ppu-a"]["unready"] = True

        snapshot = observer.fleet_snapshot()
        item = snapshot["ppus"][0]

        self.assertEqual(item["transport_state"], "reachable")
        self.assertEqual(item["execution_state"], "unavailable")
        self.assertEqual(item["observation"]["state"], "stale")
        self.assertEqual(item["last_known"]["ppu"]["ppu_id"], "ppu-a")
        self.assertEqual(len(item["last_known"]["sites"]), 2)

    def test_identity_conflict_does_not_overwrite_previous_trusted_identity(self):
        observer = self.observer(["http://ppu-a", "http://ppu-b"])
        first = observer.fleet_snapshot()
        self.assertEqual(first["summary"]["known_ppus"], 2)

        FakePPUClient.scenarios["http://ppu-b"]["ppu_id"] = "ppu-a"
        conflicted = observer.fleet_snapshot()

        self.assertEqual(conflicted["summary"]["identity_conflicts"], 1)
        self.assertEqual(conflicted["summary"]["identified_ppus"], 0)
        self.assertEqual(conflicted["summary"]["known_ppus"], 2)
        self.assertEqual(conflicted["summary"]["stale_ppus"], 2)
        self.assertEqual(conflicted["ppus"][0]["observation"]["state"], "stale")
        self.assertEqual(conflicted["ppus"][1]["observation"]["state"], "stale")
        self.assertEqual(conflicted["ppus"][0]["last_known"]["ppu"]["ppu_id"], "ppu-a")
        self.assertEqual(conflicted["ppus"][1]["last_known"]["ppu"]["ppu_id"], "ppu-b")


class CountingFleetSource:
    def __init__(self) -> None:
        self.calls = 0
        self.second_call = threading.Event()
        self.fail = False

    def fleet_snapshot(self):
        self.calls += 1
        if self.calls >= 2:
            self.second_call.set()
        if self.fail:
            raise RuntimeError("simulated refresh failure")
        return {
            "ok": True,
            "degraded": False,
            "observed_at": f"snapshot-{self.calls}",
            "ppus": [],
        }


class FleetPollerTests(unittest.TestCase):
    def test_cached_reads_do_not_poll_source(self):
        source = CountingFleetSource()
        poller = FleetPoller(source, 60.0)
        poller.start()
        try:
            first = poller.snapshot()
            second = poller.snapshot()
            self.assertEqual(source.calls, 1)
            self.assertEqual(first["observed_at"], "snapshot-1")
            self.assertEqual(second["observed_at"], "snapshot-1")
            self.assertEqual(first["cache"]["mode"], "background")
            self.assertEqual(first["cache"]["poll_interval_s"], 60.0)
            self.assertIsNone(first["cache"]["last_refresh_error"])
        finally:
            poller.stop(timeout_s=1.0)

    def test_background_thread_refreshes_without_http_request(self):
        source = CountingFleetSource()
        poller = FleetPoller(source, 0.05)
        poller.start()
        try:
            self.assertTrue(source.second_call.wait(1.0))
            self.assertGreaterEqual(source.calls, 2)
        finally:
            poller.stop(timeout_s=1.0)

    def test_refresh_failure_preserves_last_completed_snapshot(self):
        source = CountingFleetSource()
        poller = FleetPoller(source, 60.0)
        poller.start()
        try:
            source.fail = True
            with self.assertRaisesRegex(RuntimeError, "simulated refresh failure"):
                poller.refresh()
            snapshot = poller.snapshot()
            self.assertEqual(snapshot["observed_at"], "snapshot-1")
            self.assertIn("simulated refresh failure", snapshot["cache"]["last_refresh_error"])
        finally:
            poller.stop(timeout_s=1.0)


class FakeAggregator:
    def __init__(self):
        self.registry_calls = 0
        self.fleet_calls = 0

    def registry_snapshot(self):
        self.registry_calls += 1
        return {"ok": True, "ppus": [{"endpoint": "http://ppu-a", "alias": "ppu-a"}]}

    def fleet_snapshot(self):
        self.fleet_calls += 1
        return {"ok": True, "degraded": False, "ppus": []}


class ManagerHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_aggregator = PlasmaManagerHandler.aggregator
        cls.original_poller = PlasmaManagerHandler.poller
        cls.fake = FakeAggregator()
        cls.poller = FleetPoller(cls.fake, 60.0)
        cls.poller.start()
        PlasmaManagerHandler.aggregator = cls.fake
        PlasmaManagerHandler.poller = cls.poller
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaManagerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.poller.stop(timeout_s=1.0)
        PlasmaManagerHandler.aggregator = cls.original_aggregator
        PlasmaManagerHandler.poller = cls.original_poller

    def request(self, method: str, path: str):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request(method, path)
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        conn.close()
        return status, payload

    def test_manager_liveness_does_not_poll_ppus(self):
        before = self.fake.fleet_calls
        status, payload = self.request("GET", "/api/health/live")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["manager"], "alive")
        self.assertEqual(self.fake.fleet_calls, before)

    def test_repeated_fleet_reads_use_cache_without_new_poll(self):
        before = self.fake.fleet_calls
        for _ in range(3):
            status, fleet = self.request("GET", "/api/fleet")
            self.assertEqual(status, 200)
            self.assertEqual(fleet["cache"]["mode"], "background")
        self.assertEqual(self.fake.fleet_calls, before)

    def test_registry_and_fleet_are_read_only(self):
        status, registry = self.request("GET", "/api/registry")
        self.assertEqual(status, 200)
        self.assertEqual(registry["ppus"][0]["endpoint"], "http://ppu-a")

        status, fleet = self.request("GET", "/api/fleet")
        self.assertEqual(status, 200)
        self.assertTrue(fleet["ok"])

        status, payload = self.request("POST", "/api/fleet")
        self.assertEqual(status, 405)
        self.assertIn("read-only", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
