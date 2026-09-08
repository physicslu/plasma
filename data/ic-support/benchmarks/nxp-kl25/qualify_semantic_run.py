#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_evidence_pack as builder

HERE = Path(__file__).resolve().parent
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MODEL_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$", re.IGNORECASE)


class LiveModelQualificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveModelQualificationError(message)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveModelQualificationError(f"cannot read valid JSON: {path}") from exc
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def _without_digest(value: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in value.items() if k != key}


def _pack_by_primary(packs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for pack_id, pack in packs.items():
        primary = pack.get("primary_unit_id")
        require(isinstance(primary, str) and primary, f"{pack_id}: primary_unit_id missing")
        require(primary not in result, f"duplicate primary Evidence Unit: {primary}")
        result[primary] = pack
    require(bool(result), "qualification requires at least one Evidence Pack")
    return result


def _primary_refs(pack: dict[str, Any]) -> set[tuple[str, int]]:
    primary = pack.get("primary_unit_id")
    for unit in pack.get("included_units", []):
        if not isinstance(unit, dict) or unit.get("unit_id") != primary or unit.get("origin") != "PRIMARY":
            continue
        source_id = unit.get("source_id")
        page_range = unit.get("pdf_page_range")
        require(isinstance(source_id, str) and source_id, f"{primary}: primary source missing")
        require(
            isinstance(page_range, list)
            and len(page_range) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in page_range),
            f"{primary}: primary page range malformed",
        )
        start, end = page_range
        require(1 <= start <= end, f"{primary}: primary page range invalid")
        return {(source_id, page) for page in range(start, end + 1)}
    raise LiveModelQualificationError(f"{primary}: PRIMARY included unit not found")


def _contains_term(text: str, term: str) -> bool:
    """Deterministically match a concept without fuzzy semantics.

    Preserve exact bounded matching for compound terms such as ``MDM-AP`` and
    ``FLASH_CR``. A single alphanumeric concept may also match one component of
    a punctuation-delimited identifier, so ``FTFA_FSTAT`` satisfies both
    ``FTFA`` and ``FSTAT``. No stemming, embeddings, or semantic similarity are
    used here.
    """
    haystack = " ".join(text.casefold().split())
    needle = " ".join(term.casefold().split())
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9_-]+", needle):
        if re.search(rf"(?<![a-z0-9_-]){re.escape(needle)}(?![a-z0-9_-])", haystack) is not None:
            return True
    elif needle in haystack:
        return True
    if re.fullmatch(r"[a-z0-9]+", needle):
        return needle in re.findall(r"[a-z0-9]+", haystack)
    return False


def _unit_text(unit_result: dict[str, Any]) -> str:
    return "\n".join(
        fact["statement"]
        for fact in unit_result.get("facts", [])
        if isinstance(fact, dict) and isinstance(fact.get("statement"), str)
    )


def validate_reviewed_verdict(
    verdict: dict[str, Any],
    *,
    semantic_run_digest: str,
    target: str,
    expected_units: set[str],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if verdict.get("artifact_type") != "kl25_reviewed_semantic_verdict":
        errors.append("reviewed verdict artifact_type mismatch")
    if verdict.get("target") != target:
        errors.append("reviewed verdict target mismatch")
    if verdict.get("semantic_run_digest") != semantic_run_digest:
        errors.append("reviewed verdict semantic_run_digest mismatch")
    if verdict.get("review_basis") != "manufacturer_evidence":
        errors.append("review_basis must be manufacturer_evidence")
    items = verdict.get("unit_verdicts")
    if not isinstance(items, list):
        return False, errors + ["unit_verdicts must be an array"]
    observed: set[str] = set()
    all_pass = True
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"unit_verdicts[{index}] must be an object")
            all_pass = False
            continue
        unit_id = item.get("primary_unit_id")
        if unit_id not in expected_units or unit_id in observed:
            errors.append(f"unsupported or duplicate reviewed unit: {unit_id}")
            all_pass = False
            continue
        observed.add(unit_id)
        state = item.get("verdict")
        if state not in {"PASS", "FAIL"}:
            errors.append(f"{unit_id}: reviewed verdict must be PASS or FAIL")
            all_pass = False
        elif state != "PASS":
            all_pass = False
        if not isinstance(item.get("rationale"), str) or not item["rationale"].strip():
            errors.append(f"{unit_id}: non-empty review rationale required")
    if observed != expected_units:
        errors.append(f"reviewed verdict must cover all primary units; missing={sorted(expected_units - observed)}")
        all_pass = False
    expected_overall = "PASS" if all_pass and not errors else "FAIL"
    if verdict.get("overall_verdict") != expected_overall:
        errors.append(f"overall_verdict must be {expected_overall}")
    return not errors and expected_overall == "PASS", errors


