from __future__ import annotations

import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from plasma_manager.config import ManagerConfigError, load_manager_config
from plasma_manager.observation import FleetObservationStore
from plasma_manager.persistence import SQLiteObservationPersistence


class SequenceFleetSource:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)

    def fleet_snapshot(self):
        if not self.snapshots:
            raise AssertionError("no fleet snapshot remains")
        return deepcopy(self.snapshots.pop(0))


def fleet_snapshot(
    observed_at: str,
    *,
    healthy: bool,
    ppu_id: str = "ppu-a",
    enabled_sites: int = 1,
):
    ppu = {
        "ppu_id": ppu_id,
        "facility_id": "factory-a",
        "model": "test-ppu",
        "site_count": 2,
        "enabled_site_count": enabled_sites,
    }
    sites = [
        {"site_id": 1, "enabled": enabled_sites >= 1, "state": "idle"},
        {"site_id": 2, "enabled": enabled_sites >= 2, "state": "idle"},
    ]
    item = {
        "endpoint": "http://ppu-a",
        "alias": "ppu-a",
        "gateway_live": healthy,
        "execution_ready": healthy,
        "transport_state": "reachable" if healthy else "unreachable",
        "execution_state": "ready" if healthy else "unknown",
        "contract_compatible": healthy,
        "identity_conflict": False,
        "ppu": ppu if healthy else None,
        "sites": sites if healthy else [],
        "errors": [] if healthy else ["simulated PPU offline"],
    }
    return {
        "ok": True,
        "service": "plasma-manager",
        "contract_version": "1",
        "observed_at": observed_at,
        "degraded": not healthy,
        "summary": {
            "configured_ppus": 1,
            "reachable_ppus": int(healthy),
            "ready_ppus": int(healthy),
            "identified_ppus": int(healthy),
            "reported_sites": 2 if healthy else 0,
            "enabled_sites": enabled_sites if healthy else 0,
            "identity_conflicts": 0,
        },
        "facilities": [],
        "ppus": [item],
    }


