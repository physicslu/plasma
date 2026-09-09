#!/usr/bin/env python3
"""Fail-closed replay of the frozen STM32G0 Phase 4.8D admission plan."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from stm32g0_phase4_8d_admission import (
    EXPECTED_CAPABILITY_UNRESOLVED,
    admission_plan_is_clean,
    build_admission_plan,
)

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "stm32g0-phase4.8d-admission-plan.json"
EXPECTED_PLAN_SHA256 = "d5f83bb3a2417a368e2d0bfb66a146e47b7649675341dc44e9d28c0a5de39801"
EXPECTED_POLICY_SHA256 = "953df55b097ad58c93738e2aeecc7c762cb464f882493bf622fefbb61fc3a787"
EXPECTED_MAPPING_SHA256 = "f7bf4292c59aed40fd2d97be853b5ead0cd67be7f068fe8ae3827989657978d3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    try:
        if sha256(PLAN_PATH) != EXPECTED_PLAN_SHA256:
            raise RuntimeError("frozen Phase 4.8D admission-plan byte digest mismatch")
        frozen = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            historical_canonical = Path(td) / "stm32g0-commercial-icpn.csv"
            replay = build_admission_plan(canonical_path=historical_canonical)
        if not admission_plan_is_clean(replay):
            raise RuntimeError("replayed Phase 4.8D admission plan is not clean")
        if replay != frozen:
            raise RuntimeError("Phase 4.8D admission plan semantic replay drifted")
        if frozen.get("manufacturer_verified_identity_count") != 49:
            raise RuntimeError("manufacturer-verified identity count drifted")
        if frozen.get("candidate_count") != 47 or frozen.get("capability_admittable_count") != 47:
            raise RuntimeError("capability-admittable count drifted")
        if frozen.get("decision_counts") != {
            "admit": 47, "already_present": 0, "manual_review_required": 0, "reject": 0,
        }:
            raise RuntimeError("Phase 4.8D decision counts drifted")
        unresolved = frozen.get("capability_unresolved")
        if not isinstance(unresolved, list) or len(unresolved) != 2:
            raise RuntimeError("capability-unresolved list drifted")
        if {item.get("icpn") for item in unresolved} != set(EXPECTED_CAPABILITY_UNRESOLVED):
            raise RuntimeError("capability-unresolved identity set drifted")
        for item in unresolved:
            if item.get("identity_status") != "manufacturer_verified_active":
                raise RuntimeError("unresolved identity lost manufacturer-valid status")
            if item.get("capability_status") != "openocd_ordering_pattern_unresolved":
                raise RuntimeError("unresolved capability status drifted")
            if item.get("policy_action") != "exclude_from_canonical_admission_until_positive_capability_evidence":
                raise RuntimeError("unresolved policy action drifted")
            mapping = item.get("mapping")
            if not isinstance(mapping, dict) or mapping.get("status") != "unmapped" or mapping.get("match_count") != 0:
                raise RuntimeError("unresolved mapping unexpectedly resolved")
        candidates = frozen.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 47:
            raise RuntimeError("admission candidate set drifted")
        candidate_icpns = {item.get("icpn") for item in candidates}
        if candidate_icpns & set(EXPECTED_CAPABILITY_UNRESOLVED):
            raise RuntimeError("capability-unresolved N identity leaked into canonical admission")
        for item in candidates:
            if item.get("decision") != "admit":
                raise RuntimeError(f"{item.get('icpn')}: frozen candidate is not admit")
            mapping = item.get("base_mapping")
            row = item.get("proposed_canonical_row")
            if not isinstance(mapping, dict) or not isinstance(row, dict):
                raise RuntimeError(f"{item.get('icpn')}: frozen mapping/row missing")
            if mapping.get("status") != "unique" or mapping.get("match_count") != 1:
                raise RuntimeError(f"{item.get('icpn')}: mapping is not unique")
            if mapping.get("target_configs") != ["tcl/target/stm32g0x.cfg"]:
                raise RuntimeError(f"{item.get('icpn')}: target config drifted")
            if mapping.get("identifier_kind") != "ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: identifier kind drifted")
            if row.get("openocd_target_config") != "tcl/target/stm32g0x.cfg":
                raise RuntimeError(f"{item.get('icpn')}: canonical routing drifted")
            if row.get("mapping_status") != "deterministic_ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: canonical mapping status drifted")
            if row.get("cmsis_device_name") != "":
                raise RuntimeError(f"{item.get('icpn')}: CMSIS alias leaked into canonical identity")
        inputs = frozen.get("inputs") or {}
        if inputs.get("policy_baseline_sha256") != EXPECTED_POLICY_SHA256:
            raise RuntimeError("4.8C policy binding drifted")
        if inputs.get("mapping_catalog_sha256") != EXPECTED_MAPPING_SHA256:
            raise RuntimeError("OpenOCD mapping catalog binding drifted")
        for flag in (
            "canonical_write_applied", "production_write_applied",
            "programming_algorithm_equivalence_claimed",
            "n_product_version_capability_equivalence_claimed",
            "physical_target_qualification_claimed", "runtime_programming_support_claimed",
            "full_stm32g0_surface_covered",
        ):
            if frozen.get(flag) is not False:
                raise RuntimeError(f"Phase 4.8D trust boundary drifted: {flag}")
        if frozen.get("capability_unresolved_is_identity_rejection") is not False:
            raise RuntimeError("capability unresolved was mislabeled as identity rejection")
        print(json.dumps({
            "status": "valid", "phase": "4.8D",
            "manufacturer_verified_identity_count": 49,
            "canonical_admission_candidates": 47,
            "capability_unresolved": sorted(EXPECTED_CAPABILITY_UNRESOLVED),
            "plan_sha256": EXPECTED_PLAN_SHA256,
            "canonical_write_applied": False,
            "production_write_applied": False,
        }, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
