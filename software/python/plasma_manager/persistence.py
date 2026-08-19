from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol


OBSERVATION_DB_SCHEMA_VERSION = 1


class ObservationPersistenceError(RuntimeError):
    """Raised when durable Manager observation state cannot be loaded or stored safely."""


class ObservationPersistence(Protocol):
    mode: str

    def load(self) -> dict[str, dict[str, Any]]: ...

    def replace(self, records: dict[str, dict[str, Any]]) -> None: ...


class SQLiteObservationPersistence:
    """SQLite-backed last-known observation cache keyed by configured PPU endpoint."""

    mode = "sqlite"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, dict[str, Any]]:
        try:
            with self._connect() as connection:
                self._ensure_schema(connection)
                rows = connection.execute(
                    "SELECT endpoint, record_json FROM observations ORDER BY endpoint"
                ).fetchall()
        except (OSError, sqlite3.Error) as exc:
            raise ObservationPersistenceError(f"cannot load observation database: {exc}") from exc

        records: dict[str, dict[str, Any]] = {}
        for endpoint, record_json in rows:
            if not isinstance(endpoint, str) or not endpoint:
                raise ObservationPersistenceError("observation database contains an invalid endpoint")
            try:
                record = json.loads(record_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ObservationPersistenceError(
                    f"observation database contains invalid JSON for {endpoint}"
                ) from exc
            self._validate_record(endpoint, record)
            records[endpoint] = record
        return records

    def replace(self, records: dict[str, dict[str, Any]]) -> None:
        serialized: list[tuple[str, str]] = []
        for endpoint, record in records.items():
            self._validate_record(endpoint, record)
            serialized.append(
                (
                    endpoint,
                    json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                )
            )

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                self._ensure_schema(connection)
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM observations")
                connection.executemany(
                    "INSERT INTO observations(endpoint, record_json) VALUES (?, ?)",
                    serialized,
                )
                connection.commit()
        except (OSError, sqlite3.Error) as exc:
            raise ObservationPersistenceError(f"cannot store observation database: {exc}") from exc

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=2.0)

    @staticmethod
    def _validate_record(endpoint: Any, record: Any) -> None:
        if not isinstance(endpoint, str) or not endpoint:
            raise ObservationPersistenceError("observation endpoint must be a non-empty string")
        if not isinstance(record, dict):
            raise ObservationPersistenceError(f"observation record for {endpoint} must be an object")
        observed_at = record.get("observed_at")
        ppu = record.get("ppu")
        sites = record.get("sites")
        if not isinstance(observed_at, str) or not observed_at:
            raise ObservationPersistenceError(
                f"observation record for {endpoint} is missing observed_at"
            )
        if not isinstance(ppu, dict):
            raise ObservationPersistenceError(f"observation record for {endpoint} is missing ppu")
        if not isinstance(sites, list):
            raise ObservationPersistenceError(f"observation record for {endpoint} is missing sites")

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        version_row = connection.execute("PRAGMA user_version").fetchone()
        version = int(version_row[0]) if version_row else 0
        if version not in {0, OBSERVATION_DB_SCHEMA_VERSION}:
            raise ObservationPersistenceError(
                f"unsupported observation database schema version: {version}"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                endpoint TEXT PRIMARY KEY,
                record_json TEXT NOT NULL
            )
            """
        )
        if version == 0:
            connection.execute(f"PRAGMA user_version = {OBSERVATION_DB_SCHEMA_VERSION}")
            connection.commit()
