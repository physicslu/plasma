#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import canonicalize_semantic_facts as common
import canonicalize_semantic_facts_v4 as relationship_base
import semantic_extraction_v5 as semantic

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "canonicalization-contract-v3.json"
MEMORY_FIELDS = ("flash_size_bytes", "page_size_bytes", "page_count")
TARGETS = ("STM32F103C8T6", "STM32F103CBT6")

CanonicalizationError = common.CanonicalizationError
require = common.require
load_json = common.load_json


def _is_unresolved(value: Any) -> bool:
    return value is None or value == "unknown"


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for citation in citations:
        source_id = citation.get("source_id")
        page_index = citation.get("physical_page_index")
        require(isinstance(source_id, str), "relationship citation source_id required")
        require(
            isinstance(page_index, int) and not isinstance(page_index, bool),
            "relationship citation physical_page_index required",
        )
        key = (source_id, page_index)
        if key not in seen:
            seen.add(key)
            out.append({"source_id": source_id, "physical_page_index": page_index})
    return out


def _normalized_memory_facts(target_facts: dict[str, Any]) -> tuple[int, int, int] | None:
    values = {field: target_facts.get(field) for field in MEMORY_FIELDS}
    if any(_is_unresolved(values[field]) for field in MEMORY_FIELDS):
        return None
    for field in MEMORY_FIELDS:
        value = values[field]
        require(
            isinstance(value, int) and not isinstance(value, bool) and value > 0,
            f"memory_geometry.{field} must be positive integer",
        )
    return tuple(values[field] for field in MEMORY_FIELDS)  # type: ignore[return-value]


def derive_memory_geometry_relationship(
    facts: dict[str, Any],
    evidence: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    relationship_contract = contract.get("relationship_derivation", {}).get("memory_geometry")
    require(isinstance(relationship_contract, dict), "memory_geometry relationship derivation contract required")
    require(
        relationship_contract.get("scope") == "benchmark_profile_projection_only",
        "memory_geometry derivation scope mismatch",
    )
    require(
        relationship_contract.get("fields") == list(MEMORY_FIELDS),
        "memory_geometry derivation fields mismatch",
    )

    targets = facts.get("targets")
    require(isinstance(targets, dict) and set(targets) == set(TARGETS), "relationship target set mismatch")

    target_inputs: dict[str, dict[str, Any]] = {}
    normalized: dict[str, tuple[int, int, int] | None] = {}
    source_paths: list[str] = []
    citations: list[dict[str, Any]] = []

    for target in TARGETS:
        target_facts = targets[target]
        require(isinstance(target_facts, dict), f"{target}: target facts object required")
        target_inputs[target] = {field: target_facts.get(field) for field in MEMORY_FIELDS}
        normalized[target] = _normalized_memory_facts(target_facts)
        if normalized[target] is not None:
            for field in MEMORY_FIELDS:
                path = f"$.semantic_facts.targets.{target}.{field}"
                source_paths.append(path)
                field_citations = evidence.get(path)
                require(isinstance(field_citations, list) and field_citations, f"{path}: evidence required")
                citations.extend(field_citations)

    if any(normalized[target] is None for target in TARGETS):
        relationship = relationship_contract.get("incomplete")
        require(relationship == "unknown", "incomplete memory_geometry relationship must resolve to unknown")
        source_paths = []
        citations = []
    else:
        first, second = (normalized[target] for target in TARGETS)
        relationship = (
            relationship_contract.get("complete_equal")
            if first == second
            else relationship_contract.get("complete_unequal")
        )
        require(relationship in {"shared", "different"}, "invalid derived memory_geometry relationship")

    transformation = {
        "kind": "DETERMINISTIC_RELATIONSHIP_DERIVATION",
        "path": "$.canonical_spec.profile_relationships.memory_geometry",
        "relationship": "memory_geometry",
        "scope": "benchmark_profile_projection_only",
        "source_paths": source_paths,
        "input": target_inputs,
        "comparison": {"fields": list(MEMORY_FIELDS), "semantics": "exact_field_equality"},
        "output": relationship,
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

    memory_relationship, relationship_citations, transformation = derive_memory_geometry_relationship(
        facts,
        evidence,
        contract,
    )

    relationships = facts["profile_relationships"]
    adapted_facts = {
        **facts,
        "profile_relationships": {
            "programming": relationships["programming"],
            "memory_geometry": memory_relationship,
            "option": relationships["option"],
            "security": relationships["security"],
        },
    }
    adapted_evidence = dict(evidence)
    if memory_relationship != "unknown":
        adapted_evidence["$.semantic_facts.profile_relationships.memory_geometry"] = relationship_citations

    return {"semantic_facts": adapted_facts, "evidence": adapted_evidence}, transformation


def canonicalize_response(payload: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    require(
        contract.get("semantic_schema_id") == "plasma://ic-support/stm32f103c/semantic-extraction-v3",
        "unexpected memory relationship semantic schema ID",
    )
    require(
        contract.get("canonical_schema_id") == "plasma://ic-support/stm32f103c/canonical-spec-v0",
        "unexpected canonical schema ID",
    )
    base_contract_name = contract.get("base_relationship_canonicalization_contract")
    require(base_contract_name == "canonicalization-contract-v2.json", "unexpected relationship base contract")
    base_contract = load_json(HERE / base_contract_name)

    adapted_payload, memory_transformation = _adapt_for_relationship_base(payload, contract)
    report = relationship_base.canonicalize_response(adapted_payload, base_contract)
    report["canonicalization_id"] = contract["canonicalization_id"]
    report["input_sha256"] = common.canonical_sha256(payload)
    report["contract_sha256"] = common.canonical_sha256(contract)
    report["base_contract_sha256"] = common.canonical_sha256(base_contract)
    report["base_canonicalization_id"] = base_contract["canonicalization_id"]
    report["transformations"] = [memory_transformation, *report["transformations"]]
    report["trust_boundary"] = {
        **report.get("trust_boundary", {}),
        "generation_visibility_of_contract": False,
        "ai_emits_memory_geometry_relationship": False,
        "memory_geometry_relationship_is_deterministic": True,
        "ai_emits_package_hardware_relationship": False,
        "package_hardware_relationship_is_deterministic": True,
        "relationship_free_form_semantic_matching": False,
        "pin_level_minimum_programming_hardware_admission": False,
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive memory/package relationships and canonicalize semantic facts")
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
        print("IC memory/package relationship-derived canonicalization COMPLETE")
        print(f"- status: {report['canonicalization_status']}")
        print(f"- memory_geometry relationship: {report['canonical_spec']['profile_relationships']['memory_geometry']}")
        print(f"- package_hardware relationship: {report['canonical_spec']['profile_relationships']['package_hardware']}")
        print(f"- transformations: {len(report['transformations'])}")
        print(f"- unresolved paths: {len(report['unresolved_paths'])}")
        print("- memory/package relationships emitted by AI: false")
        print("- canonical dataset admission: false")
        print("- production admission: false")
        return 0
    except (OSError, json.JSONDecodeError, CanonicalizationError, semantic.SemanticExtractionError, KeyError) as exc:
        print(f"IC memory/package relationship-derived canonicalization FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
