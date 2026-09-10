#!/usr/bin/env python3
"""Deterministic KL25 canonical and operation-admission validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import post_review_disposition as disposition

HERE = Path(__file__).resolve().parent
CONTRACT = json.loads((HERE / "canonical-admission-contract.json").read_text())


class CanonicalAdmissionError(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise CanonicalAdmissionError(message)


def validate(
    disposition_artifact: dict[str, Any],
    candidate_review: dict[str, Any],
    canonical_spec: dict[str, Any],
    operation_admission: dict[str, Any],
) -> dict[str, Any]:
    review_result = disposition.validate_candidate_review(disposition_artifact, candidate_review)
    reviewed = set(review_result["manufacturer_review_pass_candidates"])
    candidates = {c["candidate_id"] for d in disposition_artifact["dispositions"] for c in d["candidates"]}
    require(canonical_spec.get("target") == CONTRACT["target"], "canonical target mismatch")
    require(canonical_spec.get("spec_digest") == disposition.canonical_digest(canonical_spec, "spec_digest"), "canonical spec digest mismatch")
    applicability = canonical_spec.get("applicability")
    require(isinstance(applicability, dict), "applicability required")
    require(applicability.get("exact_target_evidence") == CONTRACT["required_target_evidence"], "exact target must bind locked NXP datasheet evidence")
    used: set[str] = set()
    supplemental_reviews = {row.get("review_record_id"): row for row in candidate_review.get("supplemental_reviews", [])}
    for field in canonical_spec.get("canonical_fields", []):
        ids = field.get("candidate_ids")
        require(isinstance(ids, list), f"{field.get('path')}: candidate lineage must be an array")
        require(set(ids) <= candidates, f"{field.get('path')}: unknown candidate")
        require(set(ids) <= reviewed, f"{field.get('path')}: candidate lacks explicit manufacturer review PASS")
        evidence = field.get("manufacturer_evidence")
        review_id = field.get("review_record_id")
        require(ids or (isinstance(evidence, list) and evidence and review_id), f"{field.get('path')}: candidate lineage or reviewed direct evidence required")
        if evidence:
            row = supplemental_reviews.get(review_id)
            require(isinstance(row, dict), f"{field.get('path')}: explicit supplemental manufacturer review required")
            require(row.get("path") == field.get("path") and row.get("evidence") == evidence, f"{field.get('path')}: supplemental review binding mismatch")
            require(all(row.get(d) == disposition.PASS[d] for d in disposition.DIMENSIONS), f"{field.get('path')}: supplemental review did not pass")
        used.update(ids)
    matrix = operation_admission.get("operations")
    require(isinstance(matrix, dict), "operation admission matrix required")
    require(set(matrix) == set(CONTRACT["candidate_operation_set"] + CONTRACT["forbidden_operations"]), "operation set drift")
    for name in CONTRACT["candidate_operation_set"]:
        row = matrix[name]
        require(row.get("state") in CONTRACT["required_operation_states"], f"{name}: invalid state")
        if row["state"] == "ADMITTED":
            require(row.get("canonical_spec_digest") == canonical_spec["spec_digest"], f"{name}: canonical binding required")
            require(isinstance(row.get("required_fields"), list) and row["required_fields"], f"{name}: required fields missing")
            field_paths = {f["path"] for f in canonical_spec.get("canonical_fields", [])}
            require(set(row["required_fields"]) <= field_paths, f"{name}: unresolved canonical requirement")
            require(isinstance(row.get("backend_lock_digest"), str) and len(row["backend_lock_digest"]) == 64, f"{name}: backend lock required")
    for name in CONTRACT["forbidden_operations"]:
        require(matrix[name].get("state") == "BLOCKED", f"{name}: destructive operation must be BLOCKED")
    require(operation_admission.get("admission_digest") == disposition.canonical_digest(operation_admission, "admission_digest"), "operation admission digest mismatch")
    return {
        "canonical_status": "ADMITTED",
        "canonical_field_count": len(canonical_spec.get("canonical_fields", [])),
        "knowledge_candidate_count": len(candidates),
        "projected_candidate_count": len(used),
        "operation_states": {name: matrix[name]["state"] for name in CONTRACT["candidate_operation_set"]},
    }
