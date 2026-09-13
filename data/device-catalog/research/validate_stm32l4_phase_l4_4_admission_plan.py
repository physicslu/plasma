#!/usr/bin/env python3
"""Hard-lock and replay the STM32L4 L4.4 read-only admission plan."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stm32l4_phase_l4_4_admission import admission_plan_is_clean, admission_summary, build_admission_plan

HERE = Path(__file__).resolve().parent
FROZEN = HERE / "stm32l4-phase-l4.4-admission-plan.json"
EXPECTED_FROZEN_BLOB = "ec660436dd6866abca28a63d6bac774f9ab50e49"
EXPECTED_EMPTY_SET_SHA256 = "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"


class ValidationError(RuntimeError):
    pass


def req(state: bool, message: str) -> None:
    if not state:
        raise ValidationError(message)


def git_blob(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body, usedforsecurity=False).hexdigest()


def main() -> int:
    req(git_blob(FROZEN) == EXPECTED_FROZEN_BLOB, "L4.4 frozen admission plan byte drift")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    req(isinstance(frozen, dict), "L4.4 frozen plan root must be object")
    req(frozen.get("schema_version") == 1, "L4.4 frozen plan schema drift")
    req(frozen.get("phase") == "L4.4" and frozen.get("family") == "STM32L4", "L4.4 identity drift")
    req(frozen.get("capability_admittable_count") == 446, "L4.4 admittable count drift")
    req(frozen.get("capability_unresolved_count") == 0, "L4.4 unresolved count drift")
    req(frozen.get("capability_unresolved_exact_icpns") == [], "L4.4 unresolved exact set drift")
    req(frozen.get("capability_unresolved_exact_set_sha256") == EXPECTED_EMPTY_SET_SHA256, "L4.4 unresolved digest drift")
    req(frozen.get("current_mapping_replay") == {"unique": 446, "ambiguous": 0, "unmapped": 0}, "L4.4 routing replay drift")
    req(frozen.get("decision_counts") == {"admit": 446, "already_present": 0, "manual_review_required": 0, "reject": 0}, "L4.4 admission decisions drift")
    req(frozen.get("canonical_rows_before") == 0 and frozen.get("canonical_dataset_admission") == "planned", "L4.4 canonical prestate drift")
    req(set((frozen.get("claims") or {}).values()) == {False}, "L4.4 fail-closed claim boundary escaped")

    inputs = frozen.get("inputs") or {}
    req(inputs.get("policy_baseline_git_blob_sha") == "176c043ab97285ad7c488ffa4de06c4c20e13c1e", "L4.3 baseline binding drift")
    req(inputs.get("metadata_rows_sha256") == "d67e27b641b295df697b804741b7be1abbb2ee26dd7a24e11482640306bef500", "L4.3 metadata digest drift")
    req(inputs.get("policy_ready_exact_icpn_set_sha256") == "cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45", "L4.3 exact set binding drift")
    req(inputs.get("mapping_catalog_git_blob_sha") == "0ef056e3363e20bb527590c4a4cc1cc0d7afb810", "OpenOCD catalog binding drift")
    req(inputs.get("production_manifest_git_blob_sha") == "4e6a53695e86729063acd8ae102f66cc7eeb06c8", "Production prestate byte binding drift")
    req(inputs.get("production_manifest_sha256") == "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec", "Production prestate semantic digest drift")
    req(inputs.get("canonical_dataset_absent_before_admission") is True, "L4.4 canonical prestate was not absent")

    production = frozen.get("production_snapshot") or {}
    req(production.get("exact_icpn_count") == 1272, "Production exact count drift")
    req(production.get("base_device_count") == 392, "Production Base Device count drift")
    req(production.get("family_count") == 11, "Production family count drift")
    req(production.get("stm32l4_exact_icpn_count") == 0, "Production unexpectedly contains STM32L4")

    plan = build_admission_plan()
    req(admission_plan_is_clean(plan), "L4.4 planner is not clean")
    observed = admission_summary(plan)
    req(observed == frozen, "L4.4 deterministic replay differs from frozen plan")

    print("STM32L4 L4.4 admission plan: VALID")
    print("Manufacturer-verified exact ICPNs: 446")
    print("Metadata-ready exact ICPNs: 446")
    print("Capability-admittable: 446")
    print("Capability-unresolved: 0")
    print("Production exact ICPNs: 1272")
    print("STM32L4 Production: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
