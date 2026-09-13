#!/usr/bin/env python3
"""Deterministic offline result builder for STM32L1 lifecycle requalification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError
from stm32l1_requalification_probe import FAMILY, validate_current_boundary

HERE = Path(__file__).resolve().parent
EVIDENCE_ROOT = HERE / "evidence" / "stm32l1-requalification-live-2026-09-13"
DEFAULT_SUMMARY = EVIDENCE_ROOT / "probe-summary.json"
DEFAULT_TARGETS = EVIDENCE_ROOT / "targets.json"
DEFAULT_PROVENANCE = EVIDENCE_ROOT / "provenance.json"
DEFAULT_ORDERING = HERE / "stm32l1-requalification-ordering-authority.json"
FROZEN_PRODUCTION_PRESTATE = HERE / "stm32l1-requalification-production-prestate.json"
DEFAULT_OUTPUT = HERE / "stm32l1-requalification-result.json"

EXPECTED_SUBFAMILIES = ["STM32L100", "STM32L151", "STM32L152", "STM32L162"]
EXPECTED_FALSE_NEGATIVES = ["STM32L100", "STM32L151", "STM32L152"]
EXPECTED_ACTIVE = {
    "STM32L100": ["STM32L100C6U6A", "STM32L100C6U6ATR"],
    "STM32L151": ["STM32L151C6T6A", "STM32L151C6T6ATR", "STM32L151C6U6A", "STM32L151C6U6ATR"],
    "STM32L152": ["STM32L152C6T6A", "STM32L152C6U6A"],
    "STM32L162": ["STM32L162QCH6"],
}
EXPECTED_EXCLUDED = {
    "STM32L100": ["STM32L100C6U6", "STM32L100C6U6TR"],
    "STM32L151": ["STM32L151C6T6", "STM32L151C6T6TR", "STM32L151C6U6", "STM32L151C6U6TR"],
    "STM32L152": ["STM32L152C6T6", "STM32L152C6U6"],
    "STM32L162": [],
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AcquisitionError(f"{path.name}: expected JSON object")
    return payload


def _all_false(payload: object) -> bool:
    return isinstance(payload, dict) and bool(payload) and all(value is False for value in payload.values())


def build_requalification_result(
    *,
    summary_path: Path = DEFAULT_SUMMARY,
    targets_path: Path = DEFAULT_TARGETS,
    provenance_path: Path = DEFAULT_PROVENANCE,
    ordering_path: Path = DEFAULT_ORDERING,
    production_prestate_path: Path = FROZEN_PRODUCTION_PRESTATE,
) -> dict[str, object]:
    # Historical validation is intentionally bound to the transaction's frozen
    # post-L4 Production prestate, not to mutable future Production.
    current = validate_current_boundary(manifest_path=production_prestate_path)
    summary = _load(summary_path)
    targets = _load(targets_path)
    provenance = _load(provenance_path)
    ordering = _load(ordering_path)

    if summary.get("probe_id") != "stm32l1-official-st-lifecycle-requalification-v1":
        raise AcquisitionError("unexpected retained STM32L1 requalification probe")
    if summary.get("family") != FAMILY or summary.get("phase") != "post-L4-STM32L1-requalification":
        raise AcquisitionError("retained STM32L1 requalification scope drifted")
    if summary.get("target_count") != 7 or summary.get("subfamily_count") != 4:
        raise AcquisitionError("retained STM32L1 target boundary drifted")
    if summary.get("manual_review_targets") != 0 or summary.get("source_unavailable_targets") != 0:
        raise AcquisitionError("retained STM32L1 evidence is not clean")
    if summary.get("bounded_probe_complete") is not True:
        raise AcquisitionError("retained STM32L1 probe is incomplete")
    if summary.get("requalification_status") != "eligible_for_next_research_gate":
        raise AcquisitionError("STM32L1 requalification status drifted")
    if summary.get("selected_next_research_family") is not None:
        raise AcquisitionError("requalification must not select a family")
    if not _all_false(summary.get("claims")):
        raise AcquisitionError("requalification claims escaped fail-closed state")
    if summary.get("active_subfamilies") != EXPECTED_SUBFAMILIES:
        raise AcquisitionError("STM32L1 active subfamily set drifted")
    if summary.get("historical_single_page_false_negative_subfamilies") != EXPECTED_FALSE_NEGATIVES:
        raise AcquisitionError("STM32L1 historical false-negative set drifted")

    by_subfamily = summary.get("by_subfamily")
    if not isinstance(by_subfamily, dict):
        raise AcquisitionError("STM32L1 retained summary lacks by_subfamily")
    for subfamily in EXPECTED_SUBFAMILIES:
        item = by_subfamily.get(subfamily)
        if not isinstance(item, dict):
            raise AcquisitionError(f"{subfamily}: missing retained lifecycle result")
        if item.get("active_exact_icpns") != EXPECTED_ACTIVE[subfamily]:
            raise AcquisitionError(f"{subfamily}: Active exact ICPN set drifted")
        if item.get("excluded_non_active_icpns") != EXPECTED_EXCLUDED[subfamily]:
            raise AcquisitionError(f"{subfamily}: non-Active exact ICPN set drifted")
        if item.get("active_exact_available") is not True:
            raise AcquisitionError(f"{subfamily}: no current Active exact ICPN")

    if targets.get("target_count") != 7 or not _all_false(targets.get("claims")):
        raise AcquisitionError("retained target manifest drifted")
    target_rows = targets.get("targets")
    if not isinstance(target_rows, list) or len(target_rows) != 7:
        raise AcquisitionError("retained target list drifted")
    roles = {(row.get("subfamily"), row.get("role")) for row in target_rows if isinstance(row, dict)}
    for subfamily in EXPECTED_FALSE_NEGATIVES:
        if (subfamily, "historical_representative") not in roles or (subfamily, "generation_companion") not in roles:
            raise AcquisitionError(f"{subfamily}: generation-aware target pair missing")

    if provenance.get("workflow_run_id") != 34749400091 or provenance.get("workflow_run_attempt") != 1:
        raise AcquisitionError("live acquisition provenance drifted")
    if provenance.get("artifact_digest") != "sha256:b20ffce5cf4ab540fbed1458719c544ba06cfceb8f0ba10829034b76c0dbcf5f":
        raise AcquisitionError("live acquisition artifact digest drifted")
    if provenance.get("executed_git_sha") != "b7b9ce7b7e808eae765f964c0cd6e2799887a456":
        raise AcquisitionError("live acquisition executed Git SHA drifted")
    if not _all_false(provenance.get("claims")):
        raise AcquisitionError("live acquisition provenance claims escaped fail-closed state")

    coverage = ordering.get("coverage")
    if ordering.get("authority") != "official_st_datasheet_ordering_information" or not isinstance(coverage, dict):
        raise AcquisitionError("STM32L1 Ordering Information authority drifted")
    if coverage.get("required_subfamilies") != EXPECTED_SUBFAMILIES:
        raise AcquisitionError("STM32L1 ordering required set drifted")
    if coverage.get("covered_subfamilies") != EXPECTED_SUBFAMILIES or coverage.get("coverage_complete") is not True:
        raise AcquisitionError("STM32L1 Ordering Information coverage incomplete")
    if not _all_false(ordering.get("claims")):
        raise AcquisitionError("Ordering Information claims escaped fail-closed state")

    production = current["production_invariants"]
    return {
        "schema_version": 1,
        "phase": "post-L4-STM32L1-requalification",
        "family": FAMILY,
        "status": "eligible_for_next_research_gate",
        "active_subfamilies": EXPECTED_SUBFAMILIES,
        "active_subfamily_count": 4,
        "active_exact_icpn_evidence_count": sum(len(values) for values in EXPECTED_ACTIVE.values()),
        "non_active_exact_icpn_evidence_count": sum(len(values) for values in EXPECTED_EXCLUDED.values()),
        "historical_single_page_false_negative_subfamilies": EXPECTED_FALSE_NEGATIVES,
        "ordering_information_coverage_complete": True,
        "selected_next_research_family": None,
        "next_required_gate": "explicit STM32L1 bounded research foundation/discovery Gate 1",
        "production": {
            "exact_icpn_count": production["exact_icpn_count"],
            "base_device_count": production["base_device_count"],
            "family_count": len(production["production_series"]),
            "stm32l1_exact_icpn_count": production["family_exact_icpn_counts"].get(FAMILY, 0),
        },
        "claims": {
            "production_write_authorized": False,
            "canonical_admission_authorized": False,
            "exact_icpn_publication_authorized": False,
            "selected_next_research_family": False,
            "programming_policy_defined": False,
            "programming_algorithm_equivalence_claimed": False,
            "flash_geometry_qualified": False,
            "option_security_qualified": False,
            "hil_qualified": False,
            "runtime_programming_support_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = build_requalification_result()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
