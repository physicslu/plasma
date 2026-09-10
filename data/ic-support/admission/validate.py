"""Deterministic validation for vendor-neutral IC admission artifacts.

The validator checks governance structure and exact content bindings. It does
not decide whether a vendor payload or cited evidence is semantically true.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .digest import DigestError, canonical_digest, verify_canonical_digest


HEX64 = re.compile(r"^[0-9a-f]{64}$")
SCHEMA_PREFIX = "plasma://ic-support/admission/"
ACTIONS = {
    "ACCEPT",
    "REJECT",
    "REPLACE_WITH_MANUFACTURER_FACT",
    "SPLIT",
    "NARROW",
    "CITATION_SUPPLEMENT_FOR_CANONICAL",
}
PROJECTION_STATES = {
    "KNOWLEDGE_ONLY",
    "CANONICAL_REQUIRED",
    "EXECUTION_PROFILE_REQUIRED",
    "BLOCKED",
}
ADMISSION_STATES = {"ADMITTED", "BLOCKED", "INCOMPLETE"}


class AdmissionValidationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionValidationError(message)


def _object(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], required: set[str], label: str, optional: set[str] | None = None) -> None:
    allowed = required | (optional or set())
    keys = set(value)
    _require(keys == required or (required <= keys <= allowed), f"{label} fields mismatch")


def _text(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{label} must be non-empty text")
    return value


def _digest(value: Any, label: str) -> str:
    _require(isinstance(value, str) and HEX64.fullmatch(value) is not None, f"{label} must be lowercase SHA-256")
    return value


def _array(value: Any, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label} must be an array")
    return value


def _artifact_ref(value: Any, label: str) -> dict[str, Any]:
    ref = _object(value, label)
    _exact(ref, {"artifact_id", "artifact_type", "artifact_digest"}, label, {"schema_id", "schema_version"})
    _text(ref.get("artifact_id"), f"{label}.artifact_id")
    _text(ref.get("artifact_type"), f"{label}.artifact_type")
    _digest(ref.get("artifact_digest"), f"{label}.artifact_digest")
    if "schema_id" in ref:
        _text(ref["schema_id"], f"{label}.schema_id")
    if "schema_version" in ref:
        _text(ref["schema_version"], f"{label}.schema_version")
    return ref


def _evidence_ref(value: Any, label: str) -> dict[str, Any]:
    ref = _object(value, label)
    _exact(
        ref,
        {"source_lock_id", "source_id", "source_digest", "authority", "locator"},
        label,
        {"page", "section", "table"},
    )
    for field in ("source_lock_id", "source_id", "authority", "locator"):
        _text(ref.get(field), f"{label}.{field}")
    _digest(ref.get("source_digest"), f"{label}.source_digest")
    for field in ("page", "section", "table"):
        if field in ref:
            _require(isinstance(ref[field], (str, int)) and not isinstance(ref[field], bool), f"{label}.{field} must be text or integer")
    return ref


def _header(value: dict[str, Any], expected_schema: str, expected_type: str) -> None:
    _require(value.get("schema_id") == SCHEMA_PREFIX + expected_schema, "schema identity mismatch")
    _require(value.get("schema_version") == "1.0.0", "schema version mismatch")
    _text(value.get("artifact_id"), "artifact_id")
    _require(value.get("artifact_type") == expected_type, "artifact type mismatch")
    _digest(value.get("artifact_digest"), "artifact_digest")
    try:
        verify_canonical_digest(value)
    except DigestError as exc:
        raise AdmissionValidationError(str(exc)) from exc


def _resolve(ref: dict[str, Any], artifacts: Mapping[str, Any], label: str) -> dict[str, Any]:
    artifact = _object(artifacts.get(ref["artifact_id"]), f"{label} target")
    _require(artifact.get("artifact_id") == ref["artifact_id"], f"{label} identity mismatch")
    _require(artifact.get("artifact_type") == ref["artifact_type"], f"{label} type mismatch")
    _require(artifact.get("artifact_digest") == ref["artifact_digest"], f"{label} digest binding mismatch")
    if "schema_id" in ref:
        _require(artifact.get("schema_id") == ref["schema_id"], f"{label} schema mismatch")
    if "schema_version" in ref:
        _require(artifact.get("schema_version") == ref["schema_version"], f"{label} schema version mismatch")
    try:
        verify_canonical_digest(artifact)
    except DigestError as exc:
        raise AdmissionValidationError(f"{label} stale digest") from exc
    return artifact


def _same_ref(left: dict[str, Any], right: dict[str, Any], label: str) -> None:
    _require(left == right, f"{label} binding mismatch")


def validate_admission_package(package: Mapping[str, Any]) -> dict[str, Any]:
    root = _object(dict(package), "package")
    _exact(root, {"artifacts", "compiler_bindings", "root_envelope_id", "operation_admission_id"}, "package")
    artifacts = _object(root["artifacts"], "artifacts")
    compilers = _object(root["compiler_bindings"], "compiler_bindings")

    envelope = _object(artifacts.get(root["root_envelope_id"]), "canonical admission envelope")
    _exact(
        envelope,
        {"schema_id", "schema_version", "artifact_id", "artifact_type", "target", "vendor_payload", "lineage", "admission", "artifact_digest"},
        "canonical admission envelope",
    )
    _header(envelope, "canonical-admission-envelope-v1", "canonical_admission_envelope")
    target = _object(envelope["target"], "target")
    _exact(target, {"vendor_id", "icpn"}, "target")
    _text(target.get("vendor_id"), "target.vendor_id")
    _text(target.get("icpn"), "target.icpn")
    vendor_payload_ref = _artifact_ref(envelope["vendor_payload"], "vendor_payload")
    _resolve(vendor_payload_ref, artifacts, "vendor_payload")

    lineage = _object(envelope["lineage"], "lineage")
    _exact(lineage, {"source_lock", "review_binding", "disposition", "candidate_review"}, "lineage")
    lineage_refs = {name: _artifact_ref(value, f"lineage.{name}") for name, value in lineage.items()}
    source_lock = _resolve(lineage_refs["source_lock"], artifacts, "source_lock")
    review = _resolve(lineage_refs["review_binding"], artifacts, "review_binding")
    disposition = _resolve(lineage_refs["disposition"], artifacts, "disposition")
    candidate_review = _resolve(lineage_refs["candidate_review"], artifacts, "candidate_review")

    admission = _object(envelope["admission"], "admission")
    _exact(admission, {"state", "unresolved_requirements"}, "admission")
    _require(admission.get("state") in ADMISSION_STATES, "invalid canonical admission state")
    unresolved = _array(admission.get("unresolved_requirements"), "admission.unresolved_requirements")
    _require(all(isinstance(item, str) and item for item in unresolved), "invalid canonical unresolved requirement")
    if admission["state"] == "ADMITTED":
        _require(not unresolved, "admitted canonical envelope cannot have unresolved requirements")

    _validate_review_binding(review, artifacts)
    candidates = _validate_disposition(disposition, review, artifacts)
    _validate_candidate_review(candidate_review, disposition, source_lock, candidates, artifacts)

    operation_artifact = _object(artifacts.get(root["operation_admission_id"]), "operation admission")
    admitted = _validate_operations(operation_artifact, envelope, artifacts, compilers)
    return {
        "status": "VALID",
        "target": dict(target),
        "candidate_count": len(candidates),
        "operation_count": len(operation_artifact["operations"]),
        "admitted_operation_count": admitted,
    }


def _validate_review_binding(review: dict[str, Any], artifacts: Mapping[str, Any]) -> None:
    _exact(review, {"schema_id", "schema_version", "artifact_id", "artifact_type", "reviewed_artifact", "review_artifact", "review_status", "artifact_digest"}, "review binding")
    _header(review, "review-binding-v1", "review_binding")
    _resolve(_artifact_ref(review["reviewed_artifact"], "reviewed_artifact"), artifacts, "reviewed_artifact")
    _resolve(_artifact_ref(review["review_artifact"], "review_artifact"), artifacts, "review_artifact")
    _text(review.get("review_status"), "review_status")


def _validate_disposition(disposition: dict[str, Any], review: dict[str, Any], artifacts: Mapping[str, Any]) -> set[str]:
    _exact(disposition, {"schema_id", "schema_version", "artifact_id", "artifact_type", "review_binding", "dispositions", "artifact_digest"}, "disposition")
    _header(disposition, "post-review-disposition-v1", "post_review_disposition")
    review_ref = _artifact_ref(disposition["review_binding"], "disposition.review_binding")
    _resolve(review_ref, artifacts, "disposition.review_binding")
    _same_ref(review_ref, _reference(review), "disposition review")
    candidates: set[str] = set()
    seen_facts: set[str] = set()
    for index, raw in enumerate(_array(disposition["dispositions"], "dispositions")):
        row = _object(raw, f"dispositions[{index}]")
        _exact(row, {"source_fact", "action", "projection_state", "candidate_artifacts"}, f"dispositions[{index}]")
        fact_ref = _artifact_ref(row["source_fact"], f"dispositions[{index}].source_fact")
        _resolve(fact_ref, artifacts, f"dispositions[{index}].source_fact")
        _require(fact_ref["artifact_id"] not in seen_facts, "duplicate disposition source fact")
        seen_facts.add(fact_ref["artifact_id"])
        _require(row.get("action") in ACTIONS, "invalid disposition action")
        _require(row.get("projection_state") in PROJECTION_STATES, "invalid projection state")
        refs = [_artifact_ref(item, "candidate artifact") for item in _array(row["candidate_artifacts"], "candidate_artifacts")]
        if row["action"] == "REJECT":
            _require(not refs and row["projection_state"] == "BLOCKED", "rejected fact must be blocked without candidates")
        else:
            _require(bool(refs), "non-rejected fact requires candidate lineage")
        for ref in refs:
            _resolve(ref, artifacts, "candidate artifact")
            _require(ref["artifact_id"] not in candidates, "duplicate candidate lineage")
            candidates.add(ref["artifact_id"])
    _require(bool(seen_facts), "disposition coverage cannot be empty")
    return candidates


def _validate_candidate_review(candidate_review: dict[str, Any], disposition: dict[str, Any], source_lock: dict[str, Any], candidates: set[str], artifacts: Mapping[str, Any]) -> None:
    _exact(candidate_review, {"schema_id", "schema_version", "artifact_id", "artifact_type", "disposition", "candidate_reviews", "artifact_digest"}, "candidate review")
    _header(candidate_review, "candidate-review-v1", "candidate_manufacturer_review")
    disposition_ref = _artifact_ref(candidate_review["disposition"], "candidate_review.disposition")
    _resolve(disposition_ref, artifacts, "candidate_review.disposition")
    _same_ref(disposition_ref, _reference(disposition), "candidate review disposition")
    sources = _array(source_lock.get("sources"), "source_lock.sources")
    source_pairs = {(item.get("source_id"), item.get("source_digest")) for item in sources if isinstance(item, dict)}
    observed: set[str] = set()
    for index, raw in enumerate(_array(candidate_review["candidate_reviews"], "candidate_reviews")):
        row = _object(raw, f"candidate_reviews[{index}]")
        _exact(row, {"candidate", "evidence", "review_status", "dimensions"}, f"candidate_reviews[{index}]")
        ref = _artifact_ref(row["candidate"], "candidate review candidate")
        _resolve(ref, artifacts, "candidate review candidate")
        _require(ref["artifact_id"] in candidates and ref["artifact_id"] not in observed, "unknown or duplicate candidate review")
        observed.add(ref["artifact_id"])
        _text(row.get("review_status"), "candidate review status")
        dimensions = _object(row["dimensions"], "candidate review dimensions")
        _require(bool(dimensions), "candidate review dimensions cannot be empty")
        _require(all(isinstance(key, str) and key and isinstance(value, str) and value for key, value in dimensions.items()), "invalid candidate review dimensions")
        evidence = [_evidence_ref(item, "candidate evidence") for item in _array(row["evidence"], "candidate evidence")]
        _require(bool(evidence), "candidate evidence cannot be empty")
        for item in evidence:
            _require(item["source_lock_id"] == source_lock.get("artifact_id"), "candidate evidence source-lock mismatch")
            _require((item["source_id"], item["source_digest"]) in source_pairs, "candidate evidence source binding mismatch")
    _require(observed == candidates, "candidate review coverage mismatch")


def _validate_operations(operation_artifact: dict[str, Any], envelope: dict[str, Any], artifacts: Mapping[str, Any], compilers: dict[str, Any]) -> int:
    _exact(operation_artifact, {"schema_id", "schema_version", "artifact_id", "artifact_type", "target", "operations", "artifact_digest"}, "operation admission")
    _header(operation_artifact, "operation-admission-v1", "operation_admission")
    _require(operation_artifact["target"] == envelope["target"], "operation target mismatch")
    admitted = 0
    seen: set[str] = set()
    for index, raw in enumerate(_array(operation_artifact["operations"], "operations")):
        row = _object(raw, f"operations[{index}]")
        _exact(row, {"request_operation", "operation_contract_id", "operation_contract_digest", "state", "canonical_admission_digest", "backend_id", "backend_lock_digest", "compiler_id", "canonical_requirements", "unresolved_requirements", "hardware_runtime_ready"}, f"operations[{index}]")
        operation = _text(row.get("request_operation"), "request_operation")
        _require(operation not in seen, "duplicate request operation")
        seen.add(operation)
        contract_ref = {"artifact_id": row["operation_contract_id"], "artifact_type": "operation_contract", "artifact_digest": row["operation_contract_digest"]}
        _resolve(_artifact_ref(contract_ref, "operation contract"), artifacts, "operation contract")
        _require(row.get("canonical_admission_digest") == envelope["artifact_digest"], "operation canonical admission mismatch")
        backend = _object(artifacts.get(row.get("backend_id")), "backend binding")
        _validate_backend(backend, artifacts)
        _require(row.get("backend_lock_digest") == backend["lock_digest"], "backend-lock mismatch")
        allowed = compilers.get(row.get("backend_id"))
        _require(isinstance(allowed, list) and row.get("compiler_id") in allowed, "compiler mismatch")
        _require(row.get("state") in ADMISSION_STATES, "invalid operation admission state")
        requirements = _array(row.get("canonical_requirements"), "canonical requirements")
        unresolved = _array(row.get("unresolved_requirements"), "unresolved requirements")
        _require(all(isinstance(item, str) and item for item in requirements + unresolved), "invalid operation requirements")
        _require(isinstance(row.get("hardware_runtime_ready"), bool), "hardware_runtime_ready must be boolean")
        if row["state"] == "ADMITTED":
            _require(bool(requirements) and not unresolved, "admitted operation requirements invalid")
            admitted += 1
    _require(bool(seen), "operation admission cannot be empty")
    return admitted


def _validate_backend(backend: dict[str, Any], artifacts: Mapping[str, Any]) -> None:
    _exact(backend, {"schema_id", "schema_version", "artifact_id", "artifact_type", "backend_id", "implementation", "implementation_evidence", "vendor_constraint_payload", "lock_digest", "artifact_digest"}, "backend binding")
    _header(backend, "backend-implementation-binding-v1", "backend_implementation_binding")
    _require(backend.get("backend_id") == backend.get("artifact_id"), "backend identity mismatch")
    implementation = _object(backend["implementation"], "implementation")
    _exact(implementation, {"identity", "revision"}, "implementation")
    _text(implementation.get("identity"), "implementation.identity")
    _text(implementation.get("revision"), "implementation.revision")
    evidence = [_artifact_ref(item, "implementation evidence") for item in _array(backend["implementation_evidence"], "implementation evidence")]
    _require(bool(evidence), "implementation evidence cannot be empty")
    for item in evidence:
        _resolve(item, artifacts, "implementation evidence")
    _resolve(_artifact_ref(backend["vendor_constraint_payload"], "vendor constraint payload"), artifacts, "vendor constraint payload")
    _digest(backend.get("lock_digest"), "lock_digest")
    expected_lock = canonical_digest(backend, omit=("artifact_digest", "lock_digest"))
    _require(backend["lock_digest"] == expected_lock, "backend lock digest mismatch")


def _reference(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": artifact["artifact_id"],
        "artifact_type": artifact["artifact_type"],
        "artifact_digest": artifact["artifact_digest"],
        "schema_id": artifact["schema_id"],
        "schema_version": artifact["schema_version"],
    }
