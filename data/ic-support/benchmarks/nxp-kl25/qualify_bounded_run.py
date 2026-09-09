#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import re
from typing import Any

import bounded_extraction as bounded
import build_evidence_pack as builder
import qualify_semantic_run as semantic_qualification

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MODEL_DIGEST = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$", re.IGNORECASE)
GATE57_CONTRACT_ID = "nxp-kl25-live-bounded-qualification-v1"
GATE57A_CONTRACT_ID = "nxp-kl25-live-bounded-qualification-v1.1"


class LiveBoundedQualificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveBoundedQualificationError(message)


def normalized_model_digest(value: Any) -> str:
    require(isinstance(value, str), "model digest missing")
    match = MODEL_DIGEST.fullmatch(value)
    require(match is not None, "model digest malformed")
    return match.group(1).lower()


def execution_profile_from_contract(contract: dict[str, Any]) -> dict[str, Any]:
    runtime = contract.get("live_runtime")
    require(isinstance(runtime, dict), "live runtime missing")
    profile = {
        "contract_id": contract.get("contract_id"),
        "contract_digest": builder.canonical_sha256(contract),
        "execution_mode": runtime.get("execution_mode"),
        "transport": runtime.get("transport"),
        "runtime_label": runtime.get("runtime_label"),
        "generation": copy.deepcopy(runtime.get("generation")),
        "automatic_retries": runtime.get("automatic_retries"),
        "primary_unit_count": runtime.get("primary_unit_count"),
    }
    if runtime.get("semantic_scope") is not None:
        profile["semantic_scope"] = copy.deepcopy(runtime.get("semantic_scope"))
    return bounded._execution_profile(profile)


def validate_contract(contract: dict[str, Any]) -> None:
    require(contract.get("artifact_type") == "kl25_live_bounded_qualification_contract",
            "live bounded contract artifact mismatch")
    contract_id = contract.get("contract_id")
    require(contract_id in {GATE57_CONTRACT_ID, GATE57A_CONTRACT_ID},
            "live bounded contract id mismatch")
    require(contract.get("target") == "MKL25Z128VLK4", "live bounded target mismatch")
    if contract_id == GATE57_CONTRACT_ID:
        require(contract.get("schema_version") == "0.1.0", "Gate 5.7 contract schema mismatch")
    else:
        require(contract.get("schema_version") == "0.2.0", "Gate 5.7A contract schema mismatch")

    required = contract.get("required_input")
    require(isinstance(required, dict), "required_input missing")
    rules = bounded.policy()
    require(required.get("bounded_contract_id") == rules["contract_id"], "bounded base contract id mismatch")
    require(required.get("bounded_contract_digest") == builder.canonical_sha256(rules),
            "bounded base contract digest mismatch")
    require(required.get("semantic_contract_id") == rules["semantic_contract_id"],
            "semantic contract id mismatch")
    require(required.get("evidence_boundary_release_id") == rules["evidence_boundary_release_id"],
            "evidence boundary release mismatch")

    runtime = contract.get("live_runtime")
    require(isinstance(runtime, dict), "live_runtime missing")
    if contract_id == GATE57_CONTRACT_ID:
        require(runtime.get("execution_mode") == "live_bounded_sequential", "Gate 5.7 execution mode mismatch")
        require(runtime.get("runtime_label") == "kl25-live-bounded-qualification", "Gate 5.7 runtime label mismatch")
        require(runtime.get("semantic_scope") is None, "Gate 5.7 v1 must not gain primary-scoped policy")
    else:
        require(runtime.get("execution_mode") == "live_bounded_primary_scoped_sequential",
                "Gate 5.7A execution mode mismatch")
        require(runtime.get("runtime_label") == "kl25-live-bounded-primary-scoped-qualification",
                "Gate 5.7A runtime label mismatch")
        require(runtime.get("semantic_scope") == bounded.PRIMARY_SCOPE_POLICY,
                "Gate 5.7A primary-scoped policy mismatch")
    require(runtime.get("transport") == "ollama_native_chat", "live bounded transport mismatch")
    require(runtime.get("model_id") == "qwen3.8:27b-mlx", "live bounded model mismatch")
    require(runtime.get("loopback_only") is True, "live bounded runtime must remain loopback-only")
    require(runtime.get("allowed_done_reasons") == ["stop"], "done-reason policy drift")
    execution_profile_from_contract(contract)

    admissions = contract.get("admission")
    require(isinstance(admissions, dict), "live bounded admission missing")
    require(admissions.get("live_bounded_qualification_harness") is True,
            "live bounded harness admission must be true")
    for key in ("live_bounded_run_retained", "semantic_extraction", "model_quality",
                "canonical_dataset", "hil", "production", "destructive_security_operation"):
        require(admissions.get(key) is False, f"live bounded admission must remain false: {key}")
    review = contract.get("review")
    require(isinstance(review, dict), "review policy missing")
    require(review.get("manufacturer_review_required") is True, "manufacturer review must be required")
    require(review.get("gate57_can_issue_qualified") is False, "Gate 5.7 family must not issue QUALIFIED")
    require(review.get("next_status_after_screening_pass") == "READY_FOR_REVIEW",
            "live bounded success status must be READY_FOR_REVIEW")


