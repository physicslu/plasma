#!/usr/bin/env python3
"""Gate 5.5 bounded unit extraction and deterministic aggregation core.

The default execution profile remains the Gate 5.5 mock-only contract. This
module contains no provider client and no live CLI. A separately gated caller
may supply an explicit execution profile; request provenance then binds that
external execution contract without changing the Gate 5.5 base policy.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import build_evidence_pack as builder
import semantic_context
import semantic_extraction as semantic
import semantic_runner

HERE = Path(__file__).resolve().parent
POLICY_PATH = HERE / "bounded-extraction-contract.json"
HEX = set("0123456789abcdef")
PRIMARY_SCOPE_POLICY = {
    "fact_generation_authority": "PRIMARY_ONLY",
    "dependency_pages": "SUPPORTING_CONTEXT_ONLY",
    "every_fact_requires_primary_citation": True,
    "dependency_only_fact_forbidden": True,
    "primary_origin": "PRIMARY",
}


class BoundedExtractionError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BoundedExtractionError(message)


def policy() -> dict[str, Any]:
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    require(value["execution_mode"] == "mock_only", "Gate 5.5 base policy must remain mock_only")
    require(value["generation"] == {
        "num_ctx": 65536, "max_tokens": 8192, "temperature": 0.0,
        "seed": 0, "timeout_seconds": 1800.0,
    }, "bounded generation envelope drift")
    require(value["automatic_retries"] == 0, "automatic retries are forbidden")
    require(value["primary_unit_count"] == 8, "expected eight primary units")
    require(all(v is False for v in value["admission"].values()), "admissions must remain denied")
    return value


def _digest_without(value: dict[str, Any], key: str) -> str:
    return builder.canonical_sha256({k: v for k, v in value.items() if k != key})


def _execution_profile(value: dict[str, Any] | None) -> dict[str, Any]:
    rules = policy()
    if value is None:
        digest = builder.canonical_sha256(rules)
        return {
            "contract_id": rules["contract_id"],
            "contract_digest": digest,
            "execution_mode": "mock_only",
            "transport": "mock",
            "runtime_label": "gate55-model-free",
            "generation": copy.deepcopy(rules["generation"]),
            "automatic_retries": 0,
            "primary_unit_count": rules["primary_unit_count"],
        }

    require(isinstance(value, dict), "execution profile must be an object")
    profile = copy.deepcopy(value)
    for key in ("contract_id", "contract_digest", "execution_mode", "transport", "runtime_label"):
        require(isinstance(profile.get(key), str) and bool(profile[key].strip()), f"execution profile {key} required")
    digest = profile["contract_digest"].lower()
    require(len(digest) == 64 and all(c in HEX for c in digest), "execution contract digest malformed")
    profile["contract_digest"] = digest
    require(profile.get("generation") == rules["generation"], "execution generation must equal bounded base envelope")
    require(profile.get("automatic_retries") == 0, "execution profile retries are forbidden")
    require(profile.get("primary_unit_count") == rules["primary_unit_count"], "execution profile unit count mismatch")
    require(profile.get("execution_mode") != "mock_only", "external execution profile must not impersonate Gate 5.5 mock mode")
    semantic_scope = profile.get("semantic_scope")
    if semantic_scope is not None:
        require(semantic_scope == PRIMARY_SCOPE_POLICY, "unsupported primary-scoped semantic policy")
    return profile


def _primary_page_refs(pack: dict[str, Any]) -> set[tuple[str, int]]:
    primary_unit_id = pack.get("primary_unit_id")
    included = pack.get("included_units")
    require(isinstance(included, list), f"{pack.get('pack_id', '<pack>')}: included_units missing")
    primary_rows = [
        row for row in included
        if isinstance(row, dict) and row.get("origin") == PRIMARY_SCOPE_POLICY["primary_origin"]
    ]
    require(len(primary_rows) == 1, f"{pack.get('pack_id', '<pack>')}: expected exactly one PRIMARY unit row")
    row = primary_rows[0]
    require(row.get("unit_id") == primary_unit_id, f"{pack.get('pack_id', '<pack>')}: PRIMARY unit identity mismatch")
    source_id = row.get("source_id")
    page_range = row.get("pdf_page_range")
    require(isinstance(source_id, str) and bool(source_id), f"{primary_unit_id}: PRIMARY source missing")
    require(
        isinstance(page_range, list) and len(page_range) == 2
        and all(type(value) is int and value >= 1 for value in page_range)
        and page_range[0] <= page_range[1],
        f"{primary_unit_id}: PRIMARY page range malformed",
    )
    refs = {(source_id, page) for page in range(page_range[0], page_range[1] + 1)}
    allowed = semantic._allowed_page_refs(pack)
    require(refs <= allowed, f"{primary_unit_id}: PRIMARY page range is not fully admitted by the Evidence Pack")
    return refs


def _pair_schema(refs: list[tuple[str, int]]) -> dict[str, Any]:
    return {
        "anyOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_id", "pdf_page_number"],
                "properties": {
                    "source_id": {"type": "string", "enum": [source]},
                    "pdf_page_number": {"type": "integer", "enum": [page]},
                },
            }
            for source, page in refs
        ]
    }


def _apply_primary_scope_to_prompt(
    prompt: str, *, unit_id: str, pack: dict[str, Any], semantic_scope: dict[str, Any]
) -> str:
    require(semantic_scope == PRIMARY_SCOPE_POLICY, "primary-scoped prompt policy mismatch")
    primary_refs = sorted(_primary_page_refs(pack))
    rendered = ", ".join(f"{source}:p{page}" for source, page in primary_refs)
    scope_block = (
        "PRIMARY-SCOPED FACT GENERATION POLICY:\n"
        f"- The semantic subject is only PRIMARY_UNIT {unit_id}.\n"
        "- Generate facts only for claims whose semantic authority comes from PRIMARY pages.\n"
        "- Dependency pages are SUPPORTING CONTEXT ONLY. They may clarify or complete evidence for a primary-scoped fact, but must not create dependency-only facts.\n"
        "- EVERY emitted fact must cite at least one PRIMARY page from PRIMARY_ALLOWED_EVIDENCE below.\n"
        "- Dependency citations may be added only when needed to support a material clause of that same primary-scoped fact.\n"
        "- Do not pad a dependency-only claim with an irrelevant PRIMARY citation. If the PRIMARY evidence does not support a fact, omit it.\n"
        "- If no primary-scoped fact is supported, return UNKNOWN with facts=[].\n"
        f"PRIMARY_ALLOWED_EVIDENCE: [{rendered}]\n\n"
    )
    marker = "MANUFACTURER EVIDENCE CONTEXT FOLLOWS:\n"
    require(marker in prompt, "semantic prompt marker missing")
    return prompt.replace(marker, scope_block + marker, 1)


def _validate_primary_scoped_response(
    parsed: dict[str, Any], *, pack: dict[str, Any], semantic_scope: dict[str, Any] | None
) -> None:
    if semantic_scope is None:
        return
    require(semantic_scope == PRIMARY_SCOPE_POLICY, "primary-scoped response policy mismatch")
    primary_refs = _primary_page_refs(pack)
    unit_results = parsed.get("unit_results")
    require(isinstance(unit_results, list) and len(unit_results) == 1, "primary-scoped child must contain exactly one unit result")
    unit = unit_results[0]
    unit_id = unit.get("primary_unit_id")
    require(unit_id == pack.get("primary_unit_id"), "primary-scoped child unit identity mismatch")
    facts = unit.get("facts")
    require(isinstance(facts, list), f"{unit_id}: facts missing")
    for index, fact in enumerate(facts):
        evidence = fact.get("evidence") if isinstance(fact, dict) else None
        require(isinstance(evidence, list), f"{unit_id}.facts[{index}]: evidence missing")
        refs = {
            (ref.get("source_id"), ref.get("pdf_page_number"))
            for ref in evidence if isinstance(ref, dict)
        }
        require(
            bool(refs & primary_refs),
            f"{unit_id}.facts[{index}]: primary-scoped fact requires at least one PRIMARY citation",
        )


def prepare_requests(
    *, contract: dict[str, Any], pre_ai_manifest: dict[str, Any],
    packs: dict[str, dict[str, Any]], evidence_text: dict[str, str],
    model_id: str, model_digest: str,
    execution_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Validate the complete input, then render exactly one admitted pack per request."""
    rules = policy()
    execution = _execution_profile(execution_profile)
    semantic_scope = execution.get("semantic_scope")
    require(contract.get("contract_id") == rules["semantic_contract_id"], "semantic contract mismatch")
    require(contract.get("schema_version") == semantic.SEMANTIC_SCHEMA_VERSION, "semantic schema mismatch")
    require(contract.get("target") == pre_ai_manifest.get("target") == rules["target"], "target mismatch")
    require(isinstance(model_id, str) and bool(model_id.strip()), "model identity required")
    require(isinstance(model_digest, str) and len(model_digest) == 64
            and all(c in HEX for c in model_digest.lower()), "model digest required")
    model_digest = model_digest.lower()
    require(all(contract.get("admission", {}).get(k) is False for k in rules["admission"]),
            "semantic admissions must remain denied")
    builder.validate_pre_ai_manifest(
        pre_ai_manifest, bundle={"target": pre_ai_manifest.get("target"),
                                 "bundle_digest": pre_ai_manifest.get("bundle_digest")},
        packs=packs, evidence_text=evidence_text,
    )
    primary = semantic._pack_by_primary(packs)
    require(len(primary) == rules["primary_unit_count"], "expected exactly eight primary packs")
    for pack_id, pack in packs.items():
        require(pack.get("pack_id") == pack_id, "pack identity mismatch")
        require(pack.get("target") == rules["target"], "pack target mismatch")
        require(pack.get("pack_digest") == _digest_without(pack, "pack_digest"), "pack content digest mismatch")
    semantic_context.assemble_compact_model_context(pre_ai_manifest, packs=packs, evidence_text=evidence_text)

    code_fingerprints = {name: builder.sha256_file(HERE / name) for name in (
        "bounded_extraction.py", "semantic_extraction.py", "semantic_context.py",
        "semantic_runner.py", "build_evidence_pack.py",
    )}
    requests = []
    for unit_id, pack in sorted(primary.items()):
        pack_id = pack["pack_id"]
        one_pack = {pack_id: pack}
        schema = semantic.build_output_json_schema(contract, packs=one_pack)
        refs = sorted(semantic._allowed_page_refs(pack))
        evidence_schema = schema["properties"]["unit_results"]["items"]["properties"]["facts"]["items"]["properties"]["evidence"]
        evidence_schema["items"] = _pair_schema(refs)
        if semantic_scope is not None:
            primary_refs = sorted(_primary_page_refs(pack))
            evidence_schema["contains"] = _pair_schema(primary_refs)
        context = (
            "PLASMA PER-UNIT MANUFACTURER EVIDENCE CONTEXT\n"
            f"TARGET: {rules['target']}\nPRIMARY_UNIT: {unit_id}\n"
            f"PACK_DIGEST: {pack['pack_digest']}\n"
            + evidence_text[pack_id]
        )
        prompt, _ = semantic.render_prompt(context, contract=contract, packs=one_pack)
        if semantic_scope is not None:
            prompt = _apply_primary_scope_to_prompt(
                prompt, unit_id=unit_id, pack=pack, semantic_scope=semantic_scope
            )
        options = {**execution["generation"], "format_schema": schema}
        binding = {
            "target": rules["target"], "primary_unit_id": unit_id, "pack_id": pack_id,
            "pack_digest": pack["pack_digest"],
            "bundle_digest": pre_ai_manifest["bundle_digest"],
            "pre_ai_manifest_digest": pre_ai_manifest["manifest_digest"],
            "semantic_contract_digest": builder.canonical_sha256(contract),
            "bounded_contract_digest": builder.canonical_sha256(rules),
            "execution_contract_id": execution["contract_id"],
            "execution_contract_digest": execution["contract_digest"],
            "execution_mode": execution["execution_mode"],
            "model_id": model_id, "model_digest": model_digest,
            "code_fingerprints": code_fingerprints,
            "transport": execution["transport"], "runtime_label": execution["runtime_label"],
            "context_sha256": builder.sha256_text(context),
            "context_bytes": len(context.encode("utf-8")),
            "evidence_sha256": builder.sha256_text(evidence_text[pack_id]),
            "prompt_sha256": builder.sha256_text(prompt),
            "output_schema_sha256": builder.canonical_sha256(schema),
            "generation": copy.deepcopy(execution["generation"]),
        }
        if semantic_scope is not None:
            binding["semantic_scope"] = copy.deepcopy(semantic_scope)
            binding["semantic_scope_digest"] = builder.canonical_sha256(semantic_scope)
        binding["request_digest"] = builder.canonical_sha256(binding)
        requests.append({"binding": binding, "prompt": prompt, "options": options})
    return requests


