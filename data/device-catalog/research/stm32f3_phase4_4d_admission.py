#!/usr/bin/env python3
"""Phase 4.4D deterministic STM32F3 admission planner.

Requires the closed Phase 4.4C policy baseline, rebuilds the ten candidate rows,
and delegates duplicate/conflict mechanics to the generic admission framework.
This module is read-only; Production publication is a separate transaction.
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
)
from stm32f3_admission_policy import CANONICAL_FIELDS, FAMILY, build_canonical_row
from stm32f3_phase4_4c_policy import (
    ADAPTER_ID,
    DEFAULT_POLICY_BASELINE,
    DEFAULT_PRODUCTION_MANIFEST,
    EXPECTED_CANDIDATE_COUNT,
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    EXPECTED_PRODUCTION_FAMILY_COUNTS,
    policy_plan_is_clean,
    validate_policy,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.4D"
POLICY_PHASE = "4.4C"
DISCOVERY_PHASE = "4.4B"
DEFAULT_CANONICAL = HERE / "stm32f3-commercial-icpn.csv"


class STM32F3AdmissionError(AdmissionError):
    pass


def _canonical_prestate(canonical_path: Path | None) -> tuple[list[str], list[dict[str, str]], bool]:
    if canonical_path is None or not canonical_path.exists():
        return list(CANONICAL_FIELDS), [], True
    fields, rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise STM32F3AdmissionError("STM32F3 canonical CSV schema mismatch")
    if any(row.get("family") not in ("", FAMILY) for row in rows):
        raise STM32F3AdmissionError("STM32F3 canonical CSV contains a foreign family")
    identities = [row.get("icpn", "") for row in rows]
    if len(identities) != len(set(identities)):
        raise STM32F3AdmissionError("STM32F3 canonical CSV contains duplicate ICPNs")
    if rows:
        raise STM32F3AdmissionError(
            f"Phase 4.4D requires zero-row STM32F3 canonical prestate, got {len(rows)}"
        )
    return fields, rows, False


def build_admission_plan(
    *,
    canonical_path: Path | None = DEFAULT_CANONICAL,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
    production_manifest_binding_name: str | None = None,
) -> dict[str, Any]:
    policy_plan, _ = validate_policy(
        production_manifest_path=production_manifest_path,
        production_manifest_binding_name=production_manifest_binding_name,
    )
    if not policy_plan_is_clean(policy_plan):
        raise STM32F3AdmissionError("Phase 4.4C policy is not clean")

    fields, canonical_rows, absent = _canonical_prestate(canonical_path)
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
            "family_adapter": ADAPTER_ID,
            "policy_phase": POLICY_PHASE,
            "policy_baseline": DEFAULT_POLICY_BASELINE.name,
            "policy_baseline_sha256": file_sha256(DEFAULT_POLICY_BASELINE),
            "retained_evidence_directory": policy_plan["inputs"]["retained_evidence_directory"],
            "retained_evidence_baseline": policy_plan["inputs"]["retained_evidence_baseline"],
            "retained_evidence_baseline_sha256": policy_plan["inputs"][
                "retained_evidence_baseline_sha256"
            ],
            "mapping_catalog": policy_plan["inputs"]["mapping_catalog"],
            "mapping_catalog_sha256": policy_plan["inputs"]["mapping_catalog_sha256"],
            "canonical_dataset": DEFAULT_CANONICAL.name,
            "canonical_dataset_absent_before_admission": absent,
            "production_manifest": (
                production_manifest_binding_name or production_manifest_path.name
            ),
            "production_manifest_sha256": file_sha256(production_manifest_path),
        },
        row_builder=build_canonical_row,
    )
    plan.update(
        {
            "phase": PHASE,
            "policy_phase": POLICY_PHASE,
            "discovery_phase": DISCOVERY_PHASE,
            "family": FAMILY,
            "adapter_id": ADAPTER_ID,
            "lifecycle_exclusions": [],
            "production_snapshot": policy_plan["production_snapshot"],
            "production_write_applied": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "full_stm32f3_surface_covered": False,
            "fail_closed": True,
        }
    )
    return plan


def admission_plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        framework_plan_is_clean(plan)
        and plan.get("phase") == PHASE
        and plan.get("policy_phase") == POLICY_PHASE
        and plan.get("discovery_phase") == DISCOVERY_PHASE
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("candidate_count") == EXPECTED_CANDIDATE_COUNT
        and plan.get("decision_counts")
        == {
            "admit": EXPECTED_CANDIDATE_COUNT,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        }
        and plan.get("canonical_rows_before") == 0
        and plan.get("canonical_dataset_admission") == "planned"
        and plan.get("lifecycle_exclusions") == []
        and plan.get("production_snapshot", {}).get("exact_icpn_count")
        == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count")
        == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts")
        == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32f3_exact_icpn_count") == 0
        and plan.get("production_write_applied") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("runtime_programming_support_claimed") is False
        and plan.get("full_stm32f3_surface_covered") is False
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
            raise STM32F3AdmissionError("Phase 4.4D admission plan is not clean")
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