def _screen_response(
    response: Any, *, screening: dict[str, Any], packs: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    pack_by_primary = semantic_qualification._pack_by_primary(packs)
    expected_units = set(pack_by_primary)
    unit_results = response.get("unit_results") if isinstance(response, dict) else None
    if not isinstance(unit_results, list):
        return ["bounded aggregate response unit_results missing"]
    result_by_primary = {
        item["primary_unit_id"]: item
        for item in unit_results
        if isinstance(item, dict) and isinstance(item.get("primary_unit_id"), str)
    }
    if set(result_by_primary) != expected_units:
        errors.append(
            f"bounded aggregate response must cover all primary units; missing={sorted(expected_units - set(result_by_primary))}"
        )
    minimum_facts = int(screening.get("minimum_facts_per_unit", 1))
    for unit_id in sorted(expected_units):
        result = result_by_primary.get(unit_id)
        if result is None:
            continue
        if screening.get("require_facts_state_for_all_units") is True and result.get("state") != "FACTS":
            errors.append(f"{unit_id}: state must be FACTS")
            continue
        facts = result.get("facts")
        if not isinstance(facts, list) or len(facts) < minimum_facts:
            errors.append(f"{unit_id}: insufficient fact count")
            continue
        text = semantic_qualification._unit_text(result)
        for forbidden in screening.get("forbidden_terms", []):
            if semantic_qualification._contains_term(text, forbidden):
                errors.append(f"{unit_id}: forbidden cross-vendor term present: {forbidden}")
        for group in screening.get("required_term_groups", {}).get(unit_id, []):
            if not isinstance(group, list) or not group or not any(
                semantic_qualification._contains_term(text, term) for term in group
            ):
                errors.append(f"{unit_id}: missing required concept group: {group}")
        if screening.get("require_primary_unit_page_citation") is True:
            primary_refs = semantic_qualification._primary_refs(pack_by_primary[unit_id])
            has_primary_ref = any(
                (ref.get("source_id"), ref.get("pdf_page_number")) in primary_refs
                for fact in facts if isinstance(fact, dict)
                for ref in fact.get("evidence", []) if isinstance(ref, dict)
            )
            if not has_primary_ref:
                errors.append(f"{unit_id}: no citation to primary Evidence Unit pages")
    return errors


def assess_bounded_live_run(
    *, contract: dict[str, Any], aggregate: dict[str, Any], children: list[dict[str, Any]],
    provenance: dict[str, Any], semantic_contract: dict[str, Any],
    pre_ai_manifest: dict[str, Any], packs: dict[str, dict[str, Any]],
    evidence_text: dict[str, str],
) -> dict[str, Any]:
    integrity_errors: list[str] = []
    screening_errors: list[str] = []
    screening_executed = False

    def check(condition: bool, message: str) -> None:
        if not condition:
            integrity_errors.append(message)

    try:
        validate_contract(contract)
    except (LiveBoundedQualificationError, bounded.BoundedExtractionError, KeyError, TypeError) as exc:
        integrity_errors.append(str(exc))

    required = contract.get("required_input", {})
    runtime = contract.get("live_runtime", {})
    rules = bounded.policy()
    profile = execution_profile_from_contract(contract)

    check(pre_ai_manifest.get("target") == contract.get("target"), "pre-AI target mismatch")
    check(pre_ai_manifest.get("bundle_digest") == required.get("bundle_digest"), "Gate 5.6 bundle digest mismatch")
    check(pre_ai_manifest.get("manifest_digest") == required.get("pre_ai_manifest_digest"),
          "Gate 5.6 pre-AI manifest digest mismatch")
    check(semantic_contract.get("contract_id") == required.get("semantic_contract_id"),
          "semantic contract mismatch")
    check(aggregate.get("artifact_type") == "kl25_bounded_aggregate", "bounded aggregate artifact mismatch")
    check(aggregate.get("bounded_contract_id") == rules["contract_id"], "aggregate bounded contract mismatch")
    check(aggregate.get("execution_contract_id") == contract.get("contract_id"),
          "aggregate execution contract mismatch")
    check(aggregate.get("execution_mode") == runtime.get("execution_mode"), "aggregate execution mode mismatch")
    check(aggregate.get("target") == contract.get("target"), "aggregate target mismatch")
    check(aggregate.get("bundle_digest") == required.get("bundle_digest"), "aggregate bundle digest mismatch")
    check(aggregate.get("pre_ai_manifest_digest") == required.get("pre_ai_manifest_digest"),
          "aggregate manifest digest mismatch")
    check(aggregate.get("aggregate_digest") == builder.canonical_sha256(
        {k: v for k, v in aggregate.items() if k != "aggregate_digest"}
    ), "aggregate self-digest mismatch")
    check(aggregate.get("status") == "INTEGRITY_PASS", "bounded aggregate must reach INTEGRITY_PASS")
    check(aggregate.get("errors") == [], "bounded aggregate errors must be empty")
    check(aggregate.get("qualification_status") == "NOT_QUALIFIED", "bounded core must not issue qualification")
    check(all(v is False for v in aggregate.get("admission", {}).values()),
          "bounded aggregate admissions must remain denied")
    check(len(children) == runtime.get("primary_unit_count"), "bounded child count mismatch")
    semantic_scope = runtime.get("semantic_scope")
    if semantic_scope is None:
        check(aggregate.get("semantic_scope") is None, "Gate 5.7 aggregate unexpectedly carries primary scope")
    else:
        check(aggregate.get("semantic_scope") == semantic_scope, "aggregate primary semantic scope mismatch")
        check(aggregate.get("semantic_scope_digest") == builder.canonical_sha256(semantic_scope),
              "aggregate primary semantic scope digest mismatch")

    identity = provenance.get("ollama_runtime_identity") if isinstance(provenance, dict) else None
    identity = identity if isinstance(identity, dict) else {}
    model_digest = ""
    try:
        model_digest = normalized_model_digest(identity.get("model_digest"))
    except LiveBoundedQualificationError as exc:
        integrity_errors.append(str(exc))
    check(identity.get("model_id") == runtime.get("model_id"), "Ollama identity model mismatch")
    check(identity.get("ollama_url_policy") == "loopback_only", "Ollama endpoint policy mismatch")
    check(isinstance(identity.get("ollama_version"), str) and bool(identity.get("ollama_version", "").strip()),
          "Ollama version missing")

    if model_digest:
        try:
            recomputed = bounded.aggregate_results(
                copy.deepcopy(children), contract=copy.deepcopy(semantic_contract),
                pre_ai_manifest=copy.deepcopy(pre_ai_manifest), packs=copy.deepcopy(packs),
                evidence_text=copy.deepcopy(evidence_text), model_id=runtime.get("model_id"),
                model_digest=model_digest, execution_profile=copy.deepcopy(profile),
            )
        except Exception as exc:
            integrity_errors.append(f"deterministic bounded replay failed: {exc}")
        else:
            check(recomputed == aggregate, "retained children do not deterministically reproduce aggregate")

    check(provenance.get("artifact_type") == "kl25_live_bounded_run_provenance", "provenance artifact mismatch")
    check(provenance.get("target") == contract.get("target"), "provenance target mismatch")
    check(provenance.get("bundle_digest") == required.get("bundle_digest"), "provenance bundle mismatch")
    check(provenance.get("pre_ai_manifest_digest") == required.get("pre_ai_manifest_digest"),
          "provenance manifest mismatch")
    check(provenance.get("live_bounded_contract_id") == contract.get("contract_id"),
          "provenance live contract id mismatch")
    check(provenance.get("live_bounded_contract_digest") == builder.canonical_sha256(contract),
          "provenance live contract digest mismatch")
    check(provenance.get("bounded_contract_id") == rules["contract_id"], "provenance bounded contract id mismatch")
    check(provenance.get("bounded_contract_digest") == builder.canonical_sha256(rules),
          "provenance bounded contract digest mismatch")
    check(provenance.get("aggregate_digest") == aggregate.get("aggregate_digest"),
          "provenance aggregate digest mismatch")
    check(provenance.get("provenance_digest") == builder.canonical_sha256(
        {k: v for k, v in provenance.items() if k != "provenance_digest"}
    ), "provenance self-digest mismatch")
    execution = provenance.get("execution") if isinstance(provenance.get("execution"), dict) else {}
    for key in ("execution_mode", "transport", "model_id", "runtime_label", "automatic_retries", "primary_unit_count"):
        expected = runtime.get(key)
        check(execution.get(key) == expected, f"provenance execution mismatch: {key}")
    check(execution.get("generation") == runtime.get("generation"), "provenance generation mismatch")
    check(execution.get("semantic_scope") == runtime.get("semantic_scope"), "provenance semantic scope mismatch")
    check(execution.get("ollama_endpoint_policy") == "loopback_only", "provenance endpoint policy mismatch")
    fingerprints = provenance.get("code_fingerprints")
    check(isinstance(fingerprints, dict) and bool(fingerprints), "code fingerprints missing")
    if isinstance(fingerprints, dict):
        check(all(isinstance(v, str) and HEX64.fullmatch(v) is not None for v in fingerprints.values()),
              "code fingerprint malformed")
    check(provenance.get("manufacturer_text_retained_in_provenance") is False,
          "manufacturer text must not be retained in provenance")

    provenance_children = provenance.get("children")
    if not isinstance(provenance_children, list):
        integrity_errors.append("provenance children missing")
    else:
        expected_child_rows = sorted(
            ({"primary_unit_id": c.get("binding", {}).get("primary_unit_id"),
              "record_digest": c.get("record_digest"),
              "request_digest": c.get("binding", {}).get("request_digest"),
              "raw_response_sha256": c.get("raw_response_sha256")} for c in children),
            key=lambda row: str(row["primary_unit_id"]),
        )
        check(provenance_children == expected_child_rows, "provenance child digest set mismatch")

    if not integrity_errors:
        screening_executed = True
        screening_errors = _screen_response(
            aggregate.get("response"), screening=contract.get("semantic_screening", {}), packs=packs
        )

    if integrity_errors:
        status = "REJECTED_INTEGRITY"
    elif screening_errors:
        status = "REJECTED_SCREENING"
    else:
        status = "READY_FOR_REVIEW"

    if not screening_executed:
        screening_status = "NOT_REACHED"
        screening_note = "Deterministic screening was not executed because bounded integrity failed."
    elif screening_errors:
        screening_status = "FAIL"
        screening_note = "Deterministic screening is a defect filter, not proof of semantic correctness."
    else:
        screening_status = "PASS"
        screening_note = "Deterministic screening is a defect filter, not proof of semantic correctness."

    report: dict[str, Any] = {
        "schema_version": "0.1.1",
        "artifact_type": "kl25_live_bounded_qualification_report",
        "qualification_contract_id": contract.get("contract_id"),
        "target": contract.get("target"),
        "bundle_digest": required.get("bundle_digest"),
        "pre_ai_manifest_digest": required.get("pre_ai_manifest_digest"),
        "aggregate_digest": aggregate.get("aggregate_digest"),
        "model_id": runtime.get("model_id"),
        "model_digest": identity.get("model_digest"),
        "status": status,
        "integrity": {"status": "PASS" if not integrity_errors else "FAIL", "errors": integrity_errors},
        "semantic_screening": {
            "status": screening_status,
            "errors": screening_errors,
            "note": screening_note,
        },
        "review": {
            "required": True,
            "status": "PENDING" if status == "READY_FOR_REVIEW" else "NOT_REACHED",
            "basis_required": "manufacturer_evidence",
            "gate57_can_issue_qualified": False,
        },
        "trust_boundary": {
            "bounded_integrity_is_not_semantic_correctness": True,
            "primary_citation_presence_is_not_semantic_support": True,
            "screening_pass_is_not_semantic_correctness": True,
            "semantic_extraction_admission": False,
            "model_quality_admission": False,
            "canonical_dataset_admission": False,
            "hil_admission": False,
            "production_admission": False,
            "destructive_security_operation_admission": False,
        },
    }
    report["report_digest"] = builder.canonical_sha256(report)
    return report
