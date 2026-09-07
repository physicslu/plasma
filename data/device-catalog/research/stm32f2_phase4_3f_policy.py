#!/usr/bin/env python3
"""Evaluate the bounded Phase 4.3F STM32F2 batch-2 policy without writing Production."""

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
    TARGET_CONFIG,
    TEMPERATURE_BY_CODE,
    build_candidate_inputs,
    build_canonical_row,
)
from validate_stm32f2_phase4_3e_retained_evidence import (
    DEFAULT_BASELINE as DEFAULT_EVIDENCE_BASELINE,
    DEFAULT_EVIDENCE_DIR,
    validate as validate_retained_evidence,
)

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f2-commercial-icpn.csv"
DEFAULT_PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
DEFAULT_POLICY_BASELINE = HERE / "stm32f2-phase4.3f-policy-baseline.json"
PHASE = "4.3F"
ADAPTER_ID = "stm32f2-phase4.3f"
EXPECTED_COUNT = 13
SUPPORTED_BASE_DEVICES = frozenset(
    {"STM32F205RC", "STM32F207IE", "STM32F215RG", "STM32F217IG"}
)
PHASE_FLASH_BY_CODE = {**FLASH_BY_CODE, "G": "1024 KiB"}
HISTORICAL_CANONICAL_ICPNS = frozenset(
    {
        "STM32F205RBT6", "STM32F205RBT6TR", "STM32F205RBT7",
        "STM32F207ICH6", "STM32F207ICT6",
        "STM32F215RET6", "STM32F215RET6TR",
        "STM32F217IEH6", "STM32F217IET6",
    }
)


def _production_snapshot(manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise AdmissionError("Production manifest sources must be a list")
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise AdmissionError("Production manifest source must be an object")
        family = source.get("family")
        relative = source.get("path")
        declared = source.get("row_count")
        if not isinstance(family, str) or not isinstance(relative, str) or not isinstance(declared, int):
            raise AdmissionError("Production manifest source is incomplete")
        _, rows = read_csv((manifest_path.parent / relative).resolve())
        if len(rows) != declared or any(row.get("family") != family for row in rows):
            raise AdmissionError(f"{family}: Production source drifted")
        family_counts[family] = family_counts.get(family, 0) + len(rows)
        base_devices.update((family, row.get("base_device", "")) for row in rows)
    if family_counts.get("STM32F1") != 75 or family_counts.get("STM32F4") != 384:
        raise AdmissionError(f"unexpected Production family counts: {family_counts}")
    if family_counts.get("STM32F2", 0) < 9 or sum(family_counts.values()) < 468 or len(base_devices) < 161:
        raise AdmissionError("Phase 4.3F historical Production boundary is unavailable")
    return {
        "exact_icpn_count": 468,
        "base_device_count": 161,
        "family_exact_icpn_counts": {"STM32F1": 75, "STM32F2": 9, "STM32F4": 384},
        "stm32f2_exact_icpn_count": 9,
    }


def _row_builder(candidate: dict[str, Any], fields: list[str]) -> dict[str, str]:
    return build_canonical_row(
        candidate,
        fields,
        supported_base_devices=SUPPORTED_BASE_DEVICES,
        flash_by_code=PHASE_FLASH_BY_CODE,
    )


def build_policy_plan(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    evidence_baseline_path: Path = DEFAULT_EVIDENCE_BASELINE,
    catalog_path: Path = DEFAULT_CATALOG,
    canonical_path: Path = DEFAULT_CANONICAL,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
) -> dict[str, Any]:
    retained = validate_retained_evidence(
        evidence_dir=evidence_dir,
        baseline_path=evidence_baseline_path,
    )
    if retained.get("status") != "valid" or retained.get("active_exact_icpn_candidates") != EXPECTED_COUNT:
        raise AdmissionError("Phase 4.3E retained evidence is not policy-eligible")
    provenance = read_json(evidence_dir / "provenance.json")
    summary = read_json(evidence_dir / "pilot-summary.json")
    _, catalog_rows = read_csv(catalog_path)
    fields, canonical_rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise AdmissionError("STM32F2 canonical schema drifted")
    historical_rows = [row for row in canonical_rows if row.get("icpn") in HISTORICAL_CANONICAL_ICPNS]
    if len(historical_rows) != 9 or {row["icpn"] for row in historical_rows} != HISTORICAL_CANONICAL_ICPNS:
        raise AdmissionError("Phase 4.3F historical canonical boundary is unavailable")
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("STM32F2 retained evidence requires evidence_id")
    if provenance.get("scale_ready") is not True:
        raise AdmissionError("STM32F2 retained evidence is not scale-ready")
    if provenance.get("canonical_dataset_admission") is not False:
        raise AdmissionError("Phase 4.3E evidence unexpectedly authorizes admission")
    candidate_inputs = build_candidate_inputs(
        summary=summary,
        evidence_id=evidence_id,
        catalog_rows=catalog_rows,
        supported_base_devices=SUPPORTED_BASE_DEVICES,
        expected_candidate_count=EXPECTED_COUNT,
    )
    plan = build_admission_plan(
        candidate_inputs=candidate_inputs,
        canonical_fields=fields,
        canonical_rows=historical_rows,
        source_provenance={
            "evidence_id": evidence_id,
            "repository": provenance.get("source_repository"),
            "executed_git_sha": provenance.get("executed_git_sha"),
            "workflow_run_id": provenance.get("workflow_run_id"),
            "artifact_id": provenance.get("artifact_id"),
            "artifact_zip_sha256": provenance.get("artifact_zip_sha256"),
            "evidence_manifest_sha256": file_sha256(evidence_dir / "manifest.json"),
        },
        input_bindings={
            "family_adapter": ADAPTER_ID,
            "retained_evidence_directory": evidence_dir.name,
            "retained_evidence_baseline": evidence_baseline_path.name,
            "retained_evidence_baseline_sha256": file_sha256(evidence_baseline_path),
            "mapping_catalog": catalog_path.name,
            "mapping_catalog_sha256": file_sha256(catalog_path),
            "canonical_dataset": canonical_path.name,
            "production_manifest": production_manifest_path.name,
            "production_manifest_sha256": file_sha256(production_manifest_path),
        },
        row_builder=_row_builder,
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
        and plan.get("candidate_count") == EXPECTED_COUNT
        and plan.get("decision_counts")
        == {"admit": EXPECTED_COUNT, "already_present": 0, "manual_review_required": 0, "reject": 0}
        and isinstance(candidates, list)
        and {item.get("base_device") for item in candidates} == SUPPORTED_BASE_DEVICES
        and plan.get("canonical_rows_before") == 9
        and plan.get("production_snapshot", {}).get("stm32f2_exact_icpn_count") == 9
        and plan.get("production_write_applied") is False
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
        "evidence_id": plan["evidence_id"],
        "retained_evidence_directory": plan["inputs"]["retained_evidence_directory"],
        "candidate_count": plan["candidate_count"],
        "base_devices": sorted({item["base_device"] for item in candidates}),
        "policy_ready_exact_icpns": sorted(item["icpn"] for item in candidates),
        "decision_counts": plan["decision_counts"],
        "conflicts": plan["conflicts"],
        "metadata_contract": {
            "flash_by_code": PHASE_FLASH_BY_CODE,
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_policy_plan()
        summary = policy_summary(plan)
        if not policy_plan_is_clean(plan):
            raise AdmissionError("Phase 4.3F policy plan is not clean")
        if args.baseline.exists() and summary != read_json(args.baseline):
            raise AdmissionError("Phase 4.3F policy baseline drifted")
    except (AdmissionError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