def _validate_completion(metadata: Any, binding: dict[str, Any]) -> None:
    require(isinstance(metadata, dict), "provider metadata missing")
    require(metadata.get("response_model") == binding["model_id"], "provider model mismatch")
    require(metadata.get("done") is True, "provider completion missing")
    require(metadata.get("done_reason") == "stop", "provider did not stop normally")
    usage = metadata.get("usage")
    require(isinstance(usage, dict), "provider usage missing")
    input_tokens, output_tokens = usage.get("input_tokens"), usage.get("generation_tokens")
    require(type(input_tokens) is int and input_tokens > 0, "invalid input token count")
    require(type(output_tokens) is int and output_tokens > 0, "invalid generation token count")
    generation = binding["generation"]
    require(output_tokens <= generation["max_tokens"], "output budget exceeded")
    require(input_tokens + generation["max_tokens"] <= generation["num_ctx"],
            "input plus reserved output exceeds context budget")
    timing = metadata.get("timing")
    require(isinstance(timing, dict), "provider timing missing")


def _parse(raw_text: str, *, contract: dict[str, Any], packs: dict[str, Any]) -> dict[str, Any]:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise semantic.ModelOutputInvalidJSON("duplicate JSON object key")
            result[key] = value
        return result

    try:
        json.loads(raw_text, object_pairs_hook=unique_pairs)
    except (TypeError, json.JSONDecodeError) as exc:
        raise semantic.ModelOutputInvalidJSON("model output is not one valid JSON document") from exc
    return semantic.parse_model_result(raw_text, contract=contract, packs=packs)


