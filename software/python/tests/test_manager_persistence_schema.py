from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from plasma_manager.persistence import SQLiteObservationPersistence


class ManagerPersistenceSchemaSafetyTests(unittest.TestCase):
    def test_unversioned_nonempty_database_is_not_claimed_or_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "other.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE unrelated(value TEXT)")
                connection.execute("INSERT INTO unrelated(value) VALUES ('keep-me')")

            persistence = SQLiteObservationPersistence(path)
            with self.assertRaisesRegex(RuntimeError, "unversioned observation database is not empty"):
                persistence.load()

            with sqlite3.connect(path) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                value = connection.execute("SELECT value FROM unrelated").fetchone()[0]
                observation_table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='observations'"
                ).fetchone()
            self.assertEqual(version, 0)
            self.assertEqual(value, "keep-me")
            self.assertIsNone(observation_table)

    def test_schema_v1_without_required_table_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("PRAGMA user_version = 1")

            persistence = SQLiteObservationPersistence(path)
            with self.assertRaisesRegex(RuntimeError, "schema v1 is missing observations table"):
                persistence.load()

    def test_timezone_naive_persisted_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "naive.sqlite3"
            persistence = SQLiteObservationPersistence(path)
            persistence.load()  # initializes the empty schema v1 database
            record = {
                "observed_at": "2026-08-19T06:00:00",
                "ppu": {"ppu_id": "ppu-a"},
                "sites": [],
            }
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "INSERT INTO observations(endpoint, record_json) VALUES (?, ?)",
                    ("http://ppu-a", json.dumps(record)),
                )

            with self.assertRaisesRegex(RuntimeError, "observed_at must include a timezone"):
                persistence.load()


if __name__ == "__main__":
    unittest.main()
