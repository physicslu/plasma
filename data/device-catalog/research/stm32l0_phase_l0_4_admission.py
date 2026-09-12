#!/usr/bin/env python3
"""STM32L0 L0.4 deterministic read-only capability/admission planner."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    build_admission_plan as build_framework_plan,
    plan_is_clean as framework_plan_is_clean,
    read_csv,
)
from stm32l0_admission_policy import CANONICAL_FIELDS, FAMILY, TARGET_CONFIG, build_canonical_row
from stm32l0_metadata_policy import EXPECTED_ACTIVE_CANDIDATE_COUNT, build_candidate_inputs
from stm32l0_phase_l0_1_foundation import DEFAULT_CATALOG, read_catalog
from stm32l0_phase_l0_2_discovery import resolve_mapping
from stm32l0_phase_l0_3_policy import build_plan as build_metadata_plan, plan_is_clean as metadata_plan_is_clean
from validate_stm32l0_phase_l0_3_policy import main as validate_l0_3

HERE = Path(__file__).resolve().parent
PHASE = "L0.4"
POLICY_PHASE = "L0.3"
DISCOVERY_PHASE = "L0.2"
PUBLICATION_PHASE = "L0.5"
ADAPTER_ID = "stm32l0-l0.4-admission"
METADATA_ADAPTER_ID = "stm32l0-l0.3-metadata"
DEFAULT_CANONICAL = HERE / "stm32l0-commercial-icpn.csv"
DEFAULT_POLICY_BASELINE = HERE / "stm32l0-phase-l0.3-policy-baseline.json"
DEFAULT_FROZEN_PLAN = HERE / "stm32l0-phase-l0.4-admission-plan.json"
PRODUCTION = HERE / "stm32l0-phase-l0.4-production-manifest-prestate.json"

EXPECTED_METADATA_BASELINE_GIT_BLOB = "2cd2e001bc34c1f1335ae78e352e496e59d1e698"
EXPECTED_METADATA_ROWS_SHA256 = "6aefd256256febb6d5f48ec58e44b5fec64489593df333c68723581eb7786a95"
EXPECTED_POLICY_READY_EXACT_SET_SHA256 = "8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b"
EXPECTED_MAPPING_CATALOG_GIT_BLOB = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB = "8abfcc870e51ac4232cdf8d807828cfe4ff5662d"


class STM32L0AdmissionError(AdmissionError):
    pass


def _git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body, usedforsecurity=False).hexdigest()


def _set_sha(values: list[str] | set[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise STM32L0AdmissionError(f"{path.name}: expected JSON object")
    return value


def _canonical_prestate(canonical_path: Path | None) -> tuple[list[str], list[dict[str, str]], bool]:
    if canonical_path is None or not canonical_path.exists():
        return list(CANONICAL_FIELDS), [], True
    fields, rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise STM32L0AdmissionError("STM32L0 canonical CSV schema mismatch")
    if any(row.get("family") not in ("", FAMILY) for row in rows):
        raise STM32L0AdmissionError("STM32L0 canonical CSV contains a foreign family")
    identities = [row.get("icpn", "") for row in rows]
    if len(identities) != len(set(identities)):
        raise STM32L0AdmissionError("STM32L0 canonical CSV contains duplicate ICPNs")
    if rows:
        raise STM32L0AdmissionError(f"L0.4 requires zero-row STM32L0 canonical prestate, got {len(rows)}")
    return fields, rows, False


def _is_unique_mapping(mapping: dict[str, Any]) -> bool:
    ordering_pattern = mapping.get("ordering_pattern")
    return (
        mapping.get("status") == "unique"
        and mapping.get("target_config") == TARGET_CONFIG
        and isinstance(ordering_pattern, str)
        and ordering_pattern.endswith("x")
        and bool(ordering_pattern[:-1])
    )


def build_admission_plan(
    *,
    canonical_path: Path | None = None,
    mapping_catalog_path: Path = DEFAULT_CATALOG,
) -> dict[str, Any]:
    if validate_l0_3() != 0:
        raise STM32L0AdmissionError("L0.3 hard-lock validation failed")
    metadata_plan = build_metadata_plan()
    if not metadata_plan_is_clean(metadata_plan):
        raise STM32L0AdmissionError("L0.3 metadata plan is not clean")
    baseline = _read_json(DEFAULT_POLICY_BASELINE)
    if _git_blob_sha(DEFAULT_POLICY_BASELINE) != EXPECTED_METADATA_BASELINE_GIT_BLOB:
        raise STM32L0AdmissionError("L0.3 metadata baseline bytes drifted")
    if baseline.get("metadata_rows_sha256") != EXPECTED_METADATA_ROWS_SHA256:
        raise STM32L0AdmissionError("L0.3 metadata rows digest drifted")
    if baseline.get("metadata_ready_exact_icpn_set_sha256") != EXPECTED_POLICY_READY_EXACT_SET_SHA256:
        raise STM32L0AdmissionError("L0.3 metadata-ready exact set drifted")
    if baseline.get("decision_counts") != {"metadata_ready": 360, "manual_review_required": 0, "reject": 0}:
        raise STM32L0AdmissionError("L0.3 metadata disposition drifted")

    if _git_blob_sha(mapping_catalog_path) != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
        raise STM32L0AdmissionError("OpenOCD mapping catalog bytes drifted")
    if _git_blob_sha(PRODUCTION) != EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB:
        raise STM32L0AdmissionError("L0.4 frozen Production prestate drifted")

    catalog_rows = read_catalog(mapping_catalog_path)
    all_candidates = build_candidate_inputs()
    if len(all_candidates) != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise STM32L0AdmissionError("L0.3 exact candidate count drifted")

    admissible: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    routing = Counter()
    for source_candidate in all_candidates:
        candidate = dict(source_candidate)
        icpn = candidate.get("icpn")
        if not isinstance(icpn, str):
            raise STM32L0AdmissionError("candidate lacks exact ICPN")
        mapping = resolve_mapping(icpn, catalog_rows)
        status = str(mapping.get("status"))
        routing[status] += 1
        candidate["base_mapping"] = mapping
        if _is_unique_mapping(mapping):
            admissible.append(candidate)
        else:
            unresolved.append({
                "manufacturer": candidate["manufacturer"],
                "base_device": candidate["base_device"],
                "icpn": icpn,
                "identity_status": "manufacturer_verified_active",
                "metadata_status": "metadata_ready",
                "capability_status": "openocd_ordering_pattern_unresolved",
                "mapping": mapping,
                "policy_action": "exclude_from_canonical_admission_until_positive_route_evidence",
            })

    if sum(routing.values()) != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise STM32L0AdmissionError("L0.4 routing replay cardinality drifted")
    if set(routing) - {"unique", "ambiguous", "unmapped"}:
        raise STM32L0AdmissionError(f"L0.4 unsupported routing states: {dict(routing)}")

    fields, canonical_rows, absent = _canonical_prestate(canonical_path)
    evidence_id = baseline.get("inputs", {}).get("retained_l0_2_evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise STM32L0AdmissionError("L0.3 baseline lost retained L0.2 evidence identity")
    plan = build_framework_plan(
        candidate_inputs=admissible,
        canonical_fields=fields,
        canonical_rows=canonical_rows,
        source_provenance={
            "evidence_id": evidence_id,
            "identity_phase": DISCOVERY_PHASE,
            "metadata_phase": POLICY_PHASE,
        },
        input_bindings={
            "family_adapter": ADAPTER_ID,
            "metadata_adapter": METADATA_ADAPTER_ID,
            "policy_phase": POLICY_PHASE,
            "policy_baseline": DEFAULT_POLICY_BASELINE.name,
            "policy_baseline_git_blob_sha": EXPECTED_METADATA_BASELINE_GIT_BLOB,
            "metadata_rows_sha256": EXPECTED_METADATA_ROWS_SHA256,
            "policy_ready_exact_icpn_set_sha256": EXPECTED_POLICY_READY_EXACT_SET_SHA256,
            "mapping_catalog": mapping_catalog_path.name,
            "mapping_catalog_git_blob_sha": EXPECTED_MAPPING_CATALOG_GIT_BLOB,
            "canonical_dataset": DEFAULT_CANONICAL.name,
            "canonical_dataset_absent_before_admission": absent,
            "production_manifest": "production/icpn-v1-manifest.json",
            "production_manifest_git_blob_sha": EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB,
        },
        row_builder=build_canonical_row,
    )
    unresolved_icpns = sorted(item["icpn"] for item in unresolved)
    plan.update({
        "phase": PHASE,
        "policy_phase": POLICY_PHASE,
        "discovery_phase": DISCOVERY_PHASE,
        "publication_phase": PUBLICATION_PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "metadata_adapter_id": METADATA_ADAPTER_ID,
        "manufacturer_verified_identity_count": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "metadata_ready_count": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "bounded_commercial_surface_complete": True,
        "capability_admittable_count": len(admissible),
        "capability_unresolved_count": len(unresolved),
        "capability_unresolved": sorted(unresolved, key=lambda item: item["icpn"]),
        "capability_unresolved_exact_icpns": unresolved_icpns,
        "capability_unresolved_exact_set_sha256": _set_sha(unresolved_icpns),
        "capability_unresolved_is_identity_rejection": False,
        "current_mapping_replay": {
            "unique": routing["unique"],
            "ambiguous": routing["ambiguous"],
            "unmapped": routing["unmapped"],
        },
        "production_snapshot": metadata_plan["production_snapshot"],
        "metadata_policy_clean": True,
        "capability_mapping_gate_applied": True,
        "required_target_config": TARGET_CONFIG,
        "canonical_write_applied": False,
        "production_write_applied": False,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_equivalence_claimed": False,
        "option_security_semantics_claimed": False,
        "physical_target_qualification_claimed": False,
        "hil_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
        "full_stm32l0_surface_covered": False,
        "fail_closed": True,
    })
    return plan


def admission_plan_is_clean(plan: dict[str, Any]) -> bool:
    replay = plan.get("current_mapping_replay", {})
    return (
        framework_plan_is_clean(plan)
        and plan.get("phase") == PHASE
        and plan.get("family") == FAMILY
        and plan.get("manufacturer_verified_identity_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("metadata_ready_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("candidate_count") == plan.get("capability_admittable_count")
        and plan.get("capability_admittable_count", 0) + plan.get("capability_unresolved_count", 0) == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and sum(replay.get(key, 0) for key in ("unique", "ambiguous", "unmapped")) == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and replay.get("unique") == plan.get("capability_admittable_count")
        and replay.get("ambiguous", 0) + replay.get("unmapped", 0) == plan.get("capability_unresolved_count")
        and plan.get("capability_unresolved_is_identity_rejection") is False
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == 912
        and plan.get("production_snapshot", {}).get("base_device_count") == 293
        and plan.get("production_snapshot", {}).get("stm32l0_exact_icpn_count") == 0
        and plan.get("metadata_policy_clean") is True
        and plan.get("capability_mapping_gate_applied") is True
        and plan.get("required_target_config") == TARGET_CONFIG
        and plan.get("canonical_write_applied") is False
        and plan.get("production_write_applied") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("flash_geometry_equivalence_claimed") is False
        and plan.get("option_security_semantics_claimed") is False
        and plan.get("physical_target_qualification_claimed") is False
        and plan.get("hil_qualification_claimed") is False
        and plan.get("runtime_programming_support_claimed") is False
        and plan.get("full_stm32l0_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def admission_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "metadata_adapter_id": METADATA_ADAPTER_ID,
        "manufacturer_verified_identity_count": plan.get("manufacturer_verified_identity_count"),
        "metadata_ready_count": plan.get("metadata_ready_count"),
        "capability_admittable_count": plan.get("capability_admittable_count"),
        "capability_unresolved_count": plan.get("capability_unresolved_count"),
        "capability_unresolved_exact_icpns": plan.get("capability_unresolved_exact_icpns"),
        "capability_unresolved_exact_set_sha256": plan.get("capability_unresolved_exact_set_sha256"),
        "decision_counts": plan.get("decision_counts"),
        "canonical_rows_before": plan.get("canonical_rows_before"),
        "canonical_dataset_admission": plan.get("canonical_dataset_admission"),
        "required_target_config": plan.get("required_target_config"),
        "current_mapping_replay": plan.get("current_mapping_replay"),
        "production_snapshot": plan.get("production_snapshot"),
        "inputs": plan.get("inputs"),
        "claims": {
            "canonical_write_applied": plan.get("canonical_write_applied"),
            "production_write_applied": plan.get("production_write_applied"),
            "programming_algorithm_equivalence_claimed": plan.get("programming_algorithm_equivalence_claimed"),
            "flash_geometry_equivalence_claimed": plan.get("flash_geometry_equivalence_claimed"),
            "option_security_semantics_claimed": plan.get("option_security_semantics_claimed"),
            "physical_target_qualification_claimed": plan.get("physical_target_qualification_claimed"),
            "hil_qualification_claimed": plan.get("hil_qualification_claimed"),
            "runtime_programming_support_claimed": plan.get("runtime_programming_support_claimed"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    plan = build_admission_plan()
    payload = admission_summary(plan) if args.summary_only else plan
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if admission_plan_is_clean(plan) else 1


if __name__ == "__main__":
    raise SystemExit(main())