def assess_live_run(
    *,
    contract: dict[str, Any],
    semantic_run: dict[str, Any],
    raw_response: str,
    provenance: dict[str, Any],
    packs: dict[str, dict[str, Any]],
    reviewed_verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    integrity_errors: list[str] = []
    screening_errors: list[str] = []
    semantic_run_digest = builder.canonical_sha256(semantic_run)

    def check(condition: bool, message: str) -> None:
        if not condition:
            integrity_errors.append(message)

    required = contract.get("required_input", {})
    live_runtime = contract.get("live_runtime", {})
    generation = live_runtime.get("generation", {})
    context_protocol = live_runtime.get("context_protocol", {})

    check(contract.get("artifact_type") == "kl25_live_model_qualification_contract", "qualification contract artifact mismatch")
    check(semantic_run.get("artifact_type") == "kl25_semantic_extraction_run", "semantic run artifact mismatch")
    check(semantic_run.get("status") == "success", "semantic run status must be success")
    check(semantic_run.get("target") == contract.get("target"), "semantic run target mismatch")
    check(semantic_run.get("bundle_digest") == required.get("bundle_digest"), "bundle digest mismatch")
    check(semantic_run.get("pre_ai_manifest_digest") == required.get("pre_ai_manifest_digest"), "pre-AI manifest digest mismatch")
    check(semantic_run.get("semantic_contract_id") == required.get("semantic_contract_id"), "semantic contract id mismatch")

    runtime = semantic_run.get("runtime", {})
    check(runtime.get("transport") == live_runtime.get("transport"), "transport mismatch")
    check(runtime.get("model_id") == live_runtime.get("model_id"), "model id mismatch")
    check(runtime.get("runtime_label") == live_runtime.get("runtime_label"), "runtime label mismatch")
    check(semantic_run.get("transport_invoked") is True, "transport must be invoked")

    prompt_sha = semantic_run.get("prompt", {}).get("sha256")
    check(isinstance(prompt_sha, str) and HEX64.fullmatch(prompt_sha) is not None, "prompt digest missing")
    check(semantic_run.get("raw_response_sha256") == builder.sha256_text(raw_response), "raw response digest mismatch")

    run_context = semantic_run.get("context") if isinstance(semantic_run.get("context"), dict) else {}
    check(run_context.get("strategy") == context_protocol.get("strategy"), "semantic context strategy mismatch")
    check(run_context.get("gate3_artifacts_mutated") is False, "semantic context must not mutate Gate-3 artifacts")
    context_sha = run_context.get("context_sha256")
    check(isinstance(context_sha, str) and HEX64.fullmatch(context_sha) is not None, "semantic context digest missing")
    context_bytes = run_context.get("context_bytes")
    legacy_context_bytes = run_context.get("legacy_context_bytes")
    page_occurrences = run_context.get("page_occurrences")
    unique_pages = run_context.get("unique_physical_pages")
    duplicates_removed = run_context.get("duplicate_occurrences_removed")
    check(isinstance(context_bytes, int) and context_bytes > 0, "semantic context byte length missing")
    check(isinstance(legacy_context_bytes, int) and legacy_context_bytes > 0, "legacy context byte length missing")
    check(isinstance(page_occurrences, int) and page_occurrences > 0, "context page occurrence count missing")
    check(isinstance(unique_pages, int) and unique_pages > 0, "context unique physical page count missing")
    check(isinstance(duplicates_removed, int) and duplicates_removed >= 0, "context duplicate removal count missing")
    if all(isinstance(value, int) for value in (page_occurrences, unique_pages, duplicates_removed)):
        check(page_occurrences == unique_pages + duplicates_removed, "context duplicate accounting mismatch")
    if isinstance(context_bytes, int) and isinstance(legacy_context_bytes, int):
        check(context_bytes < legacy_context_bytes, "compact context must be smaller than legacy context")
    if context_protocol.get("require_cross_pack_duplicate_removal") is True:
        check(isinstance(duplicates_removed, int) and duplicates_removed > 0, "qualification requires cross-pack duplicate removal")
    check(run_context.get("dedup_identity") == context_protocol.get("dedup_identity"), "context dedup identity mismatch")

    metadata = semantic_run.get("transport_metadata", {})
    check(metadata.get("response_model") == live_runtime.get("model_id"), "provider response model mismatch")
    check(metadata.get("done") is True, "provider done must be true")
    done_reason = metadata.get("done_reason")
    if done_reason is not None:
        check(done_reason in live_runtime.get("allowed_done_reasons", []), "provider done_reason not allowed")
    usage = metadata.get("usage", {})
    for name in ("input_tokens", "generation_tokens"):
        value = usage.get(name)
        check(isinstance(value, int) and not isinstance(value, bool) and value > 0, f"{name} must be a positive integer")

    input_tokens = usage.get("input_tokens")
    generation_tokens = usage.get("generation_tokens")
    num_ctx = generation.get("num_ctx")
    if context_protocol.get("require_input_tokens_below_num_ctx") is True:
        check(
            isinstance(input_tokens, int) and isinstance(num_ctx, int) and input_tokens < num_ctx,
            "provider input_tokens must be below requested num_ctx",
        )
    if context_protocol.get("require_total_tokens_within_num_ctx") is True:
        check(
            isinstance(input_tokens, int)
            and isinstance(generation_tokens, int)
            and isinstance(num_ctx, int)
            and input_tokens + generation_tokens <= num_ctx,
            "provider input_tokens + generation_tokens must fit requested num_ctx",
        )

    check(provenance.get("artifact_type") == "kl25_live_model_run_provenance", "provenance artifact mismatch")
    check(provenance.get("target") == contract.get("target"), "provenance target mismatch")
    check(provenance.get("semantic_run_digest") == semantic_run_digest, "provenance semantic run digest mismatch")
    check(provenance.get("raw_response_sha256") == semantic_run.get("raw_response_sha256"), "provenance raw response digest mismatch")
    check(
        provenance.get("provenance_digest") == builder.canonical_sha256(_without_digest(provenance, "provenance_digest")),
        "provenance self-digest mismatch",
    )

    identity = provenance.get("ollama_runtime_identity", {})
    model_digest = identity.get("model_digest")
    check(isinstance(model_digest, str) and MODEL_DIGEST.fullmatch(model_digest) is not None, "Ollama model digest missing or malformed")
    check(identity.get("model_id") == live_runtime.get("model_id"), "Ollama identity model id mismatch")
    check(identity.get("ollama_url_policy") == "loopback_only", "Ollama identity endpoint policy mismatch")
    check(isinstance(identity.get("ollama_version"), str) and bool(identity.get("ollama_version", "").strip()), "Ollama version missing")

    execution = provenance.get("execution", {})
    check(execution.get("transport") == live_runtime.get("transport"), "provenance transport mismatch")
    check(execution.get("model_id") == live_runtime.get("model_id"), "provenance model id mismatch")
    check(execution.get("runtime_label") == live_runtime.get("runtime_label"), "provenance runtime label mismatch")
    check(execution.get("ollama_endpoint_policy") == "loopback_only", "provenance endpoint policy mismatch")
    for name, expected in generation.items():
        check(execution.get("generation", {}).get(name) == expected, f"generation setting mismatch: {name}")

    execution_context = execution.get("context") if isinstance(execution.get("context"), dict) else {}
    check(execution_context.get("strategy") == context_protocol.get("strategy"), "provenance context strategy mismatch")
    check(execution_context.get("gate3_evidence_artifacts_immutable") is True, "provenance must bind immutable Gate-3 context source")
    check(execution_context.get("dedup_identity") == context_protocol.get("dedup_identity"), "provenance context dedup identity mismatch")
    for name in (
        "context_sha256",
        "context_bytes",
        "legacy_context_bytes",
        "page_occurrences",
        "unique_physical_pages",
        "duplicate_occurrences_removed",
        "context_byte_reduction_pct",
    ):
        check(execution_context.get(name) == run_context.get(name), f"provenance semantic context mismatch: {name}")

    fingerprints = provenance.get("code_fingerprints")
    check(isinstance(fingerprints, dict) and bool(fingerprints), "code fingerprints missing")
    if isinstance(fingerprints, dict):
        check(all(isinstance(value, str) and HEX64.fullmatch(value) is not None for value in fingerprints.values()), "code fingerprint malformed")

    pack_by_primary = _pack_by_primary(packs)
    expected_units = set(pack_by_primary)
    response = semantic_run.get("response")
    unit_results = response.get("unit_results") if isinstance(response, dict) else None
    if not isinstance(unit_results, list):
        unit_results = []
        screening_errors.append("semantic response unit_results missing")
    result_by_primary = {
        item["primary_unit_id"]: item
        for item in unit_results
        if isinstance(item, dict) and isinstance(item.get("primary_unit_id"), str)
    }
    if set(result_by_primary) != expected_units:
        screening_errors.append(f"semantic response must cover all primary units; missing={sorted(expected_units - set(result_by_primary))}")

    screening = contract.get("semantic_screening", {})
    minimum_facts = int(screening.get("minimum_facts_per_unit", 1))
    for unit_id in sorted(expected_units):
        result = result_by_primary.get(unit_id)
        if result is None:
            continue
        if screening.get("require_facts_state_for_all_units") is True and result.get("state") != "FACTS":
            screening_errors.append(f"{unit_id}: state must be FACTS")
            continue
        facts = result.get("facts")
        if not isinstance(facts, list) or len(facts) < minimum_facts:
            screening_errors.append(f"{unit_id}: insufficient fact count")
            continue
        text = _unit_text(result)
        for forbidden in screening.get("forbidden_terms", []):
            if _contains_term(text, forbidden):
                screening_errors.append(f"{unit_id}: forbidden cross-vendor term present: {forbidden}")
        for group in screening.get("required_term_groups", {}).get(unit_id, []):
            if not isinstance(group, list) or not group or not any(_contains_term(text, term) for term in group):
                screening_errors.append(f"{unit_id}: missing required concept group: {group}")
        if screening.get("require_primary_unit_page_citation") is True:
            primary_refs = _primary_refs(pack_by_primary[unit_id])
            has_primary_ref = any(
                (ref.get("source_id"), ref.get("pdf_page_number")) in primary_refs
                for fact in facts if isinstance(fact, dict)
                for ref in fact.get("evidence", []) if isinstance(ref, dict)
            )
            if not has_primary_ref:
                screening_errors.append(f"{unit_id}: no citation to primary Evidence Unit pages")

    # A live success must preserve one content truth: parsed semantic response == raw model JSON.
    # Keep this as an integrity check when the semantic screening itself otherwise passes.
    if not screening_errors:
        try:
            parsed_raw = json.loads(raw_response)
        except json.JSONDecodeError:
            integrity_errors.append("raw response cannot be reparsed as JSON")
        else:
            check(parsed_raw == semantic_run.get("response"), "raw response and parsed semantic response differ")

    review_pass = False
    review_errors: list[str] = []
    if reviewed_verdict is not None:
        review_pass, review_errors = validate_reviewed_verdict(
            reviewed_verdict,
            semantic_run_digest=semantic_run_digest,
            target=contract.get("target"),
            expected_units=expected_units,
        )

    if integrity_errors:
        status = "REJECTED_INTEGRITY"
    elif screening_errors:
        status = "REJECTED_SCREENING"
    elif reviewed_verdict is None:
        status = "READY_FOR_REVIEW"
    elif review_pass:
        status = "QUALIFIED"
    else:
        status = "REJECTED_REVIEW"

    report: dict[str, Any] = {
        "schema_version": "0.2.0",
        "artifact_type": "kl25_live_model_qualification_report",
        "qualification_contract_id": contract.get("contract_id"),
        "target": contract.get("target"),
        "semantic_run_digest": semantic_run_digest,
        "model_id": live_runtime.get("model_id"),
        "model_digest": identity.get("model_digest"),
        "status": status,
        "integrity": {"status": "PASS" if not integrity_errors else "FAIL", "errors": integrity_errors},
        "semantic_screening": {
            "status": "PASS" if not screening_errors else "FAIL",
            "errors": screening_errors,
            "note": "Concept screening is a deterministic defect filter, not proof of semantic correctness.",
        },
        "review": {
            "required": True,
            "status": "PASS" if reviewed_verdict is not None and review_pass else "FAIL" if reviewed_verdict is not None else "PENDING",
            "errors": review_errors,
            "basis_required": "manufacturer_evidence",
        },
        "trust_boundary": {
            "live_run_integrity_is_not_semantic_correctness": True,
            "screening_pass_is_not_semantic_correctness": True,
            "reviewed_verdict_required_for_qualification": True,
            "semantic_extraction_admission": False,
            "model_quality_admission": False,
            "canonical_dataset_admission": False,
            "hil_admission": False,
            "production_admission": False,
            "destructive_security_operation_admission": False,
        },
    }
    report["report_digest"] = builder.canonical_sha256(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess an NXP KL25 live-model semantic run")
    parser.add_argument("--semantic-run", type=Path, required=True)
    parser.add_argument("--raw-response", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--packs-dir", type=Path, required=True)
    parser.add_argument("--reviewed-verdict", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=HERE / "live-model-qualification-contract.json")
    args = parser.parse_args()
    try:
        contract = read_json(args.contract)
        semantic_run = read_json(args.semantic_run)
        provenance = read_json(args.provenance)
        reviewed_verdict = read_json(args.reviewed_verdict) if args.reviewed_verdict else None
        raw_response = args.raw_response.read_text(encoding="utf-8")
        packs = {path.stem: read_json(path) for path in sorted(args.packs_dir.glob("*.json"))}
        require(bool(packs), "no Evidence Pack JSON files found")
        report = assess_live_run(
            contract=contract,
            semantic_run=semantic_run,
            raw_response=raw_response,
            provenance=provenance,
            packs=packs,
            reviewed_verdict=reviewed_verdict,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"KL25 live-model qualification: {report['status']}")
        return 0 if report["status"] in {"READY_FOR_REVIEW", "QUALIFIED"} else 1
    except (LiveModelQualificationError, OSError, ValueError) as exc:
        print(f"KL25 live-model qualification FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
