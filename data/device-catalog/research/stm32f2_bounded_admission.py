#!/usr/bin/env python3
"""Generic deterministic admission planner for bounded STM32F2 policy batches.

The planner requires a closed immutable policy baseline, binds the current
canonical input, and delegates duplicate/conflict mechanics to the generic
Device Catalog admission framework.  It is read-only; publication remains a
separate controlled transaction.
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
from stm32f2_admission_policy import CANONICAL_FIELDS, FAMILY
from stm32f2_bounded_policy import (
    DEFAULT_CANONICAL,
    DEFAULT_PRODUCTION_MANIFEST,
    DEFAULT_REGISTRY,
    STM32F2PolicySpec,
    _row_builder,
    build_policy_plan,
    load_policy_spec,
    policy_plan_is_clean,
    policy_summary,
)


def load_admission_spec(
    phase: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY,
) -> STM32F2PolicySpec:
    registry = read_json(registry_path)
    batches = registry.get("batches")
    if not isinstance(batches, dict):
        raise AdmissionError("STM32F2 bounded policy registry batches are missing")
    matches = [
        policy_phase
        for policy_phase, raw in batches.items()
        if isinstance(raw, dict) and raw.get("admission_phase") == phase
    ]
    if len(matches) != 1:
        raise AdmissionError(f"unregistered or ambiguous STM32F2 admission phase: {phase}")
    return load_policy_spec(matches[0], registry_path=registry_path)


def build_admission_plan(
    *,
    phase: str,
    registry_path: Path = DEFAULT_REGISTRY,
    canonical_path: Path = DEFAULT_CANONICAL,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
) -> dict[str, Any]:
    spec = load_admission_spec(phase, registry_path=registry_path)
    policy_plan = build_policy_plan(
        phase=spec.phase,
        registry_path=registry_path,
        canonical_path=canonical_path,
        production_manifest_path=production_manifest_path,
    )
    if not policy_plan_is_clean(policy_plan, spec=spec):
        raise AdmissionError(f"{spec.phase}: policy plan is not clean")
    policy_baseline = read_json(spec.policy_baseline_path)
    if policy_summary(policy_plan, spec=spec) != policy_baseline:
        raise AdmissionError(f"{spec.phase}: policy is not closed at its guarded boundary")

    fields, canonical_rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise AdmissionError("STM32F2 canonical CSV schema mismatch")
    if any(row.get("family") != FAMILY for row in canonical_rows):
        raise AdmissionError("STM32F2 canonical CSV contains a foreign family")
    identities = [row.get("icpn", "") for row in canonical_rows]
    if len(identities) != len(set(identities)):
        raise AdmissionError("STM32F2 canonical CSV contains duplicate ICPNs")
    if len(canonical_rows) != spec.expected_canonical_icpn_count_before:
        raise AdmissionError(
            f"{phase}: current canonical boundary is {len(canonical_rows)} rows; "
            f"expected {spec.expected_canonical_icpn_count_before}"
        )

    candidate_inputs = [
        {
            "manufacturer": item["manufacturer"],
            "base_device": item["base_device"],
            "icpn": item["icpn"],
            "authoritative_evidence": item["authoritative_evidence"],
            "base_mapping": item["base_mapping"],
        }
        for item in policy_plan["candidates"]
    ]
    plan = build_framework_plan(
        candidate_inputs=candidate_inputs,
        canonical_fields=fields,
        canonical_rows=canonical_rows,
        source_provenance={
            "evidence_id": policy_plan["evidence_id"],
            **policy_plan["source_provenance"],
        },
        input_bindings={
            "family_adapter": spec.adapter_id,
            "policy_phase": spec.phase,
            "policy_registry": registry_path.name,
            "policy_registry_sha256": file_sha256(registry_path),
            "policy_baseline": spec.policy_baseline_path.name,
            "policy_baseline_sha256": file_sha256(spec.policy_baseline_path),
            "retained_evidence_directory": policy_plan["inputs"]["retained_evidence_directory"],
            "retained_evidence_baseline": policy_plan["inputs"]["retained_evidence_baseline"],
            "retained_evidence_baseline_sha256": policy_plan["inputs"][
                "retained_evidence_baseline_sha256"
            ],
            "canonical_dataset": canonical_path.name,
            "production_manifest": production_manifest_path.name,
            "production_manifest_sha256": file_sha256(production_manifest_path),
        },
        row_builder=_row_builder(spec),
    )
    plan.update(
        {
            "phase": phase,
            "policy_phase": spec.phase,
            "discovery_phase": spec.discovery_phase,
            "family": FAMILY,
            "adapter_id": spec.adapter_id,
            "lifecycle_exclusions": [],
            "production_snapshot": policy_plan["production_snapshot"],
            "production_write_applied": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "full_stm32f2_surface_covered": False,
            "fail_closed": True,
        }
    )
    return plan


def admission_plan_is_clean(plan: dict[str, Any], *, spec: STM32F2PolicySpec) -> bool:
    expected = spec.expected_candidate_count
    return (
        framework_plan_is_clean(plan)
        and plan.get("phase") == spec.admission_phase
        and plan.get("policy_phase") == spec.phase
        and plan.get("discovery_phase") == spec.discovery_phase
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == spec.adapter_id
        and plan.get("candidate_count") == expected
        and plan.get("decision_counts")
        == {
            "admit": expected,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        }
        and plan.get("canonical_rows_before") == spec.expected_canonical_icpn_count_before
        and plan.get("canonical_dataset_admission") == "planned"
        and plan.get("lifecycle_exclusions") == []
        and plan.get("production_snapshot", {}).get("exact_icpn_count")
        == spec.expected_production_exact_icpn_count
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts")
        == spec.expected_production_family_counts
        and plan.get("production_write_applied") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("runtime_programming_support_claimed") is False
        and plan.get("full_stm32f2_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        spec = load_admission_spec(args.phase, registry_path=args.registry)
        plan = build_admission_plan(
            phase=args.phase,
            registry_path=args.registry,
            canonical_path=args.canonical,
        )
        if not admission_plan_is_clean(plan, spec=spec):
            raise AdmissionError(f"{args.phase}: bounded admission plan is not clean")
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
