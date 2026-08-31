from __future__ import annotations

import csv
import json
from pathlib import Path

from plasma_web.device_catalog import DeviceCatalog, get_default_device_catalog


LEGACY_COLUMNS = [
    "vendor",
    "family",
    "subfamily",
    "plasma_series",
    "part_number",
    "identifier_kind",
    "cpu_architectures",
    "target_config",
    "openocd_distribution",
    "mapping_status",
    "validation_status",
    "catalog_origin",
]


def _write_legacy_catalog(path: Path) -> None:
    rows = [
        ["Vendor A", "F1", "", "S1", "ABC123", "manufacturer_part_number", json.dumps(["ARM Cortex-M"]), "tcl/target/a.cfg", "upstream-openocd", "mapped", "not_verified", "test.csv"],
        ["Vendor A", "F1", "", "S1", "ABC1234", "cmsis_device_name", json.dumps(["ARM Cortex-M"]), "tcl/target/a.cfg", "upstream-openocd", "mapping_candidate", "not_verified", "test.csv"],
        ["Vendor B", "F2", "", "S2", "XABC123X", "manufacturer_part_number", json.dumps(["RISC-V"]), "tcl/target/b.cfg", "upstream-openocd", "mapping_candidate", "not_verified", "test.csv"],
        ["Vendor C", "F3", "", "S3", "ABC1XXX", "ordering_pattern", json.dumps(["ARM Cortex-M"]), "tcl/target/c.cfg", "upstream-openocd", "mapping_candidate", "not_verified", "test.csv"],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(LEGACY_COLUMNS)
        writer.writerows(rows)


def test_explicit_legacy_search_ranks_exact_then_prefix_then_partial_case_insensitively(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    _write_legacy_catalog(path)
    catalog = DeviceCatalog.from_csv(path)

    matches = catalog.search("abc123")

    assert [record.identifier for record in matches] == ["ABC123", "ABC1234", "XABC123X"]


def test_resolve_uses_server_catalog_identity_case_insensitively(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    _write_legacy_catalog(path)
    catalog = DeviceCatalog.from_csv(path)

    record = catalog.resolve("vendor a", "abc123")

    assert record is not None
    assert record.vendor == "Vendor A"
    assert record.identifier == "ABC123"
    assert catalog.resolve("Vendor A", "missing") is None


def test_empty_query_returns_no_results(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    _write_legacy_catalog(path)
    catalog = DeviceCatalog.from_csv(path)

    assert catalog.search("   ") == []


def test_search_limit_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    _write_legacy_catalog(path)
    catalog = DeviceCatalog.from_csv(path)

    for invalid in (0, 101, True):
        try:
            catalog.search("ABC", limit=invalid)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid limit was accepted: {invalid!r}")


def test_checked_in_production_catalog_contains_only_160_admitted_exact_icpns() -> None:
    catalog = get_default_device_catalog()

    assert catalog.size == 160
    assert catalog.catalog_id == "plasma-icpn"
    assert catalog.catalog_version == "1.0.0"
    assert catalog.status == "production"
    assert catalog.revision_sha256 is not None
    assert len(catalog.revision_sha256) == 64
    assert all(record.production_admitted for record in catalog.records)
    assert all(record.identifier_kind == "manufacturer_part_number" for record in catalog.records)
    assert all(record.icpn == record.identifier for record in catalog.records)
    assert {record.family for record in catalog.records} == {"STM32F1", "STM32F4"}


def test_production_search_supports_exact_icpn_and_taxonomy_queries() -> None:
    catalog = get_default_device_catalog()

    exact = catalog.search("stm32f407vgt6", limit=1)[0]
    batch1 = catalog.search("stm32f429zgy6tr", limit=1)[0]
    batch2 = catalog.search("stm32f437vgt7tr", limit=1)[0]
    phase40 = catalog.search("stm32f446zej7tr", limit=1)[0]
    foundation = catalog.search("stm32f405vgt7tr", limit=1)[0]
    family = catalog.search("STM32F4", limit=100)
    combined = catalog.search("STMicroelectronics STM32F4", limit=100)

    assert exact.identifier == "STM32F407VGT6"
    assert exact.package == "LQFP"
    assert exact.target_config == "tcl/target/stm32f4x.cfg"
    assert exact.mapping_status == "mapped"
    assert batch1.identifier == "STM32F429ZGY6TR"
    assert batch1.package == "WLCSP"
    assert batch1.target_config == "tcl/target/stm32f4x.cfg"
    assert batch2.identifier == "STM32F437VGT7TR"
    assert batch2.package == "LQFP"
    assert batch2.target_config == "tcl/target/stm32f4x.cfg"
    assert phase40.identifier == "STM32F446ZEJ7TR"
    assert phase40.package == "UFBGA"
    assert phase40.pin_count == "144"
    assert phase40.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation.identifier == "STM32F405VGT7TR"
    assert foundation.package == "LQFP"
    assert foundation.pin_count == "100"
    assert foundation.flash_size == "1024 KiB"
    assert foundation.target_config == "tcl/target/stm32f4x.cfg"
    assert len(family) == 85
    assert len(combined) == 85


def test_production_payload_separates_catalog_verification_from_physical_validation() -> None:
    record = get_default_device_catalog().search("STM32F103C8T6", limit=1)[0]
    payload = record.to_payload()

    assert payload["icpn"] == "STM32F103C8T6"
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["catalog"]["version"] == "1.0.0"
    assert payload["catalog_verification"]["status"].startswith("verified_")
    assert payload["backend"]["mapping_status"] == "mapped"
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_production_metadata_reports_vendor_family_taxonomy() -> None:
    metadata = get_default_device_catalog().metadata

    assert metadata["catalog_size"] == 160
    assert metadata["source_count"] == 2
    assert metadata["taxonomy"] == [
        {
            "vendor": "STMicroelectronics",
            "count": 160,
            "families": [
                {"family": "STM32F1", "count": 75},
                {"family": "STM32F4", "count": 85},
            ],
        }
    ]
