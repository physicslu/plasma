#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from stm32_next_family_prioritization import build_prioritization

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "openocd-parts-canonical.csv"
MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
BASELINE = HERE / "stm32-phase4.3a-next-family-prioritization-baseline.json"


def _candidate(report: dict, series: str) -> dict:
    matches = [
        item for item in report["candidates"] if item["plasma_series"] == series
    ]
    assert len(matches) == 1
    return matches[0]


def _write_mutated_catalog(path: Path, mutation: str) -> None:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        assert fieldnames is not None
        rows = list(reader)
    target = next(row for row in rows if row["plasma_series"] == "STM32F2")
    if mutation == "identifier_kind":
        target["identifier_kind"] = "cmsis_device_name"
    elif mutation == "target_config":
        target["target_config"] = "tcl/target/unexpected.cfg"
    elif mutation == "mapping_status":
        target["mapping_status"] = "unexpected"
    else:
        raise AssertionError(f"unsupported mutation: {mutation}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    report = build_prioritization(catalog_path=CATALOG, manifest_path=MANIFEST)

    assert report["schema_version"] == expected["schema_version"]
    assert report["phase"] == expected["phase"]
    assert report["inputs"]["openocd_catalog_sha256"] == expected["inputs"][
        "openocd_catalog_sha256"
    ]
    assert report["inputs"]["production_manifest_sha256"] == expected["inputs"][
        "production_manifest_sha256"
    ]
    assert report["production_invariants"] == expected["production_invariants"]
    assert report["inventory"] == expected["inventory"]
    assert report["eligible_ranking"] == expected["eligible_ranking"]
    assert report["selected_next_research_family"] == expected[
        "selected_next_research_family"
    ]

    claims = report["claims"]
    assert set(claims.values()) == {False}
    assert len(report["candidates"]) == report["inventory"]["candidate_series_count"]
    assert all(
        item["plasma_series"]
        not in report["production_invariants"]["production_series"]
        for item in report["candidates"]
    )
    assert sum(item["row_count"] for item in report["candidates"]) == report[
        "inventory"
    ]["candidate_source_row_count"]
    assert sum(
        item["manufacturer_part_number_rows"] for item in report["candidates"]
    ) == report["inventory"]["candidate_manufacturer_part_number_rows"]

    selected = _candidate(report, "STM32F2")
    selected_contract = expected["selected_candidate_contract"]
    for key, value in selected_contract.items():
        assert selected[key] == value
    assert selected["phase43a_eligible"] is True
    assert selected["phase43a_f_line_cohort"] is True

    # The winner must fail closed if its identifier topology or target routing
    # stops satisfying the bounded-cohort contract.
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        for mutation in ("identifier_kind", "target_config", "mapping_status"):
            mutated_catalog = temporary_root / f"{mutation}.csv"
            _write_mutated_catalog(mutated_catalog, mutation)
            mutated = build_prioritization(
                catalog_path=mutated_catalog,
                manifest_path=MANIFEST,
            )
            assert _candidate(mutated, "STM32F2")["phase43a_eligible"] is False
            assert mutated["selected_next_research_family"]["plasma_series"] == "STM32F3"

    print("Phase 4.3A next-family prioritization PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
