#!/usr/bin/env python3
"""Fail-closed replay of the frozen STM32F7 Phase 4.6D admission plan."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from stm32f7_phase4_6d_admission import admission_plan_is_clean, build_admission_plan

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "stm32f7-phase4.6d-admission-plan.json"
EXPECTED_PLAN_SHA256 = "1e13d87d9d4e445efb5dbb43b79bad1bf3b5b916126095fb5a55c58580691a7e"
EXPECTED_ICPNS = {
    "STM32F722ICK6", "STM32F722ICT6",
    "STM32F723ICK6", "STM32F723ICT6",
    "STM32F730I8K6", "STM32F730I8K6TR",
    "STM32F732IEK6", "STM32F732IET6",
    "STM32F733IEK6", "STM32F733IET6",
    "STM32F745IEK6", "STM32F745IEK6TR", "STM32F745IEK7",
    "STM32F745IEK7TR", "STM32F745IET6", "STM32F745IET7",
    "STM32F750N8H6", "STM32F778AIY6TR", "STM32F779AIY6TR",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    try:
        if sha256(PLAN_PATH) != EXPECTED_PLAN_SHA256:
            raise RuntimeError("frozen Phase 4.6D admission-plan byte digest mismatch")
        frozen = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        replay = build_admission_plan()
        if not admission_plan_is_clean(replay):
            raise RuntimeError("replayed Phase 4.6D admission plan is not clean")
        if replay != frozen:
            raise RuntimeError("Phase 4.6D admission plan semantic replay drifted")
        if frozen.get("decision_counts") != {
            "admit": 19,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        }:
            raise RuntimeError("Phase 4.6D decision counts drifted")
        candidates = frozen.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 19:
            raise RuntimeError("Phase 4.6D candidate set drifted")
        if {item.get("icpn") for item in candidates} != EXPECTED_ICPNS:
            raise RuntimeError("Phase 4.6D exact ICPN identity set drifted")
        for item in candidates:
            if item.get("decision") != "admit":
                raise RuntimeError(f"{item.get('icpn')}: frozen candidate is not admit")
            mapping = item.get("base_mapping")
            row = item.get("proposed_canonical_row")
            if not isinstance(mapping, dict) or not isinstance(row, dict):
                raise RuntimeError(f"{item.get('icpn')}: frozen mapping/row missing")
            if mapping.get("status") != "unique" or mapping.get("match_count") != 1:
                raise RuntimeError(f"{item.get('icpn')}: mapping is not unique")
            if mapping.get("target_configs") != ["tcl/target/stm32f7x.cfg"]:
                raise RuntimeError(f"{item.get('icpn')}: target config drifted")
            if mapping.get("identifier_kind") != "ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: identifier kind drifted")
            if row.get("openocd_target_config") != "tcl/target/stm32f7x.cfg":
                raise RuntimeError(f"{item.get('icpn')}: canonical routing drifted")
            if row.get("mapping_status") != "deterministic_ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: canonical mapping status drifted")
        for flag in (
            "canonical_write_applied",
            "production_write_applied",
            "programming_algorithm_equivalence_claimed",
            "physical_target_qualification_claimed",
            "runtime_programming_support_claimed",
            "full_stm32f7_surface_covered",
        ):
            if frozen.get(flag) is not False:
                raise RuntimeError(f"Phase 4.6D trust boundary drifted: {flag}")
        if frozen.get("lifecycle_exclusions_preserved") != 5:
            raise RuntimeError("lifecycle exclusions not preserved")
        if frozen.get("source_unavailable_exclusions_preserved") != 2:
            raise RuntimeError("source-unavailable exclusions not preserved")
        print(json.dumps({
            "status": "valid",
            "phase": "4.6D",
            "candidate_count": 19,
            "decision_counts": frozen["decision_counts"],
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
