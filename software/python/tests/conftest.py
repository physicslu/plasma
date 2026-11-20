"""Offline SQLite authority for legacy Phase 42/43 REST Catalog regression tests.

Only the REST tests get a qualified, explicit Catalog. Missing-DB/fail-closed
tests outside these legacy modules remain unconfigured by design.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def _phase_rest_qualified_catalog(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from plasma_web.catalog_sqlite_repository import CatalogSqliteShadowRepository
    from plasma_web.device_catalog import default_catalog_manifest_path
    from plasma_web.programming_qualification import get_default_programming_qualification_registry

    database = tmp_path_factory.mktemp("phase-rest-qualified-catalog") / "catalog.db"
    CatalogSqliteShadowRepository(database).import_verified_manifest(
        default_catalog_manifest_path(),
        qualification_registry=get_default_programming_qualification_registry(),
    )
    return database


@pytest.fixture(autouse=True)
def _provision_legacy_phase_rest_catalog(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = request.module.__name__.rsplit(".", 1)[-1]
    if not module.startswith(("test_device_catalog_phase42", "test_device_catalog_phase43")):
        return
    if "rest_catalog" not in request.node.name:
        return
    database = request.getfixturevalue("_phase_rest_qualified_catalog")
    monkeypatch.setenv("PLASMA_CATALOG_SQLITE_DB", str(database))
