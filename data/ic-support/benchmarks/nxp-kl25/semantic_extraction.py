#!/usr/bin/env python3
from __future__ import annotations

import json
from typing import Any

SEMANTIC_SCHEMA_VERSION = "0.1.0"


class SemanticExtractionError(RuntimeError):
    pass


class ModelOutputInvalidJSON(SemanticExtractionError):
    pass


class ModelOutputSchemaError(SemanticExtractionError):
    pass


class ModelOutputEvidenceError(SemanticExtractionError):
    pass


def require(condition: bool, message: str, error_type: type[SemanticExtractionError] = ModelOutputSchemaError) -> None:
    if not condition:
        raise error_type(message)


def _exact_keys(value: dict[str, Any], expected: set[str], *, context: str) -> None:
    actual = set(value)
    require(actual == expected, f"{context}: keys must be exactly {sorted(expected)}; got {sorted(actual)}")


def _pack_by_primary(packs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for pack_id, pack in packs.items():
        primary_unit_id = pack.get("primary_unit_id")
        require(isinstance(primary_unit_id, str) and primary_unit_id != "", f"{pack_id}: missing primary_unit_id")
        require(primary_unit_id not in result, f"duplicate primary unit pack: {primary_unit_id}")
        result[primary_unit_id] = pack
    require(bool(result), "semantic extraction requires at least one primary Evidence Pack")
    return result


def _allowed_page_refs(pack: dict[str, Any]) -> set[tuple[str, int]]:
    refs: set[tuple[str, int]] = set()
    for index, ref in enumerate(pack.get("page_refs", [])):
        require(isinstance(ref, dict), f"page_refs[{index}] must be an object")
        source_id = ref.get("source_id")
        page = ref.get("pdf_page_number")
        require(isinstance(source_id, str) and source_id != "", f"page_refs[{index}]: invalid source_id")
        require(isinstance(page, int) and not isinstance(page, bool) and page >= 1, f"page_refs[{index}]: invalid page")
        refs.add((source_id, page))
    require(bool(refs), f"{pack.get('pack_id', '<pack>')}: no allowed page refs")
    return refs


def render_prompt(
    manufacturer_context: str,
    *,
    contract: dict[str, Any],
    packs: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    require(contract.get("schema_version") == SEMANTIC_SCHEMA_VERSION, "semantic contract schema mismatch")
    target = contract.get("target")
    require(isinstance(target, str) and target != "", "semantic contract target missing")
    require(isinstance(manufacturer_context, str) and manufacturer_context != "", "manufacturer context is empty")
    pack_by_primary = _pack_by_primary(packs)
    allowed_kinds = contract.get("output", {}).get("allowed_fact_kinds")
    require(isinstance(allowed_kinds, list) and all(isinstance(item, str) for item in allowed_kinds), "allowed fact kinds malformed")

    unit_lines: list[str] = []
    for primary_unit_id in sorted(pack_by_primary):
        pack = pack_by_primary[primary_unit_id]
        refs = sorted(_allowed_page_refs(pack))
        rendered_refs = ", ".join(f"{source_id}:p{page}" for source_id, page in refs)
        unit_lines.append(
            f"- {primary_unit_id} | pack={pack.get('pack_id')} | allowed_evidence=[{rendered_refs}]"
        )

    instructions = f"""PLASMA NXP KL25 MANUFACTURER-NEAR SEMANTIC EXTRACTION\n\nTARGET: {target}\n\nReturn exactly one JSON object. Do not use Markdown fences or prose outside JSON.\nThe JSON root must contain exactly: schema_version, target, unit_results.\nschema_version must be {SEMANTIC_SCHEMA_VERSION!r}; target must be {target!r}.\n\nFor every primary Evidence Unit below, return exactly one unit_results entry with exactly:\n  primary_unit_id, state, facts\nstate must be FACTS or UNKNOWN. If evidence is insufficient, use UNKNOWN with facts=[].\nNever guess, synthesize missing identity levels, or convert absence of evidence into a fact.\n\nEvery FACTS entry must contain at least one fact. Each fact must contain exactly:\n  fact_id, kind, statement, evidence\nkind must be one of: {', '.join(allowed_kinds)}.\nevidence must contain one or more exact source_id/pdf_page_number references allowed for that unit's pack.\nDo not emit commercial identity equivalence, applicability bindings, cross-target relationships, canonical relationships, production admission, or destructive-security admission.\nPreserve NXP-native concepts such as FTFA, FCCOB, FSTAT, SWD and MDM-AP when supported by manufacturer evidence.\n\nPRIMARY EVIDENCE UNITS AND ALLOWED CITATIONS:\n{chr(10).join(unit_lines)}\n\nMANUFACTURER EVIDENCE CONTEXT FOLLOWS:\n{manufacturer_context}"""
    prompt_meta = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "target": target,
        "primary_unit_count": len(pack_by_primary),
        "allowed_fact_kinds": list(allowed_kinds),
        "manufacturer_context_only": True,
        "canonical_ground_truth_visible": False,
        "production_profile_visible": False,
    }
    return instructions, prompt_meta


def parse_model_result(
    raw_text: str,
    *,
    contract: dict[str, Any],
    packs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    try:
        value = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ModelOutputInvalidJSON("model output is not one valid JSON document") from exc
    if not isinstance(value, dict):
        raise ModelOutputSchemaError("model output JSON root must be an object")

    _exact_keys(value, {"schema_version", "target", "unit_results"}, context="model output")
    require(value["schema_version"] == SEMANTIC_SCHEMA_VERSION, "model output schema_version mismatch")
    require(value["target"] == contract.get("target"), "model output target mismatch")
    unit_results = value["unit_results"]
    require(isinstance(unit_results, list), "unit_results must be an array")

    pack_by_primary = _pack_by_primary(packs)
    expected_units = set(pack_by_primary)
    allowed_states = set(contract.get("output", {}).get("allowed_states", []))
    allowed_kinds = set(contract.get("output", {}).get("allowed_fact_kinds", []))
    require(allowed_states == {"FACTS", "UNKNOWN"}, "semantic contract states malformed")
    require(bool(allowed_kinds), "semantic contract fact kinds missing")

    observed_units: set[str] = set()
    observed_fact_ids: set[str] = set()
    for unit_index, unit_result in enumerate(unit_results):
        require(isinstance(unit_result, dict), f"unit_results[{unit_index}] must be an object")
        _exact_keys(unit_result, {"primary_unit_id", "state", "facts"}, context=f"unit_results[{unit_index}]")
        primary_unit_id = unit_result["primary_unit_id"]
        require(isinstance(primary_unit_id, str), f"unit_results[{unit_index}]: primary_unit_id must be a string")
        require(primary_unit_id in expected_units, f"unsupported primary unit: {primary_unit_id}")
        require(primary_unit_id not in observed_units, f"duplicate primary unit result: {primary_unit_id}")
        observed_units.add(primary_unit_id)

        state = unit_result["state"]
        require(state in allowed_states, f"{primary_unit_id}: unsupported state {state!r}")
        facts = unit_result["facts"]
        require(isinstance(facts, list), f"{primary_unit_id}: facts must be an array")
        if state == "UNKNOWN":
            require(facts == [], f"{primary_unit_id}: UNKNOWN requires an empty facts array")
            continue
        require(bool(facts), f"{primary_unit_id}: FACTS requires at least one fact")

        allowed_refs = _allowed_page_refs(pack_by_primary[primary_unit_id])
        for fact_index, fact in enumerate(facts):
            context = f"{primary_unit_id}.facts[{fact_index}]"
            require(isinstance(fact, dict), f"{context} must be an object")
            _exact_keys(fact, {"fact_id", "kind", "statement", "evidence"}, context=context)
            fact_id = fact["fact_id"]
            require(isinstance(fact_id, str) and 1 <= len(fact_id) <= 128, f"{context}: invalid fact_id")
            require(fact_id not in observed_fact_ids, f"duplicate fact_id: {fact_id}")
            observed_fact_ids.add(fact_id)
            require(fact["kind"] in allowed_kinds, f"{context}: unsupported fact kind {fact['kind']!r}")
            statement = fact["statement"]
            require(isinstance(statement, str) and 1 <= len(statement.strip()) <= 4000, f"{context}: invalid statement")
            evidence = fact["evidence"]
            require(isinstance(evidence, list) and bool(evidence), f"{context}: evidence must be a non-empty array")
            observed_refs: set[tuple[str, int]] = set()
            for evidence_index, ref in enumerate(evidence):
                ref_context = f"{context}.evidence[{evidence_index}]"
                require(isinstance(ref, dict), f"{ref_context} must be an object")
                _exact_keys(ref, {"source_id", "pdf_page_number"}, context=ref_context)
                source_id = ref["source_id"]
                page = ref["pdf_page_number"]
                require(isinstance(source_id, str) and source_id != "", f"{ref_context}: invalid source_id")
                require(isinstance(page, int) and not isinstance(page, bool) and page >= 1, f"{ref_context}: invalid page")
                key = (source_id, page)
                require(key not in observed_refs, f"{ref_context}: duplicate evidence ref")
                observed_refs.add(key)
                require(
                    key in allowed_refs,
                    f"{context}: evidence {source_id}:p{page} is outside the primary Evidence Pack",
                    ModelOutputEvidenceError,
                )

    require(observed_units == expected_units, f"unit_results must cover exactly all primary units; missing={sorted(expected_units - observed_units)}")
    require(len(unit_results) == len(expected_units), "unit_results cardinality mismatch")
    return value
