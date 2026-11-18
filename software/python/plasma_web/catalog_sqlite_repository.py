"""SQLite Catalog shadow snapshots, isolated from Selector/PPU runtime.

This is an offline, source-verified importer and parity reader, NOT an
executable/production Catalog authority or a general-purpose data publisher.
The input must first pass DeviceCatalog.from_manifest() source SHA checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .device_catalog import (
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    DeviceCatalogRecord,
    default_catalog_manifest_path,
)

if TYPE_CHECKING:
    from .programming_qualification import ProgrammingQualificationRegistry


SCHEMA_VERSION = 1


def _encoded(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_encoded(value).encode("utf-8")).hexdigest()


def _identity(record: DeviceCatalogRecord) -> tuple[str, str]:
    return record.vendor.strip().casefold(), record.identifier.strip().casefold()


@dataclass(frozen=True)
class CatalogShadowSnapshot:
    revision_sha256: str
    catalog: DeviceCatalog
    qualifications: dict[tuple[str, str], dict[str, Any]]

    @property
    def size(self) -> int:
        return self.catalog.size


class CatalogSqliteShadowRepository:
    """Import a verified source revision and compare it without live cutover.

    Full rows are deliberately retained as canonical JSON for this first
    shadow-migration milestone. Query serving and data-only publication are
    *not* switched on; later work can replace this read path after parity.
    """

    def __init__(self, database_path: Path) -> None:
        self.path = Path(database_path)

    @staticmethod
    def _init_schema(conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise DeviceCatalogIntegrityError("unsupported SQLite Catalog schema")
        if version == 0 and conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]:
            raise DeviceCatalogIntegrityError("refusing to adopt unknown SQLite schema")
        conn.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS catalog_revisions (
                revision_sha256 TEXT PRIMARY KEY,
                source_revision_sha256 TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                row_count INTEGER NOT NULL CHECK (row_count >= 0)
            );
            CREATE TABLE IF NOT EXISTS catalog_records (
                revision_sha256 TEXT NOT NULL
                    REFERENCES catalog_revisions(revision_sha256),
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                vendor_key TEXT NOT NULL,
                icpn_key TEXT NOT NULL,
                record_json TEXT NOT NULL,
                qualification_json TEXT,
                PRIMARY KEY (revision_sha256, ordinal),
                UNIQUE (revision_sha256, vendor_key, icpn_key)
            );
            CREATE TABLE IF NOT EXISTS active_catalog_revision (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                revision_sha256 TEXT NOT NULL
                    REFERENCES catalog_revisions(revision_sha256)
            );
        """)
        if version == 0:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _metadata(catalog: DeviceCatalog) -> dict[str, Any]:
        return {
            "catalog_id": catalog.catalog_id,
            "catalog_version": catalog.catalog_version,
            "status": catalog.status,
            "source_count": catalog.source_count,
            "source_revision_sha256": catalog.revision_sha256,
        }

    @staticmethod
    def _prepared_rows(
        catalog: DeviceCatalog,
        qualification_registry: ProgrammingQualificationRegistry | None,
    ) -> list[tuple[str, str, str, str | None]]:
        seen: set[tuple[str, str]] = set()
        result: list[tuple[str, str, str, str | None]] = []
        if qualification_registry is not None:
            # The qualifier must come from exactly the same admitted source.
            source = qualification_registry._catalog
            if source.revision_sha256 != catalog.revision_sha256 or source.records != catalog.records:
                raise DeviceCatalogIntegrityError("qualification source/Catalog mismatch")
        for record in catalog.records:
            key = _identity(record)
            if not all(key) or key in seen or record.icpn != record.identifier or not record.production_admitted:
                raise DeviceCatalogIntegrityError("duplicate or unadmitted exact ICPN in shadow input")
            seen.add(key)
            qualification = None
            if qualification_registry is not None:
                qualification = qualification_registry.describe(record.vendor, record.identifier)
                level = qualification.get("catalog_level")
                if (type(level) is not int or level not in (0, 1, 2, 3)
                        or qualification.get("execution_authorized") is not False
                        or qualification.get("job_selectable") is not (level >= 2)):
                    raise DeviceCatalogIntegrityError("unsafe shadow qualification projection")
            result.append((
                key[0], key[1], _encoded(asdict(record)),
                _encoded(qualification) if qualification is not None else None,
            ))
        return result

    @staticmethod
    def _fingerprint(
        metadata: dict[str, Any],
        rows: list[tuple[str, str, str, str | None]],
    ) -> str:
        return _digest({"metadata": metadata, "rows": rows})

    @classmethod
    def _read_revision(
        cls,
        conn: sqlite3.Connection,
        revision: str,
    ) -> CatalogShadowSnapshot:
        row = conn.execute(
            "SELECT metadata_json, row_count, source_revision_sha256 "
            "FROM catalog_revisions WHERE revision_sha256 = ?", (revision,)
        ).fetchone()
        if row is None:
            raise DeviceCatalogIntegrityError("missing SQLite Catalog revision")
        metadata = json.loads(row[0])
        raw = conn.execute(
            "SELECT vendor_key, icpn_key, record_json, qualification_json "
            "FROM catalog_records WHERE revision_sha256 = ? ORDER BY ordinal",
            (revision,),
        ).fetchall()
        if len(raw) != row[1] or cls._fingerprint(metadata, raw) != revision:
            raise DeviceCatalogIntegrityError("SQLite Catalog snapshot digest/row count mismatch")
        records: list[DeviceCatalogRecord] = []
        qualifications: dict[tuple[str, str], dict[str, Any]] = {}
        seen: set[tuple[str, str]] = set()
        for vendor, icpn, record_json, qualification_json in raw:
            data = json.loads(record_json)
            data["cpu_architectures"] = tuple(data["cpu_architectures"])
            record = DeviceCatalogRecord(**data)
            key = _identity(record)
            if key != (vendor, icpn) or key in seen or record.icpn != record.identifier:
                raise DeviceCatalogIntegrityError("SQLite Catalog exact identity drift")
            seen.add(key)
            records.append(record)
            if qualification_json is not None:
                value = json.loads(qualification_json)
                if value.get("execution_authorized") is not False:
                    raise DeviceCatalogIntegrityError("SQLite Catalog must not authorize execution")
                qualifications[key] = value
        if metadata.get("source_revision_sha256") != row[2]:
            raise DeviceCatalogIntegrityError("SQLite source revision drift")
        catalog = DeviceCatalog(
            records,
            catalog_id=metadata["catalog_id"],
            catalog_version=metadata["catalog_version"],
            status=metadata["status"],
            revision_sha256=metadata["source_revision_sha256"],
            source_count=metadata["source_count"],
        )
        return CatalogShadowSnapshot(revision, catalog, qualifications)

    def import_verified_manifest(
        self,
        manifest_path: Path,
        *,
        qualification_registry: ProgrammingQualificationRegistry | None = None,
    ) -> str:
        """Atomic, idempotent *shadow-only* import of verified manifest bytes."""
        catalog = DeviceCatalog.from_manifest(Path(manifest_path))
        metadata = self._metadata(catalog)
        rows = self._prepared_rows(catalog, qualification_registry)
        revision = self._fingerprint(metadata, rows)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout = 10000")
            conn.execute("PRAGMA journal_mode = WAL")
            self._init_schema(conn)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            found = conn.execute(
                "SELECT 1 FROM catalog_revisions WHERE revision_sha256 = ?", (revision,)
            ).fetchone()
            if found is None:
                conn.execute(
                    "INSERT INTO catalog_revisions VALUES (?, ?, ?, ?)",
                    (revision, catalog.revision_sha256, _encoded(metadata), len(rows)),
                )
                conn.executemany(
                    "INSERT INTO catalog_records VALUES (?, ?, ?, ?, ?, ?)",
                    ((revision, index, *row) for index, row in enumerate(rows)),
                )
            else:
                # A matching digest cannot be treated as success if the DB was altered.
                self._read_revision(conn, revision)
            conn.execute(
                "INSERT INTO active_catalog_revision VALUES (1, ?) "
                "ON CONFLICT(singleton) DO UPDATE SET revision_sha256 = excluded.revision_sha256",
                (revision,),
            )
        return revision

    def read_active(self) -> CatalogShadowSnapshot:
        if not self.path.is_file():
            raise DeviceCatalogIntegrityError("SQLite Catalog shadow database missing")
        try:
            with sqlite3.connect(f"file:{self.path.resolve().as_posix()}?mode=ro", uri=True) as conn:
                conn.execute("PRAGMA query_only = ON")
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version != SCHEMA_VERSION:
                    raise DeviceCatalogIntegrityError("unsupported SQLite Catalog schema")
                row = conn.execute(
                    "SELECT revision_sha256 FROM active_catalog_revision WHERE singleton = 1"
                ).fetchone()
                if row is None:
                    raise DeviceCatalogIntegrityError("SQLite Catalog has no published shadow revision")
                return self._read_revision(conn, row[0])
        except (sqlite3.DatabaseError, ValueError, KeyError, TypeError) as exc:
            raise DeviceCatalogIntegrityError("SQLite Catalog shadow integrity failure") from exc

    def verify_parity(
        self, manifest_path: Path, *, qualification_registry: ProgrammingQualificationRegistry | None = None
    ) -> CatalogShadowSnapshot:
        """Compare full canonical rows, source lock, qualification and representative search."""
        reference = DeviceCatalog.from_manifest(Path(manifest_path))
        snapshot = self.read_active()
        if reference.records != snapshot.catalog.records or reference.metadata != snapshot.catalog.metadata:
            raise DeviceCatalogIntegrityError("SQLite and canonical manifest full-record parity mismatch")
        expected = self._prepared_rows(reference, qualification_registry)
        stored = [
            (_identity(r)[0], _identity(r)[1], _encoded(asdict(r)),
             _encoded(snapshot.qualifications[_identity(r)]) if _identity(r) in snapshot.qualifications else None)
            for r in snapshot.catalog.records
        ]
        if expected != stored or snapshot.revision_sha256 != self._fingerprint(self._metadata(reference), expected):
            raise DeviceCatalogIntegrityError("SQLite qualification source/projection parity mismatch")
        return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline SQLite shadow import; never switches Manager/PPU")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=default_catalog_manifest_path())
    parser.add_argument("--with-qualification", action="store_true")
    args = parser.parse_args()
    qualifications = None
    if args.with_qualification:
        from .programming_qualification import get_default_programming_qualification_registry
        qualifications = get_default_programming_qualification_registry()
    repository = CatalogSqliteShadowRepository(args.db)
    revision = repository.import_verified_manifest(args.manifest, qualification_registry=qualifications)
    snapshot = repository.verify_parity(args.manifest, qualification_registry=qualifications)
    print(_encoded({
        "result": "SHADOW_PARITY_PASS",
        "revision_sha256": revision,
        "exact_icpn_count": snapshot.size,
        "qualification_count": len(snapshot.qualifications),
        "runtime_cutover": False,
        "physical_validation": "NOT_RUN",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
