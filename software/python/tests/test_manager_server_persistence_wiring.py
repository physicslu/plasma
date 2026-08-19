from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_manager.config import ManagerConfig
from plasma_manager.persistence import SQLiteObservationPersistence
from plasma_manager.server import _build_observation_store


class FakeFleetSource:
    def fleet_snapshot(self):
        raise AssertionError("wiring test must not poll the fleet source")


class ManagerServerPersistenceWiringTests(unittest.TestCase):
    def test_configured_database_builds_sqlite_persistence_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.sqlite3"
            store = _build_observation_store(
                ManagerConfig(observation_db_path=path),
                FakeFleetSource(),
            )
            self.assertIsInstance(store.persistence, SQLiteObservationPersistence)
            self.assertEqual(store.persistence.path, path)

    def test_omitted_database_keeps_memory_only_observation_store(self):
        store = _build_observation_store(ManagerConfig(), FakeFleetSource())
        self.assertIsNone(store.persistence)


if __name__ == "__main__":
    unittest.main()