class ManagerObservationPersistenceConfigTests(unittest.TestCase):
    def load(self, text: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manager.yaml"
            path.write_text(text, encoding="utf-8")
            return load_manager_config(path)

    def test_observation_database_is_opt_in_and_requires_absolute_path(self):
        self.assertIsNone(self.load("ppus: []\n").observation_db_path)
        config = self.load(
            "manager:\n  observation_db_path: /var/lib/plasma/manager-observations.sqlite3\nppus: []\n"
        )
        self.assertEqual(
            config.observation_db_path,
            Path("/var/lib/plasma/manager-observations.sqlite3"),
        )
        with self.assertRaises(ManagerConfigError):
            self.load("manager:\n  observation_db_path: relative.sqlite3\nppus: []\n")


class SQLiteObservationPersistenceTests(unittest.TestCase):
    def record(self, observed_at="2026-08-19T06:00:00+00:00", ppu_id="ppu-a"):
        return {
            "observed_at": observed_at,
            "ppu": {"ppu_id": ppu_id},
            "sites": [{"site_id": 1}],
        }

    def test_replace_round_trips_and_prunes_removed_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            persistence = SQLiteObservationPersistence(Path(directory) / "observations.sqlite3")
            persistence.replace({"http://ppu-a": self.record()})
            self.assertEqual(persistence.load()["http://ppu-a"]["ppu"]["ppu_id"], "ppu-a")

            persistence.replace(
                {"http://ppu-b": self.record("2026-08-19T06:01:00+00:00", "ppu-b")}
            )
            records = persistence.load()
            self.assertEqual(set(records), {"http://ppu-b"})
            self.assertEqual(records["http://ppu-b"]["ppu"]["ppu_id"], "ppu-b")

    def test_future_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("PRAGMA user_version = 99")
            persistence = SQLiteObservationPersistence(path)
            with self.assertRaisesRegex(RuntimeError, "unsupported observation database schema"):
                persistence.load()


class FleetObservationDurabilityTests(unittest.TestCase):
    def test_restart_restores_last_known_as_stale_when_ppu_is_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.sqlite3"
            first = FleetObservationStore(
                SequenceFleetSource(
                    [fleet_snapshot("2026-08-19T06:00:00+00:00", healthy=True)]
                ),
                SQLiteObservationPersistence(path),
            ).fleet_snapshot()
            self.assertEqual(first["ppus"][0]["observation"]["state"], "current")
            self.assertEqual(first["observation_store"]["mode"], "sqlite")
            self.assertTrue(first["observation_store"]["healthy"])

            restarted = FleetObservationStore(
                SequenceFleetSource(
                    [fleet_snapshot("2026-08-19T06:00:10+00:00", healthy=False)]
                ),
                SQLiteObservationPersistence(path),
            ).fleet_snapshot()
            ppu = restarted["ppus"][0]
            self.assertEqual(ppu["observation"]["state"], "stale")
            self.assertTrue(ppu["observation"]["stale"])
            self.assertEqual(ppu["observation"]["last_success_at"], "2026-08-19T06:00:00+00:00")
            self.assertEqual(ppu["observation"]["stale_age_s"], 10.0)
            self.assertIsNone(ppu["ppu"])
            self.assertEqual(ppu["last_known"]["ppu"]["ppu_id"], "ppu-a")
            self.assertEqual(restarted["summary"]["known_ppus"], 1)
            self.assertEqual(restarted["summary"]["stale_ppus"], 1)
            self.assertEqual(restarted["summary"]["reported_sites"], 0)

    def test_recovered_current_observation_replaces_durable_last_known_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.sqlite3"
            FleetObservationStore(
                SequenceFleetSource(
                    [fleet_snapshot("2026-08-19T06:00:00+00:00", healthy=True, enabled_sites=1)]
                ),
                SQLiteObservationPersistence(path),
            ).fleet_snapshot()

            recovered = FleetObservationStore(
                SequenceFleetSource(
                    [fleet_snapshot("2026-08-19T06:01:00+00:00", healthy=True, enabled_sites=2)]
                ),
                SQLiteObservationPersistence(path),
            ).fleet_snapshot()
            self.assertEqual(recovered["ppus"][0]["observation"]["state"], "current")

            offline_after_restart = FleetObservationStore(
                SequenceFleetSource(
                    [fleet_snapshot("2026-08-19T06:01:10+00:00", healthy=False)]
                ),
                SQLiteObservationPersistence(path),
            ).fleet_snapshot()
            last_known = offline_after_restart["ppus"][0]["last_known"]
            self.assertEqual(last_known["observed_at"], "2026-08-19T06:01:00+00:00")
            self.assertTrue(last_known["sites"][1]["enabled"])

    def test_persistence_failure_degrades_to_memory_without_losing_current_fleet_state(self):
        class FailingPersistence:
            mode = "sqlite"

            def load(self):
                raise RuntimeError("simulated load failure")

            def replace(self, records):
                raise RuntimeError("simulated write failure")

        snapshot = FleetObservationStore(
            SequenceFleetSource(
                [fleet_snapshot("2026-08-19T06:00:00+00:00", healthy=True)]
            ),
            FailingPersistence(),
        ).fleet_snapshot()
        ppu = snapshot["ppus"][0]
        self.assertEqual(ppu["observation"]["state"], "current")
        self.assertEqual(ppu["last_known"]["ppu"]["ppu_id"], "ppu-a")
        self.assertEqual(snapshot["summary"]["reported_sites"], 2)
        self.assertEqual(snapshot["observation_store"]["mode"], "sqlite")
        self.assertFalse(snapshot["observation_store"]["healthy"])
        self.assertIn("simulated write failure", snapshot["observation_store"]["last_error"])

    def test_memory_mode_preserves_pr45_restart_semantics(self):
        first = FleetObservationStore(
            SequenceFleetSource([fleet_snapshot("2026-08-19T06:00:00+00:00", healthy=True)])
        ).fleet_snapshot()
        self.assertEqual(first["observation_store"]["mode"], "memory")

        restarted = FleetObservationStore(
            SequenceFleetSource([fleet_snapshot("2026-08-19T06:00:10+00:00", healthy=False)])
        ).fleet_snapshot()
        self.assertEqual(restarted["ppus"][0]["observation"]["state"], "unknown")
        self.assertIsNone(restarted["ppus"][0]["last_known"])
        self.assertEqual(restarted["summary"]["unknown_ppus"], 1)


if __name__ == "__main__":
    unittest.main()
