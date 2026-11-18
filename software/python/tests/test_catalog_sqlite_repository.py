"""Host-only acceptance for Catalog Database v1 SQLite shadow migration."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from plasma_web.catalog_sqlite_repository import CatalogSqliteShadowRepository
from plasma_web.device_catalog import (
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    default_catalog_manifest_path,
    get_default_device_catalog,
)
from plasma_web.programming_qualification import get_default_programming_qualification_registry


@pytest.fixture
def source_catalog() -> DeviceCatalog:
    return get_default_device_catalog()


def test_real_production_manifest_full_records_metadata_and_search_parity(
    tmp_path: Path, source_catalog: DeviceCatalog
) -> None:
    db = tmp_path / "catalog-shadow.sqlite3"
    shadow = CatalogSqliteShadowRepository(db)
    revision = shadow.import_verified_manifest(default_catalog_manifest_path())
    actual = shadow.verify_parity(default_catalog_manifest_path())
    assert actual.revision_sha256 == revision
    assert actual.catalog.records == source_catalog.records
    assert actual.catalog.metadata == source_catalog.metadata
    assert actual.qualifications == {}
    assert shadow.import_verified_manifest(default_catalog_manifest_path()) == revision
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM catalog_revisions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM catalog_records").fetchone()[0] == source_catalog.size
    for term in ("STM32F103", "STM32F103C8T6", "MCX", "microchip", "R8", "STMicroelectronics"):
        for offset, limit in ((0, 10), (3, 7), (50, 20)):
            left = source_catalog.search_with_total(term, offset=offset, limit=limit)
            right = actual.catalog.search_with_total(term, offset=offset, limit=limit)
            assert right == left
    if source_catalog.records:
        first = source_catalog.records[0]
        assert actual.catalog.resolve(first.vendor.upper(), first.identifier.lower()) == first
    assert not (tmp_path / "catalog-shadow.sqlite3").is_dir()


def test_shadow_captures_unmodified_l0_to_l3_projections_and_never_execution(
    tmp_path: Path, source_catalog: DeviceCatalog
) -> None:
    registry = get_default_programming_qualification_registry()
    repo = CatalogSqliteShadowRepository(tmp_path / "qualified-shadow.db")
    revision = repo.import_verified_manifest(
        default_catalog_manifest_path(), qualification_registry=registry
    )
    snapshot = repo.verify_parity(default_catalog_manifest_path(), qualification_registry=registry)
    assert snapshot.revision_sha256 == revision
    assert len(snapshot.qualifications) == source_catalog.size
    assert all(row["execution_authorized"] is False for row in snapshot.qualifications.values())
    assert all(row["job_selectable"] is (row["catalog_level"] >= 2)
               for row in snapshot.qualifications.values())
    assert sum(q["catalog_level"] >= 2 for q in snapshot.qualifications.values()) == (
        registry.summary["catalog_level_2_programmable_exact_icpns"]
    )
    assert sum(q["catalog_level"] == 3 for q in snapshot.qualifications.values()) == (
        registry.summary["catalog_level_3_verified_exact_icpns"]
    )
    assert snapshot.catalog.records == source_catalog.records


def test_shadow_rejects_different_qualification_catalog(
    tmp_path: Path, source_catalog: DeviceCatalog
) -> None:
    class WrongRegistry:
        _catalog = DeviceCatalog(
            source_catalog.records[:-1],
            revision_sha256="different",
        )

    repo = CatalogSqliteShadowRepository(tmp_path / "shadow.sqlite3")
    with pytest.raises(DeviceCatalogIntegrityError, match="qualification source/Catalog mismatch"):
        repo.import_verified_manifest(
            default_catalog_manifest_path(), qualification_registry=WrongRegistry()
        )
    assert not repo.path.exists()


def test_shadow_duplicate_identity_aborts_without_changing_active_revision(
    tmp_path: Path, source_catalog: DeviceCatalog
) -> None:
    repo = CatalogSqliteShadowRepository(tmp_path / "shadow.sqlite3")
    original = repo.import_verified_manifest(default_catalog_manifest_path())
    duplicate = DeviceCatalog(
        [source_catalog.records[0], replace(source_catalog.records[0], identifier=source_catalog.records[0].identifier.lower())],
        catalog_id=source_catalog.catalog_id,
        catalog_version=source_catalog.catalog_version,
        status="production",
        revision_sha256=source_catalog.revision_sha256,
    )
    with patch("plasma_web.catalog_sqlite_repository.DeviceCatalog.from_manifest", return_value=duplicate):
        with pytest.raises(DeviceCatalogIntegrityError, match="duplicate or unadmitted"):
            repo.import_verified_manifest(default_catalog_manifest_path())
    assert repo.read_active().revision_sha256 == original
    assert repo.read_active().size == source_catalog.size


def test_shadow_rejects_mutated_sqlite_rows_or_missing_db(
    tmp_path: Path,
) -> None:
    db = tmp_path / "catalog-shadow.sqlite3"
    repo = CatalogSqliteShadowRepository(db)
    with pytest.raises(DeviceCatalogIntegrityError, match="missing"):
        repo.read_active()
    repo.import_verified_manifest(default_catalog_manifest_path())
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE catalog_records SET record_json = ? WHERE ordinal = 0",
            (json.dumps({"fake": "part"}),),
        )
    with pytest.raises(DeviceCatalogIntegrityError, match="digest"):
        repo.read_active()


def test_incompatible_schema_fails_closed(tmp_path: Path) -> None:
    db = tmp_path / "future-catalog.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA user_version = 999")
    repo = CatalogSqliteShadowRepository(db)
    with pytest.raises(DeviceCatalogIntegrityError, match="unsupported SQLite Catalog schema"):
        repo.read_active()
    with pytest.raises(DeviceCatalogIntegrityError, match="unsupported SQLite Catalog schema"):
        repo.import_verified_manifest(default_catalog_manifest_path())
