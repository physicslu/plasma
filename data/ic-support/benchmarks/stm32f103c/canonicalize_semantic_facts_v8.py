#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import canonicalize_semantic_facts as common
import canonicalize_semantic_facts_v7 as relationship_base
import semantic_extraction_v8 as semantic

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "canonicalization-contract-v6.json"
TARGETS = ("STM32F103C8T6", "STM32F103CBT6")

CanonicalizationError = common.CanonicalizationError
require = common.require
load_json = common.load_json


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for citation in citations:
        source_id = citation.get("source_id")
        page_index = citation.get("physical_page_index")
        require(isinstance(source_id, str), "security applicability citation source_id required")
        require(
            isinstance(page_index, int) and not isinstance(page_index, bool),
            "security applicability citation physical_page_index required",
        )
        key = (source_id, page_index)
        if key not in seen:
            seen.add(key)
            out.append({"source_id": source_id, "physical_page_index": page_index})
    return out


def _authority_units(authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    catalogs = authority.get("catalogs")
    require(isinstance(catalogs, dict), "security applicability authority catalogs required")
    units: dict[str, dict[str, Any]] = {}
    for catalog in catalogs.values():
        require(isinstance(catalog, dict), "authority catalog object required")
        for unit in catalog.get("units", []):
            require(isinstance(unit, dict), "authority evidence unit object required")
            unit_id = unit.get("unit_id")
            require(isinstance(unit_id, str) and unit_id, "authority evidence unit id required")
            require(unit_id not in units, f"duplicate authority evidence unit: {unit_id}")
            units[unit_id] = unit
    return units


def validate_security_applicability_projection(applicability: dict[str, Any]) -> None:
    require(
        applicability.get("source_lock_id") == "stm32f103c-source-lock-v0",
        "security applicability source-lock mismatch",
    )
    require(
        applicability.get("relationship_scope") == "benchmark_profile_projection_only",
        "security applicability scope mismatch",
    )
    require(
        applicability.get("contract_identity_semantics")
        == "evidence_pack_identity_for_benchmark_relationship_only",
        "security applicability contract identity semantics mismatch",
    )
    require(
        applicability.get("security_transition_safety_admission") is False,
        "security applicability must deny transition-safety admission",
    )
    require(
        applicability.get("destructive_security_operation_admission") is False,
        "security applicability must deny destructive-operation admission",
    )
    require(applicability.get("canonical_dataset_admission") is False, "applicability must deny canonical admission")
    require(applicability.get("production_admission") is False, "applicability must deny production admission")

    authority_file = applicability.get("authority_file")
    require(isinstance(authority_file, str) and authority_file, "security applicability authority file required")
    authority = load_json((HERE / authority_file).resolve())
    require(authority.get("source_lock_id") == applicability["source_lock_id"], "authority source-lock mismatch")
    binding = authority.get("applicability_binding")
    require(isinstance(binding, dict), "authority applicability binding required")
    claims = binding.get("claims")
    authority_targets = binding.get("targets")
    require(isinstance(claims, dict), "authority applicability claims required")
    require(isinstance(authority_targets, list), "authority applicability targets required")
    units = _authority_units(authority)

    projected_targets = applicability.get("targets")
    require(
        isinstance(projected_targets, dict) and set(projected_targets) == set(TARGETS),
        "security applicability target set mismatch",
    )
    declared_contract = applicability.get("security_contract_id")
    require(isinstance(declared_contract, str) and declared_contract, "security contract id required")

    for target, projected in projected_targets.items():
        require(isinstance(projected, dict), f"{target}: projected applicability object required")
        claim_id = projected.get("applicability_claim_id")
        contract_id = projected.get("contract_id")
        require(contract_id == declared_contract, f"{target}: projected security contract mismatch")
        require(isinstance(claim_id, str) and claim_id in claims, f"{target}: authority claim required")
        claim = claims[claim_id]
        require(claim.get("pack_id") == contract_id, f"{target}: projected contract/claim mismatch")
        require(
            claim.get("manufacturer_expression") == projected.get("manufacturer_expression"),
            f"{target}: manufacturer applicability expression mismatch",
        )
        matches = [entry for entry in authority_targets if entry.get("icpn") == target]
        require(len(matches) == 1, f"{target}: exact authority target binding required")
        require(contract_id in matches[0].get("pack_ids", []), f"{target}: authority pack binding missing")
        require(claim_id in matches[0].get("applicability_claim_ids", []), f"{target}: authority claim binding missing")

        authority_citations: list[dict[str, Any]] = []
        evidence_unit_ids = claim.get("evidence_unit_ids")
        require(isinstance(evidence_unit_ids, list) and evidence_unit_ids, f"{target}: authority applicability evidence required")
        for unit_id in evidence_unit_ids:
            require(unit_id in units, f"{target}: authority applicability evidence unit missing")
            unit = units[unit_id]
            authority_citations.append(
                {"source_id": unit.get("source_id"), "physical_page_index": unit.get("pdf_page_index")}
            )
        require(
            _dedupe_citations(projected.get("evidence", [])) == _dedupe_citations(authority_citations),
            f"{target}: projected applicability evidence mismatch",
        )


def _normalized_target_applicability(value: Any) -> tuple[str, str, list[dict[str, Any]]] | None:
    if not isinstance(value, dict):
        return None
    contract_id = value.get("contract_id")
    claim_id = value.get("applicability_claim_id")
    evidence = value.get("evidence")
    if contract_id in (None, "unknown") or claim_id in (None, "unknown"):
        return None
    if not isinstance(contract_id, str) or not contract_id:
        return None
    if not isinstance(claim_id, str) or not claim_id:
        return None
    if not isinstance(evidence, list) or not evidence:
        return None
    return contract_id, claim_id, _dedupe_citations(evidence)


def derive_security_relationship(
    applicability: dict[str, Any],
    contract: dict[str, Any],
    *,
    verify_authority: bool = True,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    relationship_contract = contract.get("relationship_derivation", {}).get("security")
    require(isinstance(relationship_contract, dict), "security relationship derivation contract required")
    require(
        relationship_contract.get("source") == "evidence_backed_applicability",
        "security relationship must derive from applicability",
    )
    require(
        relationship_contract.get("scope") == "benchmark_profile_projection_only",
        "security relationship derivation scope mismatch",
    )
    if verify_authority:
        validate_security_applicability_projection(applicability)

    targets = applicability.get("targets")
    require(isinstance(targets, dict), "security applicability targets object required")
    normalized: dict[str, tuple[str, str, list[dict[str, Any]]] | None] = {}
    target_inputs: dict[str, Any] = {}
    citations: list[dict[str, Any]] = []
    for target in TARGETS:
        target_inputs[target] = targets.get(target)
        normalized[target] = _normalized_target_applicability(targets.get(target))
        if normalized[target] is not None:
            citations.extend(normalized[target][2])

    if any(normalized[target] is None for target in TARGETS):
        relationship = relationship_contract.get("incomplete")
        require(relationship == "unknown", "incomplete security applicability must resolve to unknown")
        citations = []
    else:
        contract_ids = [normalized[target][0] for target in TARGETS]  # type: ignore[index]
        relationship = (
            relationship_contract.get("complete_same_contract")
            if len(set(contract_ids)) == 1
            else relationship_contract.get("complete_different_contract")
        )
        require(relationship in {"shared", "different"}, "invalid derived security relationship")

    transformation = {
        "kind": "DETERMINISTIC_APPLICABILITY_RELATIONSHIP_DERIVATION",
        "path": "$.canonical_spec.profile_relationships.security",
        "relationship": "security",
        "scope": relationship_contract.get("scope"),
        "source": "evidence_backed_applicability",
        "applicability_id": applicability.get("applicability_id"),
        "input": target_inputs,
        "comparison": {
            "semantics": "applicable_security_contract_identity",
            "contract_identity_semantics": applicability.get("contract_identity_semantics"),
        },
        "output": relationship,
        "safety_admission": {
            "security_transition_safety": False,
            "destructive_security_operation": False,
        },
    }
    return relationship, _dedupe_citations(citations), transformation


def _adapt_for_relationship_base(
    payload: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    require(set(payload) == {"semantic_facts", "evidence"}, "payload requires semantic_facts + evidence")
    facts = payload["semantic_facts"]
    evidence = payload["evidence"]
    require(isinstance(facts, dict), "semantic_facts object required")
    require(isinstance(evidence, dict), "evidence object required")
    semantic.validate_semantic_facts(facts)
    semantic.validate_evidence(facts, evidence)

    relationship_contract = contract.get("relationship_derivation", {}).get("security")
    require(isinstance(relationship_contract, dict), "security relationship derivation contract required")
    applicability_name = relationship_contract.get("applicability_file")
    require(isinstance(applicability_name, str) and applicability_name, "security applicability file required")
    applicability = load_json(HERE / applicability_name)
    security_relationship, relationship_citations, transformation = derive_security_relationship(
        applicability,
        contract,
    )

    adapted_facts = {
        **facts,
        "profile_relationships": {
            "security": security_relationship,
        },
    }
    adapted_evidence = dict(evidence)
    if security_relationship != "unknown":
        adapted_evidence["$.semantic_facts.profile_relationships.security"] = relationship_citations
    return {"semantic_facts": adapted_facts, "evidence": adapted_evidence}, transformation


def canonicalize_response(payload: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    require(
        contract.get("semantic_schema_id") == "plasma://ic-support/stm32f103c/semantic-extraction-v6",
        "unexpected security relationship semantic schema ID",
    )
    require(
        contract.get("canonical_schema_id") == "plasma://ic-support/stm32f103c/canonical-spec-v0",
        "unexpected canonical schema ID",
    )
    base_contract_name = contract.get("base_relationship_canonicalization_contract")
    require(base_contract_name == "canonicalization-contract-v5.json", "unexpected relationship base contract")
    base_contract = load_json(HERE / base_contract_name)

    adapted_payload, security_transformation = _adapt_for_relationship_base(payload, contract)
    report = relationship_base.canonicalize_response(adapted_payload, base_contract)
    report["canonicalization_id"] = contract["canonicalization_id"]
    report["input_sha256"] = common.canonical_sha256(payload)
    report["contract_sha256"] = common.canonical_sha256(contract)
    report["base_contract_sha256"] = common.canonical_sha256(base_contract)
    report["base_canonicalization_id"] = base_contract["canonicalization_id"]
    report["transformations"] = [security_transformation, *report["transformations"]]
    report["trust_boundary"] = {
        **report.get("trust_boundary", {}),
        "generation_visibility_of_contract": False,
        "ai_emits_security_relationship": False,
        "security_relationship_is_applicability_derived": True,
        "security_relationship_from_raw_generated_field_equality": False,
        "security_relationship_implies_destructive_transition_safety": False,
        "destructive_security_operation_admission": False,
        "ai_emits_option_relationship": False,
        "option_relationship_is_applicability_derived": True,
        "option_relationship_from_raw_generated_field_equality": False,
        "ai_emits_programming_relationship": False,
        "programming_relationship_is_applicability_derived": True,
        "ai_emits_memory_geometry_relationship": False,
        "memory_geometry_relationship_is_deterministic": True,
        "ai_emits_package_hardware_relationship": False,
        "package_hardware_relationship_is_deterministic": True,
        "relationship_free_form_semantic_matching": False,
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive security/option/programming/memory/package relationships and canonicalize semantic facts")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = load_json(args.input)
        contract = load_json(args.contract)
        report = canonicalize_response(payload, contract)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("IC security/applicability relationship-derived canonicalization COMPLETE")
        print(f"- status: {report['canonicalization_status']}")
        print(f"- security relationship: {report['canonical_spec']['profile_relationships']['security']}")
        print(f"- option relationship: {report['canonical_spec']['profile_relationships']['option']}")
        print(f"- programming relationship: {report['canonical_spec']['profile_relationships']['programming']}")
        print(f"- memory_geometry relationship: {report['canonical_spec']['profile_relationships']['memory_geometry']}")
        print(f"- package_hardware relationship: {report['canonical_spec']['profile_relationships']['package_hardware']}")
        print("- security relationship emitted by AI: false")
        print("- destructive security operation admission: false")
        print("- canonical dataset admission: false")
        print("- production admission: false")
        return 0
    except (OSError, json.JSONDecodeError, CanonicalizationError, semantic.SemanticExtractionError, KeyError) as exc:
        print(f"IC security/applicability relationship-derived canonicalization FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
