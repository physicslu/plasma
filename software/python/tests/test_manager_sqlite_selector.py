"""Manager-owned SQLite Selector opt-in: source parity, API parity, fail closed.

Host-only; no PPU, Z2, DUT, Gateway or live programming is contacted.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from plasma_manager import server as manager_server
from plasma_web import legacy_device_selector as selector
from plasma_web.catalog_sqlite_repository import CatalogSqliteShadowRepository
from plasma_web.catalog_sqlite_selector import read_selector_view
from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, default_catalog_manifest_path
from plasma_web.programming_qualification import get_default_programming_qualification_registry


@pytest.fixture(scope="module")
def source_qualified_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("catalog-selector-sqlite") / "catalog.db"
    CatalogSqliteShadowRepository(database).import_verified_manifest(
        default_catalog_manifest_path(),
        qualification_registry=get_default_programming_qualification_registry(),
    )
    return database


@pytest.fixture
def manager_port():
    httpd = manager_server.PlasmaManagerHTTPServer(
        ("127.0.0.1", 0), manager_server.PlasmaManagerHandler
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _get(port: int, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_sqlite_search_produces_identical_full_response_without_api_drift(
    source_qualified_database: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(selector.SQLITE_SELECTOR_DB_ENV, raising=False)
    queries = (
        "q=STM32F103C8T6&limit=1",
        "q=STM32F103&limit=5&offset=3",
        "q=STM32F103&levels=2,3&limit=7",
        "q=MCXA185VLH&limit=1",
        "q=ATSAML&levels=1&limit=3",
        "q=PIC32MX&limit=4&offset=2",
        "q=&limit=5",
    )
    original = [selector.search_response(query) for query in queries]
    legacy_levels = selector.warm()
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(source_qualified_database))
    assert selector.warm() == legacy_levels
    assert [selector.search_response(query) for query in queries] == original
    monkeypatch.delenv(selector.SQLITE_SELECTOR_DB_ENV)
    assert selector.search_response(queries[0]) == original[0]


def test_manager_http_sqlite_mode_retains_l0_and_invalid_query_contract(
    manager_port: int, source_qualified_database: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(source_qualified_database))
    status, body = _get(manager_port, "/api/devices/search?q=STM32F103C8T6&limit=1")
    assert status == 200 and body["results"][0]["icpn"] == "STM32F103C8T6"
    assert body["results"][0]["programming_qualification"]["execution_authorized"] is False
    status, body = _get(manager_port, "/api/devices/search?q=MCXA185VLH")
    assert status == 200 and body["total_count"] == 0  # L0 invisible
    status, body = _get(manager_port, "/api/devices/search?q=STM32&levels=0")
    assert status == 400 and body["error"]["error_type"] == "INVALID_DEVICE_SEARCH"


def test_unconfigured_or_missing_sqlite_fail_503_without_csv_fallback(
    tmp_path: Path, manager_port: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, "")
    status, body = _get(manager_port, "/api/devices/search?q=STM32")
    assert status == 503 and "results" not in body
    assert body["error"]["error_type"] == "DEVICE_SELECTOR_UNAVAILABLE"
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(tmp_path / "missing.sqlite3"))
    status, body = _get(manager_port, "/api/devices/search?q=STM32")
    assert status == 503 and "results" not in body
    assert not (tmp_path / "missing.sqlite3").exists()
    assert selector.warm is not None


def test_unqualified_snapshot_is_not_accepted_for_customer_search(
    tmp_path: Path, manager_port: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "unqualified.sqlite3"
    CatalogSqliteShadowRepository(db).import_verified_manifest(default_catalog_manifest_path())
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(db))
    status, body = _get(manager_port, "/api/devices/search?q=STM32F103C8T6")
    assert status == 503 and "results" not in body
    assert "complete qualification" in body["error"]["message"]


def test_tampered_sqlite_snapshot_fails_closed_not_empty(
    tmp_path: Path, manager_port: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "tamper.sqlite3"
    CatalogSqliteShadowRepository(db).import_verified_manifest(
        default_catalog_manifest_path(),
        qualification_registry=get_default_programming_qualification_registry(),
    )
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(db))
    assert _get(manager_port, "/api/devices/search?q=STM32F103C8T6")[0] == 200
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE catalog_records SET qualification_json = ? WHERE ordinal = 0",
                     ('{"catalog_level":3,"execution_authorized":true}',))
    status, body = _get(manager_port, "/api/devices/search?q=STM32F103C8T6")
    assert status == 503 and "results" not in body
    assert body["error"]["error_type"] == "DEVICE_SELECTOR_UNAVAILABLE"


def test_source_revision_drift_rejected_without_legacy_fallback(
    source_qualified_database: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual, _, _ = read_selector_view(str(source_qualified_database))
    changed = DeviceCatalog(
        actual.records[:-1],
        catalog_id=actual.catalog_id,
        catalog_version=actual.catalog_version,
        status=actual.status,
        revision_sha256=actual.revision_sha256,
        source_count=actual.source_count,
    )
    with patch("plasma_web.catalog_sqlite_selector.get_default_device_catalog", return_value=changed):
        with pytest.raises(DeviceCatalogIntegrityError, match="source parity mismatch"):
            read_selector_view(str(source_qualified_database))
