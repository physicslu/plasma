from __future__ import annotations

import csv
import json
from pathlib import Path

from plasma_web.device_catalog import DeviceCatalog, get_default_device_catalog


EXPECTED_PRODUCTION_CATALOG_SIZE = 432
EXPECTED_STM32F4_CATALOG_SIZE = 357


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


def test_checked_in_production_catalog_contains_only_current_admitted_exact_icpns() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE
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
    foundation_batch3 = catalog.search("stm32f412zet7tr", limit=1)[0]
    foundation_batch4 = catalog.search("stm32f427zit7tr", limit=1)[0]
    foundation_batch5 = catalog.search("stm32f437zit7tr", limit=1)[0]
    foundation_batch6 = catalog.search("stm32f413zgj6tr", limit=1)[0]
    foundation_batch7 = catalog.search("stm32f439zgt7tr", limit=1)[0]
    foundation_batch8 = catalog.search("stm32f417vet6tr", limit=1)[0]
    foundation_batch9 = catalog.search("stm32f469vit6tr", limit=1)[0]
    foundation_batch10 = catalog.search("stm32f479vit6", limit=1)[0]
    foundation_batch11 = catalog.search("stm32f479zit6", limit=1)[0]
    rt_batch2 = catalog.search("stm32f405rgt7tr", limit=1)[0]
    rt_batch3 = catalog.search("stm32f413rgt6tr", limit=1)[0]
    rt_batch4 = catalog.search("stm32f446ret7tr", limit=1)[0]
    phase42b = catalog.search("stm32f410cbt6", limit=1)[0]
    phase42f = catalog.search("stm32f412rgy6ptr", limit=1)[0]
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
    assert foundation_batch3.identifier == "STM32F412ZET7TR"
    assert foundation_batch3.package == "LQFP"
    assert foundation_batch3.pin_count == "144"
    assert foundation_batch3.flash_size == "512 KiB"
    assert foundation_batch3.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation_batch4.identifier == "STM32F427ZIT7TR"
    assert foundation_batch4.package == "LQFP"
    assert foundation_batch4.pin_count == "144"
    assert foundation_batch4.flash_size == "2048 KiB"
    assert foundation_batch4.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation_batch5.identifier == "STM32F437ZIT7TR"
    assert foundation_batch5.package == "LQFP"
    assert foundation_batch5.pin_count == "144"
    assert foundation_batch5.flash_size == "2048 KiB"
    assert foundation_batch5.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation_batch6.identifier == "STM32F413ZGJ6TR"
    assert foundation_batch6.package == "UFBGA"
    assert foundation_batch6.pin_count == "144"
    assert foundation_batch6.flash_size == "1024 KiB"
    assert foundation_batch6.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation_batch7.identifier == "STM32F439ZGT7TR"
    assert foundation_batch7.package == "LQFP"
    assert foundation_batch7.pin_count == "144"
    assert foundation_batch7.flash_size == "1024 KiB"
    assert foundation_batch7.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation_batch8.identifier == "STM32F417VET6TR"
    assert foundation_batch8.package == "LQFP"
    assert foundation_batch8.pin_count == "100"
    assert foundation_batch8.flash_size == "512 KiB"
    assert foundation_batch8.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation_batch9.identifier == "STM32F469VIT6TR"
    assert foundation_batch9.package == "LQFP"
    assert foundation_batch9.pin_count == "100"
    assert foundation_batch9.flash_size == "2048 KiB"
    assert foundation_batch9.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation_batch10.identifier == "STM32F479VIT6"
    assert foundation_batch10.package == "LQFP"
    assert foundation_batch10.pin_count == "100"
    assert foundation_batch10.flash_size == "2048 KiB"
    assert foundation_batch10.target_config == "tcl/target/stm32f4x.cfg"
    assert foundation_batch11.identifier == "STM32F479ZIT6"
    assert foundation_batch11.package == "LQFP"
    assert foundation_batch11.pin_count == "144"
    assert foundation_batch11.flash_size == "2048 KiB"
    assert foundation_batch11.target_config == "tcl/target/stm32f4x.cfg"
    assert rt_batch2.identifier == "STM32F405RGT7TR"
    assert rt_batch2.family == "STM32F4"
    assert rt_batch2.target_config == "tcl/target/stm32f4x.cfg"
    assert rt_batch3.identifier == "STM32F413RGT6TR"
    assert rt_batch3.family == "STM32F4"
    assert rt_batch3.target_config == "tcl/target/stm32f4x.cfg"
    assert rt_batch4.identifier == "STM32F446RET7TR"
    assert rt_batch4.family == "STM32F4"
    assert rt_batch4.package == "LQFP"
    assert rt_batch4.pin_count == "64"
    assert rt_batch4.flash_size == "512 KiB"
    assert rt_batch4.target_config == "tcl/target/stm32f4x.cfg"
    assert phase42b.identifier == "STM32F410CBT6"
    assert phase42b.family == "STM32F4"
    assert phase42b.package == "LQFP"
    assert phase42b.pin_count == "48"
    assert phase42b.flash_size == "128 KiB"
    assert phase42b.target_config == "tcl/target/stm32f4x.cfg"
    assert phase42f.identifier == "STM32F412RGY6PTR"
    assert phase42f.family == "STM32F4"
    assert phase42f.package == "WLCSP"
    assert phase42f.pin_count == "64"
    assert phase42f.flash_size == "1024 KiB"
    assert phase42f.option_suffix == "PTR"
    assert phase42f.target_config == "tcl/target/stm32f4x.cfg"
    # Search results remain capped at 100 while metadata proves the full F4 family.
    assert len(family) == 100
    assert len(combined) == 100


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
    assert metadata["catalog_size"] == EXPECTED_PRODUCTION_CATALOG_SIZE
    assert metadata["source_count"] == 2
    assert metadata["taxonomy"] == [
        {
            "vendor": "STMicroelectronics",
            "count": EXPECTED_PRODUCTION_CATALOG_SIZE,
            "families": [
                {"family": "STM32F1", "count": 75},
                {"family": "STM32F4", "count": EXPECTED_STM32F4_CATALOG_SIZE},
            ],
        }
    ]
