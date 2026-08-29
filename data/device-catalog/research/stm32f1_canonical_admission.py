"""Deterministic STM32F1 retained-evidence canonical admission model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    build_admission_plan as build_framework_plan,
    canonical_csv_sha256,
    file_sha256,
    plan_is_clean as framework_plan_is_clean,
    read_csv,
    read_json,
    write_canonical_dataset as write_framework_dataset,
)
from stm32f1_admission_policy import (
    MANUFACTURER,
    TRANSPORT,
    build_candidate_inputs,
    build_canonical_row,
)
from validate_stm32f1_retained_evidence import validate_retained_evidence

SCHEMA_VERSION = 1
HISTORICAL_PHASE27_CANDIDATE_COUNT = 26


def proposed_canonical_row(
    *,
    icpn: str,
    base_device: str,
    source_url: str,
    evidence_id: str,
    mapping: dict[str, object],
    fields: list[str],
) -> dict[str, str]:
    """Compatibility wrapper around the STM32F1 policy row builder."""

    return build_canonical_row(
        {
            "manufacturer": MANUFACTURER,
            "base_device": base_device,
            "icpn": icpn,
            "authoritative_evidence": {
                "evidence_id": evidence_id,
                "source_url": source_url,
            },
            "base_mapping": mapping,
        },
        fields,
    )


def build_admission_plan(
    *,
    evidence_dir: Path,
    canonical_path: Path,
    catalog_path: Path,
    baseline_path: Path,
) -> dict[str, Any]:
    retained = validate_retained_evidence(evidence_dir, baseline_path=baseline_path)
    provenance = read_json(evidence_dir / "provenance.json")
    summary = read_json(evidence_dir / "pilot-summary.json")
    fields, canonical_rows = read_csv(canonical_path)
    _, catalog_rows = read_csv(catalog_path)
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("retained provenance requires evidence_id")
    if retained.get("scale_ready") is not True or retained.get("canonical_dataset_admission") is not False:
        raise AdmissionError("retained evidence is not eligible for admission planning")

    candidate_inputs = build_candidate_inputs(
        summary=summary,
        evidence_id=evidence_id,
        catalog_rows=catalog_rows,
    )
    return build_framework_plan(
        candidate_inputs=candidate_inputs,
        canonical_fields=fields,
        canonical_rows=canonical_rows,
        source_provenance={
            "evidence_id": evidence_id,
            "repository": provenance.get("source_repository"),
            "executed_git_sha": provenance.get("executed_git_sha"),
            "evidence_manifest_sha256": file_sha256(evidence_dir / "manifest.json"),
        },
        input_bindings={
            "retained_evidence_directory": evidence_dir.name,
            "canonical_dataset": canonical_path.name,
            "mapping_catalog": catalog_path.name,
            "mapping_catalog_sha256": file_sha256(catalog_path),
            "baseline": baseline_path.name,
            "baseline_sha256": file_sha256(baseline_path),
        },
        row_builder=build_canonical_row,
    )


def plan_is_clean(plan: dict[str, Any]) -> bool:
    """Historical Phase 2.7 gate; the generic framework has no 26-row assumption."""

    return (
        plan.get("candidate_count") == HISTORICAL_PHASE27_CANDIDATE_COUNT
        and framework_plan_is_clean(plan)
    )


def write_canonical_dataset(
    *,
    plan: dict[str, Any],
    canonical_path: Path,
) -> dict[str, Any]:
    """Preserve the bounded Phase 2.7 writer contract on top of the generic writer."""

    if not plan_is_clean(plan):
        raise AdmissionError("admission writer refuses a non-clean plan")
    return write_framework_dataset(plan=plan, canonical_path=canonical_path)