def aggregate_results(
    children: list[dict[str, Any]], *, contract: dict[str, Any],
    pre_ai_manifest: dict[str, Any], packs: dict[str, dict[str, Any]],
    evidence_text: dict[str, str], model_id: str, model_digest: str,
    execution_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Revalidate retained children against independently regenerated requests.

    Reordering whole unit results is the only transformation. Facts, fact IDs,
    statements and evidence lists are never repaired, merged or deduplicated.
    """
    requests = prepare_requests(contract=contract, pre_ai_manifest=pre_ai_manifest,
                                packs=packs, evidence_text=evidence_text,
                                model_id=model_id, model_digest=model_digest,
                                execution_profile=execution_profile)
    expected = {r["binding"]["primary_unit_id"]: r["binding"] for r in requests}
    rules = policy()
    execution = _execution_profile(execution_profile)
    semantic_scope = execution.get("semantic_scope")
    result: dict[str, Any] = {
        "schema_version": "0.1.0", "artifact_type": "kl25_bounded_aggregate",
        "bounded_contract_id": rules["contract_id"],
        "execution_contract_id": execution["contract_id"],
        "execution_mode": execution["execution_mode"],
        "target": rules["target"], "bundle_digest": pre_ai_manifest["bundle_digest"],
        "pre_ai_manifest_digest": pre_ai_manifest["manifest_digest"],
        "status": "REJECTED_INTEGRITY", "errors": [],
        "admission": copy.deepcopy(rules["admission"]),
        "qualification_status": "NOT_QUALIFIED",
        "acceptance_blockers": copy.deepcopy(rules["known_acceptance_blockers"]),
        "review_required": True, "children": [],
    }
    if semantic_scope is not None:
        result["semantic_scope"] = copy.deepcopy(semantic_scope)
        result["semantic_scope_digest"] = builder.canonical_sha256(semantic_scope)
    errors, units, seen = result["errors"], [], set()
    for index, child in enumerate(children):
        try:
            require(isinstance(child, dict), f"child {index}: record must be an object")
            binding = child.get("binding")
            require(isinstance(binding, dict), f"child {index}: binding missing")
            unit_id = binding.get("primary_unit_id")
            require(isinstance(unit_id, str) and unit_id in expected, f"child {index}: unknown unit")
            require(unit_id not in seen, f"duplicate unit: {unit_id}")
            seen.add(unit_id)
            require(binding == expected[unit_id], f"{unit_id}: request provenance mismatch")
            require(child.get("artifact_type") == "kl25_bounded_unit_run"
                    and child.get("schema_version") == "0.1.0", f"{unit_id}: child schema mismatch")
            require(child.get("record_digest") == _digest_without(child, "record_digest"),
                    f"{unit_id}: record digest mismatch")
            result["children"].append({"primary_unit_id": unit_id,
                                       "record_digest": child["record_digest"]})
            require(child.get("status") == "success", f"{unit_id}: child failed")
            require(child.get("transport_invoked") is True, f"{unit_id}: transport not invoked")
            raw_text = child.get("raw_response")
            require(isinstance(raw_text, str), f"{unit_id}: raw response missing")
            require(child.get("raw_response_sha256") == builder.sha256_text(raw_text),
                    f"{unit_id}: raw response digest mismatch")
            _validate_completion(child.get("transport_metadata"), binding)
            pack_id = binding["pack_id"]
            parsed = _parse(raw_text, contract=contract, packs={pack_id: packs[pack_id]})
            _validate_primary_scoped_response(
                parsed, pack=packs[pack_id], semantic_scope=semantic_scope
            )
            require(parsed == child.get("response"), f"{unit_id}: raw and parsed response differ")
            units.extend(parsed["unit_results"])
        except (ValueError, KeyError, TypeError, semantic.SemanticExtractionError) as exc:
            errors.append(str(exc))
    if seen != set(expected):
        errors.append(f"missing units: {sorted(set(expected) - seen)}")
    if len(children) != len(expected):
        errors.append("child cardinality mismatch")
    if not errors:
        combined = {"schema_version": semantic.SEMANTIC_SCHEMA_VERSION, "target": rules["target"],
                    "unit_results": sorted(units, key=lambda u: u["primary_unit_id"])}
        try:
            parsed = semantic.parse_model_result(json.dumps(combined), contract=contract, packs=packs)
            result["response"] = parsed
            result["status"] = "INTEGRITY_PASS"
        except semantic.SemanticExtractionError as exc:
            errors.append(str(exc))
    result["children"].sort(key=lambda c: c["primary_unit_id"])
    result["errors"].sort()
    result["aggregate_digest"] = builder.canonical_sha256(result)
    return result


def _write_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def execute_bounded_run(
    *, contract: dict[str, Any], pre_ai_manifest: dict[str, Any],
    packs: dict[str, dict[str, Any]], evidence_text: dict[str, str],
    transport: semantic_runner.TransportCallable, model_id: str, model_digest: str,
    output_dir: Path, execution_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute exactly one injected call per unit and retain a new artifact tree.

    No built-in provider client, URL selection, retry, semantic repair, or live
    entry point exists here. The caller owns transport selection and must supply
    a separately governed execution profile for any non-mock execution.
    """
    inputs = copy.deepcopy({"contract": contract, "pre_ai_manifest": pre_ai_manifest,
                            "packs": packs, "evidence_text": evidence_text,
                            "model_id": model_id, "model_digest": model_digest,
                            "execution_profile": execution_profile})
    requests = prepare_requests(**inputs)
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "request-manifest.json",
                {"execution_contract_id": requests[0]["binding"]["execution_contract_id"],
                 "execution_mode": requests[0]["binding"]["execution_mode"],
                 "requests": [r["binding"] for r in requests]})
    children = []
    semantic_scope = _execution_profile(execution_profile).get("semantic_scope")
    for index, request in enumerate(requests):
        binding = copy.deepcopy(request["binding"])
        child: dict[str, Any] = {
            "schema_version": "0.1.0", "artifact_type": "kl25_bounded_unit_run",
            "binding": binding, "status": "error", "transport_invoked": False,
            "raw_response": "", "transport_metadata": {},
        }
        try:
            child["transport_invoked"] = True
            response = transport(prompt=request["prompt"], model_id=model_id,
                                 runtime_label=binding["runtime_label"],
                                 options=copy.deepcopy(request["options"]))
            require(isinstance(response, dict), "transport response must be an object")
            child["transport_metadata"] = copy.deepcopy({
                k: v for k, v in response.items()
                if k in {"response_model", "done", "done_reason", "usage", "timing"}
            })
            raw = response.get("raw_text")
            require(isinstance(raw, str), "raw response missing")
            child["raw_response"] = raw
            require(bool(raw.strip()), "raw response empty")
            pack_id = binding["pack_id"]
            parsed = _parse(raw, contract=inputs["contract"], packs={pack_id: inputs["packs"][pack_id]})
            _validate_primary_scoped_response(
                parsed, pack=inputs["packs"][pack_id], semantic_scope=semantic_scope
            )
            _validate_completion(child["transport_metadata"], binding)
            child["response"] = parsed
            child["status"] = "success"
        except Exception as exc:
            child["error"] = {"class": (semantic_runner._error_class(exc)
                                       if not isinstance(exc, BoundedExtractionError)
                                       else "bounded_integrity_error"),
                              "type": type(exc).__name__, "message": str(exc)}
        child["raw_response_sha256"] = builder.sha256_text(child["raw_response"])
        child["record_digest"] = builder.canonical_sha256(child)
        unit_dir = output_dir / f"unit-{index + 1:02d}"
        unit_dir.mkdir()
        with (unit_dir / "raw-response.txt").open("x", encoding="utf-8", newline="") as stream:
            stream.write(child["raw_response"])
        _write_json(unit_dir / "unit-run.json", child)
        children.append(child)
    aggregate = aggregate_results(children, **inputs)
    _write_json(output_dir / "aggregate-report.json", aggregate)
    return {"children": children, "aggregate": aggregate}
