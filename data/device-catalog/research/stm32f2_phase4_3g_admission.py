#!/usr/bin/env python3
"""Build the bounded Phase 4.3G STM32F2 batch-2 admission plan without writing Production."""

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
from stm32f2_phase4_3f_policy import (
    ADAPTER_ID,
    DEFAULT_EVIDENCE_BASELINE,
    DEFAULT_EVIDENCE_DIR,
    DEFAULT_POLICY_BASELINE,
    DEFAULT_PRODUCTION_MANIFEST,
    _row_builder,
    build_policy_plan,
    policy_plan_is_clean,
    policy_summary,
)

HERE = Path(__file__).resolve().parent
DEFAULT_CANONICAL = HERE / "stm32f2-commercial-icpn.csv"
PHASE = "4.3G"
EXPECTED_ICPN_COUNT = 13


def build_admission_plan(
    *,
    canonical_path: Path = DEFAULT_CANONICAL,
    policy_baseline_path: Path = DEFAULT_POLICY_BASELINE,
) -> dict[str, Any]:
    policy_plan = build_policy_plan()
    policy_baseline = read_json(policy_baseline_path)
    if not policy_plan_is_clean(policy_plan) or policy_summary(policy_plan) != policy_baseline:
        raise AdmissionError("Phase 4.3F policy is not closed at its guarded boundary")

    fields, canonical_rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise AdmissionError("STM32F2 canonical CSV schema mismatch")
    if any(row.get("family") != FAMILY for row in canonical_rows):
        raise AdmissionError("STM32F2 canonical CSV contains a foreign family")

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
            "policy_baseline": policy_baseline_path.name,
            "policy_baseline_sha256": file_sha256(policy_baseline_path),
            "retained_evidence_directory": DEFAULT_EVIDENCE_DIR.name,
            "retained_evidence_baseline": DEFAULT_EVIDENCE_BASELINE.name,
            "retained_evidence_baseline_sha256": file_sha256(DEFAULT_EVIDENCE_BASELINE),
            "canonical_dataset": canonical_path.name,
            "production_manifest": DEFAULT_PRODUCTION_MANIFEST.name,
            "production_manifest_sha256": file_sha256(DEFAULT_PRODUCTION_MANIFEST),
        },
        row_builder=_row_builder,
    )
    plan.update(
        {
            "phase": PHASE,
            "family": FAMILY,
            "adapter_id": ADAPTER_ID,
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


def admission_plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        framework_plan_is_clean(plan)
        and plan.get("phase") == PHASE
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("candidate_count") == EXPECTED_ICPN_COUNT
        and plan.get("decision_counts")
        == {"admit": 13, "already_present": 0, "manual_review_required": 0, "reject": 0}
        and plan.get("canonical_rows_before") == 9
        and plan.get("canonical_dataset_admission") == "planned"
        and plan.get("lifecycle_exclusions") == []
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == 468
        and plan.get("production_snapshot", {}).get("stm32f2_exact_icpn_count") == 9
        and plan.get("production_write_applied") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("runtime_programming_support_claimed") is False
        and plan.get("full_stm32f2_surface_covered") is False
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
            raise AdmissionError("Phase 4.3G admission plan is not clean")
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
