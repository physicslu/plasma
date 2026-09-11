#!/usr/bin/env python3
"""STM32U0 U0.4 deterministic read-only capability/admission planner.

Consumes the closed U0.3 metadata policy, replays the current bounded OpenOCD
ordering-pattern catalog for all 68 retained Active exact ICPNs, and plans
canonical admission only when every exact identity has one unique route to
`tcl/target/stm32u0x.cfg`.

This phase is read-only. It never writes canonical or Production state and does
not claim Flash algorithm equivalence, option/security semantics, HIL, physical
target qualification, or runtime programming support.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    build_admission_plan as build_framework_plan,
    plan_is_clean as framework_plan_is_clean,
    read_csv,
    read_json,
)
from stm32u0_admission_policy import CANONICAL_FIELDS, FAMILY, TARGET_CONFIG, build_canonical_row
from stm32u0_metadata_policy import EXPECTED_ACTIVE_CANDIDATE_COUNT, build_candidate_inputs
from stm32u0_phase_u0_1_foundation import DEFAULT_CATALOG, read_catalog
from stm32u0_phase_u0_2_discovery import resolve_mapping
from stm32u0_phase_u0_3_policy import (
    ADAPTER_ID as METADATA_ADAPTER_ID,
    DEFAULT_POLICY_BASELINE,
    DEFAULT_PRODUCTION_MANIFEST,
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    EXPECTED_PRODUCTION_FAMILY_COUNTS,
    build_policy_plan,
    policy_plan_is_clean,
    policy_summary,
)
from validate_stm32u0_phase_u0_2_retained_evidence import EVIDENCE as EVIDENCE_DIR

HERE = Path(__file__).resolve().parent
PHASE = "U0.4"
POLICY_PHASE = "U0.3"
DISCOVERY_PHASE = "U0.2"
PUBLICATION_PHASE = "U0.5"
ADAPTER_ID = "stm32u0-u0.4-admission"
DEFAULT_CANONICAL = HERE / "stm32u0-commercial-icpn.csv"
DEFAULT_FROZEN_PLAN = HERE / "stm32u0-phase-u0.4-admission-plan.json"

EXPECTED_ADMITTABLE_COUNT = 68
EXPECTED_CAPABILITY_UNRESOLVED = frozenset()
EXPECTED_METADATA_BASELINE_GIT_BLOB = "8f766def80027050e09ee5fe594ef1f379b7c2b3"
EXPECTED_MAPPING_CATALOG_GIT_BLOB = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB = "34ad9299ff0c063a8c8b5de1c253dfee47b63428"
EXPECTED_METADATA_ROWS_SHA256 = "89e15eea9e803014cd21f2a7b60137155a8153e30963f46e07624c23c66bac3d"


class STM32U0AdmissionError(AdmissionError):
    pass


def _git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def _canonical_prestate(canonical_path: Path | None) -> tuple[list[str], list[dict[str, str]], bool]:
    if canonical_path is None or not canonical_path.exists():
        return list(CANONICAL_FIELDS), [], True
    fields, rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise STM32U0AdmissionError("STM32U0 canonical CSV schema mismatch")
    if any(row.get("family") not in ("", FAMILY) for row in rows):
        raise STM32U0AdmissionError("STM32U0 canonical CSV contains a foreign family")
    identities = [row.get("icpn", "") for row in rows]
    if len(identities) != len(set(identities)):
        raise STM32U0AdmissionError("STM32U0 canonical CSV contains duplicate ICPNs")
    if rows:
        raise STM32U0AdmissionError(
            f"U0.4 requires zero-row STM32U0 canonical prestate, got {len(rows)}"
        )
    return fields, rows, False


def _is_unique_mapping(mapping: dict[str, Any]) -> bool:
    return (
        mapping.get("status") == "unique"
        and mapping.get("match_count") == 1
        and mapping.get("identifier_kind") == "ordering_pattern"
        and mapping.get("target_configs") == [TARGET_CONFIG]
        and isinstance(mapping.get("existing_identifier"), str)
        and bool(mapping.get("existing_identifier"))
    )


def build_admission_plan(
    *,
    canonical_path: Path | None = DEFAULT_CANONICAL,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
    mapping_catalog_path: Path = DEFAULT_CATALOG,
) -> dict[str, Any]:
    metadata_plan = build_policy_plan(production_manifest_path=production_manifest_path)
    if not policy_plan_is_clean(metadata_plan):
        raise STM32U0AdmissionError("U0.3 metadata policy is not clean")
    frozen_metadata = read_json(DEFAULT_POLICY_BASELINE)
    if policy_summary(metadata_plan) != frozen_metadata:
        raise STM32U0AdmissionError("U0.3 metadata policy baseline drifted")
    if _git_blob_sha(DEFAULT_POLICY_BASELINE) != EXPECTED_METADATA_BASELINE_GIT_BLOB:
        raise STM32U0AdmissionError("U0.3 metadata policy baseline bytes drifted")
    if frozen_metadata.get("metadata_rows_sha256") != EXPECTED_METADATA_ROWS_SHA256:
        raise STM32U0AdmissionError("U0.3 canonical metadata row digest drifted")

    provenance = read_json(EVIDENCE_DIR / "provenance.json")
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or evidence_id != metadata_plan.get("evidence_id"):
        raise STM32U0AdmissionError("U0.2/U0.3 evidence identity drifted")
    if provenance.get("bounded_discovery_clean") is not True or provenance.get("commercial_identity_clean") is not True:
        raise STM32U0AdmissionError("U0.2 retained commercial discovery is not clean")
    if provenance.get("exact_icpn_candidate_count") != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise STM32U0AdmissionError("U0.2 retained exact-identity count drifted")

    historical_catalog_blob = (provenance.get("source_bindings") or {}).get(
        "openocd_catalog_git_blob_sha"
    )
    current_catalog_blob = _git_blob_sha(mapping_catalog_path)
    if historical_catalog_blob != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
        raise STM32U0AdmissionError("U0.2 historical OpenOCD catalog binding drifted")
    if current_catalog_blob != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
        raise STM32U0AdmissionError(
            "current OpenOCD catalog bytes changed after U0.4 planning boundary"
        )
    if _git_blob_sha(production_manifest_path) != EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB:
        raise STM32U0AdmissionError("U0.3 Production prestate bytes drifted")

    catalog_rows = read_catalog(mapping_catalog_path)
    all_identity_candidates = build_candidate_inputs(evidence_id=evidence_id)
    admissible: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for source_candidate in all_identity_candidates:
        candidate = dict(source_candidate)
        icpn = candidate.get("icpn")
        if not isinstance(icpn, str):
            raise STM32U0AdmissionError("candidate lacks exact ICPN")
        mapping = resolve_mapping(icpn, catalog_rows)
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

    unresolved_icpns = {item["icpn"] for item in unresolved}
    if unresolved_icpns != set(EXPECTED_CAPABILITY_UNRESOLVED):
        raise STM32U0AdmissionError(
            f"U0.4 capability-unresolved set drifted: {sorted(unresolved_icpns)}"
        )
    if len(admissible) != EXPECTED_ADMITTABLE_COUNT:
        raise STM32U0AdmissionError(
            f"U0.4 expected {EXPECTED_ADMITTABLE_COUNT} uniquely routable candidates, got {len(admissible)}"
        )

    fields, canonical_rows, absent = _canonical_prestate(canonical_path)
    plan = build_framework_plan(
        candidate_inputs=admissible,
        canonical_fields=fields,
        canonical_rows=canonical_rows,
        source_provenance=provenance,
        input_bindings={
            "family_adapter": ADAPTER_ID,
            "metadata_adapter": METADATA_ADAPTER_ID,
            "policy_phase": POLICY_PHASE,
            "policy_baseline": DEFAULT_POLICY_BASELINE.name,
            "policy_baseline_git_blob_sha": EXPECTED_METADATA_BASELINE_GIT_BLOB,
            "metadata_rows_sha256": EXPECTED_METADATA_ROWS_SHA256,
            "retained_evidence_directory": EVIDENCE_DIR.name,
            "mapping_catalog": mapping_catalog_path.name,
            "mapping_catalog_git_blob_sha": current_catalog_blob,
            "historical_u0_2_mapping_catalog_git_blob_sha": historical_catalog_blob,
            "canonical_dataset": DEFAULT_CANONICAL.name,
            "canonical_dataset_absent_before_admission": absent,
            "production_manifest": production_manifest_path.name,
            "production_manifest_git_blob_sha": EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB,
        },
        row_builder=build_canonical_row,
    )
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
        "capability_admittable_count": EXPECTED_ADMITTABLE_COUNT,
        "capability_unresolved_count": len(unresolved),
        "capability_unresolved": sorted(unresolved, key=lambda item: item["icpn"]),
        "capability_unresolved_is_identity_rejection": False,
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
        "full_stm32u0_surface_covered": False,
        "fail_closed": True,
    })
    return plan


def admission_plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        framework_plan_is_clean(plan)
        and plan.get("phase") == PHASE
        and plan.get("policy_phase") == POLICY_PHASE
        and plan.get("discovery_phase") == DISCOVERY_PHASE
        and plan.get("publication_phase") == PUBLICATION_PHASE
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("metadata_adapter_id") == METADATA_ADAPTER_ID
        and plan.get("manufacturer_verified_identity_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("metadata_ready_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("candidate_count") == EXPECTED_ADMITTABLE_COUNT
        and plan.get("capability_admittable_count") == EXPECTED_ADMITTABLE_COUNT
        and plan.get("decision_counts") == {
            "admit": EXPECTED_ADMITTABLE_COUNT,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        }
        and plan.get("canonical_rows_before") == 0
        and plan.get("canonical_dataset_admission") == "planned"
        and plan.get("bounded_commercial_surface_complete") is True
        and plan.get("capability_unresolved_count") == 0
        and plan.get("capability_unresolved") == []
        and plan.get("capability_unresolved_is_identity_rejection") is False
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count") == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts") == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32u0_exact_icpn_count") == 0
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
        and plan.get("full_stm32u0_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def admission_summary(plan: dict[str, Any]) -> dict[str, Any]:
    candidates = plan.get("candidates", [])
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "metadata_adapter_id": METADATA_ADAPTER_ID,
        "evidence_id": plan.get("evidence_id"),
        "manufacturer_verified_identity_count": plan.get("manufacturer_verified_identity_count"),
        "metadata_ready_count": plan.get("metadata_ready_count"),
        "capability_admittable_count": plan.get("capability_admittable_count"),
        "capability_unresolved_count": plan.get("capability_unresolved_count"),
        "decision_counts": plan.get("decision_counts"),
        "canonical_rows_before": plan.get("canonical_rows_before"),
        "canonical_dataset_admission": plan.get("canonical_dataset_admission"),
        "canonical_dataset_absent_before_admission": (plan.get("inputs") or {}).get(
            "canonical_dataset_absent_before_admission"
        ),
        "required_target_config": plan.get("required_target_config"),
        "current_mapping_replay": {
            "unique": sum(
                1 for item in candidates
                if isinstance(item.get("base_mapping"), dict)
                and item["base_mapping"].get("status") == "unique"
            ),
            "ambiguous": sum(
                1 for item in candidates
                if isinstance(item.get("base_mapping"), dict)
                and item["base_mapping"].get("status") == "ambiguous"
            ),
            "unmapped": sum(
                1 for item in candidates
                if isinstance(item.get("base_mapping"), dict)
                and item["base_mapping"].get("status") == "unmapped"
            ),
        },
        "inputs": {
            "policy_baseline_git_blob_sha": (plan.get("inputs") or {}).get(
                "policy_baseline_git_blob_sha"
            ),
            "metadata_rows_sha256": (plan.get("inputs") or {}).get("metadata_rows_sha256"),
            "mapping_catalog_git_blob_sha": (plan.get("inputs") or {}).get(
                "mapping_catalog_git_blob_sha"
            ),
            "historical_u0_2_mapping_catalog_git_blob_sha": (plan.get("inputs") or {}).get(
                "historical_u0_2_mapping_catalog_git_blob_sha"
            ),
            "production_manifest_git_blob_sha": (plan.get("inputs") or {}).get(
                "production_manifest_git_blob_sha"
            ),
        },
        "admission_exact_icpns": sorted(str(item.get("icpn")) for item in candidates),
        "production_snapshot": plan.get("production_snapshot"),
        "claims": {
            "canonical_write_applied": plan.get("canonical_write_applied"),
            "production_write_applied": plan.get("production_write_applied"),
            "programming_algorithm_equivalence_claimed": plan.get(
                "programming_algorithm_equivalence_claimed"
            ),
            "flash_geometry_equivalence_claimed": plan.get(
                "flash_geometry_equivalence_claimed"
            ),
            "option_security_semantics_claimed": plan.get(
                "option_security_semantics_claimed"
            ),
            "physical_target_qualification_claimed": plan.get(
                "physical_target_qualification_claimed"
            ),
            "hil_qualification_claimed": plan.get("hil_qualification_claimed"),
            "runtime_programming_support_claimed": plan.get(
                "runtime_programming_support_claimed"
            ),
            "full_stm32u0_surface_covered": plan.get("full_stm32u0_surface_covered"),
        },
        "fail_closed": plan.get("fail_closed"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--full", action="store_true", help="emit the full replay plan")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_admission_plan(canonical_path=args.canonical)
        if not admission_plan_is_clean(plan):
            raise STM32U0AdmissionError("U0.4 admission plan is not clean")
    except (AdmissionError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload_obj = plan if args.full else admission_summary(plan)
    payload = json.dumps(payload_obj, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
