"""Host-only acceptance for Catalog Database v1 SQLite shadow migration."""
from __future__ import annotations

import json
import sqlite3
import hashlib
import threading
from dataclasses import asdict, replace
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
from plasma_web.catalog_sqlite_selector import read_selector_view
from plasma_web import legacy_device_selector as selector


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


def _publisher_fixture(tmp_path: Path):
    repo = CatalogSqliteShadowRepository(tmp_path / "published.sqlite3")
    registry = get_default_programming_qualification_registry()
    initial = repo.import_verified_manifest(default_catalog_manifest_path(), qualification_registry=registry)
    source = get_default_device_catalog()
    st = next(row for row in source.records if row.identifier == "STM32F103C8T6")
    candidate = next(row for row in source.records
                     if registry.describe(row.vendor, row.identifier)["catalog_level"] == 1)
    record = replace(st, identifier="STM32F103C8T6-TEST-EXACT",
                     source_reference="https://example.test/official/exact-and-route",
                     source_authority="STMicroelectronics official",
                     source_type="official_exact_and_route",
                     catalog_origin="data-only-publication-test")
    l1 = registry.describe(candidate.vendor, candidate.identifier).copy()
    l1["route_evidence"] = "https://example.test/official/exact-and-route"
    return repo, initial, record, l1, registry.describe(st.vendor, st.identifier)


def _reviewed_l2_packet(record, l2, evidence_path: Path) -> None:
    reviewed = {
        "schema_version": "catalog-l2-reviewed-evidence-v1",
        "manufacturer": record.vendor, "exact_icpn": record.identifier,
        "exact_applicability": record.identifier,
        "source_authority": record.source_authority,
        "source_reference": record.source_reference,
        "provider": {key: l2["provider"][key] for key in
                     ("provider_id", "version", "source_commit", "target_config", "flash_driver")},
        "profile": {key: l2["programming"][key] for key in
                    ("programming_profile_id", "memory_geometry_profile_id", "flash_geometry")},
        "operations": l2["operations"],
        "review_status": "ADMITTED", "reviewer": "test-reviewer",
        "fact_references": {key: "test-document section 1" for key in
                            ("identity", "route", "geometry", "operations")},
    }
    evidence_path.write_text(json.dumps(reviewed), encoding="utf-8")
    l2["publication_evidence"] = {
        "manufacturer": record.vendor, "exact_icpn": record.identifier,
        "source_authority": record.source_authority, "source_reference": record.source_reference,
        "source_path": str(evidence_path),
        "source_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "provider_id": l2["provider"]["provider_id"],
        "provider_version": l2["provider"]["version"],
        "profile_id": l2["programming"]["programming_profile_id"],
    }


def test_data_only_publish_l1_search_rollback_and_audit(tmp_path: Path, monkeypatch) -> None:
    repo, initial, record, l1, _ = _publisher_fixture(tmp_path)
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(repo.path))
    assert selector.search_response("q=STM32F103C8T6-TEST-EXACT")[1]["total_count"] == 0
    stage = repo.stage_revision([{"record": asdict(record), "qualification": l1}], actor="catalog-owner")
    assert repo.read_active().revision_sha256 == initial
    published = repo.publish_staged(stage, actor="catalog-owner")
    assert published != initial
    assert repo.publish_staged(stage, actor="catalog-owner") == published
    status, body = selector.search_response("q=STM32F103C8T6-TEST-EXACT")
    assert status == 200 and body["total_count"] == 1
    item = body["results"][0]
    assert item["catalog_level"] == 1 and item["job_selectable"] is False
    assert item["catalog"]["revision_sha256"] != record.catalog_revision_sha256
    assert item["selected_profile"] is None
    assert item["manufacturer_device_basic_profile"] is None
    assert item["backend_providers"] == []
    assert selector.search_response("q=STM32F103C8T6-TEST-EXACT&levels=2,3")[1]["total_count"] == 0
    repo.rollback(initial, actor="catalog-owner")
    assert repo.read_active().revision_sha256 == initial
    assert selector.search_response("q=STM32F103C8T6-TEST-EXACT")[1]["total_count"] == 0
    with sqlite3.connect(repo.path) as conn:
        actions = [row[0] for row in conn.execute("SELECT action FROM catalog_audit_events ORDER BY event_id")]
    assert actions == ["STAGE", "PUBLISH", "ROLLBACK"]


