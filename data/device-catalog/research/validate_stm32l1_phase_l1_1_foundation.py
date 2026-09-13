#!/usr/bin/env python3
"""Replay and hard-lock the immutable STM32L1 L1.1 research foundation."""
from __future__ import annotations

import hashlib
import json

from st_product_page_acquisition import AcquisitionError
from stm32l1_phase_l1_1_foundation import (
    DEFAULT_BASELINE,
    EXPECTED_CMSIS_COUNT,
    EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS,
    EXPECTED_ORDERING_COUNT,
    EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
    EXPECTED_ROW_COUNT,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGETS,
    FAMILY,
    PHASE,
    TARGET_CONFIG,
    build_foundation_report,
    read_catalog,
    validate_ordering_authority,
    validate_production_prestate,
    validate_requalification_result,
    validate_retained_identity,
    validate_target_manifest,
)

EXPECTED_BASELINE_GIT_BLOB = "8da20cfc02c8106d5163338e85fb6425bc9ccdc9"


def git_blob_sha(path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()


def main() -> int:
    observed_blob = git_blob_sha(DEFAULT_BASELINE)
    if observed_blob != EXPECTED_BASELINE_GIT_BLOB:
        raise AcquisitionError(f"L1.1 baseline Git blob drifted: {observed_blob}")
    frozen = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
    replay = build_foundation_report(read_catalog())
    if replay != frozen:
        raise AcquisitionError("L1.1 deterministic replay differs from frozen baseline")
    if frozen.get("phase") != PHASE or frozen.get("family") != FAMILY:
        raise AcquisitionError("L1.1 phase/family identity drifted")
    if frozen.get("scope") != "bounded_research_foundation_only":
        raise AcquisitionError("L1.1 scope escaped bounded research foundation")
    if frozen.get("target_config") != TARGET_CONFIG:
        raise AcquisitionError("L1.1 target config drifted")
    if frozen.get("source_row_count") != EXPECTED_ROW_COUNT:
        raise AcquisitionError("L1.1 source row count drifted")
    if frozen.get("identifier_kind_counts") != {
        "cmsis_device_name": EXPECTED_CMSIS_COUNT,
        "ordering_pattern": EXPECTED_ORDERING_COUNT,
    }:
        raise AcquisitionError("L1.1 identifier-kind counts drifted")
    if tuple(frozen.get("subfamilies", [])) != EXPECTED_SUBFAMILIES:
        raise AcquisitionError("L1.1 subfamily set drifted")
    expected_targets = [
        {"base_device": base, "subfamily": subfamily}
        for subfamily, base in EXPECTED_TARGETS
    ]
    if frozen.get("initial_targets") != expected_targets:
        raise AcquisitionError("L1.1 deterministic representative set drifted")
    evidence = frozen.get("evidence_foundation")
    if not isinstance(evidence, dict):
        raise AcquisitionError("L1.1 evidence foundation missing")
    if evidence.get("scope") != "representative_evidence_only_not_complete_family_inventory":
        raise AcquisitionError("L1.1 evidence scope escaped representative-only boundary")
    if evidence.get("representative_count") != 4:
        raise AcquisitionError("L1.1 representative count drifted")
    if evidence.get("active_exact_icpns_observed") != EXPECTED_REPRESENTATIVE_EXACT_ICPNS:
        raise AcquisitionError("L1.1 Active exact evidence count drifted")
    if evidence.get("excluded_non_active_part_numbers_observed") != EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS:
        raise AcquisitionError("L1.1 excluded exact evidence count drifted")
    if evidence.get("generation_migration_authority") != "TN1176":
        raise AcquisitionError("L1.1 generation migration authority drifted")
    claims = frozen.get("claims")
    if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
        raise AcquisitionError("L1.1 authority boundary escaped fail-closed state")
    requalification = validate_requalification_result()
    validate_target_manifest()
    validate_retained_identity()
    validate_ordering_authority()
    validate_production_prestate()
    production = requalification["production"]
    if production["exact_icpn_count"] != 1718 or production["base_device_count"] != 530:
        raise AcquisitionError("L1.1 frozen Production totals drifted")
    if production["family_count"] != 12 or production["stm32l1_exact_icpn_count"] != 0:
        raise AcquisitionError("L1.1 frozen family boundary drifted")
    print("STM32L1 L1.1 foundation validation: PASS")
    print(json.dumps({
        "family": FAMILY,
        "phase": PHASE,
        "source_rows": EXPECTED_ROW_COUNT,
        "ordering_patterns": EXPECTED_ORDERING_COUNT,
        "cmsis_aliases": EXPECTED_CMSIS_COUNT,
        "representatives": 4,
        "representative_exact_icpns": EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
        "excluded_non_active_part_numbers": EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS,
        "baseline_git_blob": EXPECTED_BASELINE_GIT_BLOB,
        "complete_family_inventory_claimed": False,
        "production_exact_icpns": 1718,
        "production_write_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
