#!/usr/bin/env python3
"""Permanent hard-lock validator for STM32L1 L1.4 admission planning."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stm32l1_phase_l1_4_admission import (
    DEFAULT_CANONICAL,
    DEFAULT_FROZEN_PLAN,
    EXPECTED_POLICY_READY_EXACT_SET_SHA256,
    PHASE,
    TARGET_CONFIG,
    admission_plan_is_clean,
    admission_summary,
    build_admission_plan,
)
from validate_stm32l1_phase_l1_3_policy import main as validate_l1_3

EXPECTED_FROZEN_PLAN_GIT_BLOB = "6b75db8c09809534eba530e07ff11cf91085677f"
EXPECTED_FROZEN_PLAN_SHA256 = "ea413a7c1761eded8875737c9e8fde3ff359a4bf52dfde1f52a795179d2457e4"
EXPECTED_UNRESOLVED_SET_SHA256 = "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"
EXPECTED_CANONICAL_INPUT_SHA256 = "a57ec095b1af22963ef5415d7f3cbc1cd4a920dc6e06a9817dca4d029b714971"
EXPECTED_COUNT = 144


class Error(RuntimeError):
    pass


def req(state: bool, message: str) -> None:
    if not state:
        raise Error(message)


def git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body, usedforsecurity=False).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_sha(values: set[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value


def main() -> int:
    req(validate_l1_3() == 0, "L1.3 permanent metadata validation failed")
    req(not DEFAULT_CANONICAL.exists(), "L1.4 requires absent STM32L1 canonical prestate")
    req(git_blob_sha(DEFAULT_FROZEN_PLAN) == EXPECTED_FROZEN_PLAN_GIT_BLOB, "frozen L1.4 plan blob drifted")
    req(sha256(DEFAULT_FROZEN_PLAN) == EXPECTED_FROZEN_PLAN_SHA256, "frozen L1.4 plan digest drifted")

    frozen = read_json(DEFAULT_FROZEN_PLAN)
    plan = build_admission_plan()
    req(admission_plan_is_clean(plan), "L1.4 admission plan is not clean")
    observed = admission_summary(plan)
    req(observed == frozen, "L1.4 deterministic replay differs from frozen plan")

    req(frozen.get("phase") == PHASE and frozen.get("family") == "STM32L1", "frozen plan identity drifted")
    req(frozen.get("manufacturer_verified_identity_count") == EXPECTED_COUNT, "manufacturer identity count drifted")
    req(frozen.get("metadata_ready_count") == EXPECTED_COUNT, "metadata-ready count drifted")
    req(frozen.get("capability_admittable_count") == EXPECTED_COUNT, "capability-admittable count drifted")
    req(frozen.get("capability_unresolved_count") == 0, "capability unresolved set is non-empty")
    req(frozen.get("capability_unresolved_exact_icpns") == [], "unexpected unresolved exact ICPNs")
    req(frozen.get("capability_unresolved_exact_set_sha256") == EXPECTED_UNRESOLVED_SET_SHA256, "unresolved digest drifted")
    req(frozen.get("current_mapping_replay") == {"unique": 144, "ambiguous": 0, "unmapped": 0}, "mapping replay drifted")
    req(frozen.get("decision_counts") == {"admit": 144, "already_present": 0, "manual_review_required": 0, "reject": 0}, "admission decisions drifted")
    req(frozen.get("canonical_rows_before") == 0 and frozen.get("canonical_dataset_admission") == "planned", "canonical prestate drifted")
    req(frozen.get("required_target_config") == TARGET_CONFIG, "target config drifted")

    inputs = frozen.get("inputs")
    req(isinstance(inputs, dict), "frozen inputs missing")
    req(inputs.get("canonical_input_sha256") == EXPECTED_CANONICAL_INPUT_SHA256, "canonical input digest drifted")
    req(inputs.get("policy_ready_exact_icpn_set_sha256") == EXPECTED_POLICY_READY_EXACT_SET_SHA256, "L1.3 ready set binding drifted")

    production = frozen.get("production_snapshot")
    req(isinstance(production, dict), "Production snapshot missing")
    req(production.get("exact_icpn_count") == 1718, "Production exact count drifted")
    req(production.get("base_device_count") == 530, "Production Base Device count drifted")
    req(production.get("family_count") == 12, "Production family count drifted")
    req(production.get("stm32l1_exact_icpn_count") == 0, "STM32L1 escaped into Production")

    claims = frozen.get("claims")
    req(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "L1.4 claims escaped fail-closed state")

    candidates = plan.get("candidates")
    req(isinstance(candidates, list) and len(candidates) == EXPECTED_COUNT, "full candidate replay missing")
    icpns: set[str] = set()
    for item in candidates:
        req(isinstance(item, dict), "malformed admission candidate")
        req(item.get("decision") == "admit", "non-admit candidate escaped clean L1.4 plan")
        row = item.get("proposed_canonical_row")
        mapping = item.get("base_mapping")
        req(isinstance(row, dict) and isinstance(mapping, dict), "admitted candidate lacks row/mapping")
        icpn = row.get("icpn")
        req(isinstance(icpn, str) and icpn not in icpns, "duplicate/invalid admitted ICPN")
        req(mapping.get("status") == "unique", f"{icpn}: mapping no longer unique")
        req(mapping.get("target_config") == TARGET_CONFIG, f"{icpn}: target config drifted")
        req(row.get("mapping_status") == "deterministic_ordering_pattern", f"{icpn}: canonical mapping status drifted")
        req(row.get("openocd_target_config") == TARGET_CONFIG, f"{icpn}: canonical target drifted")
        icpns.add(icpn)
    req(set_sha(icpns) == EXPECTED_POLICY_READY_EXACT_SET_SHA256, "admitted exact set differs from L1.3 ready set")

    print("STM32L1 L1.4 admission plan: VALID")
    print("Manufacturer-verified exact ICPNs: 144")
    print("Metadata-ready exact ICPNs: 144")
    print("Capability-admittable exact ICPNs: 144")
    print("Capability unresolved: 0")
    print("Production write applied: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
