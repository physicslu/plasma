#!/usr/bin/env python3
"""Phase 4.6D deterministic STM32F7 admission planner.

Requires the closed Phase 4.6C metadata policy, independently resolves current
OpenOCD ordering-pattern capability, and delegates duplicate/conflict mechanics
to the generic admission framework. This module is read-only; canonical and
Production publication remain separate controlled transactions.
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
from stm32f7_admission_policy import CANONICAL_FIELDS, FAMILY, build_canonical_row
from stm32f7_foundation import DEFAULT_CATALOG, read_catalog
from stm32f7_metadata_policy import EXPECTED_ACTIVE_CANDIDATE_COUNT, build_candidate_inputs
from stm32f7_phase4_6b_discovery import resolve_mapping
from stm32f7_phase4_6c_policy import (
    ADAPTER_ID as METADATA_ADAPTER_ID,
    DEFAULT_POLICY_BASELINE,
    DEFAULT_PRODUCTION_MANIFEST,
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    EXPECTED_PRODUCTION_FAMILY_COUNTS,
    policy_plan_is_clean,
    validate_policy,
)
from validate_stm32f7_phase4_6b_retained_evidence import (
    DEFAULT_BASELINE as DISCOVERY_BASELINE,
    DEFAULT_EVIDENCE_DIR,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.6D"
POLICY_PHASE = "4.6C"
DISCOVERY_PHASE = "4.6B"
ADAPTER_ID = "stm32f7-phase4.6d-admission"
DEFAULT_CANONICAL = HERE / "stm32f7-commercial-icpn.csv"


class STM32F7AdmissionError(AdmissionError):
    pass


def _canonical_prestate(canonical_path: Path | None) -> tuple[list[str], list[dict[str, str]], bool]:
    if canonical_path is None or not canonical_path.exists():
        return list(CANONICAL_FIELDS), [], True
    fields, rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise STM32F7AdmissionError("STM32F7 canonical CSV schema mismatch")
    if any(row.get("family") not in ("", FAMILY) for row in rows):
        raise STM32F7AdmissionError("STM32F7 canonical CSV contains a foreign family")
    identities = [row.get("icpn", "") for row in rows]
    if len(identities) != len(set(identities)):
        raise STM32F7AdmissionError("STM32F7 canonical CSV contains duplicate ICPNs")
    if rows:
        raise STM32F7AdmissionError(
            f"Phase 4.6D requires zero-row STM32F7 canonical prestate, got {len(rows)}"
        )
    return fields, rows, False


def build_admission_plan(
    *,
    canonical_path: Path | None = DEFAULT_CANONICAL,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
    mapping_catalog_path: Path = DEFAULT_CATALOG,
) -> dict[str, Any]:
    metadata_plan, _ = validate_policy(production_manifest_path=production_manifest_path)
    if not policy_plan_is_clean(metadata_plan):
        raise STM32F7AdmissionError("Phase 4.6C metadata policy is not clean")

    provenance = read_json(DEFAULT_EVIDENCE_DIR / "provenance.json")
    discovery_baseline = read_json(DISCOVERY_BASELINE)
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or evidence_id != metadata_plan.get("evidence_id"):
        raise STM32F7AdmissionError("4.6B/4.6C evidence identity drifted")

    catalog_rows = read_catalog(mapping_catalog_path)
    candidate_inputs = build_candidate_inputs(
        discovery_baseline=discovery_baseline,
        evidence_id=evidence_id,
    )
    for candidate in candidate_inputs:
        icpn = candidate.get("icpn")
        if not isinstance(icpn, str):
            raise STM32F7AdmissionError("candidate lacks exact ICPN")
        candidate["base_mapping"] = resolve_mapping(icpn, catalog_rows)

    fields, canonical_rows, absent = _canonical_prestate(canonical_path)
    plan = build_framework_plan(
        candidate_inputs=candidate_inputs,
        canonical_fields=fields,
        canonical_rows=canonical_rows,
        source_provenance=provenance,
        input_bindings={
            "family_adapter": ADAPTER_ID,
            "metadata_adapter": METADATA_ADAPTER_ID,
            "policy_phase": POLICY_PHASE,
            "policy_baseline": DEFAULT_POLICY_BASELINE.name,
            "policy_baseline_sha256": file_sha256(DEFAULT_POLICY_BASELINE),
            "retained_evidence_directory": DEFAULT_EVIDENCE_DIR.name,
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
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "metadata_adapter_id": METADATA_ADAPTER_ID,
        "lifecycle_exclusions_preserved": 5,
        "source_unavailable_exclusions_preserved": 2,
        "production_snapshot": metadata_plan["production_snapshot"],
        "metadata_policy_clean": True,
        "capability_mapping_gate_applied": True,
        "required_target_config": "tcl/target/stm32f7x.cfg",
        "canonical_write_applied": False,
        "production_write_applied": False,
        "programming_algorithm_equivalence_claimed": False,
        "physical_target_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
        "full_stm32f7_surface_covered": False,
        "fail_closed": True,
    })
    return plan


def admission_plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        framework_plan_is_clean(plan)
        and plan.get("phase") == PHASE
        and plan.get("policy_phase") == POLICY_PHASE
        and plan.get("discovery_phase") == DISCOVERY_PHASE
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("metadata_adapter_id") == METADATA_ADAPTER_ID
        and plan.get("candidate_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("decision_counts") == {
            "admit": EXPECTED_ACTIVE_CANDIDATE_COUNT,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        }
        and plan.get("canonical_rows_before") == 0
        and plan.get("canonical_dataset_admission") == "planned"
        and plan.get("lifecycle_exclusions_preserved") == 5
        and plan.get("source_unavailable_exclusions_preserved") == 2
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count") == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts") == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32f7_exact_icpn_count") == 0
        and plan.get("metadata_policy_clean") is True
        and plan.get("capability_mapping_gate_applied") is True
        and plan.get("required_target_config") == "tcl/target/stm32f7x.cfg"
        and plan.get("canonical_write_applied") is False
        and plan.get("production_write_applied") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("physical_target_qualification_claimed") is False
        and plan.get("runtime_programming_support_claimed") is False
        and plan.get("full_stm32f7_surface_covered") is False
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
            raise STM32F7AdmissionError("Phase 4.6D admission plan is not clean")
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
