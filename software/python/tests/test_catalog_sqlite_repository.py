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
from plasma_web import catalog_sqlite_repository as catalog_repository_module
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
        "schema_version": "catalog-l2-reviewed-evidence-v2",
        "manufacturer": record.vendor, "exact_icpn": record.identifier,
        "exact_applicability": record.identifier,
        "source_authority": record.source_authority,
        "source_reference": record.source_reference,
        "provider": {key: l2["provider"][key] for key in
                     ("provider_id", "version", "source_commit", "target_config", "flash_driver")},
        "profile": {key: l2["programming"][key] for key in
                    ("programming_profile_id", "memory_geometry_profile_id", "flash_geometry")},
        "operations": l2["operations"],
        "official_exact_source": None, "applicability": None,
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
        "schema_version": "catalog-l2-reviewed-evidence-v2",
        "manufacturer": record.vendor, "exact_icpn": record.identifier,
        "exact_applicability": record.identifier,
        "source_authority": record.source_authority,
        "source_reference": record.source_reference,
        "provider": {key: l2["provider"][key] for key in
                     ("provider_id", "version", "source_commit", "target_config", "flash_driver")},
        "profile": {key: l2["programming"][key] for key in
                    ("programming_profile_id", "memory_geometry_profile_id", "flash_geometry")},
        "operations": l2["operations"],
        "official_exact_source": None, "applicability": None,
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
    with pytest.raises(DeviceCatalogIntegrityError, match="exact applicability authority missing"):
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
    stored_path = repo._evidence_file(hashlib.sha256(source_bytes).hexdigest())
    stored_path.write_text("tampered", encoding="utf-8")
    before = repo.read_active().revision_sha256
    with pytest.raises(DeviceCatalogIntegrityError, match="Evidence content digest"):
        repo.publish_staged(stage, actor="owner")
    assert repo.read_active().revision_sha256 == before
    stored_path.write_bytes(source_bytes)
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