def test_l1_to_l2_requires_evidence_and_known_provider_profile(tmp_path: Path, monkeypatch) -> None:
    repo, initial, record, l1, supported = _publisher_fixture(tmp_path)
    baseline_l3 = {key for key, q in repo.read_active().qualifications.items()
                   if q["catalog_level"] == 3}
    repo.publish_staged(repo.stage_revision([{"record": asdict(record), "qualification": l1}], actor="owner"), actor="owner")
    l2 = json.loads(json.dumps(supported))
    l2.update(catalog_level=2, catalog_level_state="PROGRAMMABLE", ppu_ready=False,
              socket_ready=False, ppu_readiness_source=None, family_ready=None,
              verified_configurations=[])
    evidence_path = tmp_path / "reviewed-source.json"
    reviewed = {
        "schema_version": "catalog-l2-reviewed-evidence-v1",
        "manufacturer": record.vendor, "exact_icpn": record.identifier,
        "exact_applicability": record.identifier,
        "source_authority": record.source_authority,
        "source_reference": record.source_reference,
        "provider": {key: l2["provider"][key] for key in
                     ("provider_id", "version", "source_commit", "target_config", "flash_driver")},
        "profile": {key: l2["programming"][key] for key in
                    ("programming_profile_id", "memory_geometry_profile_id", "flash_geometry")},
        "operations": l2["operations"],
        "review_status": "ADMITTED", "reviewer": "test-reviewer",
        "fact_references": {key: "test-document section 1" for key in
                            ("identity", "route", "geometry", "operations")},
    }
    evidence_path.write_text(json.dumps(reviewed), encoding="utf-8")
    l2["publication_evidence"] = {
        "manufacturer": record.vendor, "exact_icpn": record.identifier,
        "source_authority": record.source_authority, "source_reference": record.source_reference,
        "source_path": str(evidence_path),
        "source_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "provider_id": l2["provider"]["provider_id"],
        "provider_version": l2["provider"]["version"],
        "profile_id": l2["programming"]["programming_profile_id"],
    }
    with pytest.raises(DeviceCatalogIntegrityError, match="evidence"):
        repo.stage_revision([{"record": asdict(record), "qualification": {**l2, "publication_evidence": None}}], actor="owner")
    bad = json.loads(json.dumps(l2))
    bad["provider"]["provider_id"] = "invented-provider"
    with pytest.raises(DeviceCatalogIntegrityError, match="evidence"):
        repo.stage_revision([{"record": asdict(record), "qualification": bad}], actor="owner")
    for field, value in (("exact_applicability", "different-part"), ("review_status", "CANDIDATE")):
        mismatched = {**reviewed, field: value}
        evidence_path.write_text(json.dumps(mismatched), encoding="utf-8")
        bad = json.loads(json.dumps(l2))
        bad["publication_evidence"]["source_sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        with pytest.raises(DeviceCatalogIntegrityError, match="reviewed facts"):
            repo.stage_revision([{"record": asdict(record), "qualification": bad}], actor="owner")
    evidence_path.write_text(json.dumps(reviewed), encoding="utf-8")
    bad = json.loads(json.dumps(l2))
    bad["programming"]["programming_profile_id"] = "wrong-profile"
    with pytest.raises(DeviceCatalogIntegrityError, match="evidence"):
        repo.stage_revision([{"record": asdict(record), "qualification": bad}], actor="owner")
    with pytest.raises(DeviceCatalogIntegrityError, match="exact ICPN/source applicability"):
        repo.stage_revision([{"record": asdict(record), "qualification": l2}], actor="owner")
    assert repo.read_active().qualifications[(record.vendor.casefold(), record.identifier.casefold())]["catalog_level"] == 1
    assert {key for key, q in repo.read_active().qualifications.items() if q["catalog_level"] == 3} == baseline_l3


def test_l1_to_l2_uses_existing_exact_provider_applicability(tmp_path: Path, monkeypatch) -> None:
    registry = get_default_programming_qualification_registry()
    catalog = get_default_device_catalog()
    record = next(row for row in catalog.records if row.identifier == "STM32F103C8T6")
    supported = registry.describe(record.vendor, record.identifier)
    l1 = json.loads(json.dumps(supported))
    l1.update(catalog_level=1, catalog_level_state="PROGRAMMING_CANDIDATE", state="CANDIDATE",
              reviewed=False, job_selectable=False, provider=None, programming=None,
              operations={}, ppu_ready=False, socket_ready=False, verified_configurations=[])
    class L1Baseline:
        _catalog = catalog
        def describe(self, manufacturer, exact_icpn):
            return l1 if (manufacturer, exact_icpn) == (record.vendor, record.identifier) else registry.describe(manufacturer, exact_icpn)
    repo = CatalogSqliteShadowRepository(tmp_path / "promote.sqlite3")
    initial = repo.import_verified_manifest(default_catalog_manifest_path(), qualification_registry=L1Baseline())
    l2 = json.loads(json.dumps(supported))
    l2.update(catalog_level=2, catalog_level_state="PROGRAMMABLE", ppu_ready=False,
              socket_ready=False, ppu_readiness_source=None, family_ready=None,
              verified_configurations=[])
    evidence_path = tmp_path / "reviewed-source.json"
    _reviewed_l2_packet(record, l2, evidence_path)
    bad = json.loads(json.dumps(l2))
    bad["programming"]["flash_geometry"]["main_flash_start"] = "0x08001000"
    _reviewed_l2_packet(record, bad, evidence_path)
    with pytest.raises(DeviceCatalogIntegrityError, match="Provider/Profile/geometry/operations"):
        repo.stage_revision([{"record": asdict(record), "qualification": bad}], actor="owner")
    bad = json.loads(json.dumps(l2))
    bad["operations"]["erase"]["basis"] = "invented"
    _reviewed_l2_packet(record, bad, evidence_path)
    with pytest.raises(DeviceCatalogIntegrityError, match="Provider/Profile/geometry/operations"):
        repo.stage_revision([{"record": asdict(record), "qualification": bad}], actor="owner")
    bad_record = replace(record, source_reference="https://example.test/forged-source")
    bad = json.loads(json.dumps(l2))
    _reviewed_l2_packet(bad_record, bad, evidence_path)
    with pytest.raises(DeviceCatalogIntegrityError, match="exact ICPN/source applicability"):
        repo.stage_revision([{"record": asdict(bad_record), "qualification": bad}], actor="owner")
    bad = json.loads(json.dumps(l2))
    bad["physical_programming_qualified"] = True
    _reviewed_l2_packet(record, bad, evidence_path)
    with pytest.raises(DeviceCatalogIntegrityError, match="L2 cannot claim physical qualification"):
        repo.stage_revision([{"record": asdict(record), "qualification": bad}], actor="owner")
    _reviewed_l2_packet(record, l2, evidence_path)
    stage = repo.stage_revision([{"record": asdict(record), "qualification": l2}], actor="owner")
    source_bytes = evidence_path.read_bytes()
    evidence_path.write_text("tampered", encoding="utf-8")
    before = repo.read_active().revision_sha256
    with pytest.raises(DeviceCatalogIntegrityError, match="evidence bytes"):
        repo.publish_staged(stage, actor="owner")
    assert repo.read_active().revision_sha256 == before
    evidence_path.write_bytes(source_bytes)
    revision = repo.publish_staged(stage, actor="owner")
    catalog, qualifications, _ = read_selector_view(str(repo.path))
    assert catalog.resolve(record.vendor, record.identifier)
    assert qualifications[(record.vendor.casefold(), record.identifier.casefold())]["catalog_level"] == 2
    assert "source_path" not in qualifications[(record.vendor.casefold(), record.identifier.casefold())]["publication_evidence"]
    assert qualifications[(record.vendor.casefold(), record.identifier.casefold())]["publication_evidence"]["reviewer"] == "test-reviewer"
    assert set(qualifications[(record.vendor.casefold(), record.identifier.casefold())]["publication_evidence"]["fact_references"]) == {"identity", "route", "geometry", "operations"}
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(repo.path))
    status, body = selector.search_response("q=STM32F103C8T6&levels=2,3")
    assert status == 200 and body["total_count"] >= 1
    matching = next(item for item in body["results"] if item["icpn"] == record.identifier)
    assert matching["programming_qualification"]["provider"]["provider_id"] == "openocd-upstream"
    assert revision != initial


