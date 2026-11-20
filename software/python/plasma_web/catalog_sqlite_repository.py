"""Manager-owned SQLite Catalog snapshots and data-only publication."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sqlite3
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, TYPE_CHECKING
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .device_catalog import (
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    DeviceCatalogRecord,
    default_catalog_manifest_path,
)

if TYPE_CHECKING:
    from .programming_qualification import ProgrammingQualificationRegistry


SCHEMA_VERSION = 3


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
        if version not in (0, 1, 2, SCHEMA_VERSION):
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
            CREATE TABLE IF NOT EXISTS catalog_evidence (
                evidence_id TEXT PRIMARY KEY,
                source_authority TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                source_revision TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                verification_status TEXT NOT NULL CHECK (verification_status = 'VERIFIED'),
                content_location TEXT NOT NULL,
                UNIQUE(source_authority, source_reference, source_revision)
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
                if version not in (1, 2, SCHEMA_VERSION):
                    raise DeviceCatalogIntegrityError("unsupported SQLite Catalog schema")
                row = conn.execute(
                    "SELECT revision_sha256 FROM active_catalog_revision WHERE singleton = 1"
                ).fetchone()
                if row is None:
                    raise DeviceCatalogIntegrityError("SQLite Catalog has no published shadow revision")
                snapshot = self._read_revision(conn, row[0])
                self._verify_snapshot_evidence(snapshot)
                return snapshot
        except (sqlite3.DatabaseError, ValueError, KeyError, TypeError) as exc:
            raise DeviceCatalogIntegrityError("SQLite Catalog shadow integrity failure") from exc

    def _evidence_file(self, digest: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise DeviceCatalogIntegrityError("invalid Evidence content digest")
        return Path(f"{self.path}.evidence") / "sha256" / digest[:2] / digest

    def _read_evidence(self, evidence_id: str) -> tuple[tuple[str, str, str, str], bytes]:
        if not isinstance(evidence_id, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence_id):
            raise DeviceCatalogIntegrityError("Evidence Revision missing")
        with sqlite3.connect(f"file:{self.path.resolve().as_posix()}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT source_authority,source_reference,source_revision,content_sha256,"
                "verification_status,content_location FROM catalog_evidence WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
        location = f"sha256/{row[3][:2]}/{row[3]}" if row is not None else None
        if row is None or row[4] != "VERIFIED" or row[5] != location:
            raise DeviceCatalogIntegrityError("Evidence Revision missing or invalid")
        try:
            content = self._evidence_file(row[3]).read_bytes()
        except OSError as exc:
            raise DeviceCatalogIntegrityError("Evidence content missing") from exc
        if hashlib.sha256(content).hexdigest() != row[3]:
            raise DeviceCatalogIntegrityError("Evidence content digest mismatch")
        return (row[0], row[1], row[2], row[3]), content

    def _store_evidence(self, authority: str, reference: str, revision: str, content: bytes,
                        *, actor: str = "publisher") -> str:
        """Durable CAS write precedes its SQLite reference; orphan bytes are reusable."""
        if not all(isinstance(x, str) and x.strip() for x in (authority, reference, revision)):
            raise DeviceCatalogIntegrityError("Evidence source identity/revision required")
        digest = hashlib.sha256(content).hexdigest()
        evidence_id = _digest([authority, reference, revision, digest])
        with sqlite3.connect(self.path, timeout=10) as conn:
            self._init_schema(conn)
            existing = conn.execute(
                "SELECT evidence_id,content_sha256 FROM catalog_evidence "
                "WHERE source_authority=? AND source_reference=? AND source_revision=?",
                (authority, reference, revision),
            ).fetchone()
        if existing is not None:
            if existing != (evidence_id, digest):
                raise DeviceCatalogIntegrityError("Evidence source revision is immutable")
            self._read_evidence(evidence_id)
            return evidence_id
        target = self._evidence_file(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".acquire-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise DeviceCatalogIntegrityError("Evidence content digest mismatch")
            else:
                os.replace(temporary, target)
                directory_fd = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            with sqlite3.connect(self.path, timeout=10) as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT evidence_id,content_sha256 FROM catalog_evidence "
                    "WHERE source_authority=? AND source_reference=? AND source_revision=?",
                    (authority, reference, revision),
                ).fetchone()
                if row is None:
                    conn.execute("INSERT INTO catalog_evidence "
                                 "(evidence_id,source_authority,source_reference,source_revision,"
                                 "content_sha256,verification_status,content_location) "
                                 "VALUES (?,?,?,?,?,'VERIFIED',?)",
                                 (evidence_id, authority, reference, revision, digest,
                                  f"sha256/{digest[:2]}/{digest}"))
                    conn.execute("INSERT INTO catalog_audit_events"
                                 "(action,actor,revision_sha256,detail) VALUES (?,?,?,?)",
                                 ("ACQUIRE_EVIDENCE", actor, evidence_id, reference))
                elif row != (evidence_id, digest):
                    raise DeviceCatalogIntegrityError("Evidence source revision is immutable")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self._read_evidence(evidence_id)
        return evidence_id

    def acquire_exact_evidence(self, record: DeviceCatalogRecord, *, kind: str,
                               source_revision: str, actor: str = "publisher") -> str:
        """Acquire and authenticate one official source revision; repeat calls stay offline."""
        from .openocd_software_qualification import (
            APPLICABILITY_REL, get_default_openocd_software_qualification_registry, _git_blob_sha1,
        )
        if not isinstance(source_revision, str) or not source_revision.strip():
            raise DeviceCatalogIntegrityError("Evidence source revision required")
        provider = get_default_openocd_software_qualification_registry()
        if provider is None or record.vendor != "STMicroelectronics":
            raise DeviceCatalogIntegrityError("official Exact source authority unsupported")
        url = ("https://www.st.com/en/microcontrollers-microprocessors/"
               f"{record.base_device.lower()}.html")
        if kind == "manufacturer_https":
            reference = url
            authority = "STMicroelectronics HTTPS"
        elif kind == "locked_production_identity":
            applicability = json.loads((provider._root / APPLICABILITY_REL).read_text(encoding="utf-8"))
            lock = applicability["manufacturer_authority"]["production_exact_identity"]
            reference = lock["path"]
            authority = "STMicroelectronics production identity lock"
            if source_revision != lock["git_blob_sha1"]:
                raise DeviceCatalogIntegrityError("official Exact identity lock mismatch")
        else:
            raise DeviceCatalogIntegrityError("official Exact source kind unsupported")
        with sqlite3.connect(self.path, timeout=10) as conn:
            self._init_schema(conn)
            row = conn.execute("SELECT evidence_id FROM catalog_evidence WHERE "
                               "source_authority=? AND source_reference=? AND source_revision=?",
                               (authority, reference, source_revision)).fetchone()
        if row is not None:
            metadata, content = self._read_evidence(row[0])
            self._validate_exact_content(record, kind, content, source_revision)
            return row[0]
        content = (self._fetch_official_exact_source(url) if kind == "manufacturer_https"
                   else (provider._root / reference).read_bytes())
        self._validate_exact_content(record, kind, content, source_revision)
        return self._store_evidence(authority, reference, source_revision, content, actor=actor)

    @staticmethod
    def _validate_exact_content(record: DeviceCatalogRecord, kind: str, content: bytes,
                                source_revision: str) -> None:
        if kind == "manufacturer_https":
            source_text = html.unescape(content.decode("utf-8", errors="replace")).upper()
            if (re.search(r"<TITLE[^>]*>[^<]*" + re.escape(record.base_device), source_text) is None
                    or re.search(r"PART[\s_-]*NUMBER", source_text) is None
                    or re.search(r"(?<![A-Z0-9])" + re.escape(record.identifier) + r"(?![A-Z0-9])",
                                 source_text) is None):
                raise DeviceCatalogIntegrityError("L2 official Exact source bytes or identity mismatch")
        elif kind == "locked_production_identity":
            from .openocd_software_qualification import _git_blob_sha1
            try:
                rows = [row for row in csv.DictReader(io.StringIO(content.decode("utf-8")))
                        if row["icpn"] == record.identifier]
            except (UnicodeError, ValueError, KeyError) as exc:
                raise DeviceCatalogIntegrityError("L2 official Exact identity source unavailable") from exc
            expected = {"manufacturer": record.vendor, "icpn": record.identifier,
                        "family": record.family, "series": record.subfamily,
                        "base_device": record.base_device, "package": record.package,
                        "pin_count": record.pin_count, "flash_size": record.flash_size,
                        "temperature_grade": record.temperature_grade,
                        "option_suffix": record.option_suffix or "",
                        "openocd_target_config": record.target_config,
                        "source_type": record.source_type,
                        "source_reference": record.source_reference,
                        "source_authority": record.source_authority,
                        "verification_status": record.verification_status}
            if (_git_blob_sha1(content) != source_revision or len(rows) != 1
                    or any(rows[0].get(key) != value for key, value in expected.items())):
                raise DeviceCatalogIntegrityError("L2 official Exact identity source drift")

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
                or evidence.get("source_reference") != record.source_reference
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
        if level == 2 and (q.get("ppu_ready") or q.get("socket_ready")
                           or q.get("verified_configurations") or q.get("family_ready")
                           or q.get("physical_programming_qualified")
                           or q.get("ppu_readiness_source")):
            raise DeviceCatalogIntegrityError("L2 cannot claim physical qualification")

    def _validate_l2_applicability(self, record: DeviceCatalogRecord, q: dict[str, Any],
                                   reviewed: dict[str, Any]) -> None:
        """Bind an exact part to source-validated provider semantics and manufacturer facts."""
        from .programming_qualification import get_default_programming_qualification_registry

        registry = get_default_programming_qualification_registry()
        canonical = registry._catalog.resolve(record.vendor, record.identifier)
        if canonical is not None and any(
            getattr(record, field) != getattr(canonical, field)
            for field in ("vendor", "identifier", "family", "subfamily", "plasma_series",
                          "package", "pin_count", "flash_size", "temperature_grade",
                          "option_suffix", "base_device", "target_config",
                          "source_authority", "source_reference", "source_type")
        ):
            raise DeviceCatalogIntegrityError("L2 exact ICPN/source applicability is not admitted")
        admitted = registry.describe(record.vendor, record.identifier)
        if admitted.get("state") == "SUPPORTED" and admitted.get("catalog_level") in (2, 3):
            if (canonical is None
                    or any(q.get(field) != admitted.get(field)
                           for field in ("schema_version", "registry_id", "provider", "programming",
                                         "operations", "qualification_gaps"))
                    or (q.get("catalog_level") == 3
                        and any(q.get(field) != admitted.get(field) for field in
                                ("verified_configurations", "ppu_ready", "socket_ready",
                                 "ppu_readiness_source", "family_ready")))):
                raise DeviceCatalogIntegrityError("L2 Provider/Profile/geometry/operations lack exact applicability")
            return
        self._validate_data_only_l2(record, q, reviewed)

    @staticmethod
    def _fetch_official_exact_source(url: str) -> bytes:
        """Acquire official Exact identity over verified HTTPS, including redirect scope."""
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "www.st.com"
                or parsed.query or parsed.fragment or parsed.username
                or not re.fullmatch(r"/en/microcontrollers-microprocessors/stm32f103[a-z0-9]+\.html",
                                    parsed.path)):
            raise DeviceCatalogIntegrityError("official Exact source URL is outside admitted manufacturer scope")
        try:
            request = Request(url, headers={"User-Agent": "PLASMA-Catalog-Publisher/1.0"})
            with urlopen(request, timeout=15) as response:
                final = urlsplit(response.geturl())
                if final.scheme != "https" or final.netloc != parsed.netloc or final.path != parsed.path:
                    raise DeviceCatalogIntegrityError("official Exact source redirected outside manufacturer scope")
                content = response.read(5_000_001)
        except (OSError, ValueError) as exc:
            raise DeviceCatalogIntegrityError("official Exact source could not be acquired") from exc
        if not content or len(content) > 5_000_000:
            raise DeviceCatalogIntegrityError("official Exact source has invalid size")
        return content

    def _validate_data_only_l2(self, record: DeviceCatalogRecord, q: dict[str, Any],
                               reviewed: dict[str, Any]) -> None:
        """Data-only medium-density applicability; no exact static qualification allowlist."""
        from .openocd_software_qualification import (
            APPLICABILITY_REL, get_default_openocd_software_qualification_registry,
            _git_blob_sha1,
        )

        provider = get_default_openocd_software_qualification_registry()
        if provider is None or q.get("catalog_level") != 2:
            raise DeviceCatalogIntegrityError("L2 requires a source-validated Provider applicability")
        profile_id = "stm32f1-medium-density-flash-v0"
        group = provider._programming_groups_by_profile[profile_id]
        if (group.get("manufacturer") != "STMicroelectronics"
                or group.get("series") != "STM32F103"
                or group.get("density_class") != "medium"):
            raise DeviceCatalogIntegrityError("L2 Provider programming group drift")
        root = provider._root
        try:
            applicability = json.loads((root / APPLICABILITY_REL).read_text(encoding="utf-8"))
            ordering_lock = applicability["manufacturer_authority"]["ordering"]
            ordering_blob = ordering_lock["git_blob_sha1"]
            ordering_path = root / ordering_lock["path"]
            ordering_bytes = ordering_path.read_bytes()
            authority = json.loads(ordering_bytes)
            bands = authority["records"]["STM32F103"]["bands"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise DeviceCatalogIntegrityError("L2 manufacturer applicability source unavailable") from exc
        if _git_blob_sha1(ordering_bytes) != ordering_blob:
            raise DeviceCatalogIntegrityError("L2 manufacturer ordering source lock drift")
        band = next((item for item in bands if item["name"] == "medium"), None)
        match = re.fullmatch(r"STM32F103([TCRV])([8B])([HTU])([67])(TR)?", record.identifier)
        if band is None or match is None:
            raise DeviceCatalogIntegrityError("L2 Exact ICPN is outside reviewed ordering applicability")
        pin_code, flash_code, package_code, temperature_code, tail = match.groups()
        flash_kib = band["flash_kib"].get(flash_code)
        package = band["package_pin_overrides"].get(f"{package_code}/{pin_code}",
                                                   band["package"].get(package_code))
        if (record.vendor != "STMicroelectronics" or record.family != "STM32F1"
                or record.subfamily != "STM32F103"
                or record.base_device != f"STM32F103{pin_code}{flash_code}"
                or record.pin_count != str(band["pin_count"].get(pin_code))
                or record.package != package or record.flash_size != f"{flash_kib} KiB"
                or record.temperature_grade != band["temperature_c"].get(temperature_code)
                or (record.option_suffix or "") != (tail or "")
                or record.source_authority != "STMicroelectronics official"
                or record.source_reference != band["source_url"]
                or record.target_config != provider.provider["target_config"]):
            raise DeviceCatalogIntegrityError("L2 manufacturer identity/geometry conflicts with ordering authority")
        # The previous non-LQFP review explicitly did not claim VFQFPN36. This
        # independently reviewed package route is required before the shared
        # medium-density Provider group can apply to that package.
        if (pin_code, package_code, record.pin_count, record.package) != (
            "T", "U", "36", "UFQFPN"
        ):
            raise DeviceCatalogIntegrityError("L2 package route lacks data-only applicability review")
        package_route = {
            "package": "VFQFPN36",
            "transport": "SWD",
            "swdio": {"signal": "PA13", "pin": 25},
            "swclk": {"signal": "PA14", "pin": 28},
            "source_document": "DS5319 Rev 20",
            "source_locator": "Table 5, VFQFPN36 pin definitions",
            "source_sha256": group["manufacturer_evidence"]["source_lock"]["st_ds5319_rev20"],
        }
        exact_source = reviewed.get("official_exact_source")
        expected_url = ("https://www.st.com/en/microcontrollers-microprocessors/"
                        f"{record.base_device.lower()}.html")
        if not isinstance(exact_source, dict):
            raise DeviceCatalogIntegrityError("L2 official Exact source missing")
        if exact_source.get("kind") == "locked_production_identity":
            identity_lock = applicability["manufacturer_authority"]["production_exact_identity"]
            identity_reference = f"{identity_lock['path']}#{record.identifier}"
            if exact_source != {
                "kind": "locked_production_identity",
                "path": identity_lock["path"],
                "git_blob_sha1": identity_lock["git_blob_sha1"],
                "exact_icpn": record.identifier,
                "evidence_id": exact_source.get("evidence_id"),
            }:
                raise DeviceCatalogIntegrityError("L2 official Exact identity lock mismatch")
            metadata, identity_bytes = self._read_evidence(exact_source.get("evidence_id"))
            if metadata[:3] != ("STMicroelectronics production identity lock", identity_lock["path"],
                                identity_lock["git_blob_sha1"]):
                raise DeviceCatalogIntegrityError("L2 official Exact identity lock mismatch")
            self._validate_exact_content(record, "locked_production_identity", identity_bytes, metadata[2])
        elif exact_source.get("kind") == "manufacturer_https":
            identity_reference = f"{expected_url}#{record.identifier}"
            if (exact_source.get("url") != expected_url
                    or not isinstance(exact_source.get("sha256"), str)):
                raise DeviceCatalogIntegrityError("L2 official Exact source missing")
            metadata, source_bytes = self._read_evidence(exact_source.get("evidence_id"))
            if (metadata[0] != "STMicroelectronics HTTPS" or metadata[1] != expected_url
                    or metadata[3] != exact_source["sha256"]):
                raise DeviceCatalogIntegrityError("L2 official Exact source bytes or identity mismatch")
            self._validate_exact_content(record, "manufacturer_https", source_bytes, metadata[2])
        else:
            raise DeviceCatalogIntegrityError("L2 official Exact source kind unsupported")
        geometry_id = q["programming"].get("memory_geometry_profile_id")
        if not isinstance(geometry_id, str) or not re.fullmatch(
            rf"{record.base_device.lower()}-{flash_kib}k-catalog-v[1-9][0-9]*", geometry_id
        ):
            raise DeviceCatalogIntegrityError("L2 Geometry revision is not scoped to this base device")
        reference = provider.describe("STMicroelectronics", "STM32F103C8T6")
        expected_programming = dict(reference["programming"])
        expected_programming["memory_geometry_profile_id"] = geometry_id
        expected_geometry = dict(expected_programming["flash_geometry"])
        expected_geometry["main_flash_size_bytes"] = flash_kib * 1024
        expected_geometry["page_count"] = flash_kib * 1024 // group["shared_flash_geometry"]["erase_unit_bytes"]
        expected_programming["flash_geometry"] = expected_geometry
        expected_applicability = {
            "base_device": record.base_device,
            "density_class": band["name"],
            "ordering_authority_id": authority["authority_id"],
            "ordering_source_blob": ordering_blob,
            "provider_source_lock_id": provider.source_lock_id,
            "programming_group_id": group["group_id"],
            "geometry_id": geometry_id,
            "package_route": package_route,
        }
        expected_references = {
            "identity": identity_reference,
            "route": f"{provider.source_lock_id}#{provider.provider['target_config']}",
            "geometry": (f"{band['source_url']}#{band['document']};"
                         f"st_pm0075_rev2:{group['manufacturer_evidence']['source_lock']['st_pm0075_rev2']}"),
            "operations": f"{provider.qualification_id}#{group['group_id']}",
        }
        if (q.get("schema_version") != "2.0.0"
                or q.get("registry_id") != "catalog-data-only-openocd-stm32f103-medium-v1"
                or q.get("provider") != reference["provider"]
                or q.get("programming") != expected_programming
                or q.get("operations") != reference["operations"]
                or q.get("qualification_gaps") != []
                or reviewed.get("applicability") != expected_applicability
                or reviewed.get("fact_references") != expected_references):
            raise DeviceCatalogIntegrityError("L2 Provider/Profile/geometry/operations lack exact applicability")

    def _validate_l2_source(self, record: DeviceCatalogRecord, q: dict[str, Any]) -> dict[str, Any]:
        """Bind reviewed documentary facts to the exact published qualification."""
        evidence = q["publication_evidence"]
        source_path = evidence.get("source_path")
        evidence_id = evidence.get("reviewed_evidence_id")
        if not source_path and not evidence_id:
            raise DeviceCatalogIntegrityError("L2 reviewed evidence file missing")
        try:
            if evidence_id:
                metadata, source_bytes = self._read_evidence(evidence_id)
                if metadata[:2] != ("PLASMA reviewed qualification", record.identifier):
                    raise DeviceCatalogIntegrityError("L2 reviewed Evidence identity mismatch")
            else:
                source_bytes = Path(source_path).read_bytes()
            if hashlib.sha256(source_bytes).hexdigest() != evidence["source_sha256"]:
                raise DeviceCatalogIntegrityError("L2 documentary evidence bytes unavailable or mismatched")
            reviewed = json.loads(source_bytes)
        except (OSError, ValueError, TypeError, UnicodeDecodeError) as exc:
            raise DeviceCatalogIntegrityError("L2 reviewed evidence file unavailable or malformed") from exc
        provider, programming = q["provider"], q["programming"]
        expected_provider = {key: provider.get(key) for key in (
            "provider_id", "version", "source_commit", "target_config", "flash_driver"
        )}
        expected_profile = {
            "programming_profile_id": programming.get("programming_profile_id"),
            "memory_geometry_profile_id": programming.get("memory_geometry_profile_id"),
            "flash_geometry": programming.get("flash_geometry"),
        }
        references = reviewed.get("fact_references") if isinstance(reviewed, dict) else None
        if (not isinstance(reviewed, dict)
                or set(reviewed) != {"schema_version", "manufacturer", "exact_icpn",
                                     "exact_applicability", "source_authority", "source_reference",
                                     "provider", "profile", "operations", "review_status",
                                     "reviewer", "fact_references", "official_exact_source",
                                     "applicability"}
                or reviewed.get("schema_version") != "catalog-l2-reviewed-evidence-v2"
                or reviewed.get("manufacturer") != record.vendor
                or reviewed.get("exact_icpn") != record.identifier
                or reviewed.get("exact_applicability") != record.identifier
                or reviewed.get("source_authority") != record.source_authority
                or reviewed.get("source_reference") != record.source_reference
                or reviewed.get("provider") != expected_provider
                or reviewed.get("profile") != expected_profile
                or reviewed.get("operations") != q["operations"]
                or reviewed.get("review_status") != "ADMITTED"
                or not isinstance(reviewed.get("reviewer"), str)
                or not reviewed["reviewer"].strip()
                or not isinstance(references, dict)
                or any(not isinstance(references.get(key), str) or not references[key].strip()
                       for key in ("identity", "route", "geometry", "operations"))):
            raise DeviceCatalogIntegrityError("L2 reviewed facts do not match exact Provider/Profile/geometry")
        return reviewed

    def _verify_snapshot_evidence(self, snapshot: CatalogShadowSnapshot, *, strict: bool = False) -> None:
        for record in snapshot.catalog.records:
            q = snapshot.qualifications.get(_identity(record))
            if not q or not q.get("data_only_publication") or q.get("catalog_level", 0) < 2:
                continue
            evidence = q.get("publication_evidence", {})
            if not evidence.get("reviewed_evidence_id"):
                if strict:
                    raise DeviceCatalogIntegrityError("published L2 requires durable Evidence Revision")
                # Schema v2 snapshots remain readable for explicit migration.
                continue
            reviewed = self._validate_l2_source(record, q)
            self._validate_l2_applicability(record, q, reviewed)

    def stage_revision(self, changes: list[dict[str, Any]], *, actor: str) -> str:
        """Stage exact records against the current active revision; staging is never public."""
        if not actor.strip() or not changes:
            raise DeviceCatalogIntegrityError("publisher actor and changes required")
        staged_changes = json.loads(_encoded(changes))
        seen: set[tuple[str, str]] = set()
        for change in staged_changes:
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
                reviewed = self._validate_l2_source(record, q)
                self._validate_l2_applicability(record, q, reviewed)
                if q["publication_evidence"].get("source_path"):
                    packet = Path(q["publication_evidence"]["source_path"]).read_bytes()
                    packet_id = self._store_evidence("PLASMA reviewed qualification", record.identifier,
                                                     hashlib.sha256(packet).hexdigest(), packet, actor=actor)
                    q["publication_evidence"].pop("source_path")
                    q["publication_evidence"]["reviewed_evidence_id"] = packet_id
            key = _identity(record)
            if key in seen:
                raise DeviceCatalogIntegrityError("duplicate exact ICPN in staging")
            seen.add(key)
        stage_id = _digest(staged_changes)
        with sqlite3.connect(self.path, timeout=10) as conn:
            self._init_schema(conn)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            parent = conn.execute("SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1").fetchone()
            if parent is None:
                raise DeviceCatalogIntegrityError("no active Catalog revision")
            self._read_revision(conn, parent[0])
            conn.execute("INSERT OR REPLACE INTO catalog_staging VALUES (?, ?, ?, ?)",
                         (stage_id, parent[0], actor, _encoded(staged_changes)))
            conn.execute("INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) VALUES (?,?,?,?,?)",
                         ("STAGE", actor, parent[0], stage_id, "validated input"))
        return stage_id

    def validate_changes(self, changes: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Preview an official batch without staging or changing the active snapshot."""
        if not isinstance(changes, list) or not changes or len(changes) > 1000:
            raise DeviceCatalogIntegrityError("1-1000 official changes required")
        active = self.read_active()
        seen: set[tuple[str, str]] = set()
        preview = []
        for change in changes:
            try:
                data = dict(change["record"])
                data["cpu_architectures"] = tuple(data["cpu_architectures"])
                record = DeviceCatalogRecord(**data)
                q = change["qualification"]
            except (KeyError, TypeError, ValueError) as exc:
                raise DeviceCatalogIntegrityError("malformed official candidate") from exc
            if not isinstance(q, dict):
                raise DeviceCatalogIntegrityError("malformed official qualification")
            self._validate_publication(record, q)
            if q["catalog_level"] >= 2:
                reviewed = self._validate_l2_source(record, q)
                self._validate_l2_applicability(record, q, reviewed)
            key = _identity(record)
            if key in seen:
                raise DeviceCatalogIntegrityError("duplicate exact ICPN in official batch")
            seen.add(key)
            old = active.qualifications.get(key)
            if old and old.get("catalog_level") == 3 and (old != q or active.catalog.resolve(record.vendor, record.identifier) != record):
                raise DeviceCatalogIntegrityError("L3 revision requires separately authorized revocation")
            preview.append({"vendor": record.vendor, "identifier": record.identifier, "status": "MODIFIED" if old else "ADDED"})
        return preview

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
            self._verify_snapshot_evidence(parent)
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
                    reviewed = self._validate_l2_source(record, q)
                    self._validate_l2_applicability(record, q, reviewed)
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
                    q["publication_evidence"]["reviewer"] = reviewed["reviewer"]
                    q["publication_evidence"]["fact_references"] = reviewed["fact_references"]
                    q["publication_evidence"]["official_exact_source"] = reviewed["official_exact_source"]
                    q["publication_evidence"]["applicability"] = reviewed["applicability"]
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
            if any(q.get("data_only_publication") and q.get("catalog_level", 0) >= 2
                   and not q.get("publication_evidence", {}).get("reviewed_evidence_id")
                   for q in qualifications.values()):
                raise DeviceCatalogIntegrityError("published L2 requires durable Evidence Revision")
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
            target = self._read_revision(conn, revision)
            current = self._read_revision(conn, previous[0])
            self._verify_snapshot_evidence(target, strict=True)
            current_records = {_identity(row): row for row in current.catalog.records}
            target_records = {_identity(row): row for row in target.catalog.records}
            if any(
                target.qualifications.get(key) != qualification
                or target_records.get(key) != current_records.get(key)
                for key, qualification in current.qualifications.items()
                if qualification.get("catalog_level") == 3
            ):
                raise DeviceCatalogIntegrityError("L3 revision requires separately authorized revocation")
            conn.execute("UPDATE active_catalog_revision SET revision_sha256=? WHERE singleton=1", (revision,))
            conn.execute("INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) VALUES (?,?,?,?,?)",
                         ("ROLLBACK", actor, previous[0], revision, "validated snapshot"))

    def put_local_profile(self, namespace: str, manufacturer: str, exact_icpn: str,
                          profile: dict[str, Any], *, actor: str) -> None:
        if not all(isinstance(x, str) and x.strip() for x in (namespace, manufacturer, exact_icpn, actor)):
            raise DeviceCatalogIntegrityError("local namespace, identity and actor required")
        if (not isinstance(profile, dict) or not profile.get("profile_id")
                or profile.get("official") is not False or profile.get("execution_authorized") is not False
                or profile.get("catalog_level") not in (None, 0, 1)
                or profile.get("job_selectable") is True
                or profile.get("state") == "SUPPORTED"
                or profile.get("installed_runtime_attested") is True
                or profile.get("hardware_runtime_ready") is True):
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

    def local_records(self) -> list[dict[str, Any]]:
        """Controller-owned records remain outside immutable official snapshots."""
        with sqlite3.connect(self.path) as conn:
            self._init_schema(conn)
            rows = conn.execute("SELECT profile_json FROM controller_overlays WHERE namespace='user_catalog' ORDER BY vendor_key,icpn_key").fetchall()
        return [json.loads(row[0]) for row in rows]

    def linked_customer_profiles(
        self, official_keys: set[tuple[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Read customer-owned links without granting Job authority.

        An optional caller-owned snapshot keyset keeps Selector origin labels
        consistent with the exact Catalog revision searched, without a second
        full SQLite Catalog scan.
        """
        if official_keys is None:
            snapshot = self.read_active()
            official_keys = {_identity(row) for row in snapshot.catalog.records}
        with sqlite3.connect(self.path) as conn:
            self._init_schema(conn)
            rows = conn.execute(
                "SELECT profile_json FROM controller_overlays "
                "WHERE namespace='official_profile_link' ORDER BY vendor_key,icpn_key"
            ).fetchall()
        linked = []
        for (payload,) in rows:
            entry = json.loads(payload)
            identity = entry["record"]
            is_official = (identity["vendor"].casefold(), identity["identifier"].casefold()) in official_keys
            linked.append({
                **entry,
                "ic_origin": "OFFICIAL" if is_official else "CUSTOMER",
                "profile_origin": "CUSTOMER",
                "link_status": "ACTIVE" if is_official else "PENDING_OFFICIAL",
                "verification": "UNVERIFIED",
            })
        return linked

    def link_local_to_official(
        self, vendor: str, icpn: str, *, expected_local_revision: int,
        confirmed_same_ic: bool, actor: str,
    ) -> dict[str, Any]:
        """Link an intact Customer Profile to an already-published Official IC.

        Identity and qualification stay owned by the active Official revision.
        This transaction never grants the Customer Profile Job authorization.
        """
        if (not all(isinstance(x, str) and x.strip() for x in (vendor, icpn, actor))
                or type(expected_local_revision) is not int or expected_local_revision <= 0
                or confirmed_same_ic is not True):
            raise DeviceCatalogIntegrityError(
                "explicit same-IC confirmation and current Local revision required"
            )
        key = (vendor.strip().casefold(), icpn.strip().casefold())
        with sqlite3.connect(self.path, timeout=10) as conn:
            self._init_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT profile_json FROM controller_overlays "
                "WHERE namespace='user_catalog' AND vendor_key=? AND icpn_key=?", key
            ).fetchone()
            if current is None:
                raise DeviceCatalogIntegrityError("customer Local record not found; reload before linking")
            local = json.loads(current[0])
            if local.get("revision") != expected_local_revision:
                raise DeviceCatalogIntegrityError("customer Local record revision changed; reload before linking")
            record = local.get("record", {})
            if (str(record.get("vendor", "")).casefold(),
                    str(record.get("identifier", "")).casefold()) != key:
                raise DeviceCatalogIntegrityError("customer Local identity does not match stored key")
            if not isinstance(local.get("profile"), dict) or not local["profile"].get("profile_id"):
                raise DeviceCatalogIntegrityError("customer Profile is incomplete; link refused")
            if conn.execute(
                "SELECT 1 FROM controller_overlays WHERE namespace='official_profile_link' "
                "AND vendor_key=? AND icpn_key=?", key
            ).fetchone():
                raise DeviceCatalogIntegrityError("Official IC already has a customer Profile link")
            active = conn.execute(
                "SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1"
            ).fetchone()
            if active is None:
                raise DeviceCatalogIntegrityError("no active Official Catalog")
            snapshot = self._read_revision(conn, active[0])
            official = snapshot.catalog.resolve(vendor, icpn)
            if official is None:
                raise DeviceCatalogIntegrityError(
                    "the same exact ICPN must be published as an Official IC before linking"
                )
            # Never copy a customer-supplied Level or Provider over the Official
            # identity. Preserve the entire previous local record and Profile.
            linked = {
                **local,
                "origin": "CUSTOMER",
                "verification": "UNVERIFIED",
                "official_link": {
                    "manufacturer": official.vendor,
                    "exact_icpn": official.identifier,
                    "source_authority": official.source_authority,
                    "official_revision_at_link": active[0],
                },
            }
            conn.execute(
                "INSERT INTO controller_overlays(namespace,vendor_key,icpn_key,profile_json) "
                "VALUES ('official_profile_link',?,?,?)", (*key, _encoded(linked))
            )
            removed = conn.execute(
                "DELETE FROM controller_overlays WHERE namespace='user_catalog' "
                "AND vendor_key=? AND icpn_key=?", key
            )
            if removed.rowcount != 1:
                raise DeviceCatalogIntegrityError("customer Local record changed during link")
            detail = _encoded({
                "manufacturer": official.vendor,
                "exact_icpn": official.identifier,
                "local_revision": expected_local_revision,
                "profile_id": local["profile"]["profile_id"],
                "preserved_source_sha256": _digest(local),
                "link_namespace": "official_profile_link",
            })
            conn.execute(
                "INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) "
                "VALUES (?,?,?,?,?)",
                ("LOCAL_LINK_OFFICIAL", actor, active[0], None, detail),
            )
        return {
            "manufacturer": official.vendor,
            "exact_icpn": official.identifier,
            "ic_origin": "OFFICIAL",
            "profile_origin": "CUSTOMER",
            "link_status": "ACTIVE",
            "local_revision": expected_local_revision,
            "profile_id": local["profile"]["profile_id"],
        }

    def delete_local_record(self, vendor: str, icpn: str, *, actor: str) -> None:
        if not all(isinstance(value, str) and value.strip() for value in (vendor, icpn, actor)):
            raise DeviceCatalogIntegrityError("local identity and actor required")
        with sqlite3.connect(self.path, timeout=10) as conn:
            self._init_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute("DELETE FROM controller_overlays WHERE namespace='user_catalog' AND vendor_key=? AND icpn_key=?", (vendor.casefold(), icpn.casefold()))
            if cursor.rowcount != 1:
                raise DeviceCatalogIntegrityError("local exact ICPN not found")
            conn.execute("INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) VALUES (?,?,?,?,?)", ("LOCAL_DELETE", actor, None, None, f"{vendor.casefold()}:{icpn.casefold()}"))

    def save_local_records(self, entries: list[dict[str, Any]], *, actor: str, dry_run: bool = False) -> list[dict[str, Any]]:
        """Persist LOCAL identities independently from same-key Official records."""
        if not actor.strip() or not entries or len(entries) > 1000:
            raise DeviceCatalogIntegrityError("actor and 1-1000 local records required")
        prepared = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("record"), dict):
                raise DeviceCatalogIntegrityError("local record must be an object")
            record = entry["record"]
            profile = entry.get("profile", {})
            if (not isinstance(profile, dict) or not isinstance(record.get("vendor"), str)
                    or not isinstance(record.get("identifier"), str)
                    or not record["vendor"].strip() or not record["identifier"].strip()
                    or len(record["vendor"]) > 128 or len(record["identifier"]) > 128
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+/-]*", record["identifier"])):
                raise DeviceCatalogIntegrityError("invalid local identity or Profile")
            if set(record) - {"vendor", "identifier", "family", "package", "flash_size"}:
                raise DeviceCatalogIntegrityError("unsupported local record field")
            if (set(profile) - {"profile_id", "provider_id", "operations", "flash_geometry", "source_evidence"}
                    or not isinstance(profile.get("profile_id"), str) or not profile["profile_id"].strip()
                    or not isinstance(profile.get("provider_id", ""), str)
                    or not isinstance(profile.get("operations", []), list)
                    or any(op not in ("erase", "program", "verify", "read") for op in profile.get("operations", []))
                    or not isinstance(profile.get("source_evidence", []), list)
                    or any(not isinstance(item, str) for item in profile.get("source_evidence", []))):
                raise DeviceCatalogIntegrityError("unsupported local Profile or Evidence field")
            forbidden = {"catalog_level", "job_selectable", "execution_authorized", "official", "state", "supported", "qualification", "publication_evidence", "installed_runtime_attested", "hardware_runtime_ready"}
            if forbidden.intersection(record) or forbidden.intersection(profile):
                raise DeviceCatalogIntegrityError("local data cannot claim official qualification or execution")
            geometry = profile.get("flash_geometry")
            if geometry is not None:
                if not isinstance(geometry, dict):
                    raise DeviceCatalogIntegrityError("invalid local flash geometry")
                try:
                    size, pages, erase, write = (geometry[k] for k in ("main_flash_size_bytes", "page_count", "erase_unit_bytes", "program_unit_bytes"))
                    valid = all(type(n) is int and n > 0 for n in (size, pages, erase, write)) and size == pages * erase and erase % write == 0
                except KeyError:
                    valid = False
                if not valid:
                    raise DeviceCatalogIntegrityError("invalid local flash geometry")
            key = (record["vendor"].strip().casefold(), record["identifier"].strip().casefold())
            if key in seen:
                raise DeviceCatalogIntegrityError("duplicate exact ICPN in import")
            seen.add(key)
            prepared.append((key, {"record": {"vendor": record["vendor"].strip(), "identifier": record["identifier"].strip(), "family": str(record.get("family", "")), "package": str(record.get("package", "")), "flash_size": str(record.get("flash_size", ""))}, "profile": profile}))
        with sqlite3.connect(self.path, timeout=10) as conn:
            self._init_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute("SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1").fetchone()
            if active is None:
                raise DeviceCatalogIntegrityError("no active official Catalog revision")
            output = []
            for key, data in prepared:
                old = conn.execute("SELECT profile_json FROM controller_overlays WHERE namespace='user_catalog' AND vendor_key=? AND icpn_key=?", key).fetchone()
                previous = json.loads(old[0]) if old else None
                unchanged = bool(previous and previous["record"] == data["record"] and previous["profile"] == data["profile"])
                revision = previous.get("revision", 0) if unchanged else (previous.get("revision", 0) if previous else 0) + 1
                value = {**data, "revision": revision, "origin": "LOCAL", "verification": "UNVERIFIED"}
                output.append({**value, "change": "UNCHANGED" if unchanged else "UPDATED" if old else "ADDED"})
                if not dry_run and not unchanged:
                    conn.execute("INSERT OR REPLACE INTO controller_overlays VALUES ('user_catalog',?,?,?)", (*key, _encoded(value)))
                    conn.execute("INSERT INTO catalog_audit_events(action,actor,predecessor,revision_sha256,detail) VALUES (?,?,?,?,?)", ("LOCAL_SAVE", actor, None, active[0], f"{key[0]}:{key[1]}:r{revision}"))
        return output

    def history(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            self._init_schema(conn)
            active = conn.execute("SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1").fetchone()
            revisions = conn.execute("SELECT revision_sha256,row_count FROM catalog_revisions ORDER BY rowid DESC LIMIT 100").fetchall()
            audit = conn.execute("SELECT action,actor,predecessor,revision_sha256,detail,created_at FROM catalog_audit_events ORDER BY event_id DESC LIMIT 100").fetchall()
        return {"active_revision": active[0] if active else None, "revisions": [{"revision": r, "count": n} for r, n in revisions], "audit": [dict(zip(("action", "actor", "predecessor", "revision", "detail", "created_at"), row)) for row in audit]}

    def evidence_history(self) -> list[dict[str, str]]:
        with sqlite3.connect(self.path) as conn:
            self._init_schema(conn)
            rows = conn.execute("SELECT evidence_id,source_authority,source_reference,source_revision,acquired_at FROM catalog_evidence ORDER BY acquired_at DESC LIMIT 100").fetchall()
        result = []
        for evidence_id, authority, reference, source_revision, acquired_at in rows:
            self._read_evidence(evidence_id)
            result.append({"evidence_id": evidence_id, "authority": authority, "reference": reference, "source_revision": source_revision, "acquired_at": acquired_at})
        return result

    def diff_revision(self, revision: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            self._init_schema(conn)
            active = conn.execute("SELECT revision_sha256 FROM active_catalog_revision WHERE singleton=1").fetchone()
            if active is None:
                raise DeviceCatalogIntegrityError("no active Catalog revision")
            current, target = self._read_revision(conn, active[0]), self._read_revision(conn, revision)
        before = {_identity(r): {"record": asdict(r), "qualification": current.qualifications.get(_identity(r))} for r in current.catalog.records}
        after = {_identity(r): {"record": asdict(r), "qualification": target.qualifications.get(_identity(r))} for r in target.catalog.records}
        return [{"vendor": k[0], "identifier": k[1], "status": "ADDED" if k not in before else "REMOVED" if k not in after else "MODIFIED", "before": before.get(k), "after": after.get(k)} for k in sorted(before.keys() | after.keys()) if before.get(k) != after.get(k)]

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
    action.add_argument("--acquire-evidence", type=Path,
                        help="JSON official source request: manufacturer, exact_icpn, kind, source_revision")
    action.add_argument("--local-file", type=Path, help="JSON local Profile with namespace/manufacturer/icpn/profile")
    parser.add_argument("--actor", help="authorized publisher identity (required for writes)")
    args = parser.parse_args()
    repository = CatalogSqliteShadowRepository(args.db)
    if args.stage_file or args.publish_stage or args.rollback or args.local_file or args.acquire_evidence:
        if not args.actor:
            parser.error("--actor is required for publication and local writes")
        if args.acquire_evidence:
            request = json.loads(args.acquire_evidence.read_text(encoding="utf-8"))
            record = repository.read_active().catalog.resolve(request["manufacturer"], request["exact_icpn"])
            if record is None:
                raise DeviceCatalogIntegrityError("official Exact ICPN not in active Catalog")
            evidence_id = repository.acquire_exact_evidence(
                record, kind=request["kind"], source_revision=request["source_revision"], actor=args.actor
            )
            result = {"result": "EVIDENCE_VERIFIED", "evidence_id": evidence_id}
        elif args.stage_file:
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
