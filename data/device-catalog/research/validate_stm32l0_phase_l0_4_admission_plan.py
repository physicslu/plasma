#!/usr/bin/env python3
"""Hard-lock and replay the STM32L0 L0.4 read-only admission plan."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stm32l0_phase_l0_4_admission import admission_plan_is_clean, admission_summary, build_admission_plan

HERE = Path(__file__).resolve().parent
FROZEN = HERE / "stm32l0-phase-l0.4-admission-plan.json"
EXPECTED_FROZEN_BLOB = "d46b7491ca34fa9d5c8b3adfb16709e9698e417e"
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
    req(git_blob(FROZEN) == EXPECTED_FROZEN_BLOB, "L0.4 frozen admission plan byte drift")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    req(isinstance(frozen, dict), "L0.4 frozen plan root must be object")
    req(frozen.get("schema_version") == 1, "L0.4 frozen plan schema drift")
    req(frozen.get("phase") == "L0.4" and frozen.get("family") == "STM32L0", "L0.4 identity drift")
    req(frozen.get("capability_admittable_count") == 360, "L0.4 admittable count drift")
    req(frozen.get("capability_unresolved_count") == 0, "L0.4 unresolved count drift")
    req(frozen.get("capability_unresolved_exact_icpns") == [], "L0.4 unresolved exact set drift")
    req(frozen.get("capability_unresolved_exact_set_sha256") == EXPECTED_EMPTY_SET_SHA256, "L0.4 unresolved digest drift")
    req(frozen.get("current_mapping_replay") == {"unique": 360, "ambiguous": 0, "unmapped": 0}, "L0.4 routing replay drift")
    req(frozen.get("decision_counts") == {"admit": 360, "already_present": 0, "manual_review_required": 0, "reject": 0}, "L0.4 admission decisions drift")
    req(frozen.get("canonical_rows_before") == 0 and frozen.get("canonical_dataset_admission") == "planned", "L0.4 canonical prestate drift")
    req(set((frozen.get("claims") or {}).values()) == {False}, "L0.4 fail-closed claim boundary escaped")

    inputs = frozen.get("inputs") or {}
    req(inputs.get("policy_baseline_git_blob_sha") == "2cd2e001bc34c1f1335ae78e352e496e59d1e698", "L0.3 baseline binding drift")
    req(inputs.get("metadata_rows_sha256") == "6aefd256256febb6d5f48ec58e44b5fec64489593df333c68723581eb7786a95", "L0.3 metadata digest drift")
    req(inputs.get("policy_ready_exact_icpn_set_sha256") == "8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b", "L0.3 exact set binding drift")
    req(inputs.get("mapping_catalog_git_blob_sha") == "0ef056e3363e20bb527590c4a4cc1cc0d7afb810", "OpenOCD catalog binding drift")
    req(inputs.get("production_manifest_git_blob_sha") == "8abfcc870e51ac4232cdf8d807828cfe4ff5662d", "Production prestate binding drift")
    req(inputs.get("canonical_dataset_absent_before_admission") is True, "L0.4 canonical prestate was not absent")

    production = frozen.get("production_snapshot") or {}
    req(production.get("exact_icpn_count") == 912, "Production exact count drift")
    req(production.get("base_device_count") == 293, "Production Base Device count drift")
    req(production.get("stm32l0_exact_icpn_count") == 0, "Production unexpectedly contains STM32L0")
    req(len(production.get("family_exact_icpn_counts") or {}) == 10, "Production family count drift")

    plan = build_admission_plan()
    req(admission_plan_is_clean(plan), "L0.4 planner is not clean")
    observed = admission_summary(plan)
    req(observed == frozen, "L0.4 deterministic replay differs from frozen plan")

    print("STM32L0 L0.4 admission plan: VALID")
    print("Manufacturer-verified exact ICPNs: 360")
    print("Metadata-ready exact ICPNs: 360")
    print("Capability-admittable: 360")
    print("Capability-unresolved: 0")
    print("Production exact ICPNs: 912")
    print("STM32L0 Production: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