def test_rollback_rejects_cross_revision_l3_loss_without_audit(tmp_path: Path) -> None:
    registry = get_default_programming_qualification_registry()
    catalog = get_default_device_catalog()
    record = next(row for row in catalog.records if row.identifier == "STM32F103C8T6")
    supported = registry.describe(record.vendor, record.identifier)
    l1 = json.loads(json.dumps(supported))
    l1.update(catalog_level=1, catalog_level_state="PROGRAMMING_CANDIDATE", state="CANDIDATE",
              reviewed=False, job_selectable=False, provider=None, programming=None,
              operations={}, ppu_ready=False, socket_ready=False, verified_configurations=[])
    class L1Baseline:
        _catalog = catalog
        def describe(self, manufacturer, exact_icpn):
            return l1 if (manufacturer, exact_icpn) == (record.vendor, record.identifier) else registry.describe(manufacturer, exact_icpn)
    repo = CatalogSqliteShadowRepository(tmp_path / "rollback-l3.sqlite3")
    older = repo.import_verified_manifest(default_catalog_manifest_path(), qualification_registry=L1Baseline())
    l3 = json.loads(json.dumps(supported))
    _reviewed_l2_packet(record, l3, tmp_path / "l3-reviewed.json")
    active = repo.publish_staged(
        repo.stage_revision([{"record": asdict(record), "qualification": l3}], actor="owner"), actor="owner"
    )
    with sqlite3.connect(repo.path) as conn:
        audit_before = conn.execute("SELECT count(*) FROM catalog_audit_events").fetchone()[0]
    with pytest.raises(DeviceCatalogIntegrityError, match="L3 revision"):
        repo.rollback(older, actor="owner")
    assert repo.read_active().revision_sha256 == active
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute("SELECT count(*) FROM catalog_audit_events").fetchone()[0] == audit_before


