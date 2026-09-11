#!/usr/bin/env python3
"""Replay and hard-lock the immutable STM32C0 C0.1 research foundation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32c0_phase_c0_1_foundation import (
    DEFAULT_BASELINE,
    EXPECTED_CMSIS_COUNT,
    EXPECTED_ORDERING_COUNT,
    EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
    EXPECTED_ROW_COUNT,
    EXPECTED_TARGETS,
    FAMILY,
    PHASE,
    TARGET_CONFIG,
    build_foundation_report,
    read_catalog,
    validate_ordering_authority,
    validate_retained_identity,
    validate_selection,
)

EXPECTED_BASELINE_SHA256 = "c89e8c528f80f9b199a2b153d3d40aa4af090e50c492a7c88bfa7876ce406515"


def main() -> int:
    observed_digest = hashlib.sha256(DEFAULT_BASELINE.read_bytes()).hexdigest()
    if observed_digest != EXPECTED_BASELINE_SHA256:
        raise AcquisitionError(f"C0.1 baseline SHA-256 drifted: {observed_digest}")

    frozen = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
    replay = build_foundation_report(read_catalog())
    if replay != frozen:
        raise AcquisitionError("C0.1 deterministic replay differs from frozen baseline")

    if frozen.get("phase") != PHASE or frozen.get("family") != FAMILY:
        raise AcquisitionError("C0.1 phase/family identity drifted")
    if frozen.get("target_config") != TARGET_CONFIG:
        raise AcquisitionError("C0.1 target config drifted")
    if frozen.get("source_row_count") != EXPECTED_ROW_COUNT:
        raise AcquisitionError("C0.1 source row count drifted")
    if frozen.get("identifier_kind_counts") != {
        "cmsis_device_name": EXPECTED_CMSIS_COUNT,
        "ordering_pattern": EXPECTED_ORDERING_COUNT,
    }:
        raise AcquisitionError("C0.1 identifier-kind counts drifted")

    expected_targets = [
        {"subfamily": subfamily, "base_device": base}
        for subfamily, base in EXPECTED_TARGETS
    ]
    if frozen.get("initial_targets") != expected_targets:
        raise AcquisitionError("C0.1 deterministic representative set drifted")

    evidence = frozen.get("evidence_foundation")
    if not isinstance(evidence, dict):
        raise AcquisitionError("C0.1 evidence foundation missing")
    if evidence.get("scope") != "representative_evidence_only_not_complete_family_inventory":
        raise AcquisitionError("C0.1 evidence scope escaped representative-only boundary")
    if evidence.get("representative_count") != 6:
        raise AcquisitionError("C0.1 representative count drifted")
    if evidence.get("active_exact_icpns_observed") != EXPECTED_REPRESENTATIVE_EXACT_ICPNS:
        raise AcquisitionError("C0.1 representative ICPN count drifted")

    representatives = evidence.get("representatives")
    if not isinstance(representatives, list) or len(representatives) != 6:
        raise AcquisitionError("C0.1 representative evidence rows drifted")
    exact_icpns = [
        icpn
        for item in representatives
        if isinstance(item, dict)
        for icpn in item.get("exact_icpns", [])
    ]
    if len(exact_icpns) != EXPECTED_REPRESENTATIVE_EXACT_ICPNS or len(set(exact_icpns)) != len(exact_icpns):
        raise AcquisitionError("C0.1 representative exact ICPNs are incomplete or duplicated")

    claims = frozen.get("claims")
    if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
        raise AcquisitionError("C0.1 authority boundary escaped fail-closed state")

    validate_selection()
    validate_retained_identity()
    validate_ordering_authority()

    print("STM32C0 C0.1 foundation validation: PASS")
    print(json.dumps({
        "family": FAMILY,
        "phase": PHASE,
        "source_rows": EXPECTED_ROW_COUNT,
        "ordering_patterns": EXPECTED_ORDERING_COUNT,
        "cmsis_aliases": EXPECTED_CMSIS_COUNT,
        "representatives": 6,
        "representative_exact_icpns": EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
        "baseline_sha256": EXPECTED_BASELINE_SHA256,
        "complete_family_inventory_claimed": False,
        "production_write_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
