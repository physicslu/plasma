#!/usr/bin/env python3
"""Build the post-F/G0/G4 STM32 cross-family research prioritization inventory.

This policy is deliberately read-only.  It separates OpenOCD structural
researchability from architecture-risk cohorts and emits a bounded shortlist,
not a selected next family.  Manufacturer identity/lifecycle evidence must be
probed separately before a family can be selected for discovery.

Official ST family-level classification references used by the governance
policy (not retained commercial identity evidence):
- STM32C0: https://www.st.com/en/microcontrollers-microprocessors/stm32c0-series.html
- STM32 ultra-low-power overview: https://www.st.com/en/microcontrollers-microprocessors/stm32-ultra-low-power-mcus.html
- STM32L5: https://www.st.com/en/microcontrollers-microprocessors/stm32l5-series.html
- STM32U3: https://www.st.com/en/microcontrollers-microprocessors/stm32u3-series.html
- STM32U5: https://www.st.com/en/microcontrollers-microprocessors/stm32u5-series.html
- STM32 wireless: https://www.st.com/en/microcontrollers-microprocessors/stm32-wireless-mcus.html
- STM32H7: https://www.st.com/en/microcontrollers-microprocessors/stm32h7-series.html
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
REPO_ROOT = HERE.parents[2]
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
MANUFACTURER = "STMicroelectronics"
STM32_SERIES_RE = re.compile(r"STM32[A-Z0-9]+")
SCHEMA_VERSION = 1
POLICY_ID = "stm32-cross-family-prioritization-v1"
PHASE = "cross-family-prioritization"
SHORTLIST_LIMIT = 3

# These are explicit governance cohorts, not programming-equivalence claims.
# Wireless families are isolated because integrated radio/network processors
# can materially expand discovery/security scope.  TrustZone families are
# isolated because secure/non-secure state and security configuration require
# explicit treatment.  H7 is isolated because the current OpenOCD surface is
# already split across multiple target configs.
TRUSTZONE_SERIES = frozenset({"STM32L5", "STM32U3", "STM32U5"})
HIGH_COMPLEXITY_SERIES = frozenset({"STM32H7"})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _family_cohort(series: str) -> str:
    if series.startswith("STM32W"):
        return "wireless_requires_dedicated_scope"
    if series in TRUSTZONE_SERIES:
        return "trustzone_requires_security_scope"
    if series in HIGH_COMPLEXITY_SERIES:
        return "high_complexity_requires_partitioned_scope"
    return "standard_nonwireless_research"


def _summarize_series(series: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    kinds = Counter(row["identifier_kind"] for row in rows)
    ordering_rows = kinds.get("ordering_pattern", 0)
    target_configs = sorted({row["target_config"] for row in rows if row["target_config"]})
    family_labels = sorted({row["family"] for row in rows if row["family"]})
    subfamilies = sorted({row["subfamily"] for row in rows if row["subfamily"]})
    distributions = Counter(row["openocd_distribution"] for row in rows)
    mapping_statuses = Counter(row["mapping_status"] for row in rows)
    validation_statuses = Counter(row["validation_status"] for row in rows)
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
    cohort = _family_cohort(series)
    structural_gate = bool(
        ordering_rows > 0
        and len(target_configs) == 1
        and complete_mapping_metadata
        and expected_candidate_contract
    )
    shortlist_eligible = bool(cohort == "standard_nonwireless_research" and structural_gate)
    risk_flags: list[str] = []
    if kinds != Counter({"ordering_pattern": len(rows)}):
        risk_flags.append("mixed_identifier_kinds")
    if len(target_configs) != 1:
        risk_flags.append("target_config_count_not_one")
    if not complete_mapping_metadata:
        risk_flags.append("incomplete_mapping_metadata")
    if not expected_candidate_contract:
        risk_flags.append("unexpected_openocd_candidate_contract")
    if validation_statuses == Counter({"not_verified": len(rows)}):
        risk_flags.append("openocd_mapping_not_verified")
    if cohort != "standard_nonwireless_research":
        risk_flags.append(cohort)
    return {
        "plasma_series": series,
        "row_count": len(rows),
        "ordering_pattern_rows": ordering_rows,
        "cmsis_device_name_rows": kinds.get("cmsis_device_name", 0),
        "ordering_pattern_fraction": round(ordering_rows / len(rows), 6),
        "family_labels": family_labels,
        "subfamily_count": len(subfamilies),
        "subfamilies": subfamilies,
        "identifier_kind_counts": dict(sorted(kinds.items())),
        "target_configs": target_configs,
        "cohort": cohort,
        "complete_mapping_metadata": complete_mapping_metadata,
        "expected_openocd_candidate_contract": expected_candidate_contract,
        "structural_gate_pass": structural_gate,
        "shortlist_eligible": shortlist_eligible,
        "risk_flags": risk_flags,
    }


def _production_snapshot(manifest_path: Path) -> tuple[list[str], int, int, dict[str, int]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "production":
        raise ValueError("Production manifest status must be production")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Production manifest requires non-empty sources")
    families: list[str] = []
    exact = 0
    bases: set[tuple[str, str]] = set()
    family_counts: dict[str, int] = {}
    for source in sources:
        if source.get("manufacturer") != MANUFACTURER:
            continue
        family = source["family"]
        source_path = (manifest_path.parent / source["path"]).resolve()
        rows = _read_csv(source_path)
        if len(rows) != int(source["row_count"]):
            raise ValueError(f"{family}: Production manifest row count mismatch")
        if any(row.get("manufacturer") != MANUFACTURER or row.get("family") != family for row in rows):
            raise ValueError(f"{family}: Production source identity mismatch")
        families.append(family)
        family_counts[family] = len(rows)
        exact += len(rows)
        bases.update((family, row["base_device"]) for row in rows)
    return sorted(families), exact, len(bases), dict(sorted(family_counts.items()))


def build_prioritization(*, catalog_path: Path, manifest_path: Path) -> dict[str, Any]:
    # Canonicalize caller-supplied paths before hashing, dereferencing relative
    # source paths, or recording provenance.  This makes frozen replay
    # independent of whether the caller passed an absolute or relative path.
    catalog_path = catalog_path.resolve()
    manifest_path = manifest_path.resolve()

    catalog_rows = _read_csv(catalog_path)
    production_series, exact_count, base_count, family_counts = _production_snapshot(manifest_path)
    production_set = set(production_series)

    rows_by_series: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in catalog_rows:
        series = row.get("plasma_series", "")
        if row.get("vendor") != MANUFACTURER or STM32_SERIES_RE.fullmatch(series) is None:
            continue
        rows_by_series[series].append(row)

    candidates = [
        _summarize_series(series, rows)
        for series, rows in sorted(rows_by_series.items())
        if series not in production_set
    ]
    shortlist_pool = sorted(
        (item for item in candidates if item["shortlist_eligible"]),
        key=lambda item: (
            item["ordering_pattern_rows"],
            item["row_count"],
            -item["ordering_pattern_fraction"],
            item["plasma_series"],
        ),
    )
    shortlist = [
        {
            "shortlist_rank": index,
            "plasma_series": item["plasma_series"],
            "ordering_pattern_rows": item["ordering_pattern_rows"],
            "source_row_count": item["row_count"],
            "ordering_pattern_fraction": item["ordering_pattern_fraction"],
            "target_config": item["target_configs"][0],
            "next_required_gate": "bounded_official_manufacturer_evidence_accessibility_probe",
        }
        for index, item in enumerate(shortlist_pool[:SHORTLIST_LIMIT], start=1)
    ]
    cohort_counts = Counter(item["cohort"] for item in candidates)
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "phase": PHASE,
        "scope": "read-only cross-family STM32 research prioritization",
        "claims": {
            "production_write_authorized": False,
            "exact_icpn_claimed_from_openocd": False,
            "marketing_lifecycle_claimed_from_openocd": False,
            "programming_policy_defined": False,
            "programming_algorithm_equivalence_claimed": False,
            "selected_next_research_family": False,
            "shortlist_is_admission_ready": False,
            "runtime_programming_support_claimed": False,
        },
        "inputs": {
            "openocd_catalog": catalog_path.name,
            "openocd_catalog_sha256": _sha256(catalog_path),
            "production_manifest": str(manifest_path.relative_to(REPO_ROOT)),
            "production_manifest_sha256": _sha256(manifest_path),
        },
        "production_invariants": {
            "manufacturer": MANUFACTURER,
            "production_series": production_series,
            "exact_icpn_count": exact_count,
            "base_device_count": base_count,
            "family_exact_icpn_counts": family_counts,
        },
        "policy": {
            "shortlist_limit": SHORTLIST_LIMIT,
            "structural_gate": [
                "at least one ordering_pattern row",
                "exactly one OpenOCD target config",
                "complete non-blank mapping metadata",
                "all rows satisfy upstream-openocd/mapping_candidate/not_verified source contract",
            ],
            "architecture_gate": "standard_nonwireless_research cohort only for first shortlist",
            "ranking": [
                "fewest ordering_pattern rows",
                "fewest total source rows",
                "highest ordering_pattern fraction",
                "lexical plasma_series tie-break",
            ],
            "selection_boundary": "shortlist only; manufacturer evidence probe required before selecting a family",
        },
        "inventory": {
            "candidate_series_count": len(candidates),
            "candidate_source_row_count": sum(item["row_count"] for item in candidates),
            "candidate_ordering_pattern_rows": sum(item["ordering_pattern_rows"] for item in candidates),
            "shortlist_eligible_series_count": len(shortlist_pool),
            "cohort_counts": dict(sorted(cohort_counts.items())),
        },
        "research_shortlist": shortlist,
        "selected_next_research_family": None,
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_prioritization(catalog_path=args.catalog, manifest_path=args.manifest)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