def test_new_exact_data_only_l1_to_l2_uses_official_source_and_provider_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plasma_web.openocd_software_qualification import (
        APPLICABILITY_REL, get_default_openocd_software_qualification_registry,
    )

    registry = get_default_programming_qualification_registry()
    provider = get_default_openocd_software_qualification_registry()
    assert provider is not None
    record = registry._catalog.resolve("STMicroelectronics", "STM32F103T8U6")
    assert record is not None and registry.describe(record.vendor, record.identifier)["catalog_level"] == 1
    assert (record.vendor, record.identifier) not in provider.reviewed_exact_keys
    repo = CatalogSqliteShadowRepository(tmp_path / "data-only-l2.sqlite3")
    initial = repo.import_verified_manifest(default_catalog_manifest_path(), qualification_registry=registry)
    initial_l3 = {key: value for key, value in repo.read_active().qualifications.items()
                  if value["catalog_level"] == 3}
    # A pure data revision can be published while the product software stays fixed.
    l1 = registry.describe(record.vendor, record.identifier)
    stage_l1 = repo.stage_revision([{"record": asdict(record), "qualification": l1}], actor="owner")
    l1_revision = repo.publish_staged(stage_l1, actor="owner")
    assert l1_revision != initial

    reference = registry.describe("STMicroelectronics", "STM32F103C8T6")
    l2 = json.loads(json.dumps(reference))
    geometry_id = "stm32f103t8-64k-catalog-v1"
    l2.update(registry_id="catalog-data-only-openocd-stm32f103-medium-v1",
              catalog_level=2, catalog_level_state="PROGRAMMABLE", ppu_ready=False,
              socket_ready=False, ppu_readiness_source=None, family_ready=None,
              verified_configurations=[])
    l2["programming"]["memory_geometry_profile_id"] = geometry_id
    source_url = "https://www.st.com/en/microcontrollers-microprocessors/stm32f103t8.html"
    official_bytes = b"<html><title>STM32F103T8 - ST</title><body>Part Number: STM32F103T8U6, STM32F103T8U6TR</body></html>"
    source_response = [official_bytes]
    fetches = []
    def fetch(url):
        fetches.append(url)
        return source_response[0] if url == source_url else b""
    monkeypatch.setattr(CatalogSqliteShadowRepository, "_fetch_official_exact_source",
                        staticmethod(fetch))
    exact_evidence_id = repo.acquire_exact_evidence(record, kind="manufacturer_https", source_revision="st-page-v1")
    assert repo.acquire_exact_evidence(record, kind="manufacturer_https", source_revision="st-page-v1") == exact_evidence_id
    assert fetches == [source_url]
    applicability = json.loads((provider._root / APPLICABILITY_REL).read_text(encoding="utf-8"))
    ordering_lock = applicability["manufacturer_authority"]["ordering"]
    authority = json.loads((provider._root / ordering_lock["path"]).read_text(encoding="utf-8"))
    packet_path = tmp_path / "data-only-reviewed.json"
    _reviewed_l2_packet(record, l2, packet_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["official_exact_source"] = {"kind": "manufacturer_https", "url": source_url,
                                       "sha256": hashlib.sha256(official_bytes).hexdigest(),
                                       "evidence_id": exact_evidence_id}
    group = provider._programming_groups_by_profile["stm32f1-medium-density-flash-v0"]
    packet["applicability"] = {
        "base_device": record.base_device,
        "density_class": "medium",
        "ordering_authority_id": authority["authority_id"],
        "ordering_source_blob": ordering_lock["git_blob_sha1"],
        "provider_source_lock_id": provider.source_lock_id,
        "programming_group_id": provider._programming_groups_by_profile[
            "stm32f1-medium-density-flash-v0"]["group_id"],
        "geometry_id": geometry_id,
        "package_route": {
            "package": "VFQFPN36", "transport": "SWD",
            "swdio": {"signal": "PA13", "pin": 25},
            "swclk": {"signal": "PA14", "pin": 28},
            "source_document": "DS5319 Rev 20",
            "source_locator": "Table 5, VFQFPN36 pin definitions",
            "source_sha256": group["manufacturer_evidence"]["source_lock"]["st_ds5319_rev20"],
        },
    }
    packet["fact_references"] = {
        "identity": f"{source_url}#{record.identifier}",
        "route": f"{provider.source_lock_id}#{provider.provider['target_config']}",
        "geometry": (f"{record.source_reference}#DS5319 Rev 20;"
                     f"st_pm0075_rev2:{group['manufacturer_evidence']['source_lock']['st_pm0075_rev2']}"),
        "operations": f"{provider.qualification_id}#{group['group_id']}",
    }
    def stage_packet(candidate: dict, *, candidate_record=record) -> str:
        packet_path.write_text(json.dumps(candidate), encoding="utf-8")
        l2["publication_evidence"]["source_sha256"] = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        return repo.stage_revision([{"record": asdict(candidate_record), "qualification": l2}], actor="owner")

    for field, replacement, error in (
        ("official_exact_source", {**packet["official_exact_source"], "sha256": "0" * 64}, "official Exact source"),
        ("applicability", {**packet["applicability"], "density_class": "high"}, "exact applicability"),
        ("applicability", {**packet["applicability"], "package_route": {
            **packet["applicability"]["package_route"], "swclk": {"signal": "PA14", "pin": 27}
        }}, "exact applicability"),
        ("fact_references", {**packet["fact_references"], "identity": "invented reference"}, "exact applicability"),
    ):
        with pytest.raises(DeviceCatalogIntegrityError, match=error):
            stage_packet({**packet, field: replacement})
    source_response[0] = b"<html>STM32F103C8T6 only</html>"
    with pytest.raises(DeviceCatalogIntegrityError, match="official Exact source"):
        repo.acquire_exact_evidence(record, kind="manufacturer_https", source_revision="bad-page-v1")
    source_response[0] = b"<html>404: STM32F103T8U6</html>"
    with pytest.raises(DeviceCatalogIntegrityError, match="official Exact source"):
        repo.acquire_exact_evidence(record, kind="manufacturer_https", source_revision="bad-page-v2")
    source_response[0] = official_bytes
    monkeypatch.setattr(CatalogSqliteShadowRepository, "_fetch_official_exact_source",
                        staticmethod(lambda url: (_ for _ in ()).throw(AssertionError("HTTPS not used"))))
    bad = json.loads(json.dumps(l2))
    bad["programming"]["memory_geometry_profile_id"] = "stm32f103c8-64k-v0"
    bad_packet = json.loads(json.dumps(packet))
    bad_packet["profile"]["memory_geometry_profile_id"] = "stm32f103c8-64k-v0"
    packet_path.write_text(json.dumps(bad_packet), encoding="utf-8")
    bad["publication_evidence"]["source_sha256"] = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    with pytest.raises(DeviceCatalogIntegrityError, match="Geometry revision"):
        repo.stage_revision([{"record": asdict(record), "qualification": bad}], actor="owner")
    for mutate in (
        lambda q: q["provider"].update(version="0.99.0"),
        lambda q: q["programming"].update(programming_profile_id="another-mcu-profile"),
        lambda q: q["programming"]["flash_geometry"].update(
            main_flash_size_bytes=131072, page_count=128),
        lambda q: q["operations"]["read"].update(scope="invented capability"),
    ):
        bad = json.loads(json.dumps(l2))
        mutate(bad)
        _reviewed_l2_packet(record, bad, packet_path)
        bad_packet = json.loads(packet_path.read_text(encoding="utf-8"))
        bad_packet["official_exact_source"] = packet["official_exact_source"]
        bad_packet["applicability"] = packet["applicability"]
        bad_packet["fact_references"] = packet["fact_references"]
        packet_path.write_text(json.dumps(bad_packet), encoding="utf-8")
        bad["publication_evidence"]["source_sha256"] = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        with pytest.raises(DeviceCatalogIntegrityError, match="Provider/Profile/geometry/operations"):
            repo.stage_revision([{"record": asdict(record), "qualification": bad}], actor="owner")
    assert repo.read_active().revision_sha256 == l1_revision

    with patch("plasma_web.programming_qualification.get_default_programming_qualification_registry",
               side_effect=AssertionError("static Exact registry used by data-only Publisher")):
        stage = stage_packet(packet)
    with sqlite3.connect(repo.path) as conn:
        audit_before = conn.execute("SELECT count(*) FROM catalog_audit_events").fetchone()[0]
    source_response[0] = b"<html>changed official page</html>"
    official_path = repo._evidence_file(hashlib.sha256(official_bytes).hexdigest())
    official_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(DeviceCatalogIntegrityError, match="Evidence content digest"):
        repo.publish_staged(stage, actor="owner")
    assert repo.read_active().revision_sha256 == l1_revision
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute("SELECT count(*) FROM catalog_audit_events").fetchone()[0] == audit_before
    official_path.write_bytes(official_bytes)
    packet_path.unlink()
    repo = CatalogSqliteShadowRepository(repo.path)
    assert repo.acquire_exact_evidence(record, kind="manufacturer_https", source_revision="st-page-v1") == exact_evidence_id
    with patch("plasma_web.programming_qualification.get_default_programming_qualification_registry",
               side_effect=AssertionError("static Exact registry used by data-only Publisher")):
        l2_revision = repo.publish_staged(stage, actor="owner")
    snapshot = repo.read_active()
    assert l2_revision != l1_revision
    assert snapshot.qualifications[(record.vendor.casefold(), record.identifier.casefold())]["catalog_level"] == 2
    assert {key: value for key, value in snapshot.qualifications.items()
            if value["catalog_level"] == 3} == initial_l3
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(repo.path))
    status, body = selector.search_response("q=STM32F103T8U6&levels=2,3")
    assert status == 200
    exact = next(item for item in body["results"] if item["icpn"] == record.identifier)
    assert exact["job_selectable"] is True
    assert exact["programming_qualification"]["execution_authorized"] is False
    published_evidence = exact["programming_qualification"]["publication_evidence"]
    assert "source_path" not in published_evidence
    assert published_evidence["official_exact_source"] == packet["official_exact_source"]
    assert published_evidence["applicability"] == packet["applicability"]
    assert len(fetches) == 3  # one valid Acquire and two rejected invalid revisions
    with sqlite3.connect(repo.path) as conn:
        audit_before = conn.execute("SELECT count(*) FROM catalog_audit_events").fetchone()[0]
    official_path.unlink()
    repo.rollback(l1_revision, actor="owner")
    with pytest.raises(DeviceCatalogIntegrityError, match="Evidence content missing"):
        repo.rollback(l2_revision, actor="owner")
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute("SELECT count(*) FROM catalog_audit_events").fetchone()[0] == audit_before + 1
        assert conn.execute("SELECT revision_sha256 FROM active_catalog_revision").fetchone()[0] == l1_revision
    official_path.write_bytes(official_bytes)
    repo.rollback(l2_revision, actor="owner")
    assert repo.read_active().revision_sha256 == l2_revision
    repo.rollback(l1_revision, actor="owner")
    assert repo.read_active().revision_sha256 == l1_revision
    assert repo.read_active().qualifications[(record.vendor.casefold(), record.identifier.casefold())]["catalog_level"] == 1
    # A changed manufacturer page receives a new Evidence Revision; the old bytes remain.
    newer_bytes = official_bytes.replace(b"</body>", b" New revision</body>")
    monkeypatch.setattr(CatalogSqliteShadowRepository, "_fetch_official_exact_source",
                        staticmethod(lambda url: newer_bytes))
    newer_id = repo.acquire_exact_evidence(record, kind="manufacturer_https", source_revision="st-page-v2")
    assert newer_id != exact_evidence_id
    assert repo._read_evidence(exact_evidence_id)[1] == official_bytes
    assert repo._read_evidence(newer_id)[1] == newer_bytes
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute("SELECT count(*) FROM catalog_evidence WHERE source_authority='STMicroelectronics HTTPS'").fetchone()[0] == 2
    monkeypatch.setattr(CatalogSqliteShadowRepository, "_fetch_official_exact_source",
                        staticmethod(lambda url: (_ for _ in ()).throw(AssertionError("HTTPS not used"))))
    identity_lock = applicability["manufacturer_authority"]["production_exact_identity"]
    locked_evidence_id = repo.acquire_exact_evidence(
        record, kind="locked_production_identity", source_revision=identity_lock["git_blob_sha1"]
    )
    locked_packet = {**packet, "official_exact_source": {
        "kind": "locked_production_identity", "path": identity_lock["path"],
        "git_blob_sha1": identity_lock["git_blob_sha1"], "exact_icpn": record.identifier,
        "evidence_id": locked_evidence_id,
    }, "fact_references": {
        **packet["fact_references"], "identity": f"{identity_lock['path']}#{record.identifier}"
    }}
    with pytest.raises(DeviceCatalogIntegrityError, match="identity lock mismatch"):
        stage_packet({**locked_packet, "official_exact_source": {
            **locked_packet["official_exact_source"], "git_blob_sha1": "0" * 40
        }})
    locked_bytes = (provider._root / identity_lock["path"]).read_bytes()
    locked_path = repo._evidence_file(hashlib.sha256(locked_bytes).hexdigest())
    locked_path.write_text("tampered identity source", encoding="utf-8")
    with pytest.raises(DeviceCatalogIntegrityError, match="Evidence content digest"):
        stage_packet(locked_packet)
    locked_path.write_bytes(locked_bytes)
    monkeypatch.setattr(CatalogSqliteShadowRepository, "_fetch_official_exact_source",
                        staticmethod(lambda url: (_ for _ in ()).throw(AssertionError("HTTPS not used"))))
    locked_stage = stage_packet(locked_packet)
    locked_path.unlink()
    with sqlite3.connect(repo.path) as conn:
        audit_before = conn.execute("SELECT count(*) FROM catalog_audit_events").fetchone()[0]
    with pytest.raises(DeviceCatalogIntegrityError, match="Evidence content missing"):
        repo.publish_staged(locked_stage, actor="owner")
    assert repo.read_active().revision_sha256 == l1_revision
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute("SELECT count(*) FROM catalog_audit_events").fetchone()[0] == audit_before
    locked_path.write_bytes(locked_bytes)
    locked_revision = repo.publish_staged(locked_stage, actor="owner")
    assert locked_revision != l2_revision
    assert repo.read_active().qualifications[(record.vendor.casefold(), record.identifier.casefold())]["catalog_level"] == 2


