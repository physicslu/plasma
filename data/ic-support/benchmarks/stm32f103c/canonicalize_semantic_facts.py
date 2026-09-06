#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "canonicalization-contract-v0.json"
CANONICALIZATION_REPORT_SCHEMA_VERSION = "0.1.0"


class CanonicalizationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CanonicalizationError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalize_hex_address(value: str) -> str:
    require(isinstance(value, str), "hex address must be a string")
    compact = re.sub(r"\s+", "", value)
    require(re.fullmatch(r"0[xX][0-9A-Fa-f]+", compact) is not None, f"invalid hexadecimal address: {value!r}")
    number = int(compact, 16)
    return f"0x{number:X}"


def _normalize_label(value: str) -> str:
    return " ".join(value.strip().lower().split())


def normalize_option_encoding(value: str, contract: dict[str, Any]) -> str:
    require(isinstance(value, str) and value.strip() != "", "option encoding label must be a non-empty string")
    vocabulary = contract.get("controlled_vocabulary", {}).get("option_encoding")
    require(isinstance(vocabulary, dict) and vocabulary, "option encoding vocabulary missing")
    aliases: dict[str, str] = {}
    for canonical, raw_aliases in vocabulary.items():
        require(isinstance(canonical, str) and canonical != "", "canonical option encoding label invalid")
        require(isinstance(raw_aliases, list) and raw_aliases, f"{canonical}: aliases required")
        for raw_alias in raw_aliases:
            require(isinstance(raw_alias, str), f"{canonical}: alias must be string")
            normalized = _normalize_label(raw_alias)
            previous = aliases.get(normalized)
            require(previous in (None, canonical), f"ambiguous option encoding alias: {raw_alias!r}")
            aliases[normalized] = canonical
    normalized_value = _normalize_label(value)
    canonical = aliases.get(normalized_value)
    require(canonical is not None, f"unrecognized option encoding semantics: {value!r}")
    return canonical


def _exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    require(set(value) == expected, f"{path}: keys mismatch; expected={sorted(expected)}, observed={sorted(value)}")


def _nullable_string(value: Any, path: str) -> None:
    require(value is None or isinstance(value, str), f"{path}: expected string or null")


def _positive_int_or_none(value: Any, path: str) -> None:
    require(
        value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 1),
        f"{path}: expected positive integer or null",
    )


def _bool_or_none(value: Any, path: str) -> None:
    require(value is None or isinstance(value, bool), f"{path}: expected boolean or null")


