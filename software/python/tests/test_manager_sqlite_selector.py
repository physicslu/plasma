"""Manager-owned SQLite Selector opt-in: API parity and fail closed.

Host-only; no PPU, Z2, DUT, Gateway or live programming is contacted.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict
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


def test_selector_does_not_require_legacy_source_parity(
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
    with patch("plasma_web.device_catalog.get_default_device_catalog", return_value=changed):
        loaded, _, _ = read_selector_view(str(source_qualified_database))
    assert loaded.records == actual.records


def test_catalog_management_local_round_trip_and_publisher_boundary(
    tmp_path: Path, manager_port: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "management.db"
    repo = CatalogSqliteShadowRepository(database)
    official_revision = repo.import_verified_manifest(
        default_catalog_manifest_path(),
        qualification_registry=get_default_programming_qualification_registry(),
    )
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(database))
    monkeypatch.setenv("PLASMA_CATALOG_PUBLISH_TOKEN", "test-publisher-secret")
    status, catalog_search = _get(manager_port, "/api/catalog/management/search?q=STM32F103C8T6")
    assert status == 200 and catalog_search["official"][0]["source"]
    assert catalog_search["official"][0]["level"] >= 1
    entry = {"record": {"vendor": "LocalVendor", "identifier": "LOCAL123", "family": "Demo", "package": "QFN", "flash_size": "64 KB"},
             "profile": {"profile_id": "custom-v1", "provider_id": "example", "operations": ["erase", "program"]}}

    def post(action: str, payload: dict, token: str | None = "test-publisher-secret") -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Plasma-Catalog-Publisher"] = token
        request = urllib.request.Request(
            f"http://127.0.0.1:{manager_port}/api/catalog/management/{action}",
            data=json.dumps(payload).encode(), headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    assert post("local", {"entries": [entry]}, None)[0] == 403
    assert post("local", {"entries": [entry]}, "wrong")[0] == 403
    assert post("validate", {"entries": [entry]})[1]["changes"][0]["change"] == "ADDED"
    assert repo.local_records() == []
    assert post("local", {"entries": [entry]})[0] == 200
    assert CatalogSqliteShadowRepository(database).local_records()[0]["revision"] == 1
    status, result = _get(manager_port, "/api/devices/search?q=LOCAL123")
    assert status == 200 and result["local_results"][0]["verification"] == "UNVERIFIED"
    assert result["results"] == []
    assert repo.read_active().revision_sha256 == official_revision
    changed = json.loads(json.dumps(entry))
    changed["profile"]["profile_id"] = "custom-v2"
    assert post("local", {"entries": [changed]})[1]["changes"][0]["revision"] == 2
    assert repo.local_records()[0]["profile"]["profile_id"] == "custom-v2"
    forged = json.loads(json.dumps(entry))
    forged["record"]["identifier"] = "FORGED1"
    forged["profile"]["catalog_level"] = 2
    assert post("local", {"entries": [entry, forged]})[0] == 400
    assert len(repo.local_records()) == 1
    assert repo.read_active().revision_sha256 == official_revision
    official = json.loads(json.dumps(entry))
    official["record"].update(vendor="STMicroelectronics", identifier="STM32F103C8T6")
    assert post("local", {"entries": [official]})[0] == 400


def test_manager_http_export_reads_one_snapshot_and_preserves_catalog(
    tmp_path: Path, source_qualified_database: Path, manager_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "export.db"
    with sqlite3.connect(source_qualified_database) as source, sqlite3.connect(database) as target:
        source.backup(target)
    repo = CatalogSqliteShadowRepository(database)
    repo.save_local_records([{
        "record": {"vendor": "LocalVendor", "identifier": "EXPORT123"},
        "profile": {"profile_id": "export-test"},
    }], actor="test")
    before = repo.read_active()
    local = repo.local_records()
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(database))
    original = CatalogSqliteShadowRepository.read_active
    reads = 0

    def counted_read_active(self):
        nonlocal reads
        reads += 1
        return original(self)

    monkeypatch.setattr(CatalogSqliteShadowRepository, "read_active", counted_read_active)
    started = time.monotonic()
    status, body = _get(manager_port, "/api/catalog/management/export")
    elapsed = time.monotonic() - started
    assert status == 200 and body["ok"] is True
    assert set(body) == {"ok", "local", "official"}
    assert body["local"] == local
    expected_official = [
        {"record": asdict(record), "qualification": before.qualifications.get(
            (record.vendor.casefold(), record.identifier.casefold()))}
        for record in before.catalog.records
    ]
    assert body["official"] == json.loads(json.dumps(expected_official))
    assert reads == 1
    print(f"HTTP export: {len(body['official'])} records, {reads} snapshot read, {elapsed:.3f}s")
    assert repo.read_active().revision_sha256 == before.revision_sha256
    assert len(repo.local_records()) == 1


def test_local_ic_survives_manager_http_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "restart-catalog.db"
    CatalogSqliteShadowRepository(database).import_verified_manifest(
        default_catalog_manifest_path(),
        qualification_registry=get_default_programming_qualification_registry(),
    )
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(database))
    monkeypatch.setenv("PLASMA_CATALOG_PUBLISH_TOKEN", "restart-test-publisher")

    def start_manager():
        server = manager_server.PlasmaManagerHTTPServer(("127.0.0.1", 0), manager_server.PlasmaManagerHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    server, thread = start_manager()
    try:
        entry = {"record": {"vendor": "LocalVendor", "identifier": "RESTART123", "family": "Demo", "package": "QFN", "flash_size": "64 KB"},
                 "profile": {"profile_id": "restart-custom-v1", "operations": ["program"]}}
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/catalog/management/local",
            data=json.dumps({"entries": [entry]}).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-Plasma-Catalog-Publisher": "restart-test-publisher"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 200
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)

    restarted, restarted_thread = start_manager()
    try:
        status, result = _get(restarted.server_port, "/api/devices/search?q=RESTART123")
        assert status == 200 and result["local_results"][0]["record"]["identifier"] == "RESTART123"
        status, management = _get(restarted.server_port, "/api/catalog/management")
        assert status == 200 and management["local"][0]["revision"] == 1
    finally:
        restarted.shutdown(); restarted.server_close(); restarted_thread.join(timeout=2)
