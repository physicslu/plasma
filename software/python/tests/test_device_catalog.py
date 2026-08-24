from __future__ import annotations

import csv
import json
from pathlib import Path

from plasma_web.device_catalog import DeviceCatalog, get_default_device_catalog


COLUMNS = [
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


def _write_catalog(path: Path) -> None:
    rows = [
        ["Vendor A", "F1", "", "S1", "ABC123", "manufacturer_part_number", json.dumps(["ARM Cortex-M"]), "tcl/target/a.cfg", "upstream-openocd", "mapped", "not_verified", "test.csv"],
        ["Vendor A", "F1", "", "S1", "ABC1234", "cmsis_device_name", json.dumps(["ARM Cortex-M"]), "tcl/target/a.cfg", "upstream-openocd", "mapping_candidate", "not_verified", "test.csv"],
        ["Vendor B", "F2", "", "S2", "XABC123X", "manufacturer_part_number", json.dumps(["RISC-V"]), "tcl/target/b.cfg", "upstream-openocd", "mapping_candidate", "not_verified", "test.csv"],
        ["Vendor C", "F3", "", "S3", "ABC1XXX", "ordering_pattern", json.dumps(["ARM Cortex-M"]), "tcl/target/c.cfg", "upstream-openocd", "mapping_candidate", "not_verified", "test.csv"],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def test_search_ranks_exact_then_prefix_then_partial_case_insensitively(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    _write_catalog(path)
    catalog = DeviceCatalog.from_csv(path)

    matches = catalog.search("abc123")

    assert [record.identifier for record in matches] == ["ABC123", "ABC1234", "XABC123X"]


def test_icpn_requires_authoritative_exact_part_number_kind(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    _write_catalog(path)
    catalog = DeviceCatalog.from_csv(path)

    exact, device_name = catalog.search("ABC123", limit=2)

    assert exact.icpn == "ABC123"
    assert device_name.icpn is None
    assert device_name.to_payload()["physical_validation"] == {
        "engineering_status": "not_verified",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_empty_query_returns_no_results(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    _write_catalog(path)
    catalog = DeviceCatalog.from_csv(path)

    assert catalog.search("   ") == []


def test_search_limit_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    _write_catalog(path)
    catalog = DeviceCatalog.from_csv(path)

    for invalid in (0, 101, True):
        try:
            catalog.search("ABC", limit=invalid)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid limit was accepted: {invalid!r}")


def test_checked_in_canonical_catalog_is_loadable() -> None:
    catalog = get_default_device_catalog()

    assert catalog.size == 7657
    assert catalog.search("ADUC7019BCPZ62I", limit=1)[0].icpn == "ADUC7019BCPZ62I"