def validate_semantic_facts(facts: dict[str, Any], contract: dict[str, Any]) -> None:
    _exact_keys(
        facts,
        {"profile_relationships", "targets", "programming_contract", "option_contract", "security_contract"},
        "$.semantic_facts",
    )

    relationships = facts["profile_relationships"]
    require(isinstance(relationships, dict), "$.semantic_facts.profile_relationships: object required")
    relationship_keys = {"programming", "memory_geometry", "package_hardware", "option", "security"}
    _exact_keys(relationships, relationship_keys, "$.semantic_facts.profile_relationships")
    for key, value in relationships.items():
        require(value in {"shared", "different", "unknown"}, f"$.semantic_facts.profile_relationships.{key}: invalid relationship")

    targets = facts["targets"]
    require(isinstance(targets, dict), "$.semantic_facts.targets: object required")
    identity_context = contract.get("target_identity_context")
    require(isinstance(identity_context, dict) and identity_context, "target identity context missing")
    _exact_keys(targets, set(identity_context), "$.semantic_facts.targets")
    target_fields = {"manufacturer_device_reference", "flash_size_bytes", "page_size_bytes", "page_count"}
    for target, values in targets.items():
        require(isinstance(values, dict), f"$.semantic_facts.targets.{target}: object required")
        _exact_keys(values, target_fields, f"$.semantic_facts.targets.{target}")
        _nullable_string(values["manufacturer_device_reference"], f"$.semantic_facts.targets.{target}.manufacturer_device_reference")
        for field in ("flash_size_bytes", "page_size_bytes", "page_count"):
            _positive_int_or_none(values[field], f"$.semantic_facts.targets.{target}.{field}")

    programming = facts["programming_contract"]
    require(isinstance(programming, dict), "$.semantic_facts.programming_contract: object required")
    _exact_keys(programming, {"program_granularity_bytes", "unlock_keys", "write_erase_requires_hsi"}, "$.semantic_facts.programming_contract")
    _positive_int_or_none(programming["program_granularity_bytes"], "$.semantic_facts.programming_contract.program_granularity_bytes")
    unlock_keys = programming["unlock_keys"]
    require(unlock_keys is None or (isinstance(unlock_keys, list) and all(isinstance(item, str) for item in unlock_keys)), "$.semantic_facts.programming_contract.unlock_keys: expected string array or null")
    _bool_or_none(programming["write_erase_requires_hsi"], "$.semantic_facts.programming_contract.write_erase_requires_hsi")

    option = facts["option_contract"]
    require(isinstance(option, dict), "$.semantic_facts.option_contract: object required")
    _exact_keys(option, {"region_start_text", "region_size_bytes", "encoding_semantics"}, "$.semantic_facts.option_contract")
    _nullable_string(option["region_start_text"], "$.semantic_facts.option_contract.region_start_text")
    _positive_int_or_none(option["region_size_bytes"], "$.semantic_facts.option_contract.region_size_bytes")
    _nullable_string(option["encoding_semantics"], "$.semantic_facts.option_contract.encoding_semantics")

    security = facts["security_contract"]
    require(isinstance(security, dict), "$.semantic_facts.security_contract: object required")
    _exact_keys(security, {"read_unprotect_is_destructive", "write_protection_granularity_bytes"}, "$.semantic_facts.security_contract")
    _bool_or_none(security["read_unprotect_is_destructive"], "$.semantic_facts.security_contract.read_unprotect_is_destructive")
    _positive_int_or_none(security["write_protection_granularity_bytes"], "$.semantic_facts.security_contract.write_protection_granularity_bytes")


def _validate_citation(citation: Any, path: str) -> dict[str, Any]:
    require(isinstance(citation, dict), f"{path}: citation must be an object")
    source_id = citation.get("source_id")
    page_index = citation.get("physical_page_index")
    require(isinstance(source_id, str) and source_id != "", f"{path}: source_id required")
    require(isinstance(page_index, int) and not isinstance(page_index, bool) and page_index >= 0, f"{path}: non-negative physical_page_index required")
    return dict(citation)


def _citations_for(evidence: dict[str, Any], path: str, *, required: bool) -> list[dict[str, Any]]:
    value = evidence.get(path)
    if value is None:
        require(not required, f"{path}: evidence required for asserted semantic fact")
        return []
    require(isinstance(value, list) and value, f"{path}: evidence must be a non-empty array")
    return [_validate_citation(citation, f"{path}[{index}]") for index, citation in enumerate(value)]


def _authority_citation(identity_entry: dict[str, Any], target: str) -> dict[str, Any]:
    authority = identity_entry.get("authority")
    require(isinstance(authority, dict), f"{target}: deterministic identity authority required")
    return _validate_citation(authority, f"$.contract.target_identity_context.{target}.authority")


def _copy_asserted(
    *,
    source: dict[str, Any],
    source_key: str,
    source_path: str,
    evidence: dict[str, Any],
    canonical_evidence: dict[str, Any],
    canonical_path: str,
) -> Any:
    value = source[source_key]
    asserted = value is not None and value != "unknown"
    citations = _citations_for(evidence, source_path, required=asserted)
    if asserted:
        canonical_evidence[canonical_path] = citations
    return value


