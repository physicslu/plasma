#!/usr/bin/env python3
"""Evaluate the bounded Phase 4.3C STM32F2 policy without writing Production."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    build_admission_plan,
    file_sha256,
    plan_is_clean,
    read_csv,
    read_json,
)
from stm32f2_admission_policy import (
    CANONICAL_FIELDS,
    FAMILY,
    FLASH_BY_CODE,
    OPTION_SUFFIXES,
    PACKAGE_BY_CODE,
    PINS_BY_COMBINATION,
    SUPPORTED_BASE_DEVICES,
    TARGET_CONFIG,
    TEMPERATURE_BY_CODE,
    build_candidate_inputs,
    build_canonical_row,
)
from validate_stm32f2_phase4_3b_retained_evidence import (
    DEFAULT_BASELINE,
    DEFAULT_EVIDENCE_DIR,
    validate as validate_retained_evidence,
)

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
DEFAULT_POLICY_BASELINE = HERE / "stm32f2-phase4.3c-policy-baseline.json"
PHASE = "4.3C"
ADAPTER_ID = "stm32f2-phase4.3c"
HISTORICAL_PRODUCTION_FAMILY_COUNTS = {"STM32F1": 75, "STM32F4": 384}


def _production_snapshot(manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise AdmissionError("Production manifest sources must be a list")

    # Phase 4.3C is a historical, pre-STM32F2 boundary. Validate every current
    # source for structural integrity, but include only the family set that was
    # in Production when this policy decision was made. Families admitted later
    # must not rewrite the historical policy baseline.
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise AdmissionError("Production manifest source must be an object")
        family = source.get("family")
        relative = source.get("path")
        declared = source.get("row_count")
        if not isinstance(family, str) or not isinstance(relative, str) or not isinstance(
            declared, int
        ):
            raise AdmissionError("Production manifest source is incomplete")
        source_path = (manifest_path.parent / relative).resolve()
        _, rows = read_csv(source_path)
        if len(rows) != declared:
            raise AdmissionError(f"{family}: Production manifest row count drifted")
        if any(row.get("family") != family for row in rows):
            raise AdmissionError(f"{family}: canonical source contains a foreign family")
        if family in HISTORICAL_PRODUCTION_FAMILY_COUNTS:
            family_counts[family] = family_counts.get(family, 0) + len(rows)
            base_devices.update((family, row.get("base_device", "")) for row in rows)

    exact_count = sum(family_counts.values())
    if family_counts != HISTORICAL_PRODUCTION_FAMILY_COUNTS:
        raise AdmissionError(f"unexpected Production family counts: {family_counts}")
    if exact_count != 459 or len(base_devices) != 157:
        raise AdmissionError("Phase 4.3C Production snapshot drifted")
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(base_devices),
        "family_exact_icpn_counts": family_counts,
        "stm32f2_exact_icpn_count": family_counts.get(FAMILY, 0),
    }


def build_policy_plan(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    baseline_path: Path = DEFAULT_BASELINE,
    catalog_path: Path = DEFAULT_CATALOG,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
) -> dict[str, Any]:
    retained = validate_retained_evidence(
        evidence_dir=evidence_dir,
        baseline_path=baseline_path,
    )
    if retained.get("status") != "valid" or retained.get("active_exact_icpn_candidates") != 9:
        raise AdmissionError("Phase 4.3B retained evidence is not policy-eligible")

    provenance = read_json(evidence_dir / "provenance.json")
    summary = read_json(evidence_dir / "pilot-summary.json")
    _, catalog_rows = read_csv(catalog_path)
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("STM32F2 retained evidence requires evidence_id")
    if provenance.get("scale_ready") is not True:
        raise AdmissionError("STM32F2 retained evidence is not scale-ready")
    if provenance.get("canonical_dataset_admission") is not False:
        raise AdmissionError("Phase 4.3B evidence unexpectedly authorizes admission")
    if provenance.get("production_admission_ready") is not False:
        raise AdmissionError("Phase 4.3B evidence unexpectedly claims Production readiness")

    candidate_inputs = build_candidate_inputs(
        summary=summary,
        evidence_id=evidence_id,
        catalog_rows=catalog_rows,
    )
    plan = build_admission_plan(
        candidate_inputs=candidate_inputs,
        canonical_fields=list(CANONICAL_FIELDS),
        canonical_rows=[],
        source_provenance={
            "evidence_id": evidence_id,
            "repository": provenance.get("source_repository"),
            "executed_git_sha": provenance.get("executed_git_sha"),
            "workflow_run_id": provenance.get("workflow_run_id"),
            "evidence_manifest_sha256": file_sha256(evidence_dir / "manifest.json"),
        },
        input_bindings={
            "family_adapter": ADAPTER_ID,
            "retained_evidence_directory": evidence_dir.name,
            "retained_evidence_baseline": baseline_path.name,
            "retained_evidence_baseline_sha256": file_sha256(baseline_path),
            "mapping_catalog": catalog_path.name,
            "mapping_catalog_sha256": file_sha256(catalog_path),
            "production_manifest": production_manifest_path.name,
            "production_manifest_sha256": file_sha256(production_manifest_path),
        },
        row_builder=build_canonical_row,
    )
    plan.update(
        {
            "phase": PHASE,
            "family": FAMILY,
            "adapter_id": ADAPTER_ID,
            "canonical_dataset_admission": "deferred",
            "policy_ready_count": plan["decision_counts"]["admit"],
            "production_snapshot": _production_snapshot(production_manifest_path),
            "production_write_applied": False,
            "exact_icpn_admission_deferred": True,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_support_claimed": False,
            "full_stm32f2_surface_covered": False,
            "fail_closed": True,
        }
    )
    return plan


def policy_plan_is_clean(plan: dict[str, Any]) -> bool:
    candidates = plan.get("candidates")
    return (
        plan_is_clean(plan)
        and plan.get("phase") == PHASE
        and plan.get("family") == FAMILY
        and plan.get("candidate_count") == 9
        and plan.get("policy_ready_count") == 9
        and isinstance(candidates, list)
        and {item.get("base_device") for item in candidates} == SUPPORTED_BASE_DEVICES
        and plan.get("canonical_rows_before") == 0
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_snapshot", {}).get("stm32f2_exact_icpn_count") == 0
        and plan.get("production_write_applied") is False
        and plan.get("exact_icpn_admission_deferred") is True
        and plan.get("runtime_support_claimed") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("fail_closed") is True
    )


def policy_summary(plan: dict[str, Any]) -> dict[str, Any]:
    candidates = plan["candidates"]
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "base_main": "5fdaa608692e82088f3e67ff5b85c7569338ebcc",
        "evidence_id": plan["evidence_id"],
        "retained_evidence_directory": plan["inputs"]["retained_evidence_directory"],
        "candidate_count": plan["candidate_count"],
        "base_devices": sorted({item["base_device"] for item in candidates}),
        "policy_ready_exact_icpns": sorted(item["icpn"] for item in candidates),
        "decision_counts": plan["decision_counts"],
        "conflicts": plan["conflicts"],
        "metadata_contract": {
            "flash_by_code": FLASH_BY_CODE,
            "temperature_by_code": TEMPERATURE_BY_CODE,
            "package_by_code": PACKAGE_BY_CODE,
            "pins_by_combination": {
                f"{pin}/{package}": pins
                for (pin, package), pins in sorted(PINS_BY_COMBINATION.items())
            },
            "allowed_option_suffixes": sorted(OPTION_SUFFIXES),
            "openocd_target_config": TARGET_CONFIG,
        },
        "production_snapshot": plan["production_snapshot"],
        "production_write_applied": False,
        "exact_icpn_admission_deferred": True,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_support_claimed": False,
        "full_stm32f2_surface_covered": False,
        "fail_closed": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_POLICY_BASELINE)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_policy_plan()
        summary = policy_summary(plan)
        baseline = read_json(args.baseline)
        if not policy_plan_is_clean(plan):
            raise AdmissionError("Phase 4.3C policy plan is not clean")
        if summary != baseline:
            raise AdmissionError("Phase 4.3C policy baseline drifted")
    except (AdmissionError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