def test_low_density_twelve_publish_from_l1_without_active_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections import Counter
    from plasma_web.openocd_software_qualification import _git_blob_sha1
    from plasma_web.runtime_evidence_root import default_runtime_evidence_root

    registry = get_default_programming_qualification_registry()
    catalog = get_default_device_catalog()
    root = default_runtime_evidence_root()
    qualification = json.loads((root / "release/openocd-qualification/"
                                "openocd-0.12.0-stm32f103-low-density-12-v1.json").read_text())
    qualification_sha = hashlib.sha256((root / "release/openocd-qualification/"
        "openocd-0.12.0-stm32f103-low-density-12-v1.json").read_bytes()).hexdigest()
    app_lock = qualification["applicability"]
    app = json.loads((root / app_lock["path"]).read_text())
    exacts = {item["icpn"] for item in app["records"]}
    excluded = set(app["excluded_exact_icpns"])
    assert len(exacts) == 12 and len(excluded) == 3 and not (exacts & excluded)
    records = [catalog.resolve("STMicroelectronics", name) for name in sorted(exacts)]
    assert all(records)

    def l1(record):
        value = json.loads(json.dumps(registry.describe(record.vendor, record.identifier)))
        value.update(state="CANDIDATE", reviewed=False, catalog_level=1,
                     catalog_level_state="PROGRAMMING_CANDIDATE", job_selectable=False,
                     provider=None, programming=None, operations={})
        return value

    class BeforePublication:
        _catalog = catalog

        def describe(self, vendor, icpn):
            record = catalog.resolve(vendor, icpn)
            return l1(record) if icpn in exacts else registry.describe(vendor, icpn)

    repo = CatalogSqliteShadowRepository(tmp_path / "low-density.sqlite3")
    before = repo.import_verified_manifest(default_catalog_manifest_path(),
                                           qualification_registry=BeforePublication())
    old = repo.read_active()
    assert Counter(q["catalog_level"] for q in old.qualifications.values()) == {
        0: 204, 1: 5604, 3: 77,
    }
    assert not any(q.get("programming", {}) and q["programming"].get("programming_profile_id") ==
                   "stm32f1-low-density-flash-v0" for q in old.qualifications.values())
    old_l3 = {key: (old.catalog.resolve(*key), q) for key, q in old.qualifications.items()
              if q["catalog_level"] == 3}
    identity_lock = app["production_catalog"]
    group = qualification["manufacturer_programming_group"]
    changes = []
    for record in records:
        candidate = json.loads(json.dumps(registry.describe(record.vendor, record.identifier)))
        candidate["catalog_level"] = 2
        candidate["catalog_level_state"] = "PROGRAMMABLE"
        packet_path = tmp_path / (record.identifier + ".json")
        _reviewed_l2_packet(record, candidate, packet_path)
        packet = json.loads(packet_path.read_text())
        evidence_id = repo.acquire_exact_evidence(
            record, kind="locked_production_identity",
            source_revision=identity_lock["git_blob_sha1"])
        packet["official_exact_source"] = {
            "kind": "locked_production_identity", "path": identity_lock["path"],
            "git_blob_sha1": identity_lock["git_blob_sha1"],
            "exact_icpn": record.identifier, "evidence_id": evidence_id,
        }
        app_row = next(row for row in app["records"] if row["icpn"] == record.identifier)
        packet["applicability"] = {
            "base_device": record.base_device, "density_class": "low",
            "provider_source_lock_id": qualification["provider_source_lock_id"],
            "programming_group_id": group["group_id"],
            "qualification_sha256": qualification_sha,
            "profile_git_blob_sha1": qualification["programming_profile"]["git_blob_sha1"],
            "geometry_git_blob_sha1": app_row["geometry_git_blob_sha1"],
            "exact_applicability_git_blob_sha1": app_lock["git_blob_sha1"],
        }
        packet["fact_references"] = {
            "identity": f"{identity_lock['path']}#{record.identifier}",
            "route": f"{qualification['provider_source_lock_id']}#{record.target_config}",
            "geometry": f"{app_row['geometry_profile_path']}#{app_row['geometry_git_blob_sha1']}",
            "operations": f"{qualification['qualification_id']}#{group['group_id']}",
        }
        packet_path.write_text(json.dumps(packet))
        candidate["publication_evidence"]["source_sha256"] = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        changes.append({"record": asdict(record), "qualification": candidate})
    with patch("plasma_web.programming_qualification.get_default_programming_qualification_registry",
               side_effect=AssertionError("static exact registry used by Publisher")):
        assert len(repo.validate_changes(changes)) == 12
    bad = json.loads(json.dumps(changes[0]))
    bad["qualification"]["programming"]["flash_geometry"]["page_count"] += 1
    with pytest.raises(DeviceCatalogIntegrityError, match="geometry|reviewed facts"):
        repo.stage_revision([bad], actor="owner")
    bad = json.loads(json.dumps(changes[0]))
    bad["qualification"]["operations"]["erase"]["scope"] = "full-bank erase"
    with pytest.raises(DeviceCatalogIntegrityError, match="reviewed facts"):
        repo.stage_revision([bad], actor="owner")
    bad = json.loads(json.dumps(changes[0]))
    bad["qualification"]["provider"]["version"] = "unreviewed"
    with pytest.raises(DeviceCatalogIntegrityError, match="evidence"):
        repo.stage_revision([bad], actor="owner")
    # A reviewed packet alone cannot promote a different, unqualified Provider.
    independent = json.loads(json.dumps(changes[0]))
    independent_path = tmp_path / (independent["record"]["identifier"] + ".json")
    original_packet = independent_path.read_bytes()
    independent_packet = json.loads(original_packet)
    independent["qualification"]["provider"]["provider_id"] = "unqualified-independent-provider"
    independent["qualification"]["publication_evidence"]["provider_id"] = "unqualified-independent-provider"
    independent_packet["provider"]["provider_id"] = "unqualified-independent-provider"
    independent_path.write_text(json.dumps(independent_packet))
    independent["qualification"]["publication_evidence"]["source_sha256"] = hashlib.sha256(
        independent_path.read_bytes()).hexdigest()
    with pytest.raises(DeviceCatalogIntegrityError, match="Provider/Profile/geometry/operations"):
        repo.stage_revision([independent], actor="owner")
    independent_path.write_bytes(original_packet)
    forged_authority = json.loads(original_packet)
    forged_authority["applicability"]["qualification_sha256"] = "0" * 64
    independent_path.write_text(json.dumps(forged_authority))
    forged = json.loads(json.dumps(changes[0]))
    forged["qualification"]["publication_evidence"]["source_sha256"] = hashlib.sha256(
        independent_path.read_bytes()).hexdigest()
    with pytest.raises(DeviceCatalogIntegrityError, match="qualification authority"):
        repo.stage_revision([forged], actor="owner")
    independent_path.write_bytes(original_packet)
    with pytest.raises(DeviceCatalogIntegrityError, match="duplicate exact ICPN"):
        repo.stage_revision([changes[0], changes[0]], actor="owner")
    with patch("plasma_web.programming_qualification.get_default_programming_qualification_registry",
               side_effect=AssertionError("static exact registry used by Publisher")):
        stage = repo.stage_revision(changes, actor="owner")
        assert repo.read_active().revision_sha256 == before
        published = repo.publish_staged(stage, actor="owner")
    assert published != before
    after = repo.read_active()
    assert Counter(q["catalog_level"] for q in after.qualifications.values()) == {
        0: 204, 1: 5592, 2: 12, 3: 77,
    }
    assert len(after.qualifications) == 5885
    assert {key: (after.catalog.resolve(*key), q) for key, q in after.qualifications.items()
            if q["catalog_level"] == 3} == old_l3
    assert all(after.qualifications[("stmicroelectronics", name.casefold())]["catalog_level"] == 1
               for name in excluded)
    assert len({key for key in after.qualifications}) == 5885
    for name in exacts:
        evidence = after.qualifications[("stmicroelectronics", name.casefold())]["publication_evidence"]
        assert evidence["reviewed_evidence_id"] and "source_path" not in evidence
        assert evidence["official_exact_source"]["evidence_id"]
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(repo.path))
    status, body = selector.search_response("q=STM32F103C4T6A&levels=2,3")
    assert status == 200 and body["results"][0]["catalog_level"] == 2
    repo.rollback(before, actor="owner")
    assert repo.read_active().revision_sha256 == before
    repo.rollback(published, actor="owner")
    assert repo.read_active().revision_sha256 == published


