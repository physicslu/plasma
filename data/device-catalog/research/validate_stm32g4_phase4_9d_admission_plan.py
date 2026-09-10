#!/usr/bin/env python3
"""Fail-closed replay of the frozen STM32G4 Phase 4.9D admission plan."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from stm32g4_metadata_policy import EXPECTED_PROPOSAL_EXCLUSIONS, SOURCE_UNAVAILABLE_BASES
from stm32g4_phase4_9d_admission import admission_plan_is_clean, build_admission_plan

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "stm32g4-phase4.9d-admission-plan.json"
EXPECTED_PLAN_SHA256 = "4ba41c97414ca4eb45b069f08b0200e2e53faaaed2cd5e4e57e7ac260d3d1291"
EXPECTED_POLICY_SHA256 = "23e83659d694ad8428eda19d7c570372c86ad40d75be8c6bbb8c16007bd398fd"
EXPECTED_MAPPING_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_PRODUCTION_PRESTATE_SHA256 = "0dbb7df5a3ddc771326507fb42a47416d892d1d17f4e4141dde37cde23e95ddf"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    try:
        if sha256(PLAN_PATH) != EXPECTED_PLAN_SHA256:
            raise RuntimeError("frozen Phase 4.9D admission-plan byte digest mismatch")
        frozen = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            historical_canonical = Path(td) / "stm32g4-commercial-icpn.csv"
            replay = build_admission_plan(canonical_path=historical_canonical)
        if not admission_plan_is_clean(replay):
            raise RuntimeError("replayed Phase 4.9D admission plan is not clean")
        if replay != frozen:
            raise RuntimeError("Phase 4.9D admission plan semantic replay drifted")

        if frozen.get("manufacturer_verified_identity_count") != 25:
            raise RuntimeError("manufacturer-verified identity count drifted")
        if frozen.get("candidate_count") != 25 or frozen.get("capability_admittable_count") != 25:
            raise RuntimeError("capability-admittable count drifted")
        if frozen.get("decision_counts") != {
            "admit": 25, "already_present": 0, "manual_review_required": 0, "reject": 0,
        }:
            raise RuntimeError("Phase 4.9D decision counts drifted")
        if frozen.get("capability_unresolved_count") != 0 or frozen.get("capability_unresolved") != []:
            raise RuntimeError("Phase 4.9D unexpectedly contains capability-unresolved identities")
        if frozen.get("capability_unresolved_is_identity_rejection") is not False:
            raise RuntimeError("capability-unresolved semantics drifted")
        if frozen.get("bounded_commercial_surface_complete") is not False:
            raise RuntimeError("three HTTP-404 commercial-identity gaps were incorrectly erased")
        if frozen.get("source_unavailable_base_devices") != sorted(SOURCE_UNAVAILABLE_BASES):
            raise RuntimeError("source-unavailable Base Device set drifted")
        if frozen.get("proposal_exact_identity_exclusions") != sorted(EXPECTED_PROPOSAL_EXCLUSIONS):
            raise RuntimeError("Proposal exclusion set drifted")

        candidates = frozen.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 25:
            raise RuntimeError("admission candidate set drifted")
        candidate_icpns = {item.get("icpn") for item in candidates}
        if len(candidate_icpns) != 25 or candidate_icpns & set(EXPECTED_PROPOSAL_EXCLUSIONS):
            raise RuntimeError("admission exact-identity set is duplicated or contains Proposal identities")
        if any(any(str(icpn).startswith(base) for base in SOURCE_UNAVAILABLE_BASES) for icpn in candidate_icpns):
            raise RuntimeError("source-unavailable Base Device leaked into canonical admission")

        for item in candidates:
            if item.get("decision") != "admit":
                raise RuntimeError(f"{item.get('icpn')}: frozen candidate is not admit")
            mapping = item.get("base_mapping")
            row = item.get("proposed_canonical_row")
            if not isinstance(mapping, dict) or not isinstance(row, dict):
                raise RuntimeError(f"{item.get('icpn')}: frozen mapping/row missing")
            if mapping.get("status") != "unique" or mapping.get("match_count") != 1:
                raise RuntimeError(f"{item.get('icpn')}: mapping is not unique")
            if mapping.get("target_configs") != ["tcl/target/stm32g4x.cfg"]:
                raise RuntimeError(f"{item.get('icpn')}: target config drifted")
            if mapping.get("identifier_kind") != "ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: identifier kind drifted")
            if not isinstance(mapping.get("existing_identifier"), str) or not mapping["existing_identifier"].endswith("x"):
                raise RuntimeError(f"{item.get('icpn')}: ordering-pattern identity drifted")
            if row.get("openocd_target_config") != "tcl/target/stm32g4x.cfg":
                raise RuntimeError(f"{item.get('icpn')}: canonical routing drifted")
            if row.get("mapping_status") != "deterministic_ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: canonical mapping status drifted")
            if row.get("existing_identifier_kind") != "ordering_pattern" or row.get("cmsis_device_name") != "":
                raise RuntimeError(f"{item.get('icpn')}: CMSIS alias leaked into canonical admission")

        by_icpn = {item["icpn"]: item["proposed_canonical_row"] for item in candidates}
        wlcsp = by_icpn.get("STM32G441CBY6TR")
        if not isinstance(wlcsp, dict):
            raise RuntimeError("WLCSP49 exact identity missing from admission plan")
        if (wlcsp.get("package"), wlcsp.get("pin_count"), wlcsp.get("option_suffix")) != ("WLCSP", "49", "TR"):
            raise RuntimeError("STM32G441CBY6TR package-specific metadata drifted")

        inputs = frozen.get("inputs") or {}
        if inputs.get("policy_baseline_sha256") != EXPECTED_POLICY_SHA256:
            raise RuntimeError("4.9C policy binding drifted")
        if inputs.get("mapping_catalog_sha256") != EXPECTED_MAPPING_SHA256:
            raise RuntimeError("OpenOCD mapping catalog binding drifted")
        if inputs.get("production_manifest_sha256") != EXPECTED_PRODUCTION_PRESTATE_SHA256:
            raise RuntimeError("Production prestate binding drifted")

        production = frozen.get("production_snapshot") or {}
        if production.get("exact_icpn_count") != 610 or production.get("base_device_count") != 209:
            raise RuntimeError("Production prestate counts drifted")
        if production.get("stm32g4_exact_icpn_count") != 0:
            raise RuntimeError("STM32G4 appeared in Production during read-only planning")

        for flag in (
            "canonical_write_applied",
            "production_write_applied",
            "programming_algorithm_equivalence_claimed",
            "flash_geometry_equivalence_claimed",
            "option_security_semantics_claimed",
            "physical_target_qualification_claimed",
            "hil_qualification_claimed",
            "runtime_programming_support_claimed",
            "full_stm32g4_surface_covered",
        ):
            if frozen.get(flag) is not False:
                raise RuntimeError(f"Phase 4.9D trust boundary drifted: {flag}")

        print(json.dumps({
            "status": "valid",
            "phase": "4.9D",
            "manufacturer_verified_identity_count": 25,
            "canonical_admission_candidates": 25,
            "capability_unresolved": [],
            "source_unavailable_base_devices": sorted(SOURCE_UNAVAILABLE_BASES),
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
