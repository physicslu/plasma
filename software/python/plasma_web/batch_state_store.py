from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import iso_now


BATCH_STATE_SCHEMA_VERSION = 1
DEFAULT_BATCH_RETENTION_DAYS = 30


@dataclass(frozen=True, slots=True)
class StoredBatch:
    batch_id: str
    spec: dict[str, Any]
    snapshot: dict[str, Any]
    asset_data: bytes | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class StoredBatchJob:
    batch_id: str
    site_key: str
    job_id: str
    facility_id: str
    ppu_id: str
    site_id: int
    operation: str
    round_index: int
    phase: str
    job: dict[str, Any] | None
    updated_at: str


class BatchStateStore:
    """Crash-safe local persistence for server-owned Batch execution state.

    SQLite is intentionally used as an embedded durability boundary. The
    Gateway must be able to commit Batch identity and Job admission provenance
    atomically without depending on a separate database service.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        terminal_retention_days: int = DEFAULT_BATCH_RETENTION_DAYS,
    ) -> None:
        if (
            isinstance(terminal_retention_days, bool)
            or not isinstance(terminal_retention_days, int)
            or terminal_retention_days < 1
        ):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "Batch terminal retention must be a positive number of days",
            )
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.terminal_retention_days = terminal_retention_days
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._migrate()
            self.prune_terminal()

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _object(raw: str, label: str) -> dict[str, Any]:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"Persisted {label} JSON is invalid",
                original_exception=exc,
            ) from exc
        if not isinstance(value, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"Persisted {label} must be an object")
        return value

    @classmethod
    def _stored_batch(cls, row: sqlite3.Row) -> StoredBatch:
        return StoredBatch(
            batch_id=str(row["batch_id"]),
            spec=cls._object(str(row["spec_json"]), "Batch spec"),
            snapshot=cls._object(str(row["snapshot_json"]), "Batch snapshot"),
            asset_data=bytes(row["asset_blob"]) if row["asset_blob"] is not None else None,
            updated_at=str(row["updated_at"]),
        )

    def _migrate(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 0:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    spec_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    asset_blob BLOB,
                    terminal INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS batch_jobs (
                    batch_id TEXT NOT NULL,
                    site_key TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    facility_id TEXT NOT NULL,
                    ppu_id TEXT NOT NULL,
                    site_id INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    round_index INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    job_json TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (batch_id, job_id),
                    FOREIGN KEY (batch_id) REFERENCES batches(batch_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS batch_jobs_site_index
                    ON batch_jobs(batch_id, site_key, updated_at);
                """
            )
            self._connection.execute(f"PRAGMA user_version={BATCH_STATE_SCHEMA_VERSION}")
            self._connection.commit()
            version = BATCH_STATE_SCHEMA_VERSION
        if version != BATCH_STATE_SCHEMA_VERSION:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "Unsupported Batch state database schema version",
                context={"expected": BATCH_STATE_SCHEMA_VERSION, "actual": version},
            )

    def prepare_batch(
        self,
        batch_id: str,
        *,
        spec: dict[str, Any],
        asset_data: bytes | None,
    ) -> None:
        now = iso_now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO batches (
                    batch_id, schema_version, spec_json, snapshot_json,
                    asset_blob, terminal, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    batch_id,
                    BATCH_STATE_SCHEMA_VERSION,
                    self._json(spec),
                    self._json({}),
                    asset_data,
                    now,
                    now,
                ),
            )
            self._connection.commit()

    def discard_batch(self, batch_id: str) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM batches WHERE batch_id = ?", (batch_id,))
            self._connection.commit()

    def save_snapshot(self, batch_id: str, snapshot: dict[str, Any]) -> None:
        state = str(snapshot.get("state", ""))
        terminal = int(state in {"success", "partial", "error", "cancelled"})
        now = iso_now()
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE batches
                SET snapshot_json = ?, terminal = ?, updated_at = ?
                WHERE batch_id = ?
                """,
                (self._json(snapshot), terminal, now, batch_id),
            )
            if cursor.rowcount != 1:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"Batch state row missing: {batch_id}")
            self._connection.commit()

    def record_job_intent(
        self,
        *,
        batch_id: str,
        site_key: str,
        job_id: str,
        facility_id: str,
        ppu_id: str,
        site_id: int,
        operation: str,
        round_index: int,
    ) -> None:
        now = iso_now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO batch_jobs (
                    batch_id, site_key, job_id, facility_id, ppu_id, site_id,
                    operation, round_index, phase, job_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'submitting', NULL, ?)
                ON CONFLICT(batch_id, job_id) DO UPDATE SET
                    site_key=excluded.site_key,
                    facility_id=excluded.facility_id,
                    ppu_id=excluded.ppu_id,
                    site_id=excluded.site_id,
                    operation=excluded.operation,
                    round_index=excluded.round_index,
                    updated_at=excluded.updated_at
                """,
                (
                    batch_id,
                    site_key,
                    job_id,
                    facility_id,
                    ppu_id,
                    site_id,
                    operation,
                    round_index,
                    now,
                ),
            )
            self._connection.commit()

    def update_job(
        self,
        batch_id: str,
        job_id: str,
        *,
        phase: str,
        job: dict[str, Any] | None = None,
    ) -> None:
        if phase not in {"submitting", "accepted", "terminal", "rejected"}:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"invalid persisted Job phase: {phase}")
        now = iso_now()
        job_json = self._json(job) if job is not None else None
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE batch_jobs
                SET phase = ?, job_json = COALESCE(?, job_json), updated_at = ?
                WHERE batch_id = ? AND job_id = ?
                """,
                (phase, job_json, now, batch_id, job_id),
            )
            if cursor.rowcount != 1:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    f"Persisted Batch Job row missing: {batch_id}/{job_id}",
                )
            self._connection.commit()

    def load_batch(self, batch_id: str) -> StoredBatch | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT batch_id, spec_json, snapshot_json, asset_blob, updated_at
                FROM batches
                WHERE batch_id = ?
                """,
                (batch_id,),
            ).fetchone()
        return self._stored_batch(row) if row is not None else None

    def load_recoverable(self) -> list[StoredBatch]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT batch_id, spec_json, snapshot_json, asset_blob, updated_at
                FROM batches
                WHERE terminal = 0
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [self._stored_batch(row) for row in rows]

    def load_jobs(self, batch_id: str) -> list[StoredBatchJob]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT batch_id, site_key, job_id, facility_id, ppu_id, site_id,
                       operation, round_index, phase, job_json, updated_at
                FROM batch_jobs
                WHERE batch_id = ?
                ORDER BY updated_at ASC, job_id ASC
                """,
                (batch_id,),
            ).fetchall()
        result: list[StoredBatchJob] = []
        for row in rows:
            raw_job = row["job_json"]
            result.append(
                StoredBatchJob(
                    batch_id=str(row["batch_id"]),
                    site_key=str(row["site_key"]),
                    job_id=str(row["job_id"]),
                    facility_id=str(row["facility_id"]),
                    ppu_id=str(row["ppu_id"]),
                    site_id=int(row["site_id"]),
                    operation=str(row["operation"]),
                    round_index=int(row["round_index"]),
                    phase=str(row["phase"]),
                    job=self._object(str(raw_job), "Batch Job") if raw_job is not None else None,
                    updated_at=str(row["updated_at"]),
                )
            )
        return result

    def prune_terminal(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.terminal_retention_days)
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM batches WHERE terminal = 1 AND updated_at < ?",
                (cutoff.isoformat(),),
            )
            self._connection.commit()
            return max(0, cursor.rowcount)

    def close(self) -> None:
        with self._lock:
            self._connection.commit()
            self._connection.close()
