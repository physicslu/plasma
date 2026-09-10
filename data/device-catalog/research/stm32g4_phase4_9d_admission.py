#!/usr/bin/env python3
"""Phase 4.9D deterministic STM32G4 capability/admission planner.

Requires the closed Phase 4.9C metadata policy, then independently resolves the
current guarded OpenOCD ordering-pattern surface for each of the 25 retained
Active exact ICPNs. Only one strict ordering-pattern match to stm32g4x.cfg can
enter the generic canonical-admission transaction.

Phase 4.9D is read-only planning. It does not write the canonical dataset or
Production and does not claim Flash algorithm equivalence, option/security
semantics, physical/HIL qualification, or runtime programming support.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    build_admission_plan as build_framework_plan,
    file_sha256,
    plan_is_clean as framework_plan_is_clean,
    read_csv,
    read_json,
)
from stm32g4_admission_policy import CANONICAL_FIELDS, FAMILY, TARGET_CONFIG, build_canonical_row
from stm32g4_foundation import DEFAULT_CATALOG, read_catalog
from stm32g4_metadata_policy import (
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    EXPECTED_PROPOSAL_EXCLUSIONS,
    SOURCE_UNAVAILABLE_BASES,
    build_candidate_inputs,
)
from stm32g4_phase4_9b_discovery import resolve_mapping
from stm32g4_phase4_9c_policy import (
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
from validate_stm32g4_phase4_9b_retained_evidence import (
    BASELINE as DISCOVERY_BASELINE,
    EVIDENCE as EVIDENCE_DIR,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.9D"
POLICY_PHASE = "4.9C"
DISCOVERY_PHASE = "4.9B"
PUBLICATION_PHASE = "4.9E"
ADAPTER_ID = "stm32g4-phase4.9d-admission"
DEFAULT_CANONICAL = HERE / "stm32g4-commercial-icpn.csv"
EXPECTED_ADMITTABLE_COUNT = 25
EXPECTED_CAPABILITY_UNRESOLVED = frozenset()


class STM32G4AdmissionError(AdmissionError):
    pass


def _canonical_prestate(canonical_path: Path | None) -> tuple[list[str], list[dict[str, str]], bool]:
    if canonical_path is None or not canonical_path.exists():
        return list(CANONICAL_FIELDS), [], True
    fields, rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise STM32G4AdmissionError("STM32G4 canonical CSV schema mismatch")
    if any(row.get("family") not in ("", FAMILY) for row in rows):
        raise STM32G4AdmissionError("STM32G4 canonical CSV contains a foreign family")
    identities = [row.get("icpn", "") for row in rows]
    if len(identities) != len(set(identities)):
        raise STM32G4AdmissionError("STM32G4 canonical CSV contains duplicate ICPNs")
    if rows:
        raise STM32G4AdmissionError(
            f"Phase 4.9D requires zero-row STM32G4 canonical prestate, got {len(rows)}"
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
        raise STM32G4AdmissionError("Phase 4.9C metadata policy is not clean")
    if policy_summary(metadata_plan) != read_json(DEFAULT_POLICY_BASELINE):
        raise STM32G4AdmissionError("Phase 4.9C policy baseline drifted")

    provenance = read_json(EVIDENCE_DIR / "provenance.json")
    discovery_baseline = read_json(DISCOVERY_BASELINE)
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or evidence_id != metadata_plan.get("evidence_id"):
        raise STM32G4AdmissionError("4.9B/4.9C evidence identity drifted")
    if provenance.get("bounded_discovery_clean") is not True:
        raise STM32G4AdmissionError("Phase 4.9B bounded discovery is not clean")
    if provenance.get("commercial_identity_clean") is not False:
        raise STM32G4AdmissionError("Phase 4.9B commercial-incomplete boundary drifted")
    if provenance.get("source_unavailable_exclusion_count") != len(SOURCE_UNAVAILABLE_BASES):
        raise STM32G4AdmissionError("Phase 4.9B source-unavailable exclusion count drifted")

    catalog_rows = read_catalog(mapping_catalog_path)
    all_identity_candidates = build_candidate_inputs(
        discovery_baseline=discovery_baseline,
        evidence_id=evidence_id,
    )
    admissible: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for candidate in all_identity_candidates:
        icpn = candidate.get("icpn")
        if not isinstance(icpn, str):
            raise STM32G4AdmissionError("candidate lacks exact ICPN")
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
                "capability_status": "openocd_ordering_pattern_unresolved",
                "mapping": mapping,
                "policy_action": "exclude_from_canonical_admission_until_positive_route_evidence",
            })

    unresolved_icpns = {item["icpn"] for item in unresolved}
    if unresolved_icpns != set(EXPECTED_CAPABILITY_UNRESOLVED):
        raise STM32G4AdmissionError(
            f"Phase 4.9D capability-unresolved set drifted: {sorted(unresolved_icpns)}"
        )
    if len(admissible) != EXPECTED_ADMITTABLE_COUNT:
        raise STM32G4AdmissionError(
            f"Phase 4.9D expected {EXPECTED_ADMITTABLE_COUNT} uniquely routable candidates, got {len(admissible)}"
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
            "policy_baseline_sha256": file_sha256(DEFAULT_POLICY_BASELINE),
            "retained_evidence_directory": EVIDENCE_DIR.name,
            "retained_discovery_baseline": DISCOVERY_BASELINE.name,
            "retained_discovery_baseline_sha256": file_sha256(DISCOVERY_BASELINE),
            "mapping_catalog": mapping_catalog_path.name,
            "mapping_catalog_sha256": file_sha256(mapping_catalog_path),
            "canonical_dataset": DEFAULT_CANONICAL.name,
            "canonical_dataset_absent_before_admission": absent,
            "production_manifest": production_manifest_path.name,
            "production_manifest_sha256": file_sha256(production_manifest_path),
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
        "bounded_commercial_surface_complete": False,
        "source_unavailable_base_devices": sorted(SOURCE_UNAVAILABLE_BASES),
        "proposal_exact_identity_exclusions": sorted(EXPECTED_PROPOSAL_EXCLUSIONS),
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
        "full_stm32g4_surface_covered": False,
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
        and plan.get("bounded_commercial_surface_complete") is False
        and plan.get("source_unavailable_base_devices") == sorted(SOURCE_UNAVAILABLE_BASES)
        and plan.get("proposal_exact_identity_exclusions") == sorted(EXPECTED_PROPOSAL_EXCLUSIONS)
        and plan.get("capability_unresolved_count") == 0
        and plan.get("capability_unresolved") == []
        and plan.get("capability_unresolved_is_identity_rejection") is False
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count") == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts") == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32g4_exact_icpn_count") == 0
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
        and plan.get("full_stm32g4_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_admission_plan(canonical_path=args.canonical)
        if not admission_plan_is_clean(plan):
            raise STM32G4AdmissionError("Phase 4.9D admission plan is not clean")
    except (AdmissionError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
