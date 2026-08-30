"""Generic evidence-to-admission pipeline composition for device catalogs.

The pipeline owns composition only. Manufacturer/family adapters produce normalized
candidate inputs and provenance; the admission framework owns deterministic decisions
and canonical writes. This module intentionally knows nothing about ST, STM32, browser
transport, part-number grammar, or OpenOCD target names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from device_catalog_admission_framework import (
    CandidateRowBuilder,
    build_admission_plan,
    plan_is_clean,
    read_csv,
)


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdmissionInputs:
    evidence_id: str
    candidate_inputs: list[dict[str, Any]]
    source_provenance: dict[str, Any]
    input_bindings: dict[str, Any]
    expected_candidate_count: int


AdmissionInputAdapter = Callable[..., AdmissionInputs]


def build_pipeline_plan(
    *,
    canonical_path: Path,
    row_builder: CandidateRowBuilder,
    admission_inputs: AdmissionInputs,
) -> dict[str, Any]:
    """Compose normalized evidence/policy output with generic admission mechanics."""

    if not admission_inputs.evidence_id:
        raise PipelineError("adapter requires evidence_id")
    if admission_inputs.expected_candidate_count < 0:
        raise PipelineError("adapter expected_candidate_count must be non-negative")
    if len(admission_inputs.candidate_inputs) != admission_inputs.expected_candidate_count:
        raise PipelineError(
            "adapter candidate count does not match expected candidate count"
        )

    fields, canonical_rows = read_csv(canonical_path)
    provenance = dict(admission_inputs.source_provenance)
    provenance["evidence_id"] = admission_inputs.evidence_id
    plan = build_admission_plan(
        candidate_inputs=admission_inputs.candidate_inputs,
        canonical_fields=fields,
        canonical_rows=canonical_rows,
        source_provenance=provenance,
        input_bindings=admission_inputs.input_bindings,
        row_builder=row_builder,
    )
    plan["pipeline_expected_candidate_count"] = admission_inputs.expected_candidate_count
    return plan


def pipeline_plan_is_clean(plan: dict[str, Any]) -> bool:
    expected = plan.get("pipeline_expected_candidate_count")
    return (
        isinstance(expected, int)
        and expected >= 0
        and plan.get("candidate_count") == expected
        and plan_is_clean(plan)
    )