def test_rejected_publication_keeps_active_and_local_namespace_isolated(tmp_path: Path) -> None:
    repo, initial, record, l1, supported = _publisher_fixture(tmp_path)
    duplicate = [{"record": asdict(record), "qualification": l1}] * 2
    with pytest.raises(DeviceCatalogIntegrityError, match="duplicate"):
        repo.stage_revision(duplicate, actor="owner")
    stage = repo.stage_revision([{"record": asdict(record), "qualification": l1}], actor="owner")
    with pytest.raises(DeviceCatalogIntegrityError, match="actor mismatch"):
        repo.publish_staged(stage, actor="other")
    assert repo.read_active().revision_sha256 == initial
    existing = next(row for row in repo.read_active().catalog.records if row.identifier == "STM32F103C8T6")
    downgrade = {**supported, "catalog_level": 1, "catalog_level_state": "PROGRAMMING_CANDIDATE",
                 "state": "CANDIDATE", "job_selectable": False, "provider": None, "programming": None,
                 "ppu_ready": False, "socket_ready": False, "verified_configurations": [],
                 "route_evidence": existing.source_reference}
    degrade_stage = repo.stage_revision([{"record": asdict(existing), "qualification": downgrade}], actor="owner")
    with pytest.raises(DeviceCatalogIntegrityError, match="L3 revision"):
        repo.publish_staged(degrade_stage, actor="owner")
    assert repo.read_active().revision_sha256 == initial
    profile = {"profile_id": "local-v1", "official": False, "execution_authorized": False,
               "catalog_level": 1}
    repo.put_local_profile("controller-a", record.vendor, record.identifier, profile, actor="owner")
    assert repo.get_local_profile("controller-a", record.vendor, record.identifier) == profile
    assert repo.get_local_profile("controller-b", record.vendor, record.identifier) is None
    with pytest.raises(DeviceCatalogIntegrityError, match="official L2"):
        repo.put_local_profile("controller-a", record.vendor, record.identifier,
                               {**profile, "catalog_level": 2}, actor="owner")
    with pytest.raises(DeviceCatalogIntegrityError, match="official L2"):
        repo.put_local_profile("controller-a", record.vendor, record.identifier,
                               {**profile, "job_selectable": True}, actor="owner")
    with pytest.raises(DeviceCatalogIntegrityError, match="official L2"):
        repo.put_local_profile("controller-a", record.vendor, record.identifier,
                               {**profile, "state": "SUPPORTED"}, actor="owner")
    assert repo.read_active().revision_sha256 == initial


def test_readers_observe_complete_revision_during_publish(tmp_path: Path) -> None:
    repo, initial, record, l1, _ = _publisher_fixture(tmp_path)
    stage = repo.stage_revision([{"record": asdict(record), "qualification": l1}], actor="owner")
    observed: list[tuple[str, int]] = []
    failures: list[Exception] = []
    def reader() -> None:
        try:
            for _ in range(25):
                snapshot = repo.read_active()
                observed.append((snapshot.revision_sha256, snapshot.size))
        except Exception as exc:
            failures.append(exc)
    threads = [threading.Thread(target=reader) for _ in range(3)]
    for thread in threads:
        thread.start()
    published = repo.publish_staged(stage, actor="owner")
    for thread in threads:
        thread.join()
    assert not failures
    assert set(observed) <= {(initial, repo.read_active().size - 1), (published, repo.read_active().size)}