def canonicalize_response(payload: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(payload, {"semantic_facts", "evidence"}, "$")
    facts = payload["semantic_facts"]
    evidence = payload["evidence"]
    require(isinstance(facts, dict), "$.semantic_facts: object required")
    require(isinstance(evidence, dict), "$.evidence: object required")
    validate_semantic_facts(facts, contract)

    canonical_evidence: dict[str, Any] = {}
    transformations: list[dict[str, Any]] = []

    relationships: dict[str, Any] = {}
    for key in ("programming", "memory_geometry", "package_hardware", "option", "security"):
        relationships[key] = _copy_asserted(
            source=facts["profile_relationships"],
            source_key=key,
            source_path=f"$.semantic_facts.profile_relationships.{key}",
            evidence=evidence,
            canonical_evidence=canonical_evidence,
            canonical_path=f"$.canonical_spec.profile_relationships.{key}",
        )

    canonical_targets: dict[str, Any] = {}
    identity_context = contract["target_identity_context"]
    for target, target_facts in facts["targets"].items():
        identity_entry = identity_context[target]
        require(isinstance(identity_entry, dict), f"{target}: identity context entry must be object")
        commercial_part_base = identity_entry.get("commercial_part_base")
        require(isinstance(commercial_part_base, str) and commercial_part_base != "", f"{target}: commercial_part_base required")
        authority = _authority_citation(identity_entry, target)

        target_spec: dict[str, Any] = {
            "icpn": target,
            "manufacturer_device_reference": _copy_asserted(
                source=target_facts,
                source_key="manufacturer_device_reference",
                source_path=f"$.semantic_facts.targets.{target}.manufacturer_device_reference",
                evidence=evidence,
                canonical_evidence=canonical_evidence,
                canonical_path=f"$.canonical_spec.targets.{target}.manufacturer_device_reference",
            ),
            "commercial_part_base": commercial_part_base,
        }
        canonical_evidence[f"$.canonical_spec.targets.{target}.icpn"] = [authority]
        canonical_evidence[f"$.canonical_spec.targets.{target}.commercial_part_base"] = [authority]
        transformations.append(
            {
                "kind": "DETERMINISTIC_IDENTITY_CONTEXT",
                "path": f"$.canonical_spec.targets.{target}.commercial_part_base",
                "input": target,
                "output": commercial_part_base,
                "authority": authority,
            }
        )
        for field in ("flash_size_bytes", "page_size_bytes", "page_count"):
            target_spec[field] = _copy_asserted(
                source=target_facts,
                source_key=field,
                source_path=f"$.semantic_facts.targets.{target}.{field}",
                evidence=evidence,
                canonical_evidence=canonical_evidence,
                canonical_path=f"$.canonical_spec.targets.{target}.{field}",
            )
        canonical_targets[target] = target_spec

    programming: dict[str, Any] = {}
    for field in ("program_granularity_bytes", "unlock_keys", "write_erase_requires_hsi"):
        programming[field] = _copy_asserted(
            source=facts["programming_contract"],
            source_key=field,
            source_path=f"$.semantic_facts.programming_contract.{field}",
            evidence=evidence,
            canonical_evidence=canonical_evidence,
            canonical_path=f"$.canonical_spec.programming_contract.{field}",
        )

    raw_region = facts["option_contract"]["region_start_text"]
    if raw_region is None:
        canonical_region = None
    else:
        source_path = "$.semantic_facts.option_contract.region_start_text"
        citations = _citations_for(evidence, source_path, required=True)
        canonical_region = normalize_hex_address(raw_region)
        canonical_evidence["$.canonical_spec.option_contract.region_start"] = citations
        transformations.append(
            {
                "kind": "HEX_ADDRESS_NORMALIZATION",
                "path": "$.canonical_spec.option_contract.region_start",
                "source_path": source_path,
                "input": raw_region,
                "output": canonical_region,
            }
        )

    region_size = _copy_asserted(
        source=facts["option_contract"],
        source_key="region_size_bytes",
        source_path="$.semantic_facts.option_contract.region_size_bytes",
        evidence=evidence,
        canonical_evidence=canonical_evidence,
        canonical_path="$.canonical_spec.option_contract.region_size_bytes",
    )

    raw_encoding = facts["option_contract"]["encoding_semantics"]
    if raw_encoding is None:
        canonical_encoding = None
    else:
        source_path = "$.semantic_facts.option_contract.encoding_semantics"
        citations = _citations_for(evidence, source_path, required=True)
        canonical_encoding = normalize_option_encoding(raw_encoding, contract)
        canonical_evidence["$.canonical_spec.option_contract.encoding"] = citations
        transformations.append(
            {
                "kind": "CONTROLLED_VOCABULARY",
                "path": "$.canonical_spec.option_contract.encoding",
                "source_path": source_path,
                "input": raw_encoding,
                "output": canonical_encoding,
            }
        )

    security: dict[str, Any] = {}
    for field in ("read_unprotect_is_destructive", "write_protection_granularity_bytes"):
        security[field] = _copy_asserted(
            source=facts["security_contract"],
            source_key=field,
            source_path=f"$.semantic_facts.security_contract.{field}",
            evidence=evidence,
            canonical_evidence=canonical_evidence,
            canonical_path=f"$.canonical_spec.security_contract.{field}",
        )

    canonical_spec = {
        "profile_relationships": relationships,
        "targets": canonical_targets,
        "programming_contract": programming,
        "option_contract": {
            "region_start": canonical_region,
            "region_size_bytes": region_size,
            "encoding": canonical_encoding,
        },
        "security_contract": security,
    }

    unresolved = sorted(_unresolved_paths(canonical_spec, "$.canonical_spec"))
    return {
        "schema_version": CANONICALIZATION_REPORT_SCHEMA_VERSION,
        "canonicalization_id": contract["canonicalization_id"],
        "source_lock_id": contract["source_lock_id"],
        "input_sha256": canonical_sha256(payload),
        "contract_sha256": canonical_sha256(contract),
        "canonicalization_status": "complete" if not unresolved else "partial",
        "canonical_spec": canonical_spec,
        "evidence": canonical_evidence,
        "transformations": transformations,
        "unresolved_paths": unresolved,
        "trust_boundary": {
            "generation_visibility_of_contract": False,
            "canonical_dataset_admission": False,
            "production_admission": False,
        },
    }


def _unresolved_paths(value: Any, path: str) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for key, child in value.items():
            out.extend(_unresolved_paths(child, f"{path}.{key}"))
        return out
    if value is None or value == "unknown":
        return [path]
    return []


def legacy_benchmark_projection(canonical_spec: dict[str, Any]) -> dict[str, Any]:
    """Project the new canonical model into the existing v0 benchmark score shape.

    This bridge exists only to compare the foundation against retained v0 benchmark
    ground truth. New extraction should target semantic-extraction-v0 instead of
    reusing the ambiguous v0 `base_device` field.
    """
    targets = canonical_spec["targets"]
    return {
        "profile_relationships": canonical_spec["profile_relationships"],
        "parts": {
            target: {
                "base_device": target_spec["commercial_part_base"],
                "flash_size_bytes": target_spec["flash_size_bytes"],
                "page_size_bytes": target_spec["page_size_bytes"],
                "page_count": target_spec["page_count"],
            }
            for target, target_spec in targets.items()
        },
        "programming_contract": canonical_spec["programming_contract"],
        "option_contract": canonical_spec["option_contract"],
        "security_contract": canonical_spec["security_contract"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministically canonicalize evidence-backed IC semantic facts")
    parser.add_argument("--input", type=Path, required=True, help="JSON object containing semantic_facts + evidence")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = load_json(args.input)
        contract = load_json(args.contract)
        report = canonicalize_response(payload, contract)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("IC semantic canonicalization COMPLETE")
        print(f"- status: {report['canonicalization_status']}")
        print(f"- transformations: {len(report['transformations'])}")
        print(f"- unresolved paths: {len(report['unresolved_paths'])}")
        print("- canonical dataset admission: false")
        print("- production admission: false")
        return 0
    except (OSError, json.JSONDecodeError, CanonicalizationError, KeyError) as exc:
        print(f"IC semantic canonicalization FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
