from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import ab_benchmark as harness

HERE = Path(__file__).resolve().parent
SEMANTIC_SCHEMA = HERE / "semantic-extraction.schema.json"
PROMPT_TEMPLATE = HERE / "semantic-extraction-prompt-v0.txt"
SEMANTIC_EXPERIMENT_ID = "stm32f103c-semantic-extraction-v0"
SEMANTIC_RUN_SCHEMA_VERSION = "0.1.0"


class SemanticExtractionError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticExtractionError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


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


def _type_matches(value: Any, type_name: str) -> bool:
    if type_name == "null":
        return value is None
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    return False


def _resolve_local_ref(root_schema: dict[str, Any], reference: str) -> dict[str, Any]:
    require(reference.startswith("#/"), f"unsupported schema ref: {reference}")
    current: Any = root_schema
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        require(isinstance(current, dict) and token in current, f"unresolved schema ref: {reference}")
        current = current[token]
    require(isinstance(current, dict), f"schema ref does not resolve to object: {reference}")
    return current


def validate_against_schema(
    value: Any,
    schema: dict[str, Any],
    *,
    root_schema: dict[str, Any],
    path: str = "$",
) -> list[str]:
    if isinstance(schema.get("$ref"), str):
        schema = _resolve_local_ref(root_schema, schema["$ref"])

    errors: list[str] = []
    schema_type = schema.get("type")
    allowed_types = schema_type if isinstance(schema_type, list) else [schema_type]
    allowed_types = [item for item in allowed_types if isinstance(item, str)]
    if allowed_types and not any(_type_matches(value, item) for item in allowed_types):
        return [f"{path}: type mismatch, allowed={allowed_types}"]

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value not in enum")
    if isinstance(value, int) and not isinstance(value, bool) and isinstance(schema.get("minimum"), int):
        if value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            errors.append(f"{path}: below minLength")
        if isinstance(schema.get("pattern"), str) and re.fullmatch(schema["pattern"], value) is None:
            errors.append(f"{path}: pattern mismatch")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: unexpected")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(
                    validate_against_schema(
                        child,
                        child_schema,
                        root_schema=root_schema,
                        path=f"{path}.{key}",
                    )
                )
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            errors.extend(
                validate_against_schema(
                    child,
                    schema["items"],
                    root_schema=root_schema,
                    path=f"{path}[{index}]",
                )
            )
    return errors


def flatten_leaves(value: Any, path: str) -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value):
            out.update(flatten_leaves(value[key], f"{path}.{key}"))
        return out
    return {path: value}


def asserted_leaf_paths(semantic_facts: dict[str, Any]) -> set[str]:
    leaves = flatten_leaves(semantic_facts, "$.semantic_facts")
    return {path for path, value in leaves.items() if value is not None and value != "unknown"}


def allowed_pages_from_run_context(context: dict[str, Any]) -> dict[str, set[int]]:
    ds_pages = context.get("datasheet_physical_pages")
    pm_pages = context.get("programming_manual_physical_pages")
    require(isinstance(ds_pages, list) and all(isinstance(v, int) for v in ds_pages), "datasheet pages invalid")
    require(isinstance(pm_pages, list) and all(isinstance(v, int) for v in pm_pages), "programming manual pages invalid")
    return {
        harness.DS_SOURCE_ID: set(ds_pages),
        harness.PM_SOURCE_ID: set(pm_pages),
    }


def validate_evidence(
    semantic_facts: dict[str, Any],
    evidence: dict[str, Any],
    *,
    allowed_pages: dict[str, set[int]] | None = None,
) -> None:
    expected_paths = asserted_leaf_paths(semantic_facts)
    require(set(evidence) == expected_paths, "evidence paths must exactly match asserted semantic leaves")
    for path in sorted(expected_paths):
        citations = evidence[path]
        require(isinstance(citations, list) and citations, f"{path}: non-empty evidence array required")
        for index, citation in enumerate(citations):
            require(isinstance(citation, dict), f"{path}[{index}]: citation object required")
            require(set(citation) == {"source_id", "physical_page_index"}, f"{path}[{index}]: citation keys mismatch")
            source_id = citation["source_id"]
            page_index = citation["physical_page_index"]
            require(isinstance(source_id, str) and source_id != "", f"{path}[{index}]: source_id required")
            require(
                isinstance(page_index, int) and not isinstance(page_index, bool) and page_index >= 0,
                f"{path}[{index}]: non-negative physical_page_index required",
            )
            if allowed_pages is not None:
                require(source_id in allowed_pages, f"{path}[{index}]: source outside supplied context")
                require(page_index in allowed_pages[source_id], f"{path}[{index}]: page outside supplied context")


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

    schema = load_json(SEMANTIC_SCHEMA)
    errors = validate_against_schema(
        payload["semantic_facts"],
        schema,
        root_schema=schema,
        path="$.semantic_facts",
    )
    require(not errors, "semantic schema validation failed: " + "; ".join(errors[:10]))
    validate_evidence(payload["semantic_facts"], payload["evidence"], allowed_pages=allowed_pages)
    return payload
