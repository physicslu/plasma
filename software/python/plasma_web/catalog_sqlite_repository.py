"""Manager-owned SQLite Catalog snapshots and data-only publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, replace
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


SCHEMA_VERSION = 2


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
        if version not in (0, 1, SCHEMA_VERSION):
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
            CREATE TABLE IF NOT EXISTS catalog_staging (
                stage_id TEXT PRIMARY KEY,
                parent_revision TEXT NOT NULL REFERENCES catalog_revisions(revision_sha256),
                actor TEXT NOT NULL,
                changes_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS catalog_audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                predecessor TEXT,
                revision_sha256 TEXT,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS controller_overlays (
                namespace TEXT NOT NULL,
                vendor_key TEXT NOT NULL,
                icpn_key TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                PRIMARY KEY(namespace, vendor_key, icpn_key)
            );
        """)
        if version < SCHEMA_VERSION:
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
            active = conn.execute("SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1").fetchone()
            if (active is not None and conn.execute(
                "SELECT 1 FROM catalog_audit_events WHERE action='PUBLISH' LIMIT 1"
            ).fetchone() is not None):
                if active[0] != revision:
                    raise DeviceCatalogIntegrityError("manifest import cannot replace published active revision")
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
                if version not in (1, SCHEMA_VERSION):
                    raise DeviceCatalogIntegrityError("unsupported SQLite Catalog schema")
                row = conn.execute(
                    "SELECT revision_sha256 FROM active_catalog_revision WHERE singleton = 1"
                ).fetchone()
                if row is None:
                    raise DeviceCatalogIntegrityError("SQLite Catalog has no published shadow revision")
                return self._read_revision(conn, row[0])
        except (sqlite3.DatabaseError, ValueError, KeyError, TypeError) as exc:
            raise DeviceCatalogIntegrityError("SQLite Catalog shadow integrity failure") from exc

    @staticmethod
    def _validate_publication(record: DeviceCatalogRecord, q: dict[str, Any]) -> None:
        """Validate source authority and the published, non-executable level projection."""
        if (not record.production_admitted or record.identifier_kind != "manufacturer_part_number"
                or not record.vendor or not record.identifier or not record.source_authority
                or not record.source_reference or not record.source_type):
            raise DeviceCatalogIntegrityError("exact ICPN or source authority missing")
        level = q.get("catalog_level")
        states = ("DISCOVERED", "PROGRAMMING_CANDIDATE", "PROGRAMMABLE", "PLASMA_VERIFIED")
        if (type(level) is not int or level not in range(4)
                or q.get("catalog_level_state") != states[level]
                or q.get("identity_state") != "IDENTIFIED"
                or q.get("execution_authorized") is not False
                or q.get("job_selectable") is not (level >= 2)
                or q.get("selector_visible") is not (level >= 1)
                or q.get("installed_runtime_attested") is not False
                or q.get("hardware_runtime_ready") is not False):
            raise DeviceCatalogIntegrityError("unsafe Catalog qualification projection")
        if level >= 1 and not (record.target_config or q.get("route_evidence")):
            raise DeviceCatalogIntegrityError("L1 requires a source-backed programming route")
        if level == 1 and not record.target_config and q.get("route_evidence") != record.source_reference:
            raise DeviceCatalogIntegrityError("L1 route evidence must match the admitted source")
        if level < 2:
            if (q.get("state") == "SUPPORTED" or q.get("provider") or q.get("programming")
                    or q.get("ppu_ready") or q.get("socket_ready") or q.get("verified_configurations")):
                raise DeviceCatalogIntegrityError("unqualified L1/L0 support claim")
            return
        provider, program = q.get("provider"), q.get("programming")
        evidence = q.get("publication_evidence")
        if (q.get("state") != "SUPPORTED" or not q.get("reviewed")
                or not isinstance(provider, dict) or not isinstance(program, dict)
                or not isinstance(evidence, dict)
                or evidence.get("exact_icpn") != record.identifier
                or evidence.get("manufacturer") != record.vendor
                or evidence.get("source_authority") != record.source_authority
                or not evidence.get("source_reference")
                or not isinstance(evidence.get("source_sha256"), str)
                or len(evidence["source_sha256"]) != 64
                or any(ch not in "0123456789abcdef" for ch in evidence["source_sha256"])
                or provider.get("provider_id") != evidence.get("provider_id")
                or provider.get("version") != evidence.get("provider_version")
                or not provider.get("source_commit")
                or provider.get("target_config") != record.target_config
                or not provider.get("flash_driver")
                or program.get("programming_profile_id") != evidence.get("profile_id")):
            raise DeviceCatalogIntegrityError("L2 lacks exact pinned Provider/Profile evidence")
        operations = q.get("operations")
        if not isinstance(operations, dict) or any(
            not isinstance(operations.get(op), dict) or operations[op].get("state") != "SUPPORTED"
            for op in ("erase", "program", "read", "verify")
        ):
            raise DeviceCatalogIntegrityError("L2 operation scope incomplete")
        geometry = program.get("flash_geometry")
        if not isinstance(geometry, dict) or not program.get("memory_geometry_profile_id"):
            raise DeviceCatalogIntegrityError("L2 geometry/Profile missing")
        try:
            size = geometry["main_flash_size_bytes"]
            pages = geometry["page_count"]
            erase = geometry["erase_unit_bytes"]
            write = geometry["program_unit_bytes"]
            start = int(geometry["main_flash_start"], 0)
            valid = all(type(n) is int and n > 0 for n in (size, pages, erase, write))
            valid = valid and size == pages * erase and erase % write == 0 and start >= 0
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise DeviceCatalogIntegrityError("invalid L2 flash geometry")
        if level == 3 and not (q.get("ppu_ready") or q.get("socket_ready")):
            raise DeviceCatalogIntegrityError("L3 physical evidence missing")

    def stage_revision(self, changes: list[dict[str, Any]], *, actor: str) -> str:
        """Stage exact records against the current active revision; staging is never public."""
        if not actor.strip() or not changes:
            raise DeviceCatalogIntegrityError("publisher actor and changes required")
        seen: set[tuple[str, str]] = set()
        for change in changes:
            try:
                data = dict(change["record"])
                data["cpu_architectures"] = tuple(data["cpu_architectures"])
                record = DeviceCatalogRecord(**data)
                q = change["qualification"]
            except (KeyError, TypeError, ValueError) as exc:
                raise DeviceCatalogIntegrityError("malformed staged Catalog record") from exc
            if not isinstance(q, dict):
                raise DeviceCatalogIntegrityError("malformed staged qualification")
            self._validate_publication(record, q)
            if q.get("catalog_level", 0) >= 2:
                evidence = q["publication_evidence"]
                path = Path(evidence.get("source_path", ""))
                if (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != evidence["source_sha256"]):
                    raise DeviceCatalogIntegrityError("L2 documentary evidence bytes unavailable or mismatched")
            key = _identity(record)
            if key in seen:
                raise DeviceCatalogIntegrityError("duplicate exact ICPN in staging")
            seen.add(key)
        stage_id = _digest(changes)
        with sqlite3.connect(self.path, timeout=10) as conn:
            self._init_schema(conn)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            parent = conn.execute("SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1").fetchone()
            if parent is None:
                raise DeviceCatalogIntegrityError("no active Catalog revision")
            self._read_revision(conn, parent[0])
            conn.execute("INSERT OR REPLACE INTO catalog_staging VALUES (?, ?, ?, ?)",
                         (stage_id, parent[0], actor, _encoded(changes)))
            conn.execute("INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) VALUES (?,?,?,?,?)",
                         ("STAGE", actor, parent[0], stage_id, "validated input"))
        return stage_id

    def publish_staged(self, stage_id: str, *, actor: str) -> str:
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            stage = conn.execute("SELECT parent_revision,actor,changes_json FROM catalog_staging WHERE stage_id=?", (stage_id,)).fetchone()
            active = conn.execute("SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1").fetchone()
            if stage is None and active is not None:
                prior = conn.execute(
                    "SELECT revision_sha256 FROM catalog_audit_events WHERE action='PUBLISH' AND actor=? AND detail=? ORDER BY event_id DESC LIMIT 1",
                    (actor, stage_id),
                ).fetchone()
                if prior is not None and prior[0] == active[0]:
                    return active[0]
            if stage is None or active is None or stage[0] != active[0] or stage[1] != actor:
                raise DeviceCatalogIntegrityError("staging missing, stale or actor mismatch")
            parent = self._read_revision(conn, active[0])
            changes = json.loads(stage[2])
            source_revision = _digest({"parent": active[0], "stage": stage_id})
            records = {_identity(row): row for row in parent.catalog.records}
            qualifications = dict(parent.qualifications)
            known_providers = {
                (p.get("provider_id"), p.get("version"), p.get("source_commit"), p.get("target_config"),
                 q.get("programming", {}).get("programming_profile_id"))
                for q in qualifications.values() if isinstance(q.get("provider"), dict)
                for p in [q["provider"]] if isinstance(q.get("programming"), dict)
            }
            for change in changes:
                data = dict(change["record"])
                data["cpu_architectures"] = tuple(data["cpu_architectures"])
                record = DeviceCatalogRecord(**data)
                q = dict(change["qualification"])
                self._validate_publication(record, q)
                if q["catalog_level"] >= 2:
                    evidence = q["publication_evidence"]
                    path = Path(evidence.get("source_path", ""))
                    if (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != evidence["source_sha256"]):
                        raise DeviceCatalogIntegrityError("L2 documentary evidence bytes unavailable or mismatched")
                    p = q["provider"]
                    lock = (p["provider_id"], p["version"], p["source_commit"], p["target_config"],
                            q["programming"]["programming_profile_id"])
                    if lock not in known_providers:
                        raise DeviceCatalogIntegrityError("unknown Provider release or Profile lock")
                key = _identity(record)
                old = qualifications.get(key)
                if old and old.get("catalog_level") == 3 and q != old:
                    raise DeviceCatalogIntegrityError("L3 revision requires separately authorized revocation")
                # This marker prevents legacy display enrichers from claiming authority
                # over data they have never reviewed.
                if q["catalog_level"] >= 2:
                    q["publication_evidence"] = {
                        field: value for field, value in q["publication_evidence"].items()
                        if field != "source_path"
                    }
                q["data_only_publication"] = True
                records[key], qualifications[key] = replace(
                    record, catalog_revision_sha256=source_revision
                ), q
            ordered = sorted(records.values(), key=lambda r: _identity(r))
            catalog = DeviceCatalog(ordered, catalog_id=parent.catalog.catalog_id,
                                    catalog_version=parent.catalog.catalog_version,
                                    status=parent.catalog.status,
                                    revision_sha256=source_revision,
                                    source_count=parent.catalog.source_count)
            rows = [(key[0], key[1], _encoded(asdict(row)), _encoded(qualifications[key]))
                    for row in ordered for key in [_identity(row)]]
            metadata = self._metadata(catalog)
            revision = self._fingerprint(metadata, rows)
            if conn.execute("SELECT 1 FROM catalog_revisions WHERE revision_sha256=?", (revision,)).fetchone() is None:
                conn.execute("INSERT INTO catalog_revisions VALUES (?,?,?,?)",
                             (revision, catalog.revision_sha256, _encoded(metadata), len(rows)))
                conn.executemany("INSERT INTO catalog_records VALUES (?,?,?,?,?,?)",
                                 ((revision, i, *row) for i, row in enumerate(rows)))
            self._read_revision(conn, revision)
            conn.execute("UPDATE active_catalog_revision SET revision_sha256=? WHERE singleton=1", (revision,))
            conn.execute("DELETE FROM catalog_staging WHERE stage_id=?", (stage_id,))
            conn.execute("INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) VALUES (?,?,?,?,?)",
                         ("PUBLISH", actor, active[0], revision, stage_id))
        return revision

    def rollback(self, revision: str, *, actor: str) -> None:
        if not actor.strip():
            raise DeviceCatalogIntegrityError("rollback actor required")
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute("SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1").fetchone()
            if previous is None:
                raise DeviceCatalogIntegrityError("no active Catalog revision")
            self._read_revision(conn, revision)
            conn.execute("UPDATE active_catalog_revision SET revision_sha256=? WHERE singleton=1", (revision,))
            conn.execute("INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) VALUES (?,?,?,?,?)",
                         ("ROLLBACK", actor, previous[0], revision, "validated snapshot"))

    def put_local_profile(self, namespace: str, manufacturer: str, exact_icpn: str,
                          profile: dict[str, Any], *, actor: str) -> None:
        if not all(isinstance(x, str) and x.strip() for x in (namespace, manufacturer, exact_icpn, actor)):
            raise DeviceCatalogIntegrityError("local namespace, identity and actor required")
        if (not isinstance(profile, dict) or not profile.get("profile_id")
                or profile.get("official") is not False or profile.get("execution_authorized") is not False
                or profile.get("catalog_level") in (2, 3)):
            raise DeviceCatalogIntegrityError("local Profile cannot claim official L2 or execution")
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR REPLACE INTO controller_overlays VALUES (?,?,?,?)",
                         (namespace, manufacturer.casefold(), exact_icpn.casefold(), _encoded(profile)))
            conn.execute("INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) VALUES (?,?,?,?,?)",
                         ("LOCAL_PROFILE", actor, None, None, namespace))

    def get_local_profile(self, namespace: str, manufacturer: str, exact_icpn: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute("SELECT profile_json FROM controller_overlays WHERE namespace=? AND vendor_key=? AND icpn_key=?",
                               (namespace, manufacturer.casefold(), exact_icpn.casefold())).fetchone()
        return json.loads(row[0]) if row else None

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
    parser = argparse.ArgumentParser(description="Manager-owned SQLite Catalog import and data-only publisher")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=default_catalog_manifest_path())
    parser.add_argument("--with-qualification", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--stage-file", type=Path, help="JSON list of exact record/qualification changes")
    action.add_argument("--publish-stage", help="validated stage digest")
    action.add_argument("--rollback", help="previous published revision digest")
    action.add_argument("--local-file", type=Path, help="JSON local Profile with namespace/manufacturer/icpn/profile")
    parser.add_argument("--actor", help="authorized publisher identity (required for writes)")
    args = parser.parse_args()
    repository = CatalogSqliteShadowRepository(args.db)
    if args.stage_file or args.publish_stage or args.rollback or args.local_file:
        if not args.actor:
            parser.error("--actor is required for publication and local writes")
        if args.stage_file:
            stage_id = repository.stage_revision(json.loads(args.stage_file.read_text(encoding="utf-8")), actor=args.actor)
            result = {"result": "STAGED", "stage_id": stage_id, "active_revision": repository.read_active().revision_sha256}
        elif args.publish_stage:
            revision = repository.publish_staged(args.publish_stage, actor=args.actor)
            result = {"result": "PUBLISHED", "revision_sha256": revision}
        elif args.rollback:
            repository.rollback(args.rollback, actor=args.actor)
            result = {"result": "ROLLED_BACK", "revision_sha256": args.rollback}
        else:
            local = json.loads(args.local_file.read_text(encoding="utf-8"))
            repository.put_local_profile(local["namespace"], local["manufacturer"],
                                         local["exact_icpn"], local["profile"], actor=args.actor)
            result = {"result": "LOCAL_PROFILE_STORED", "namespace": local["namespace"]}
        print(_encoded(result))
        return 0
    qualifications = None
    if args.with_qualification:
        from .programming_qualification import get_default_programming_qualification_registry
        qualifications = get_default_programming_qualification_registry()
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
