#!/usr/bin/env python3
"""Build a fail-closed, read-only priority inventory for the next STM32 family.

The OpenOCD-derived catalog is routing evidence, not exact commercial ICPN,
marketing-lifecycle, or programming-algorithm-equivalence evidence.  This tool
therefore selects only the next bounded research surface and never emits
Production rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
MANUFACTURER = "STMicroelectronics"
STM32_SERIES_RE = re.compile(r"STM32[A-Z0-9]+")
F_LINE_RE = re.compile(r"STM32F\d+")
SCHEMA_VERSION = 1
PHASE = "4.3A"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _summarize_series(series: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    identifier_kinds = Counter(row["identifier_kind"] for row in rows)
    target_configs = sorted(
        {row["target_config"] for row in rows if row["target_config"]}
    )
    family_labels = sorted({row["family"] for row in rows if row["family"]})
    subfamilies = sorted({row["subfamily"] for row in rows if row["subfamily"]})
    distributions = Counter(row["openocd_distribution"] for row in rows)
    mapping_statuses = Counter(row["mapping_status"] for row in rows)
    validation_statuses = Counter(row["validation_status"] for row in rows)
    ordering_pattern_only = identifier_kinds == Counter({"ordering_pattern": len(rows)})
    complete_mapping_metadata = all(
        row["part_number"]
        and row["target_config"]
        and row["openocd_distribution"]
        and row["mapping_status"]
        and row["validation_status"]
        for row in rows
    )
    expected_candidate_contract = bool(
        distributions == Counter({"upstream-openocd": len(rows)})
        and mapping_statuses == Counter({"mapping_candidate": len(rows)})
        and validation_statuses == Counter({"not_verified": len(rows)})
    )
    phase43a_eligible = bool(
        F_LINE_RE.fullmatch(series)
        and ordering_pattern_only
        and len(target_configs) == 1
        and complete_mapping_metadata
        and expected_candidate_contract
    )
    risk_flags: list[str] = []
    if not ordering_pattern_only:
        risk_flags.append("mixed_identifier_kinds")
    if len(target_configs) != 1:
        risk_flags.append("target_config_count_not_one")
    if not complete_mapping_metadata:
        risk_flags.append("incomplete_mapping_metadata")
    if not expected_candidate_contract:
        risk_flags.append("unexpected_openocd_candidate_contract")
    if validation_statuses == Counter({"not_verified": len(rows)}):
        risk_flags.append("openocd_mapping_not_verified")
    return {
        "plasma_series": series,
        "row_count": len(rows),
        "family_labels": family_labels,
        "subfamily_count": len(subfamilies),
        "subfamilies": subfamilies,
        "identifier_kind_counts": dict(sorted(identifier_kinds.items())),
        "manufacturer_part_number_rows": identifier_kinds.get(
            "manufacturer_part_number", 0
        ),
        "target_configs": target_configs,
        "openocd_distribution_counts": dict(sorted(distributions.items())),
        "mapping_status_counts": dict(sorted(mapping_statuses.items())),
        "validation_status_counts": dict(sorted(validation_statuses.items())),
        "blank_part_number_rows": sum(not row["part_number"] for row in rows),
        "expected_openocd_candidate_contract": expected_candidate_contract,
        "phase43a_f_line_cohort": F_LINE_RE.fullmatch(series) is not None,
        "phase43a_eligible": phase43a_eligible,
        "risk_flags": risk_flags,
    }


def build_prioritization(*, catalog_path: Path, manifest_path: Path) -> dict[str, Any]:
    catalog_rows = _read_csv(catalog_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "production":
        raise ValueError("Production manifest status must be production")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Production manifest requires non-empty sources")
    production_series = sorted(
        {
            source["family"]
            for source in sources
            if source.get("manufacturer") == MANUFACTURER
        }
    )
    production_rows_by_family: dict[str, list[dict[str, str]]] = {}
    for source in sources:
        if source.get("manufacturer") != MANUFACTURER:
            continue
        family = source["family"]
        source_path = (manifest_path.parent / source["path"]).resolve()
        source_rows = _read_csv(source_path)
        if len(source_rows) != int(source["row_count"]):
            raise ValueError(f"{family}: Production manifest row count mismatch")
        if any(
            row.get("manufacturer") != MANUFACTURER or row.get("family") != family
            for row in source_rows
        ):
            raise ValueError(f"{family}: Production source identity mismatch")
        production_rows_by_family[family] = source_rows

    rows_by_series: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in catalog_rows:
        series = row.get("plasma_series", "")
        if row.get("vendor") != MANUFACTURER or STM32_SERIES_RE.fullmatch(series) is None:
            continue
        rows_by_series[series].append(row)

    candidates = [
        _summarize_series(series, rows)
        for series, rows in sorted(rows_by_series.items())
        if series not in production_series
    ]
    eligible = sorted(
        (item for item in candidates if item["phase43a_eligible"]),
        key=lambda item: (item["row_count"], item["plasma_series"]),
    )
    if not eligible:
        selected: dict[str, Any] | None = None
    else:
        selected = {
            "plasma_series": eligible[0]["plasma_series"],
            "row_count": eligible[0]["row_count"],
            "target_config": eligible[0]["target_configs"][0],
            "selection_rank": 1,
            "selection_basis": [
                "not already present in the Production manifest",
                "STM32 F-line cohort bounds architectural novelty for the first third-family pilot",
                "all source rows are ordering_pattern identifiers",
                "all source rows use one non-blank OpenOCD target config",
                "smallest source-row surface in the eligible cohort",
            ],
        }

    eligible_ranking = [
        {
            "selection_rank": index,
            "plasma_series": item["plasma_series"],
            "row_count": item["row_count"],
            "target_config": item["target_configs"][0],
        }
        for index, item in enumerate(eligible, start=1)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "scope": "read-only prioritization of the next bounded STM32 family research surface",
        "claims": {
            "production_write_authorized": False,
            "exact_icpn_claimed_from_openocd": False,
            "marketing_lifecycle_claimed_from_openocd": False,
            "programming_algorithm_equivalence_claimed": False,
            "selected_family_admission_ready": False,
        },
        "inputs": {
            "openocd_catalog": catalog_path.name,
            "openocd_catalog_sha256": _sha256(catalog_path),
            "production_manifest": str(manifest_path.relative_to(HERE.parents[2])),
            "production_manifest_sha256": _sha256(manifest_path),
        },
        "production_invariants": {
            "manufacturer": MANUFACTURER,
            "production_series": production_series,
            "exact_icpn_count": sum(
                len(rows) for rows in production_rows_by_family.values()
            ),
            "base_device_count": len(
                {
                    row["base_device"]
                    for rows in production_rows_by_family.values()
                    for row in rows
                }
            ),
            "family_exact_icpn_counts": {
                family: len(rows)
                for family, rows in sorted(production_rows_by_family.items())
            },
            "family_base_device_counts": {
                family: len({row["base_device"] for row in rows})
                for family, rows in sorted(production_rows_by_family.items())
            },
        },
        "inventory": {
            "stm32_catalog_series_count": len(rows_by_series),
            "candidate_series_count": len(candidates),
            "eligible_f_line_series_count": len(eligible),
            "candidate_source_row_count": sum(
                item["row_count"] for item in candidates
            ),
            "candidate_manufacturer_part_number_rows": sum(
                item["manufacturer_part_number_rows"] for item in candidates
            ),
        },
        "eligible_ranking": eligible_ranking,
        "selected_next_research_family": selected,
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_prioritization(
        catalog_path=args.catalog,
        manifest_path=args.manifest,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
