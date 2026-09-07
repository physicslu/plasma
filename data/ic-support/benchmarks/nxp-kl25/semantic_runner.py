#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import build_evidence_pack as builder
import semantic_extraction as semantic

RUN_SCHEMA_VERSION = "0.1.0"


class SemanticTransportError(RuntimeError):
    pass


class SemanticTransportTimeout(SemanticTransportError):
    pass


class SemanticTransportUnavailable(SemanticTransportError):
    pass


class SemanticTransportProtocolError(SemanticTransportError):
    pass


TransportCallable = Callable[..., dict[str, Any]]


def _error_class(exc: BaseException) -> str:
    if isinstance(exc, (SemanticTransportTimeout, TimeoutError)):
        return "transport_timeout"
    if isinstance(exc, SemanticTransportUnavailable):
        return "transport_unavailable"
    if isinstance(exc, SemanticTransportProtocolError):
        return "transport_protocol_error"
    if isinstance(exc, semantic.ModelOutputInvalidJSON):
        return "model_output_invalid_json"
    if isinstance(exc, semantic.ModelOutputEvidenceError):
        return "model_output_evidence_error"
    if isinstance(exc, semantic.ModelOutputSchemaError):
        return "model_output_schema_error"
    if isinstance(exc, builder.KL25EvidencePackError):
        return "pre_ai_validation_error"
    if isinstance(exc, semantic.SemanticExtractionError):
        return "model_output_validation_error"
    return "runner_internal_error"


def _validate_transport_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise SemanticTransportProtocolError("transport response must be an object")
    raw_text = response.get("raw_text")
    if not isinstance(raw_text, str) or raw_text.strip() == "":
        raise SemanticTransportProtocolError("transport response requires non-empty raw_text")
    return response


def execute_semantic_run(
    *,
    contract: dict[str, Any],
    pre_ai_manifest: dict[str, Any],
    packs: dict[str, dict[str, Any]],
    evidence_text: dict[str, str],
    transport: TransportCallable,
    transport_label: str,
    model_id: str,
    runtime_label: str,
    request_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "artifact_type": "kl25_semantic_extraction_run",
        "target": pre_ai_manifest.get("target"),
        "bundle_digest": pre_ai_manifest.get("bundle_digest"),
        "pre_ai_manifest_digest": pre_ai_manifest.get("manifest_digest"),
        "semantic_contract_id": contract.get("contract_id"),
        "runtime": {
            "transport": transport_label,
            "runtime_label": runtime_label,
            "model_id": model_id,
        },
        "trust_boundary": {
            "manufacturer_evidence_only": True,
            "pre_ai_manifest_validation_required": True,
            "ai_may_change_applicability_binding": False,
            "canonical_ground_truth_visible": False,
            "production_profile_visible": False,
            "semantic_extraction_admission": False,
            "model_quality_admission": False,
            "canonical_dataset_admission": False,
            "hil_admission": False,
            "production_admission": False,
            "destructive_security_operation_admission": False,
        },
        "status": "pending",
    }

    raw_text = ""
    transport_invoked = False
    try:
        if contract.get("schema_version") != semantic.SEMANTIC_SCHEMA_VERSION:
            raise semantic.ModelOutputSchemaError("semantic contract schema mismatch")
        if contract.get("target") != pre_ai_manifest.get("target"):
            raise semantic.ModelOutputSchemaError("semantic contract target does not match pre-AI manifest")
        admission = contract.get("admission", {})
        if admission.get("semantic_extraction") is not False:
            raise semantic.ModelOutputSchemaError("Gate 4 runner contract must keep semantic extraction admission false")
        if admission.get("model_quality") is not False:
            raise semantic.ModelOutputSchemaError("Gate 4 runner contract must keep model quality admission false")

        builder.validate_pre_ai_manifest(
            pre_ai_manifest,
            bundle={
                "target": pre_ai_manifest.get("target"),
                "bundle_digest": pre_ai_manifest.get("bundle_digest"),
            },
            packs=packs,
            evidence_text=evidence_text,
        )
        manufacturer_context = builder.assemble_model_context(
            pre_ai_manifest,
            packs=packs,
            evidence_text=evidence_text,
        )
        prompt, prompt_meta = semantic.render_prompt(
            manufacturer_context,
            contract=contract,
            packs=packs,
        )
        record["prompt"] = {
            **prompt_meta,
            "sha256": builder.sha256_text(prompt),
            "byte_length": len(prompt.encode("utf-8")),
        }

        transport_invoked = True
        response = _validate_transport_response(
            transport(
                prompt=prompt,
                model_id=model_id,
                runtime_label=runtime_label,
                options=dict(request_options or {}),
            )
        )
        raw_text = response["raw_text"]
        parsed = semantic.parse_model_result(raw_text, contract=contract, packs=packs)
        record["status"] = "success"
        record["response"] = parsed
        record["transport_metadata"] = {
            key: value
            for key, value in response.items()
            if key in {"response_model", "done", "done_reason", "usage", "timing"}
        }
    except Exception as exc:  # fail closed; do not convert invalid model output into partial facts
        record["status"] = "error"
        record["error"] = {
            "class": _error_class(exc),
            "type": type(exc).__name__,
            "message": str(exc),
        }

    record["transport_invoked"] = transport_invoked
    record["raw_response_sha256"] = builder.sha256_text(raw_text)
    return record
