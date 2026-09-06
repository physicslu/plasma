from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ab_benchmark as harness
import semantic_extraction_v2 as shared

HERE = Path(__file__).resolve().parent
SEMANTIC_SCHEMA = HERE / "semantic-extraction-v2.schema.json"
PROMPT_TEMPLATE = HERE / "semantic-extraction-prompt-v2.txt"
SEMANTIC_EXPERIMENT_ID = "stm32f103c-semantic-extraction-v2"
SEMANTIC_RUN_SCHEMA_VERSION = "0.3.0"

SemanticExtractionError = shared.SemanticExtractionError
require = shared.require
load_json = shared.load_json
flatten_leaves = shared.flatten_leaves
asserted_leaf_paths = shared.asserted_leaf_paths
allowed_pages_from_run_context = shared.allowed_pages_from_run_context
validate_evidence = shared.validate_evidence


def render_prompt(context: str) -> tuple[str, dict[str, Any]]:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    schema_text = SEMANTIC_SCHEMA.read_text(encoding="utf-8").strip()
    require(
        "{{SEMANTIC_EXTRACTION_SCHEMA}}" in template and "{{CONTEXT}}" in template,
        "semantic prompt template placeholders missing",
    )
    rendered = template.replace("{{SEMANTIC_EXTRACTION_SCHEMA}}", schema_text).replace("{{CONTEXT}}", context)
    return rendered, {
        "template_sha256": harness.sha256_text(template),
        "semantic_schema_sha256": harness.sha256_text(schema_text),
        "rendered_sha256": harness.sha256_text(rendered),
        "rendered_byte_length": len(rendered.encode("utf-8")),
    }


def validate_semantic_facts(facts: dict[str, Any]) -> None:
    schema = load_json(SEMANTIC_SCHEMA)
    errors = shared.validate_against_schema(
        facts,
        schema,
        root_schema=schema,
        path="$.semantic_facts",
    )
    require(not errors, "semantic schema validation failed: " + "; ".join(errors[:10]))


def parse_model_result(
    raw_text: str,
    *,
    allowed_pages: dict[str, set[int]] | None = None,
) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[len("```json") : -3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SemanticExtractionError(f"model response is not one JSON object: {exc}") from exc
    require(isinstance(payload, dict), "model response root must be object")
    require(set(payload) == {"semantic_facts", "evidence"}, "model response requires exactly semantic_facts + evidence")
    require(isinstance(payload["semantic_facts"], dict), "semantic_facts must be object")
    require(isinstance(payload["evidence"], dict), "evidence must be object")
    validate_semantic_facts(payload["semantic_facts"])
    validate_evidence(payload["semantic_facts"], payload["evidence"], allowed_pages=allowed_pages)
    return payload
