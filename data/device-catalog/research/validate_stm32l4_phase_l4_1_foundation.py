#!/usr/bin/env python3
"""Replay and hard-lock the immutable STM32L4 L4.1 research foundation."""
from __future__ import annotations

import hashlib
import json

from st_product_page_acquisition import AcquisitionError
from stm32l4_phase_l4_1_foundation import (
    DEFAULT_BASELINE,
    EXPECTED_CMSIS_COUNT,
    EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS,
    EXPECTED_ORDERING_COUNT,
    EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
    EXPECTED_ROW_COUNT,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGETS,
    EXPECTED_UNIQUE_OFFICIAL_DATASHEETS,
    FAMILY,
    PHASE,
    TARGET_CONFIG,
    build_foundation_report,
    read_catalog,
    validate_ordering_authority,
    validate_production_prestate,
    validate_retained_identity,
    validate_selection,
    validate_target_manifest,
)

EXPECTED_BASELINE_SHA256 = "3f85587e74f9af1ee93f59d53a05ea1d47201e6b8564b8e8a91cb91f378bd40f"


def main() -> int:
    observed_digest = hashlib.sha256(DEFAULT_BASELINE.read_bytes()).hexdigest()
    if observed_digest != EXPECTED_BASELINE_SHA256:
        raise AcquisitionError(f"L4.1 baseline SHA-256 drifted: {observed_digest}")
    frozen = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
    replay = build_foundation_report(read_catalog())
    if replay != frozen:
        raise AcquisitionError("L4.1 deterministic replay differs from frozen baseline")
    if frozen.get("phase") != PHASE or frozen.get("family") != FAMILY:
        raise AcquisitionError("L4.1 phase/family identity drifted")
    if frozen.get("scope") != "bounded_research_foundation_only":
        raise AcquisitionError("L4.1 scope escaped bounded research foundation")
    if frozen.get("target_config") != TARGET_CONFIG:
        raise AcquisitionError("L4.1 target config drifted")
    if frozen.get("source_row_count") != EXPECTED_ROW_COUNT:
        raise AcquisitionError("L4.1 source row count drifted")
    if frozen.get("identifier_kind_counts") != {
        "cmsis_device_name": EXPECTED_CMSIS_COUNT,
        "ordering_pattern": EXPECTED_ORDERING_COUNT,
    }:
        raise AcquisitionError("L4.1 identifier-kind counts drifted")
    if tuple(frozen.get("subfamilies", [])) != EXPECTED_SUBFAMILIES:
        raise AcquisitionError("L4.1 subfamily set drifted")
    expected_targets = [
        {"subfamily": subfamily, "base_device": base}
        for subfamily, base in EXPECTED_TARGETS
    ]
    if frozen.get("initial_targets") != expected_targets:
        raise AcquisitionError("L4.1 deterministic representative set drifted")
    evidence = frozen.get("evidence_foundation")
    if not isinstance(evidence, dict):
        raise AcquisitionError("L4.1 evidence foundation missing")
    if evidence.get("scope") != "representative_evidence_only_not_complete_family_inventory":
        raise AcquisitionError("L4.1 evidence scope escaped representative-only boundary")
    if evidence.get("representative_count") != 24:
        raise AcquisitionError("L4.1 representative count drifted")
    if evidence.get("active_exact_icpns_observed") != EXPECTED_REPRESENTATIVE_EXACT_ICPNS:
        raise AcquisitionError("L4.1 active exact evidence count drifted")
    if evidence.get("excluded_non_active_part_numbers_observed") != EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS:
        raise AcquisitionError("L4.1 excluded exact evidence count drifted")
    if evidence.get("unique_official_datasheets") != EXPECTED_UNIQUE_OFFICIAL_DATASHEETS:
        raise AcquisitionError("L4.1 Ordering Information authority count drifted")
    claims = frozen.get("claims")
    if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
        raise AcquisitionError("L4.1 authority boundary escaped fail-closed state")
    validate_selection()
    validate_target_manifest()
    validate_retained_identity()
    validate_ordering_authority()
    validate_production_prestate()
    print("STM32L4 L4.1 foundation validation: PASS")
    print(json.dumps({
        "family": FAMILY,
        "phase": PHASE,
        "source_rows": EXPECTED_ROW_COUNT,
        "ordering_patterns": EXPECTED_ORDERING_COUNT,
        "cmsis_aliases": EXPECTED_CMSIS_COUNT,
        "representatives": 24,
        "representative_exact_icpns": EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
        "excluded_non_active_part_numbers": EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS,
        "official_datasheets": EXPECTED_UNIQUE_OFFICIAL_DATASHEETS,
        "baseline_sha256": EXPECTED_BASELINE_SHA256,
        "complete_family_inventory_claimed": False,
        "production_exact_icpns": 1272,
        "production_write_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
