#!/usr/bin/env python3
"""Fail-closed replay of the frozen STM32U0 U0.4 read-only admission plan."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from stm32u0_phase_u0_4_admission import (
    EXPECTED_ADMITTABLE_COUNT,
    EXPECTED_MAPPING_CATALOG_GIT_BLOB,
    EXPECTED_METADATA_BASELINE_GIT_BLOB,
    EXPECTED_METADATA_ROWS_SHA256,
    EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB,
    admission_plan_is_clean,
    admission_summary,
    build_admission_plan,
)

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "stm32u0-phase-u0.4-admission-plan.json"
EXPECTED_PLAN_SHA256 = "525fc7301c470fbf3f38b4ddb5d1a4effac5c47da343b1ca43654d6278bbbe94"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    try:
        if sha256(PLAN_PATH) != EXPECTED_PLAN_SHA256:
            raise RuntimeError("frozen U0.4 admission-plan byte digest mismatch")
        frozen = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            historical_canonical = Path(td) / "stm32u0-commercial-icpn.csv"
            replay = build_admission_plan(canonical_path=historical_canonical)
        if not admission_plan_is_clean(replay):
            raise RuntimeError("replayed U0.4 admission plan is not clean")
        if admission_summary(replay) != frozen:
            raise RuntimeError("U0.4 admission plan semantic replay drifted")

        if frozen.get("manufacturer_verified_identity_count") != 68:
            raise RuntimeError("manufacturer-verified identity count drifted")
        if frozen.get("metadata_ready_count") != 68:
            raise RuntimeError("metadata-ready count drifted")
        if frozen.get("capability_admittable_count") != EXPECTED_ADMITTABLE_COUNT:
            raise RuntimeError("capability-admittable count drifted")
        if frozen.get("capability_unresolved_count") != 0:
            raise RuntimeError("U0.4 unexpectedly contains capability-unresolved identities")
        if frozen.get("decision_counts") != {
            "admit": 68,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        }:
            raise RuntimeError("U0.4 decision counts drifted")
        if frozen.get("current_mapping_replay") != {
            "unique": 68,
            "ambiguous": 0,
            "unmapped": 0,
        }:
            raise RuntimeError("U0.4 current routing replay counts drifted")

        exact = frozen.get("admission_exact_icpns")
        if not isinstance(exact, list) or len(exact) != 68 or len(set(exact)) != 68:
            raise RuntimeError("U0.4 frozen exact-identity set drifted")
        if exact != sorted(exact):
            raise RuntimeError("U0.4 frozen exact-identity set is not deterministic")

        candidates = replay.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 68:
            raise RuntimeError("U0.4 replay candidate set drifted")
        if {item.get("icpn") for item in candidates} != set(exact):
            raise RuntimeError("U0.4 replay/frozen exact-identity sets disagree")
        for item in candidates:
            if item.get("decision") != "admit":
                raise RuntimeError(f"{item.get('icpn')}: replay candidate is not admit")
            mapping = item.get("base_mapping")
            row = item.get("proposed_canonical_row")
            if not isinstance(mapping, dict) or not isinstance(row, dict):
                raise RuntimeError(f"{item.get('icpn')}: replay mapping/row missing")
            if mapping.get("status") != "unique" or mapping.get("match_count") != 1:
                raise RuntimeError(f"{item.get('icpn')}: mapping is not unique")
            if mapping.get("target_configs") != ["tcl/target/stm32u0x.cfg"]:
                raise RuntimeError(f"{item.get('icpn')}: target config drifted")
            if mapping.get("identifier_kind") != "ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: identifier kind drifted")
            if not isinstance(mapping.get("existing_identifier"), str) or not mapping["existing_identifier"].endswith("x"):
                raise RuntimeError(f"{item.get('icpn')}: ordering-pattern identity drifted")
            if row.get("openocd_target_config") != "tcl/target/stm32u0x.cfg":
                raise RuntimeError(f"{item.get('icpn')}: canonical routing drifted")
            if row.get("mapping_status") != "deterministic_ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: canonical mapping status drifted")
            if row.get("existing_identifier_kind") != "ordering_pattern":
                raise RuntimeError(f"{item.get('icpn')}: canonical identifier kind drifted")
            if row.get("cmsis_device_name") != "":
                raise RuntimeError(f"{item.get('icpn')}: CMSIS alias leaked into canonical admission")

        by_icpn = {item["icpn"]: item["proposed_canonical_row"] for item in candidates}
        m_i = by_icpn.get("STM32U073M8I6")
        m_t = by_icpn.get("STM32U073M8T6")
        if not isinstance(m_i, dict) or not isinstance(m_t, dict):
            raise RuntimeError("package-dependent U073M8 controls are missing")
        if (m_i.get("package"), m_i.get("pin_count")) != ("UFBGA", "81"):
            raise RuntimeError("STM32U073M8I6 package/pin semantics drifted")
        if (m_t.get("package"), m_t.get("pin_count")) != ("LQFP", "80"):
            raise RuntimeError("STM32U073M8T6 package/pin semantics drifted")

        inputs = frozen.get("inputs") or {}
        if inputs.get("policy_baseline_git_blob_sha") != EXPECTED_METADATA_BASELINE_GIT_BLOB:
            raise RuntimeError("U0.3 policy binding drifted")
        if inputs.get("metadata_rows_sha256") != EXPECTED_METADATA_ROWS_SHA256:
            raise RuntimeError("U0.3 metadata row digest drifted")
        if inputs.get("mapping_catalog_git_blob_sha") != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
            raise RuntimeError("current OpenOCD mapping catalog binding drifted")
        if inputs.get("historical_u0_2_mapping_catalog_git_blob_sha") != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
            raise RuntimeError("U0.2 historical OpenOCD mapping binding drifted")
        if inputs.get("production_manifest_git_blob_sha") != EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB:
            raise RuntimeError("Production prestate binding drifted")

        production = frozen.get("production_snapshot") or {}
        if production.get("exact_icpn_count") != 635 or production.get("base_device_count") != 217:
            raise RuntimeError("Production prestate counts drifted")
        if production.get("stm32u0_exact_icpn_count") != 0:
            raise RuntimeError("STM32U0 appeared in Production during read-only planning")

        claims = frozen.get("claims")
        if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
            raise RuntimeError("U0.4 trust boundary escaped fail-closed state")
        if frozen.get("fail_closed") is not True:
            raise RuntimeError("U0.4 fail-closed flag drifted")

        print(json.dumps({
            "status": "valid",
            "phase": "U0.4",
            "manufacturer_verified_identity_count": 68,
            "metadata_ready_count": 68,
            "canonical_admission_candidates": 68,
            "capability_unresolved_count": 0,
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
