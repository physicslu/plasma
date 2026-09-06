#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import canonicalize_semantic_facts as common
import canonicalize_semantic_facts_v3 as structured_base
import semantic_extraction_v4 as semantic

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "canonicalization-contract-v2.json"
PACKAGE_FIELDS = ("package", "pin_count", "debug_programming_interfaces")
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


def _normalized_package_facts(values: dict[str, Any]) -> tuple[str, int, tuple[str, ...]] | None:
    require(isinstance(values, dict), "package_hardware facts object required")
    require(set(values) == set(PACKAGE_FIELDS), "package_hardware facts keys mismatch")
    if any(_is_unresolved(values[field]) for field in PACKAGE_FIELDS):
        return None

    package = values["package"]
    pin_count = values["pin_count"]
    interfaces = values["debug_programming_interfaces"]
    require(isinstance(package, str) and package != "", "package_hardware.package must be non-empty string")
    require(
        isinstance(pin_count, int) and not isinstance(pin_count, bool) and pin_count > 0,
        "package_hardware.pin_count must be positive integer",
    )
    require(
        isinstance(interfaces, list) and all(isinstance(item, str) and item != "" for item in interfaces),
        "package_hardware.debug_programming_interfaces must be string array",
    )
    normalized_interfaces = tuple(sorted(set(interfaces)))
    return package, pin_count, normalized_interfaces


def derive_package_hardware_relationship(
    facts: dict[str, Any],
    evidence: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    relationship_contract = contract.get("relationship_derivation", {}).get("package_hardware")
    require(isinstance(relationship_contract, dict), "package_hardware relationship derivation contract required")
    require(relationship_contract.get("fields") == list(PACKAGE_FIELDS), "package_hardware derivation fields mismatch")
    require(relationship_contract.get("interface_list_semantics") == "set", "package_hardware interface semantics must be set")

    target_inputs: dict[str, Any] = {}
    normalized: dict[str, tuple[str, int, tuple[str, ...]] | None] = {}
    source_paths: list[str] = []
    citations: list[dict[str, Any]] = []

    targets = facts.get("targets")
    require(isinstance(targets, dict) and set(targets) == set(TARGETS), "relationship target set mismatch")
    for target in TARGETS:
        target_facts = targets[target]
        require(isinstance(target_facts, dict), f"{target}: target facts object required")
        package_facts = target_facts.get("package_hardware")
        require(isinstance(package_facts, dict), f"{target}: package_hardware facts required")
        target_inputs[target] = package_facts
        normalized[target] = _normalized_package_facts(package_facts)
        if normalized[target] is not None:
            for field in PACKAGE_FIELDS:
                path = f"$.semantic_facts.targets.{target}.package_hardware.{field}"
                source_paths.append(path)
                field_citations = evidence.get(path)
                require(isinstance(field_citations, list) and field_citations, f"{path}: evidence required")
                citations.extend(field_citations)

    if any(normalized[target] is None for target in TARGETS):
        relationship = relationship_contract.get("incomplete")
        require(relationship == "unknown", "incomplete package_hardware relationship must resolve to unknown")
        citations = []
        source_paths = []
    else:
        first, second = (normalized[target] for target in TARGETS)
        relationship = (
            relationship_contract.get("complete_equal")
            if first == second
            else relationship_contract.get("complete_unequal")
        )
        require(relationship in {"shared", "different"}, "invalid derived package_hardware relationship")

    transformation = {
        "kind": "DETERMINISTIC_RELATIONSHIP_DERIVATION",
        "path": "$.canonical_spec.profile_relationships.package_hardware",
        "relationship": "package_hardware",
        "source_paths": source_paths,
        "input": target_inputs,
        "comparison": {
            "fields": list(PACKAGE_FIELDS),
            "debug_programming_interfaces": "set_equality",
        },
        "output": relationship,
    }
    return relationship, _dedupe_citations(citations), transformation


def _adapt_for_structured_base(
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

    package_relationship, relationship_citations, transformation = derive_package_hardware_relationship(
        facts,
        evidence,
        contract,
    )

    legacy_relationships = facts["profile_relationships"]
    adapted_relationships = {
        "programming": legacy_relationships["programming"],
        "memory_geometry": legacy_relationships["memory_geometry"],
        "package_hardware": package_relationship,
        "option": legacy_relationships["option"],
        "security": legacy_relationships["security"],
    }

    adapted_targets: dict[str, Any] = {}
    for target, target_facts in facts["targets"].items():
        adapted_targets[target] = {
            "manufacturer_device_reference": target_facts["manufacturer_device_reference"],
            "flash_size_bytes": target_facts["flash_size_bytes"],
            "page_size_bytes": target_facts["page_size_bytes"],
            "page_count": target_facts["page_count"],
        }

    adapted_facts = {
        "profile_relationships": adapted_relationships,
        "targets": adapted_targets,
        "programming_contract": facts["programming_contract"],
        "option_contract": facts["option_contract"],
        "security_contract": facts["security_contract"],
    }

    adapted_evidence = {
        path: citations
        for path, citations in evidence.items()
        if ".package_hardware." not in path
    }
    if package_relationship != "unknown":
        adapted_evidence["$.semantic_facts.profile_relationships.package_hardware"] = relationship_citations

    return {"semantic_facts": adapted_facts, "evidence": adapted_evidence}, transformation


def canonicalize_response(payload: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    require(
        contract.get("semantic_schema_id") == "plasma://ic-support/stm32f103c/semantic-extraction-v2",
        "unexpected relationship semantic schema ID",
    )
    require(
        contract.get("canonical_schema_id") == "plasma://ic-support/stm32f103c/canonical-spec-v0",
        "unexpected canonical schema ID",
    )
    base_contract_name = contract.get("base_structured_canonicalization_contract")
    require(base_contract_name == "canonicalization-contract-v1.json", "unexpected structured base contract")
    base_contract = load_json(HERE / base_contract_name)

    adapted_payload, relationship_transformation = _adapt_for_structured_base(payload, contract)
    report = structured_base.canonicalize_response(adapted_payload, base_contract)
    report["canonicalization_id"] = contract["canonicalization_id"]
    report["input_sha256"] = common.canonical_sha256(payload)
    report["contract_sha256"] = common.canonical_sha256(contract)
    report["base_contract_sha256"] = common.canonical_sha256(base_contract)
    report["base_canonicalization_id"] = base_contract["canonicalization_id"]
    report["transformations"] = [relationship_transformation, *report["transformations"]]
    report["trust_boundary"] = {
        "generation_visibility_of_contract": False,
        "ai_emits_package_hardware_relationship": False,
        "package_hardware_relationship_is_deterministic": True,
        "relationship_free_form_semantic_matching": False,
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive package-hardware relationship and canonicalize evidence-backed semantic facts")
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
        print("IC relationship-derived semantic canonicalization COMPLETE")
        print(f"- status: {report['canonicalization_status']}")
        print(f"- package_hardware relationship: {report['canonical_spec']['profile_relationships']['package_hardware']}")
        print(f"- transformations: {len(report['transformations'])}")
        print(f"- unresolved paths: {len(report['unresolved_paths'])}")
        print("- package relationship emitted by AI: false")
        print("- canonical dataset admission: false")
        print("- production admission: false")
        return 0
    except (OSError, json.JSONDecodeError, CanonicalizationError, semantic.SemanticExtractionError, KeyError) as exc:
        print(f"IC relationship-derived semantic canonicalization FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