def test_locked_source_admits_new_profile_without_python_exact_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second source-locked Profile uses the same Publisher with no ID dispatch."""
    from plasma_web.openocd_software_qualification import _git_blob_sha1
    from plasma_web.runtime_evidence_root import default_runtime_evidence_root

    source_root = default_runtime_evidence_root()
    fixture_root = tmp_path / "authority"
    source_qual = json.loads((source_root / "release/openocd-qualification/"
        "openocd-0.12.0-stm32f103-low-density-12-v1.json").read_text())
    source_app = json.loads((source_root / source_qual["applicability"]["path"]).read_text())
    source_profile = json.loads((source_root / source_qual["programming_profile"]["path"]).read_text())
    record = get_default_device_catalog().resolve("STMicroelectronics", "STM32F103C4T6A")
    assert record is not None
    new_profile_id = "independent-locked-profile-v1"
    registry = get_default_programming_qualification_registry()
    repo = CatalogSqliteShadowRepository(tmp_path / "new-profile.sqlite3")
    repo.import_verified_manifest(default_catalog_manifest_path(), qualification_registry=registry)
    before = repo.read_active()
    assert all((q.get("programming") or {}).get("programming_profile_id") != new_profile_id
               for q in before.qualifications.values())

    def write_source(relative: str, content: bytes) -> None:
        target = fixture_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    app = json.loads(json.dumps(source_app))
    app["records"] = [row for row in app["records"] if row["icpn"] == record.identifier]
    app["records"][0]["programming_profile_id"] = new_profile_id
    app_path = "release/openocd-qualification/independent-profile-app-v1.json"
    app_bytes = json.dumps(app, sort_keys=True).encode()
    write_source(app_path, app_bytes)
    profile = json.loads(json.dumps(source_profile))
    profile["profile_id"] = new_profile_id
    profile_path = "data/ic-support/profiles/programming/independent-locked-profile-v1.json"
    profile_bytes = json.dumps(profile, sort_keys=True).encode()
    write_source(profile_path, profile_bytes)
    qualification = json.loads(json.dumps(source_qual))
    qualification["qualification_id"] = "independent-locked-profile-qualification-v1"
    qualification["applicability"] = {"path": app_path, "git_blob_sha1": _git_blob_sha1(app_bytes)}
    qualification["programming_profile"] = {"path": profile_path,
        "git_blob_sha1": _git_blob_sha1(profile_bytes), "profile_id": new_profile_id}
    qualification["manufacturer_programming_group"]["manufacturer_evidence"][
        "programming_profile_id"] = new_profile_id
    qualification["records"] = [row for row in qualification["records"]
        if row["icpn"] == record.identifier]
    qualification["records"][0]["programming_profile_id"] = new_profile_id
    qualification_bytes = json.dumps(qualification, sort_keys=True).encode()
    write_source("release/openocd-qualification/independent-profile-qualification-v1.json",
                 qualification_bytes)
    for relative in (qualification["source_lock"]["path"],
                     app["production_catalog"]["path"],
                     app["records"][0]["geometry_profile_path"]):
        write_source(relative, (source_root / relative).read_bytes())

    candidate = json.loads(json.dumps(registry.describe(record.vendor, record.identifier)))
    candidate["programming"]["programming_profile_id"] = new_profile_id
    packet_path = tmp_path / "independent-profile-reviewed.json"
    _reviewed_l2_packet(record, candidate, packet_path)
    packet = json.loads(packet_path.read_text())
    monkeypatch.setattr("plasma_web.runtime_evidence_root.default_runtime_evidence_root",
                        lambda: fixture_root)
    identity_lock = app["production_catalog"]
    identity_id = repo.acquire_exact_evidence(record, kind="locked_production_identity",
        source_revision=identity_lock["git_blob_sha1"])
    packet["official_exact_source"] = {"kind": "locked_production_identity",
        "path": identity_lock["path"], "git_blob_sha1": identity_lock["git_blob_sha1"],
        "exact_icpn": record.identifier, "evidence_id": identity_id}
    exact = app["records"][0]
    group = qualification["manufacturer_programming_group"]
    packet["applicability"] = {"base_device": record.base_device,
        "density_class": group["density_class"],
        "provider_source_lock_id": qualification["provider_source_lock_id"],
        "programming_group_id": group["group_id"],
        "qualification_sha256": hashlib.sha256(qualification_bytes).hexdigest(),
        "profile_git_blob_sha1": _git_blob_sha1(profile_bytes),
        "geometry_git_blob_sha1": exact["geometry_git_blob_sha1"],
        "exact_applicability_git_blob_sha1": _git_blob_sha1(app_bytes)}
    packet["fact_references"] = {"identity": f"{identity_lock['path']}#{record.identifier}",
        "route": f"{qualification['provider_source_lock_id']}#{record.target_config}",
        "geometry": f"{exact['geometry_profile_path']}#{exact['geometry_git_blob_sha1']}",
        "operations": f"{qualification['qualification_id']}#{group['group_id']}"}
    packet_path.write_text(json.dumps(packet))
    candidate["publication_evidence"]["source_sha256"] = hashlib.sha256(
        packet_path.read_bytes()).hexdigest()
    with patch("plasma_web.programming_qualification.get_default_programming_qualification_registry",
               side_effect=AssertionError("static Exact registry used by Publisher")):
        stage = repo.stage_revision([{"record": asdict(record), "qualification": candidate}],
                                    actor="owner")
        revision = repo.publish_staged(stage, actor="owner")
    assert revision != before.revision_sha256
    published = repo.read_active().qualifications[(record.vendor.casefold(), record.identifier.casefold())]
    assert published["programming"]["programming_profile_id"] == new_profile_id
    assert published["execution_authorized"] is False


def test_v2_schema_upgrade_keeps_revisions_and_audit(tmp_path: Path) -> None:
    repo = CatalogSqliteShadowRepository(tmp_path / "upgrade.sqlite3")
    revision = repo.import_verified_manifest(default_catalog_manifest_path())
    with sqlite3.connect(repo.path) as conn:
        conn.execute("DROP TABLE catalog_evidence")
        conn.execute("PRAGMA user_version=2")
        conn.execute("INSERT INTO catalog_audit_events(action,actor,detail) VALUES ('IMPORT','owner','v2')")
    assert repo.read_active().revision_sha256 == revision
    repo._store_evidence("test authority", "test source", "v1", b"persistent bytes")
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute("SELECT revision_sha256 FROM active_catalog_revision").fetchone()[0] == revision
        assert conn.execute("SELECT detail FROM catalog_audit_events").fetchone()[0] == "v2"


def test_official_exact_source_requires_manufacturer_https_and_bounded_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://www.st.com/en/microcontrollers-microprocessors/stm32f103t8.html"
    class Response:
        def __init__(self, final_url: str):
            self.final_url = final_url
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def geturl(self):
            return self.final_url
        def read(self, limit: int):
            assert limit <= 5_000_001
            return b"<html>STM32F103T8U6</html>"
    monkeypatch.setattr(catalog_repository_module, "urlopen",
                        lambda request, timeout: Response(request.full_url))
    assert CatalogSqliteShadowRepository._fetch_official_exact_source(url) == b"<html>STM32F103T8U6</html>"
    with pytest.raises(DeviceCatalogIntegrityError, match="outside admitted manufacturer scope"):
        CatalogSqliteShadowRepository._fetch_official_exact_source(
            "https://example.test/en/microcontrollers-microprocessors/stm32f103t8.html")
    monkeypatch.setattr(catalog_repository_module, "urlopen",
                        lambda request, timeout: Response("https://example.test/forged.html"))
    with pytest.raises(DeviceCatalogIntegrityError, match="redirected outside manufacturer scope"):
        CatalogSqliteShadowRepository._fetch_official_exact_source(url)


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


def test_customer_and_official_same_exact_icpn_coexist_across_publish_rollback(
    tmp_path: Path, monkeypatch,
) -> None:
    """Official and LOCAL are independent namespaces, not identity conflicts."""
    repo, initial, future_official_record, l1, _ = _publisher_fixture(tmp_path)
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(repo.path))
    entries = [
        {"record": {"vendor": "LocalVendor", "identifier": "CUSTOM-A"},
         "profile": {"profile_id": "customer-profile-a", "operations": ["program"]}},
        {"record": {"vendor": "LocalVendor", "identifier": "CUSTOM-B"},
         "profile": {"profile_id": "customer-profile-b", "operations": ["erase", "verify"]}},
    ]
    repo.save_local_records(entries, actor="customer")
    before = repo.local_records()
    assert len(before) == 2
    assert all(row["origin"] == "LOCAL" and row["verification"] == "UNVERIFIED" for row in before)
    assert repo.import_verified_manifest(
        default_catalog_manifest_path(),
        qualification_registry=get_default_programming_qualification_registry(),
    ) == initial
    assert repo.local_records() == before

    change = [{"record": asdict(future_official_record), "qualification": l1}]
    # Create the LOCAL identity after validation/staging to also prove that
    # an Official release can proceed if customers create matching ICPNs later.
    assert repo.validate_changes(change)[0]["status"] == "ADDED"
    stage = repo.stage_revision(change, actor="publisher")
    local_same_key = {
        "record": {"vendor": future_official_record.vendor,
                   "identifier": future_official_record.identifier},
        "profile": {"profile_id": "customer-custom-profile", "operations": ["program"]},
    }
    local_save = repo.save_local_records([local_same_key], actor="customer")
    assert local_save[0]["revision"] == 1
    preserved = repo.local_records()
    published = repo.publish_staged(stage, actor="publisher")
    assert published != initial
    assert repo.local_records() == preserved
    assert CatalogSqliteShadowRepository(repo.path).local_records() == preserved

    same_key = future_official_record.identifier
    status, payload = selector.search_response(f"q={same_key}")
    assert status == 200, payload
    official = next(row for row in payload["results"] if row["icpn"] == same_key)
    customer = next(row for row in payload["local_results"] if row["record"]["identifier"] == same_key)
    assert official["catalog_level"] == 1
    assert official["job_selectable"] is False
    assert customer["origin"] == "LOCAL"
    assert customer["verification"] == "UNVERIFIED"
    assert customer["profile"]["profile_id"] == "customer-custom-profile"
    assert all(row["origin"] == "LOCAL" for row in preserved)

    # Repeat LOCAL save on an already-Official identity: both must remain intact.
    assert repo.save_local_records([local_same_key], actor="customer")[0]["change"] == "UNCHANGED"
    assert repo.read_active().revision_sha256 == published
    assert repo.local_records() == preserved

    repo.rollback(initial, actor="publisher")
    assert repo.local_records() == preserved
    assert repo.read_active().revision_sha256 == initial
    # Re-publishing a previously staged Official snapshot must still be legal.
    second = repo.publish_staged(repo.stage_revision(change, actor="publisher"), actor="publisher")
    assert second == published
    assert repo.local_records() == preserved
    assert selector.search_response(f"q={same_key}")[0] == 200


def test_customer_profile_links_to_existing_official_ic_without_identity_or_qualification_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, initial, _, _, _ = _publisher_fixture(tmp_path)
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(repo.path))
    official = repo.read_active().catalog.resolve("STMicroelectronics", "STM32F103C8T6")
    assert official is not None
    customer = {
        "record": {"vendor": official.vendor, "identifier": official.identifier,
                   "family": "Customer F1", "package": "LQFP48", "flash_size": "64 KiB"},
        "profile": {"profile_id": "customer-f1-profile", "provider_id": "customer-vendor",
                    "operations": ["erase", "program"], "source_evidence": ["customer-provenance-1"]},
    }
    repo.save_local_records([customer], actor="owner")
    original = repo.local_records()[0]
    before = repo.read_active()
    assert repo.linked_customer_profiles() == []
    with pytest.raises(DeviceCatalogIntegrityError, match="same-IC confirmation"):
        repo.link_local_to_official(
            official.vendor, official.identifier, expected_local_revision=1,
            confirmed_same_ic=False, actor="owner",
        )
    with pytest.raises(DeviceCatalogIntegrityError, match="revision changed"):
        repo.link_local_to_official(
            official.vendor, official.identifier, expected_local_revision=2,
            confirmed_same_ic=True, actor="owner",
        )
    assert repo.local_records() == [original]

    linked = repo.link_local_to_official(
        official.vendor, official.identifier, expected_local_revision=1,
        confirmed_same_ic=True, actor="owner",
    )
    assert linked == {
        "manufacturer": official.vendor, "exact_icpn": official.identifier,
        "ic_origin": "OFFICIAL", "profile_origin": "CUSTOMER",
        "link_status": "ACTIVE", "local_revision": 1, "profile_id": "customer-f1-profile",
    }
    assert repo.local_records() == []
    with pytest.raises(DeviceCatalogIntegrityError, match="already linked to Official IC"):
        repo.save_local_records([customer], actor="owner")
    retained = CatalogSqliteShadowRepository(repo.path).linked_customer_profiles()[0]
    assert retained["record"] == original["record"]
    assert retained["profile"] == original["profile"]
    assert retained["revision"] == original["revision"]
    assert retained["ic_origin"] == "OFFICIAL"
    assert retained["profile_origin"] == "CUSTOMER"
    assert retained["verification"] == "UNVERIFIED"
    assert retained["official_link"]["official_revision_at_link"] == initial
    assert repo.read_active().revision_sha256 == before.revision_sha256
    assert repo.read_active().qualifications == before.qualifications
    assert [e["action"] for e in repo.history()["audit"]].count("LOCAL_LINK_OFFICIAL") == 1
    with pytest.raises(DeviceCatalogIntegrityError, match="not found"):
        repo.link_local_to_official(
            official.vendor, official.identifier, expected_local_revision=1,
            confirmed_same_ic=True, actor="owner",
        )
    status, response = selector.search_response("q=STM32F103C8T6&limit=1")
    assert status == 200
    result = response["results"][0]
    assert result["ic_origin"] == "OFFICIAL"
    assert result["linked_customer_profile"] == {
        "origin": "CUSTOMER", "profile_id": "customer-f1-profile",
        "local_revision": 1, "verification": "UNVERIFIED",
    }
    assert result["programming_qualification"] == before.qualifications[
        (official.vendor.casefold(), official.identifier.casefold())
    ]
    assert result["job_selectable"] is before.qualifications[
        (official.vendor.casefold(), official.identifier.casefold())
    ]["job_selectable"]


def test_link_does_not_allow_nonofficial_ic_and_survives_official_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, initial, future, l1, _ = _publisher_fixture(tmp_path)
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(repo.path))
    customer = {
        "record": {"vendor": future.vendor, "identifier": future.identifier,
                   "family": "Customer exact F1", "package": "LQFP48", "flash_size": "64 KiB"},
        "profile": {"profile_id": "customer-custom-f1", "operations": ["program"]},
    }
    repo.save_local_records([customer], actor="owner")
    with pytest.raises(DeviceCatalogIntegrityError, match="must be published"):
        repo.link_local_to_official(
            future.vendor, future.identifier, expected_local_revision=1,
            confirmed_same_ic=True, actor="owner",
        )
    assert repo.local_records()[0]["profile"]["profile_id"] == "customer-custom-f1"

    changes = [{"record": asdict(future), "qualification": l1}]
    published = repo.publish_staged(repo.stage_revision(changes, actor="publisher"), actor="publisher")
    assert repo.read_active().revision_sha256 == published
    repo.link_local_to_official(
        future.vendor, future.identifier, expected_local_revision=1,
        confirmed_same_ic=True, actor="owner",
    )
    assert repo.linked_customer_profiles()[0]["link_status"] == "ACTIVE"
    repo.rollback(initial, actor="publisher")
    preserved = repo.linked_customer_profiles()[0]
    assert preserved["link_status"] == "PENDING_OFFICIAL"
    assert preserved["ic_origin"] == "CUSTOMER"
    assert preserved["profile"]["profile_id"] == "customer-custom-f1"
    assert repo.local_records() == []
    pending_status, pending = selector.search_response("q=STM32F103C8T6-TEST-EXACT")
    assert pending_status == 200
    assert any(item["record"]["identifier"] == future.identifier for item in pending["local_results"])
    assert not any(item["identifier"] == future.identifier for item in pending["results"])
    revived = repo.publish_staged(repo.stage_revision(changes, actor="publisher"), actor="publisher")
    assert revived == published
    assert repo.linked_customer_profiles()[0]["link_status"] == "ACTIVE"
    assert repo.linked_customer_profiles()[0]["profile"] == preserved["profile"]


def test_management_local_batch_atomic_preview_and_selector_refresh(tmp_path: Path, monkeypatch) -> None:
    repo, initial, official_record, l1, _ = _publisher_fixture(tmp_path)
    monkeypatch.setenv(selector.SQLITE_SELECTOR_DB_ENV, str(repo.path))
    entry = {"record": {"vendor": "LocalVendor", "identifier": "LOCAL123", "family": "Demo", "package": "QFN", "flash_size": "64 KB"},
             "profile": {"profile_id": "custom-v1", "operations": ["erase", "program"]}}
    assert repo.save_local_records([entry], actor="test", dry_run=True)[0]["change"] == "ADDED"
    assert repo.local_records() == []
    saved = repo.save_local_records([entry], actor="test")
    assert saved[0]["revision"] == 1
    assert repo.save_local_records([entry], actor="test")[0]["change"] == "UNCHANGED"
    assert repo.local_records()[0]["revision"] == 1
    assert CatalogSqliteShadowRepository(repo.path).local_records()[0]["profile"]["profile_id"] == "custom-v1"
    response = selector.search_response("q=LOCAL123")[1]
    assert response["local_results"][0]["verification"] == "UNVERIFIED"
    assert response["results"] == []
    changed = json.loads(json.dumps(entry)); changed["profile"]["profile_id"] = "custom-v2"
    repo.save_local_records([changed], actor="test")
    assert repo.local_records()[0]["revision"] == 2
    forged = json.loads(json.dumps(entry)); forged["record"]["identifier"] = "FORGED1"; forged["profile"]["catalog_level"] = 2
    with pytest.raises(DeviceCatalogIntegrityError):
        repo.save_local_records([entry, forged], actor="test")
    assert len(repo.local_records()) == 1
    official = json.loads(json.dumps(entry)); official["record"].update(vendor="STMicroelectronics", identifier="STM32F103C8T6")
    coexistence = repo.save_local_records([official], actor="test", dry_run=True)
    assert coexistence[0]["change"] == "ADDED"
    assert coexistence[0]["origin"] == "LOCAL"
    assert coexistence[0]["verification"] == "UNVERIFIED"
    assert len(repo.local_records()) == 1
    assert repo.read_active().revision_sha256 == initial
    official_changes = [{"record": asdict(official_record), "qualification": l1}]
    assert repo.validate_changes(official_changes)[0]["status"] == "ADDED"
    assert repo.read_active().revision_sha256 == initial
    published = repo.publish_staged(repo.stage_revision(official_changes, actor="test"), actor="test")
    assert published != initial
    assert repo.local_records()[0]["revision"] == 2
    assert selector.search_response("q=STM32F103C8T6-TEST-EXACT")[1]["total_count"] == 1
    assert repo.history()["active_revision"] == published
    assert any(change["status"] == "REMOVED" for change in repo.diff_revision(initial))
    repo.rollback(initial, actor="test")
    assert repo.local_records()[0]["revision"] == 2
    repo.delete_local_record("LocalVendor", "LOCAL123", actor="test")
    assert repo.local_records() == []
    assert repo.read_active().revision_sha256 == initial
