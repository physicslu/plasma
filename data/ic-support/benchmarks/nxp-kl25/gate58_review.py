#!/usr/bin/env python3
"""Gate 5.8 manufacturer-evidence semantic/citation review for NXP KL25.

This module never calls a model or the network. It consumes the exact retained
Gate 5.7A run, emits a deterministic per-fact review view/template, and validates
an explicit manufacturer-evidence review without mutating model output.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_evidence_pack as builder

HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "gate58-manufacturer-review-contract.json"
LIVE_CONTRACT_PATH = HERE / "live-bounded-primary-qualification-contract.json"
UNIT_DEFINITIONS_PATH = HERE / "reviewed-evidence-unit-definitions.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MODEL_DIGEST = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$", re.IGNORECASE)

EXPECTED_REQUIRED_RUN = {
    "run_id": "20260909T080946Z",
    "parent_dir_name": "bounded-primary-runs",
    "live_bounded_contract_id": "nxp-kl25-live-bounded-qualification-v1.1",
    "execution_mode": "live_bounded_primary_scoped_sequential",
    "aggregate_status": "INTEGRITY_PASS",
    "pre_review_qualification_status": "READY_FOR_REVIEW",
    "evidence_boundary_release_id": "nxp-kl25-evidence-boundary-release-v1",
    "bundle_digest": "ffe9bfaa8a6ed47c8edd6d952fe1ca2cc114513c2a1f0832892ab9484e7322bf",
    "pre_ai_manifest_digest": "03155ede421cddb7c2ab64e079ef43b1124a7c78cbedf1e7a08c60c29796bb6e",
    "model_id": "qwen3.8:27b-mlx",
    "model_digest": "5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e",
}

EXPECTED_DIMENSIONS = {
    "semantic_support": ({"NOT_REVIEWED", "SUPPORTED", "CONTRADICTED", "NOT_ESTABLISHED", "AMBIGUOUS"}, "SUPPORTED"),
    "citation_entailment": ({"NOT_REVIEWED", "COMPLETE", "PARTIAL", "NOT_ENTAILED", "PADDING_PRESENT"}, "COMPLETE"),
    "atomicity": ({"NOT_REVIEWED", "PASS", "NEEDS_SPLIT"}, "PASS"),
    "scope": ({"NOT_REVIEWED", "PASS", "OVER_BROAD", "PRIMARY_SCOPE_VIOLATION", "FORBIDDEN_ASSERTION"}, "PASS"),
    "terminology": ({"NOT_REVIEWED", "PASS", "LOSSY_NXP_TRANSLATION", "CROSS_VENDOR_CONTAMINATION"}, "PASS"),
}


class Gate58ReviewError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate58ReviewError(message)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Gate58ReviewError(f"cannot read valid JSON: {path}") from exc
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def _read_repo_json(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    require(resolved.parent == HERE, f"Gate 5.8 repository input must be under {HERE}")
    return read_json(resolved)


def _without(value: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in value.items() if k != key}


def _verify_self_digest(value: dict[str, Any], key: str, *, label: str) -> str:
    digest = value.get(key)
    require(isinstance(digest, str) and HEX64.fullmatch(digest) is not None, f"{label} {key} missing or malformed")
    require(digest == builder.canonical_sha256(_without(value, key)), f"{label} {key} mismatch")
    return digest


def normalized_model_digest(value: Any) -> str:
    require(isinstance(value, str), "model digest missing")
    match = MODEL_DIGEST.fullmatch(value)
    require(match is not None, "model digest malformed")
    return match.group(1).lower()


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    return _read_repo_json(path)


def load_live_contract() -> dict[str, Any]:
    return _read_repo_json(LIVE_CONTRACT_PATH)


def load_unit_definitions() -> dict[str, Any]:
    return _read_repo_json(UNIT_DEFINITIONS_PATH)


def validate_contract(
    contract: dict[str, Any],
    *,
    live_contract: dict[str, Any] | None = None,
    definitions: dict[str, Any] | None = None,
) -> None:
    require(contract.get("schema_version") == "0.1.0", "Gate 5.8 contract schema mismatch")
    require(contract.get("artifact_type") == "kl25_manufacturer_review_contract", "Gate 5.8 contract artifact mismatch")
    require(contract.get("contract_id") == "nxp-kl25-gate58-manufacturer-review-v1", "Gate 5.8 contract id mismatch")
    require(contract.get("target") == "MKL25Z128VLK4", "Gate 5.8 target mismatch")
    require(contract.get("required_retained_run") == EXPECTED_REQUIRED_RUN, "Gate 5.8 retained-run binding drift")

    dimensions = contract.get("review_dimensions")
    require(isinstance(dimensions, dict) and set(dimensions) == set(EXPECTED_DIMENSIONS), "Gate 5.8 review dimensions mismatch")
    for name, (allowed, pass_value) in EXPECTED_DIMENSIONS.items():
        dimension = dimensions.get(name)
        require(isinstance(dimension, dict), f"Gate 5.8 dimension missing: {name}")
        require(set(dimension.get("allowed", [])) == allowed, f"Gate 5.8 vocabulary drift: {name}")
        require(dimension.get("pass") == pass_value, f"Gate 5.8 pass value drift: {name}")

    policy = contract.get("review_policy")
    require(isinstance(policy, dict), "Gate 5.8 review policy missing")
    require(policy.get("review_basis") == "manufacturer_evidence", "Gate 5.8 review basis must be manufacturer evidence")
    for key in (
        "one_verdict_per_fact",
        "fact_digest_binding_required",
        "all_retained_facts_must_be_covered",
        "extra_fact_verdicts_forbidden",
        "every_fact_requires_primary_citation",
        "supplemental_citations_are_context_only",
        "retained_model_output_mutation_forbidden",
        "deterministic_fact_repair_forbidden",
        "local_ai_rerun_forbidden_for_gate58",
    ):
        require(policy.get(key) is True, f"Gate 5.8 policy must enable {key}")
    require(policy.get("local_ai_rerun_required") is False, "Gate 5.8 must not require another AI run")

    qualification = contract.get("qualification")
    require(
        qualification == {
            "input_status": "READY_FOR_REVIEW",
            "qualified_status": "QUALIFIED",
            "incomplete_status": "REVIEW_INCOMPLETE",
            "rejected_status": "REJECTED_REVIEW",
        },
        "Gate 5.8 qualification vocabulary drift",
    )
    admission = contract.get("admission")
    require(isinstance(admission, dict), "Gate 5.8 admission policy missing")
    require(admission.get("exact_retained_semantic_run") == "CONDITIONAL_ON_QUALIFIED", "exact-run admission policy drift")
    for key in ("model_quality", "canonical_dataset", "hil", "production", "destructive_security_operation"):
        require(admission.get(key) is False, f"Gate 5.8 must keep admission false: {key}")

    if live_contract is not None:
        required = contract["required_retained_run"]
        require(live_contract.get("contract_id") == required["live_bounded_contract_id"], "Gate 5.7A contract id mismatch")
        require(live_contract.get("target") == contract["target"], "Gate 5.7A target mismatch")
        live_required = live_contract.get("required_input")
        require(isinstance(live_required, dict), "Gate 5.7A required_input missing")
        require(live_required.get("evidence_boundary_release_id") == required["evidence_boundary_release_id"], "evidence boundary release mismatch")
        require(live_required.get("bundle_digest") == required["bundle_digest"], "bundle digest mismatch")
        require(live_required.get("pre_ai_manifest_digest") == required["pre_ai_manifest_digest"], "manifest digest mismatch")
        runtime = live_contract.get("live_runtime")
        require(isinstance(runtime, dict), "Gate 5.7A runtime missing")
        require(runtime.get("execution_mode") == required["execution_mode"], "Gate 5.7A execution mode mismatch")
        require(runtime.get("model_id") == required["model_id"], "Gate 5.7A model id mismatch")
        scope = runtime.get("semantic_scope")
        require(isinstance(scope, dict), "Gate 5.7A primary semantic scope missing")
        require(scope.get("fact_generation_authority") == "PRIMARY_ONLY", "Gate 5.7A primary authority drift")
        require(scope.get("dependency_pages") == "SUPPORTING_CONTEXT_ONLY", "Gate 5.7A dependency authority drift")
        require(scope.get("every_fact_requires_primary_citation") is True, "Gate 5.7A primary-citation policy drift")

    if definitions is not None:
        required = contract["required_retained_run"]
        require(definitions.get("target") == contract["target"], "reviewed Evidence Unit target mismatch")
        release = definitions.get("boundary_release")
        require(isinstance(release, dict), "reviewed Evidence Unit boundary release missing")
        require(release.get("release_id") == required["evidence_boundary_release_id"], "reviewed Evidence Unit release mismatch")
        units = definitions.get("units")
        require(isinstance(units, list) and len(units) == 8, "Gate 5.8 requires exactly eight primary Evidence Units")
        ids = [unit.get("unit_id") for unit in units if isinstance(unit, dict)]
        require(len(ids) == len(set(ids)) == 8 and all(isinstance(v, str) and v for v in ids), "reviewed Evidence Unit identities malformed")


def _unit_index(definitions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for unit in definitions.get("units", []):
        require(isinstance(unit, dict), "Evidence Unit definition must be an object")
        unit_id = unit.get("unit_id")
        source_id = unit.get("source_id")
        page_range = unit.get("pdf_page_range")
        require(isinstance(unit_id, str) and unit_id, "Evidence Unit id missing")
        require(isinstance(source_id, str) and source_id, f"{unit_id}: source id missing")
        require(
            isinstance(page_range, list)
            and len(page_range) == 2
            and all(type(page) is int and page >= 1 for page in page_range)
            and page_range[0] <= page_range[1],
            f"{unit_id}: primary page range malformed",
        )
        result[unit_id] = {
            "definition": unit,
            "primary_refs": {(source_id, page) for page in range(page_range[0], page_range[1] + 1)},
        }
    return result


def _fact_digest(primary_unit_id: str, fact: dict[str, Any]) -> str:
    return builder.canonical_sha256({"primary_unit_id": primary_unit_id, "fact": fact})


def _validate_fact_shape(fact: Any, *, unit_id: str, fact_ids: set[str]) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    require(isinstance(fact, dict), f"{unit_id}: fact must be an object")
    require(set(fact) == {"fact_id", "kind", "statement", "evidence"}, f"{unit_id}: retained fact keys changed")
    fact_id = fact.get("fact_id")
    require(isinstance(fact_id, str) and fact_id, f"{unit_id}: fact_id missing")
    require(fact_id not in fact_ids, f"duplicate retained fact_id: {fact_id}")
    fact_ids.add(fact_id)
    require(isinstance(fact.get("kind"), str) and fact["kind"], f"{fact_id}: fact kind missing")
    require(isinstance(fact.get("statement"), str) and fact["statement"].strip(), f"{fact_id}: statement missing")
    evidence = fact.get("evidence")
    require(isinstance(evidence, list) and evidence, f"{fact_id}: evidence missing")
    refs: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for index, ref in enumerate(evidence):
        require(isinstance(ref, dict) and set(ref) == {"source_id", "pdf_page_number"}, f"{fact_id}: evidence[{index}] malformed")
        source_id = ref.get("source_id")
        page = ref.get("pdf_page_number")
        require(isinstance(source_id, str) and source_id, f"{fact_id}: evidence[{index}] source missing")
        require(type(page) is int and page >= 1, f"{fact_id}: evidence[{index}] page malformed")
        pair = (source_id, page)
        require(pair not in seen, f"{fact_id}: duplicate citation {source_id}:p{page}")
        seen.add(pair)
        refs.append(pair)
    return fact, refs


def validate_retained_artifacts(
    *,
    run_dir: Path,
    aggregate: dict[str, Any],
    provenance: dict[str, Any],
    qualification_report: dict[str, Any],
    contract: dict[str, Any],
    live_contract: dict[str, Any],
    definitions: dict[str, Any],
) -> None:
    validate_contract(contract, live_contract=live_contract, definitions=definitions)
    required = contract["required_retained_run"]
    resolved = run_dir.resolve()
    require(resolved.name == required["run_id"], f"Gate 5.8 is bound to retained run {required['run_id']}")
    require(resolved.parent.name == required["parent_dir_name"], f"Gate 5.8 run must be under {required['parent_dir_name']}")

    aggregate_digest = _verify_self_digest(aggregate, "aggregate_digest", label="aggregate")
    provenance_digest = _verify_self_digest(provenance, "provenance_digest", label="provenance")
    report_digest = _verify_self_digest(qualification_report, "report_digest", label="qualification report")
    require(bool(provenance_digest and report_digest), "retained provenance/report digest missing")

    require(aggregate.get("artifact_type") == "kl25_bounded_aggregate", "retained aggregate artifact mismatch")
    require(aggregate.get("target") == contract["target"], "retained aggregate target mismatch")
    require(aggregate.get("execution_contract_id") == required["live_bounded_contract_id"], "retained aggregate contract mismatch")
    require(aggregate.get("execution_mode") == required["execution_mode"], "retained aggregate execution mode mismatch")
    require(aggregate.get("bundle_digest") == required["bundle_digest"], "retained aggregate bundle mismatch")
    require(aggregate.get("pre_ai_manifest_digest") == required["pre_ai_manifest_digest"], "retained aggregate manifest mismatch")
    require(aggregate.get("status") == required["aggregate_status"], "retained aggregate is not INTEGRITY_PASS")
    require(aggregate.get("errors") == [], "retained aggregate has integrity errors")
    require(aggregate.get("qualification_status") == "NOT_QUALIFIED", "bounded core must not self-qualify")
    scope = aggregate.get("semantic_scope")
    require(isinstance(scope, dict) and scope.get("fact_generation_authority") == "PRIMARY_ONLY", "retained aggregate primary scope missing")
    require(scope.get("dependency_pages") == "SUPPORTING_CONTEXT_ONLY", "retained aggregate dependency scope mismatch")
    require(scope.get("every_fact_requires_primary_citation") is True, "retained aggregate primary-citation rule missing")

    require(provenance.get("artifact_type") == "kl25_live_bounded_run_provenance", "retained provenance artifact mismatch")
    require(provenance.get("target") == contract["target"], "retained provenance target mismatch")
    require(provenance.get("bundle_digest") == required["bundle_digest"], "retained provenance bundle mismatch")
    require(provenance.get("pre_ai_manifest_digest") == required["pre_ai_manifest_digest"], "retained provenance manifest mismatch")
    require(provenance.get("live_bounded_contract_id") == required["live_bounded_contract_id"], "retained provenance contract mismatch")
    require(provenance.get("live_bounded_contract_digest") == builder.canonical_sha256(live_contract), "retained Gate 5.7A contract digest mismatch")
    require(provenance.get("aggregate_digest") == aggregate_digest, "retained provenance aggregate binding mismatch")
    identity = provenance.get("ollama_runtime_identity")
    require(isinstance(identity, dict), "retained Ollama identity missing")
    require(identity.get("model_id") == required["model_id"], "retained model id mismatch")
    require(normalized_model_digest(identity.get("model_digest")) == required["model_digest"], "retained model digest mismatch")
    execution = provenance.get("execution")
    require(isinstance(execution, dict), "retained execution provenance missing")
    require(execution.get("execution_mode") == required["execution_mode"], "retained execution mode mismatch")
    require(execution.get("model_id") == required["model_id"], "retained execution model mismatch")
    require(execution.get("semantic_scope") == live_contract.get("live_runtime", {}).get("semantic_scope"), "retained semantic scope provenance mismatch")
    require(execution.get("automatic_retries") == 0, "retained Gate 5.7A run must have zero retries")

    require(qualification_report.get("artifact_type") == "kl25_live_bounded_qualification_report", "qualification report artifact mismatch")
    require(qualification_report.get("qualification_contract_id") == required["live_bounded_contract_id"], "qualification report contract mismatch")
    require(qualification_report.get("target") == contract["target"], "qualification report target mismatch")
    require(qualification_report.get("bundle_digest") == required["bundle_digest"], "qualification report bundle mismatch")
    require(qualification_report.get("pre_ai_manifest_digest") == required["pre_ai_manifest_digest"], "qualification report manifest mismatch")
    require(qualification_report.get("aggregate_digest") == aggregate_digest, "qualification report aggregate binding mismatch")
    require(qualification_report.get("model_id") == required["model_id"], "qualification report model mismatch")
    require(normalized_model_digest(qualification_report.get("model_digest")) == required["model_digest"], "qualification report model digest mismatch")
    require(qualification_report.get("status") == required["pre_review_qualification_status"], "Gate 5.8 input must be READY_FOR_REVIEW")
    require(qualification_report.get("integrity", {}).get("status") == "PASS", "Gate 5.8 input integrity must PASS")
    require(qualification_report.get("semantic_screening", {}).get("status") == "PASS", "Gate 5.8 input screening must PASS")
    require(qualification_report.get("review", {}).get("status") == "PENDING", "Gate 5.8 input review must still be pending")
    require(qualification_report.get("review", {}).get("basis_required") == "manufacturer_evidence", "manufacturer review basis mismatch")

    units = _unit_index(definitions)
    response = aggregate.get("response")
    require(isinstance(response, dict), "retained aggregate response missing")
    unit_results = response.get("unit_results")
    require(isinstance(unit_results, list), "retained aggregate unit_results missing")
    result_ids = [item.get("primary_unit_id") for item in unit_results if isinstance(item, dict)]
    require(len(result_ids) == len(set(result_ids)) == len(units), "retained unit result cardinality/identity mismatch")
    require(set(result_ids) == set(units), "retained aggregate must cover all reviewed primary Evidence Units")
    fact_ids: set[str] = set()
    for unit_result in unit_results:
        require(isinstance(unit_result, dict), "retained unit result must be an object")
        unit_id = unit_result.get("primary_unit_id")
        require(unit_result.get("state") == "FACTS", f"{unit_id}: Gate 5.8 requires FACTS state")
        facts = unit_result.get("facts")
        require(isinstance(facts, list) and facts, f"{unit_id}: Gate 5.8 requires at least one fact")
        primary_refs = units[unit_id]["primary_refs"]
        for fact in facts:
            parsed, refs = _validate_fact_shape(fact, unit_id=unit_id, fact_ids=fact_ids)
            require(any(ref in primary_refs for ref in refs), f"{parsed['fact_id']}: missing PRIMARY citation")


def load_retained_run(
    run_dir: Path,
    *,
    contract: dict[str, Any] | None = None,
    live_contract: dict[str, Any] | None = None,
    definitions: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = contract or load_contract()
    live_contract = live_contract or load_live_contract()
    definitions = definitions or load_unit_definitions()
    aggregate = read_json(run_dir / "aggregate-report.json")
    provenance = read_json(run_dir / "live-bounded-provenance.json")
    qualification_report = read_json(run_dir / "qualification-report.json")
    validate_retained_artifacts(
        run_dir=run_dir,
        aggregate=aggregate,
        provenance=provenance,
        qualification_report=qualification_report,
        contract=contract,
        live_contract=live_contract,
        definitions=definitions,
    )
    return aggregate, provenance, qualification_report, contract, live_contract, definitions


def build_review_view_from_artifacts(
    *,
    run_id: str,
    aggregate: dict[str, Any],
    provenance: dict[str, Any],
    qualification_report: dict[str, Any],
    contract: dict[str, Any],
    definitions: dict[str, Any],
) -> dict[str, Any]:
    units = _unit_index(definitions)
    identity = provenance["ollama_runtime_identity"]
    response = aggregate["response"]
    result_by_unit = {item["primary_unit_id"]: item for item in response["unit_results"]}
    view_units: list[dict[str, Any]] = []
    fact_count = 0
    for unit_id in sorted(units):
        meta = units[unit_id]["definition"]
        primary_refs = units[unit_id]["primary_refs"]
        facts: list[dict[str, Any]] = []
        for fact in result_by_unit[unit_id]["facts"]:
            all_citations = [
                {"source_id": ref["source_id"], "pdf_page_number": ref["pdf_page_number"]}
                for ref in fact["evidence"]
            ]
            primary_citations = [
                ref for ref in all_citations
                if (ref["source_id"], ref["pdf_page_number"]) in primary_refs
            ]
            supplemental_citations = [
                ref for ref in all_citations
                if (ref["source_id"], ref["pdf_page_number"]) not in primary_refs
            ]
            require(primary_citations, f"{fact['fact_id']}: review view cannot contain dependency-only fact")
            facts.append({
                "fact_id": fact["fact_id"],
                "fact_digest": _fact_digest(unit_id, fact),
                "kind": fact["kind"],
                "statement": fact["statement"],
                "primary_citations": primary_citations,
                "supplemental_citations": supplemental_citations,
                "all_citations": all_citations,
            })
            fact_count += 1
        view_units.append({
            "primary_unit_id": unit_id,
            "role": meta.get("role"),
            "section_scope": meta.get("section_scope"),
            "primary_source_id": meta.get("source_id"),
            "primary_pdf_page_range": meta.get("pdf_page_range"),
            "manufacturer_native_terms": meta.get("manufacturer_native_terms"),
            "facts": facts,
        })

    required = contract["required_retained_run"]
    view: dict[str, Any] = {
        "schema_version": "0.1.0",
        "artifact_type": "kl25_gate58_review_view",
        "contract_id": contract["contract_id"],
        "target": contract["target"],
        "retained_run_id": run_id,
        "aggregate_digest": aggregate["aggregate_digest"],
        "provenance_digest": provenance["provenance_digest"],
        "qualification_report_digest": qualification_report["report_digest"],
        "evidence_boundary_release_id": required["evidence_boundary_release_id"],
        "bundle_digest": required["bundle_digest"],
        "pre_ai_manifest_digest": required["pre_ai_manifest_digest"],
        "model_id": required["model_id"],
        "model_digest": normalized_model_digest(identity["model_digest"]),
        "review_basis": contract["review_policy"]["review_basis"],
        "fact_count": fact_count,
        "units": view_units,
    }
    view["review_view_digest"] = builder.canonical_sha256(view)
    return view


def build_review_view(run_dir: Path) -> dict[str, Any]:
    aggregate, provenance, report, contract, _, definitions = load_retained_run(run_dir)
    return build_review_view_from_artifacts(
        run_id=run_dir.resolve().name,
        aggregate=aggregate,
        provenance=provenance,
        qualification_report=report,
        contract=contract,
        definitions=definitions,
    )


def build_review_template(view: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    verdicts: list[dict[str, Any]] = []
    for unit in view.get("units", []):
        unit_id = unit["primary_unit_id"]
        for fact in unit.get("facts", []):
            verdicts.append({
                "primary_unit_id": unit_id,
                "fact_id": fact["fact_id"],
                "fact_digest": fact["fact_digest"],
                "semantic_support": "NOT_REVIEWED",
                "citation_entailment": "NOT_REVIEWED",
                "atomicity": "NOT_REVIEWED",
                "scope": "NOT_REVIEWED",
                "terminology": "NOT_REVIEWED",
                "rationale": "",
            })
    return {
        "schema_version": "0.1.0",
        "artifact_type": "kl25_gate58_manufacturer_review_verdict",
        "contract_id": contract["contract_id"],
        "target": view["target"],
        "retained_run_id": view["retained_run_id"],
        "aggregate_digest": view["aggregate_digest"],
        "provenance_digest": view["provenance_digest"],
        "qualification_report_digest": view["qualification_report_digest"],
        "review_view_digest": view["review_view_digest"],
        "review_basis": contract["review_policy"]["review_basis"],
        "fact_verdicts": verdicts,
        "overall_verdict": "REVIEW_INCOMPLETE",
    }


def validate_verdict(
    verdict: dict[str, Any],
    *,
    view: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    expected_root = {
        "schema_version", "artifact_type", "contract_id", "target", "retained_run_id",
        "aggregate_digest", "provenance_digest", "qualification_report_digest",
        "review_view_digest", "review_basis", "fact_verdicts", "overall_verdict",
    }
    require(set(verdict) == expected_root, "Gate 5.8 verdict root keys mismatch")
    require(verdict.get("schema_version") == "0.1.0", "Gate 5.8 verdict schema mismatch")
    require(verdict.get("artifact_type") == "kl25_gate58_manufacturer_review_verdict", "Gate 5.8 verdict artifact mismatch")
    require(verdict.get("contract_id") == contract["contract_id"], "Gate 5.8 verdict contract mismatch")
    require(verdict.get("target") == view["target"], "Gate 5.8 verdict target mismatch")
    for key in (
        "retained_run_id", "aggregate_digest", "provenance_digest",
        "qualification_report_digest", "review_view_digest", "review_basis",
    ):
        require(verdict.get(key) == view.get(key), f"Gate 5.8 verdict binding mismatch: {key}")

    expected_facts = {
        (unit["primary_unit_id"], fact["fact_id"]): fact["fact_digest"]
        for unit in view["units"]
        for fact in unit["facts"]
    }
    items = verdict.get("fact_verdicts")
    require(isinstance(items, list), "Gate 5.8 fact_verdicts must be an array")
    observed: dict[tuple[str, str], dict[str, Any]] = {}
    pending = False
    failed = False
    reviewed_count = 0
    expected_item_keys = {
        "primary_unit_id", "fact_id", "fact_digest", "semantic_support",
        "citation_entailment", "atomicity", "scope", "terminology", "rationale",
    }
    for index, item in enumerate(items):
        require(isinstance(item, dict), f"fact_verdicts[{index}] must be an object")
        require(set(item) == expected_item_keys, f"fact_verdicts[{index}] keys mismatch")
        unit_id = item.get("primary_unit_id")
        fact_id = item.get("fact_id")
        require(isinstance(unit_id, str) and isinstance(fact_id, str), f"fact_verdicts[{index}] identity malformed")
        key = (unit_id, fact_id)
        require(key in expected_facts, f"unsupported Gate 5.8 fact verdict: {unit_id}/{fact_id}")
        require(key not in observed, f"duplicate Gate 5.8 fact verdict: {unit_id}/{fact_id}")
        require(item.get("fact_digest") == expected_facts[key], f"{unit_id}/{fact_id}: fact digest mismatch")
        observed[key] = item

        fact_pending = False
        fact_failed = False
        for dimension_name, (allowed, pass_value) in EXPECTED_DIMENSIONS.items():
            value = item.get(dimension_name)
            require(value in allowed, f"{unit_id}/{fact_id}: invalid {dimension_name} verdict {value!r}")
            if value == "NOT_REVIEWED":
                fact_pending = True
            elif value != pass_value:
                fact_failed = True
        rationale = item.get("rationale")
        require(isinstance(rationale, str), f"{unit_id}/{fact_id}: rationale must be a string")
        if not fact_pending:
            require(bool(rationale.strip()), f"{unit_id}/{fact_id}: completed review requires rationale")
            reviewed_count += 1
        pending = pending or fact_pending
        failed = failed or fact_failed

    require(set(observed) == set(expected_facts), f"Gate 5.8 verdict must cover the exact retained fact set; missing={sorted(set(expected_facts) - set(observed))}")
    if pending:
        expected_overall = "REVIEW_INCOMPLETE"
        status = contract["qualification"]["incomplete_status"]
    elif failed:
        expected_overall = "FAIL"
        status = contract["qualification"]["rejected_status"]
    else:
        expected_overall = "PASS"
        status = contract["qualification"]["qualified_status"]
    require(verdict.get("overall_verdict") == expected_overall, f"overall_verdict must be {expected_overall}")

    report: dict[str, Any] = {
        "schema_version": "0.1.0",
        "artifact_type": "kl25_gate58_qualification_report",
        "contract_id": contract["contract_id"],
        "target": view["target"],
        "retained_run_id": view["retained_run_id"],
        "aggregate_digest": view["aggregate_digest"],
        "review_view_digest": view["review_view_digest"],
        "review_basis": verdict["review_basis"],
        "status": status,
        "fact_count": len(expected_facts),
        "fully_reviewed_fact_count": reviewed_count,
        "overall_verdict": expected_overall,
        "trust_boundary": {
            "exact_retained_semantic_run_qualified": status == "QUALIFIED",
            "model_quality_admission": False,
            "canonical_dataset_admission": False,
            "hil_admission": False,
            "production_admission": False,
            "destructive_security_operation_admission": False,
        },
    }
    report["report_digest"] = builder.canonical_sha256(report)
    return report


def qualify_review(run_dir: Path, verdict: dict[str, Any]) -> dict[str, Any]:
    aggregate, provenance, qualification_report, contract, _, definitions = load_retained_run(run_dir)
    view = build_review_view_from_artifacts(
        run_id=run_dir.resolve().name,
        aggregate=aggregate,
        provenance=provenance,
        qualification_report=qualification_report,
        contract=contract,
        definitions=definitions,
    )
    return validate_verdict(verdict, view=view, contract=contract)


def _write_json_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="NXP KL25 Gate 5.8 manufacturer-evidence review")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-contract", help="Validate frozen Gate 5.8 repository contracts")
    validate_parser.set_defaults(command="validate-contract")

    view_parser = subparsers.add_parser("build-view", help="Build a deterministic per-fact review view from the retained Gate 5.7A run")
    view_parser.add_argument("--run-dir", type=Path, required=True)
    view_parser.add_argument("--output", type=Path, required=True)
    view_parser.add_argument("--template-output", type=Path)

    qualify_parser = subparsers.add_parser("qualify", help="Validate a completed Gate 5.8 verdict against the exact retained fact set")
    qualify_parser.add_argument("--run-dir", type=Path, required=True)
    qualify_parser.add_argument("--verdict", type=Path, required=True)
    qualify_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        contract = load_contract()
        live_contract = load_live_contract()
        definitions = load_unit_definitions()
        validate_contract(contract, live_contract=live_contract, definitions=definitions)
        if args.command == "validate-contract":
            print("KL25 Gate 5.8 contract: PASS")
            return 0
        if args.command == "build-view":
            view = build_review_view(args.run_dir)
            _write_json_new(args.output, view)
            if args.template_output is not None:
                _write_json_new(args.template_output, build_review_template(view, contract))
            print(f"KL25 Gate 5.8 review view: facts={view['fact_count']}; digest={view['review_view_digest']}")
            return 0
        if args.command == "qualify":
            verdict = read_json(args.verdict)
            report = qualify_review(args.run_dir, verdict)
            _write_json_new(args.output, report)
            print(
                "KL25 Gate 5.8 qualification: "
                f"status={report['status']}; reviewed={report['fully_reviewed_fact_count']}/{report['fact_count']}"
            )
            return 0 if report["status"] == "QUALIFIED" else 1
        raise Gate58ReviewError(f"unsupported command: {args.command}")
    except (Gate58ReviewError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"KL25 Gate 5.8 FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
