from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_manager.client import PPUHTTPError
from plasma_manager.config import ManagerConfig, ManagerConfigError, PPURegistryEntry, load_manager_config
from plasma_manager.fleet import FleetAggregator
from plasma_manager.server import PlasmaManagerHandler


class FakePPUClient:
    scenarios = {}

    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.scenario = self.scenarios[endpoint]

    def liveness(self):
        if self.scenario.get("offline"):
            raise PPUHTTPError("simulated PPU offline")
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
ppus:
  - alias: line-a
    endpoint: https://ppu-a.example.invalid/
  - endpoint: http://ppu-b.example.invalid:18080
"""
        )
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 18180)
        self.assertEqual(config.request_timeout_s, 1.5)
        self.assertEqual(config.ppus[0].endpoint, "https://ppu-a.example.invalid")
        self.assertEqual(config.ppus[0].alias, "line-a")

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
        self.assertIn("simulated PPU offline", snapshot["ppus"][1]["errors"][0])
        self.assertTrue(snapshot["ppus"][2]["execution_ready"])

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
        cls.fake = FakeAggregator()
        PlasmaManagerHandler.aggregator = cls.fake
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaManagerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        PlasmaManagerHandler.aggregator = cls.original_aggregator

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
