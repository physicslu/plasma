"""Manager-owned SQLite-only Selector: full source parity and fail closed.

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
from plasma_web.catalog_sqlite_repository import CatalogSqliteShadowRepository, CatalogLocalIdentityConflict
from plasma_web.catalog_sqlite_selector import read_selector_view
from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, default_catalog_manifest_path, get_default_device_catalog
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


def test_sqlite_only_matches_full_exact_source_and_qualification_snapshot(
    source_qualified_database: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Compare against the original trusted import sources in this OFFLINE test,
    # never through a runtime Selector fallback.
    source = get_default_device_catalog()
    qualification = get_default_programming_qualification_registry()
    imported, projections, level_counts = read_selector_view(str(source_qualified_database))
    assert imported.records == source.records  # all L0/L1/L2/L3 Exact ICPNs, ordered
    assert imported.size == len(projections)
    assert level_counts == qualification.summary["catalog_level_counts"]
    for record in source.records:
        key = (record.vendor.casefold(), record.identifier.casefold())
        assert projections[key] == qualification.describe(record.vendor, record.identifier)

    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(source_qualified_database))
    assert selector.warm() == level_counts
    for query, selected_levels, page_size in (
        ("STM32F103", (1, 2, 3), 7),
        ("STM32F103", (2, 3), 7),
        ("ATSAML", (1,), 5),
        ("PIC32MX", (1, 2, 3), 3),
        ("", (1, 2, 3), 100),
    ):
        expected, total = source.search_with_total(
            query, limit=source.size, offset=0,
            predicate=lambda record: qualification.describe(
                record.vendor, record.identifier
            )["catalog_level"] in selected_levels,
        )
        received = []
        for offset in range(0, total + page_size, page_size):
            raw = f"q={query}&levels={','.join(map(str, selected_levels))}&limit={page_size}&offset={offset}"
            status, payload = selector.search_response(raw)
            assert status == 200, payload
            assert payload["total_count"] == total
            assert payload["offset"] == offset
            assert payload["catalog_size"] == sum(level_counts[str(i)] for i in selected_levels)
            received.extend((row["vendor"], row["identifier"]) for row in payload["results"])
        assert received == [(row.vendor, row.identifier) for row in expected]
    assert selector.search_response("q=MCXA185VLH&limit=1")[1]["total_count"] == 0

    # Neither a missing env nor a stale source manifest may resurrect the old path.
    monkeypatch.delenv(selector.SQLITE_SELECTOR_DB_ENV)
    assert selector.search_response("q=STM32F103C8T6")[0] == 503
    with pytest.raises(DeviceCatalogIntegrityError):
        selector.warm()


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
    monkeypatch.delenv(selector.SQLITE_SELECTOR_DB_ENV, raising=False)
    status, body = _get(manager_port, "/api/devices/search?q=STM32")
    assert status == 503 and body["error"]["error_type"] == "DEVICE_SELECTOR_UNAVAILABLE"
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


@pytest.mark.parametrize("action,payload,method", [
    ("validate-official", {"changes": []}, "validate_changes"),
    ("stage", {"changes": []}, "stage_revision"),
    ("publish", {"stage_id": "test-stage"}, "publish_staged"),
    ("rollback", {"revision": "test-revision"}, "rollback"),
])
def test_manager_official_conflict_http_409_exposes_customer_resolution_details(
    manager_port: int, monkeypatch: pytest.MonkeyPatch,
    action: str, payload: dict, method: str,
) -> None:
    """Official updates fail closed with actionable details, never auto-delete Local."""
    monkeypatch.setenv("PLASMA_CATALOG_PUBLISH_TOKEN", "test-publisher-secret")
    expected = [{
        "manufacturer": "LocalVendor",
        "exact_icpn": "LOCAL123",
        "local_revision": 3,
        "local_profile_id": "custom-v3",
    }]

    def conflict(*args, **kwargs):
        raise CatalogLocalIdentityConflict(expected, count=1)

    monkeypatch.setattr(CatalogSqliteShadowRepository, method, conflict)
    request = urllib.request.Request(
        f"http://127.0.0.1:{manager_port}/api/catalog/management/{action}",
        data=json.dumps(payload).encode(), method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Plasma-Catalog-Publisher": "test-publisher-secret",
        },
    )
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(request, timeout=30)
    response = raised.value
    assert response.code == 409
    body = json.loads(response.read())
    assert body["ok"] is False
    assert body["error"]["code"] == "CATALOG_LOCAL_IDENTITY_CONFLICT"
    assert body["error"]["conflicts"] == expected
    assert body["error"]["conflict_count"] == 1
    assert body["error"]["truncated"] is False
    assert "resolve" in body["error"]["message"]


def test_manager_customer_official_link_api_preserves_both_provenances(
    manager_port: int, source_qualified_database: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "link-manager.sqlite3"
    with sqlite3.connect(source_qualified_database) as src, sqlite3.connect(database) as dst:
        src.backup(dst)
    repo = CatalogSqliteShadowRepository(database)
    monkeypatch.setenv("PLASMA_CATALOG_SQLITE_DB", str(database))
    monkeypatch.setenv("PLASMA_CATALOG_PUBLISH_TOKEN", "link-test-publisher")

    record = {"vendor": "STMicroelectronics", "identifier": "STM32F103C8T6",
              "family": "Customer STM32F1", "package": "LQFP48", "flash_size": "64 KiB"}
    original = {"record": record, "profile": {
        "profile_id": "customer-owned-f1", "provider_id": "customer-provider",
        "operations": ["erase", "program"], "source_evidence": ["owner-verified-custom"]}}
    repo.save_local_records([original], actor="owner")
    def post(token: str, confirmation: bool, revision: int) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{manager_port}/api/catalog/management/link-local-official",
            data=json.dumps({
                "vendor": record["vendor"], "icpn": record["identifier"],
                "expected_local_revision": revision, "confirmed_same_ic": confirmation,
            }).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-Plasma-Catalog-Publisher": token},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    assert post("wrong", True, 1)[0] == 403
    assert post("link-test-publisher", False, 1)[0] == 400
    assert post("link-test-publisher", True, 2)[0] == 400
    assert len(repo.local_records()) == 1
    status, result = post("link-test-publisher", True, 1)
    assert status == 200
    assert result["link"]["ic_origin"] == "OFFICIAL"
    assert result["link"]["profile_origin"] == "CUSTOMER"
    assert result["link"]["profile_id"] == "customer-owned-f1"
    assert repo.local_records() == []

    status, manager = _get(manager_port, "/api/catalog/management")
    assert status == 200
    assert manager["local"] == []
    assert len(manager["linked_profiles"]) == 1
    assert manager["linked_profiles"][0]["profile"]["profile_id"] == "customer-owned-f1"
    assert manager["linked_profiles"][0]["verification"] == "UNVERIFIED"
    assert manager["linked_profiles"][0]["link_status"] == "ACTIVE"
    status, search = _get(manager_port, "/api/devices/search?q=STM32F103C8T6&limit=1")
    assert status == 200
    assert search["results"][0]["ic_origin"] == "OFFICIAL"
    assert search["results"][0]["linked_customer_profile"]["origin"] == "CUSTOMER"
    assert search["results"][0]["linked_customer_profile"]["verification"] == "UNVERIFIED"
    assert post("link-test-publisher", True, 1)[0] == 400
    assert [event["action"] for event in repo.history()["audit"]].count("LOCAL_LINK_OFFICIAL") == 1
