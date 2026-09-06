#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import canonicalize_semantic_facts as base
import semantic_extraction_v3 as semantic

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "canonicalization-contract-v1.json"
STRUCTURED_FIELDS = (
    "logical_value_width_bits",
    "stored_pair_width_bits",
    "companion_value_present",
    "companion_relation",
)

CanonicalizationError = base.CanonicalizationError
require = base.require
load_json = base.load_json


def _is_unresolved(value: Any) -> bool:
    return value is None or value == "unknown"


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for citation in citations:
        source_id = citation.get("source_id")
        page_index = citation.get("physical_page_index")
        require(isinstance(source_id, str), "structured option citation source_id required")
        require(isinstance(page_index, int) and not isinstance(page_index, bool), "structured option citation page required")
        key = (source_id, page_index)
        if key not in seen:
            seen.add(key)
            out.append({"source_id": source_id, "physical_page_index": page_index})
    return out


def map_structured_option_encoding(
    facts: dict[str, Any],
    evidence: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[str | None, list[dict[str, Any]], dict[str, Any] | None]:
    structure = facts["option_contract"]["encoding_structure"]
    require(isinstance(structure, dict), "structured option encoding object required")
    require(set(structure) == set(STRUCTURED_FIELDS), "structured option encoding keys mismatch")

    if any(_is_unresolved(structure[field]) for field in STRUCTURED_FIELDS):
        return None, [], None

    mappings = contract.get("structured_option_encoding_mapping")
    require(isinstance(mappings, dict) and mappings, "structured option encoding mapping required")
    matches = [
        canonical
        for canonical, expected in mappings.items()
        if isinstance(canonical, str) and isinstance(expected, dict) and structure == expected
    ]
    require(
        len(matches) == 1,
        "structured option encoding does not match exactly one admitted canonical mapping",
    )
    canonical = matches[0]

    citations: list[dict[str, Any]] = []
    source_paths: list[str] = []
    for field in STRUCTURED_FIELDS:
        path = f"$.semantic_facts.option_contract.encoding_structure.{field}"
        source_paths.append(path)
        field_citations = evidence.get(path)
        require(isinstance(field_citations, list) and field_citations, f"{path}: evidence required")
        citations.extend(field_citations)

    return canonical, _dedupe_citations(citations), {
        "kind": "STRUCTURED_OPTION_ENCODING_MAPPING",
        "path": "$.canonical_spec.option_contract.encoding",
        "source_paths": source_paths,
        "input": structure,
        "output": canonical,
    }


def _adapt_for_base_canonicalizer(
    payload: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    require(set(payload) == {"semantic_facts", "evidence"}, "payload requires semantic_facts + evidence")
    facts = payload["semantic_facts"]
    evidence = payload["evidence"]
    require(isinstance(facts, dict), "semantic_facts object required")
    require(isinstance(evidence, dict), "evidence object required")
    semantic.validate_semantic_facts(facts)
    semantic.validate_evidence(facts, evidence)

    canonical_encoding, encoding_citations, transformation = map_structured_option_encoding(
        facts,
        evidence,
        contract,
    )

    adapted_facts = {
        "profile_relationships": facts["profile_relationships"],
        "targets": facts["targets"],
        "programming_contract": facts["programming_contract"],
        "option_contract": {
            "region_start_text": facts["option_contract"]["region_start_text"],
            "region_size_bytes": facts["option_contract"]["region_size_bytes"],
            "encoding_semantics": canonical_encoding,
        },
        "security_contract": facts["security_contract"],
    }

    adapted_evidence = {
        path: citations
        for path, citations in evidence.items()
        if not path.startswith("$.semantic_facts.option_contract.encoding_structure.")
    }
    if canonical_encoding is not None:
        adapted_evidence["$.semantic_facts.option_contract.encoding_semantics"] = encoding_citations

    return {"semantic_facts": adapted_facts, "evidence": adapted_evidence}, transformation


def canonicalize_response(payload: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    require(contract.get("semantic_schema_id") == "plasma://ic-support/stm32f103c/semantic-extraction-v1", "unexpected structured semantic schema ID")
    require(contract.get("canonical_schema_id") == "plasma://ic-support/stm32f103c/canonical-spec-v0", "unexpected canonical schema ID")
    base_contract_name = contract.get("base_canonicalization_contract")
    require(base_contract_name == "canonicalization-contract-v0.json", "unexpected base canonicalization contract")
    base_contract = load_json(HERE / base_contract_name)

    adapted_payload, structured_transformation = _adapt_for_base_canonicalizer(payload, contract)
    report = base.canonicalize_response(adapted_payload, base_contract)
    report["canonicalization_id"] = contract["canonicalization_id"]
    report["input_sha256"] = base.canonical_sha256(payload)
    report["contract_sha256"] = base.canonical_sha256(contract)
    report["base_contract_sha256"] = base.canonical_sha256(base_contract)
    report["base_canonicalization_id"] = base_contract["canonicalization_id"]
    if structured_transformation is not None:
        report["transformations"] = [structured_transformation, *report["transformations"]]
    report["trust_boundary"] = {
        "generation_visibility_of_contract": False,
        "free_form_semantic_matching": False,
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministically canonicalize structured evidence-backed IC semantic facts")
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
        print("IC structured semantic canonicalization COMPLETE")
        print(f"- status: {report['canonicalization_status']}")
        print(f"- transformations: {len(report['transformations'])}")
        print(f"- unresolved paths: {len(report['unresolved_paths'])}")
        print("- free-form semantic matching: false")
        print("- canonical dataset admission: false")
        print("- production admission: false")
        return 0
    except (OSError, json.JSONDecodeError, CanonicalizationError, semantic.SemanticExtractionError, KeyError) as exc:
        print(f"IC structured semantic canonicalization FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
