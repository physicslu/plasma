#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import canonicalize_semantic_facts as common
import canonicalize_semantic_facts_v8 as base
import semantic_extraction_v9 as semantic

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "canonicalization-contract-v7.json"
TARGETS = ("STM32F103C8T6", "STM32F103CBT6")

CanonicalizationError = common.CanonicalizationError
require = common.require
load_json = common.load_json


def _project_identity(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    require(set(payload) == {"semantic_facts", "evidence"}, "payload requires semantic_facts + evidence")
    facts = payload["semantic_facts"]
    evidence = payload["evidence"]
    require(isinstance(facts, dict), "semantic_facts object required")
    require(isinstance(evidence, dict), "evidence object required")
    semantic.validate_semantic_facts(facts)
    semantic.validate_evidence(facts, evidence)

    targets = facts.get("targets")
    require(isinstance(targets, dict) and set(targets) == set(TARGETS), "semantic target set mismatch")
    projected_targets: dict[str, Any] = {}
    projected_evidence: dict[str, Any] = {}
    for path, citations in evidence.items():
        projected_evidence[path.replace(".manufacturer_applicability_expression", ".manufacturer_device_reference")] = citations

    mappings: list[dict[str, str]] = []
    for target in TARGETS:
        target_facts = targets[target]
        require(isinstance(target_facts, dict), f"{target}: target facts required")
        expression = target_facts.get("manufacturer_applicability_expression")
        projected = dict(target_facts)
        projected.pop("manufacturer_applicability_expression")
        projected["manufacturer_device_reference"] = expression
        projected_targets[target] = projected
        mappings.append({
            "target_icpn": target,
            "input_path": f"$.semantic_facts.targets.{target}.manufacturer_applicability_expression",
            "output_path": f"$.semantic_facts.targets.{target}.manufacturer_device_reference"
        })

    projected_facts = dict(facts)
    projected_facts["targets"] = projected_targets
    transformation = {
        "kind": "DETERMINISTIC_IDENTITY_ONTOLOGY_PROJECTION",
        "path": "$.canonical_spec.targets.*.manufacturer_device_reference",
        "commercial_target_identity_source": "semantic_facts.targets object key",
        "manufacturer_expression_source": "manufacturer_applicability_expression",
        "semantics": "exact_evidence_backed_manufacturer_expression",
        "fuzzy_matching": False,
        "mappings": mappings
    }
    return {"semantic_facts": projected_facts, "evidence": projected_evidence}, transformation


def canonicalize_response(payload: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    require(
        contract.get("semantic_schema_id") == "plasma://ic-support/stm32f103c/semantic-extraction-v7",
        "unexpected identity ontology semantic schema ID"
    )
    require(
        contract.get("canonical_schema_id") == "plasma://ic-support/stm32f103c/canonical-spec-v0",
        "unexpected canonical schema ID"
    )
    projection = contract.get("identity_projection")
    require(isinstance(projection, dict), "identity projection contract required")
    require(projection.get("commercial_target_identity_is_ai_extracted_leaf") is False, "commercial identity must not be AI leaf")
    require(projection.get("comparison_or_fuzzy_matching") is False, "identity projection must not use fuzzy matching")
    require(projection.get("manufacturer_applicability_input_field") == "manufacturer_applicability_expression", "identity input field mismatch")
    require(projection.get("canonical_output_field") == "manufacturer_device_reference", "identity output field mismatch")
    base_name = contract.get("base_identity_canonicalization_contract")
    require(base_name == "canonicalization-contract-v6.json", "unexpected identity base contract")
    base_contract = load_json(HERE / base_name)

    projected_payload, identity_transformation = _project_identity(payload)
    report = base.canonicalize_response(projected_payload, base_contract)
    report["canonicalization_id"] = contract["canonicalization_id"]
    report["input_sha256"] = common.canonical_sha256(payload)
    report["contract_sha256"] = common.canonical_sha256(contract)
    report["base_contract_sha256"] = common.canonical_sha256(base_contract)
    report["base_canonicalization_id"] = base_contract["canonicalization_id"]
    report["transformations"] = [identity_transformation, *report["transformations"]]
    report["trust_boundary"] = {
        **report.get("trust_boundary", {}),
        "identity_projection_is_deterministic": True,
        "commercial_target_identity_is_ai_extracted_leaf": False,
        "manufacturer_applicability_expression_is_ai_extracted": True,
        "identity_fuzzy_matching": False,
        "identity_substring_matching": False,
        "identity_regex_inference": False,
        "canonical_dataset_admission": False,
        "production_admission": False,
        "destructive_security_operation_admission": False
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Project v9 identity ontology and canonicalize STM32F103C semantic facts")
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
        print("IC v9 identity ontology canonicalization COMPLETE")
        print(f"- status: {report['canonicalization_status']}")
        print("- commercial target identity source: targets map key")
        print("- identity fuzzy matching: false")
        print("- canonical dataset / production admission: false")
        return 0
    except (OSError, json.JSONDecodeError, CanonicalizationError, semantic.SemanticExtractionError, KeyError) as exc:
        print(f"IC v9 identity ontology canonicalization FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
