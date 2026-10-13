#!/usr/bin/env python3
from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Mapping

_ALLOWED_SCOPE_KINDS = {
    "exact_icpn",
    "base_device",
    "family",
    "package",
    "flash_controller",
}
_ALLOWED_STATUSES = {"research_candidate", "frozen_manufacturer_only"}
_CATALOG_CONSTRAINTS = {"manufacturer", "family", "base_device", "package", "flash_size"}
_FACT_PATH = re.compile(r"^(device|programming)\.")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ManufacturerEnrichmentError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ManufacturerEnrichmentError(message)


def _require_exact_keys(value: Mapping[str, Any], *, allowed: set[str], required: set[str], label: str) -> None:
    keys = set(value)
    missing = required - keys
    extra = keys - allowed
    require(not missing, f"{label}: missing keys {sorted(missing)}")
    require(not extra, f"{label}: undeclared keys {sorted(extra)}")


def validate_scope_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    require(isinstance(payload, Mapping), "scope artifact must be an object")
    _require_exact_keys(
        payload,
        allowed={
            "schema_version",
            "scope_id",
            "status",
            "authority",
            "scope_kind",
            "applicability",
            "catalog_constraints",
            "source_locks",
            "facts",
        },
        required={
            "schema_version",
            "scope_id",
            "status",
            "authority",
            "scope_kind",
            "applicability",
            "catalog_constraints",
            "source_locks",
            "facts",
        },
        label="scope artifact",
    )
    require(payload["schema_version"] == "1.0.0", "scope artifact: unsupported schema_version")
    scope_id = payload["scope_id"]
    require(isinstance(scope_id, str) and scope_id, "scope artifact: scope_id is required")
    require(payload["status"] in _ALLOWED_STATUSES, f"{scope_id}: unsupported status")
    require(payload["authority"] == "manufacturer_official_only", f"{scope_id}: manufacturer-only authority is required")
    require(payload["scope_kind"] in _ALLOWED_SCOPE_KINDS, f"{scope_id}: unsupported scope_kind")

    applicability = payload["applicability"]
    require(isinstance(applicability, Mapping), f"{scope_id}: applicability must be an object")
    _require_exact_keys(
        applicability,
        allowed={"mode", "exact_icpns"},
        required={"mode", "exact_icpns"},
        label=f"{scope_id}.applicability",
    )
    require(applicability["mode"] == "explicit_exact_icpns", f"{scope_id}: implicit applicability is forbidden")
    exact_icpns = applicability["exact_icpns"]
    require(isinstance(exact_icpns, list) and exact_icpns, f"{scope_id}: explicit exact_icpns are required")
    require(all(isinstance(item, str) and item for item in exact_icpns), f"{scope_id}: invalid exact ICPN")
    require(len(exact_icpns) == len(set(exact_icpns)), f"{scope_id}: duplicate exact ICPN applicability")

    constraints = payload["catalog_constraints"]
    require(isinstance(constraints, Mapping), f"{scope_id}: catalog_constraints must be an object")
    require(set(constraints) <= _CATALOG_CONSTRAINTS, f"{scope_id}: unsupported catalog constraint")
    require(
        isinstance(constraints.get("manufacturer"), str) and constraints["manufacturer"],
        f"{scope_id}: manufacturer catalog constraint is required",
    )
    for key, value in constraints.items():
        require(isinstance(value, str) and value, f"{scope_id}: catalog constraint {key} must be non-empty")

    source_locks = payload["source_locks"]
    require(isinstance(source_locks, list) and source_locks, f"{scope_id}: source_locks must be non-empty")
    source_ids: set[str] = set()
    normalized_locks: list[dict[str, Any]] = []
    for index, item in enumerate(source_locks):
        require(isinstance(item, Mapping), f"{scope_id}: source_locks[{index}] must be an object")
        _require_exact_keys(
            item,
            allowed={"source_id", "revision", "sha256", "source_kind"},
            required={"source_id", "revision", "sha256", "source_kind"},
            label=f"{scope_id}.source_locks[{index}]",
        )
        source_id = item["source_id"]
        require(isinstance(source_id, str) and source_id, f"{scope_id}: source_id is required")
        require(source_id not in source_ids, f"{scope_id}: duplicate source lock {source_id}")
        source_ids.add(source_id)
        require(isinstance(item["revision"], str) and item["revision"], f"{scope_id}: source revision is required")
        require(isinstance(item["sha256"], str) and _SHA256.fullmatch(item["sha256"]) is not None, f"{scope_id}: invalid source sha256")
        require(
            item["source_kind"] == "manufacturer_official",
            f"{scope_id}: non-manufacturer source {source_id!r} cannot establish manufacturer facts",
        )
        normalized_locks.append(dict(item))

    facts = payload["facts"]
    require(isinstance(facts, list) and facts, f"{scope_id}: facts must be non-empty")
    fact_paths: set[str] = set()
    normalized_facts: list[dict[str, Any]] = []
    for index, fact in enumerate(facts):
        require(isinstance(fact, Mapping), f"{scope_id}: facts[{index}] must be an object")
        _require_exact_keys(
            fact,
            allowed={"path", "value", "evidence_source_ids"},
            required={"path", "value", "evidence_source_ids"},
            label=f"{scope_id}.facts[{index}]",
        )
        path = fact["path"]
        require(isinstance(path, str) and _FACT_PATH.match(path) is not None, f"{scope_id}: invalid fact path {path!r}")
        require(path not in fact_paths, f"{scope_id}: duplicate fact path {path}")
        fact_paths.add(path)
        evidence_ids = fact["evidence_source_ids"]
        require(isinstance(evidence_ids, list) and evidence_ids, f"{scope_id}: fact {path} requires evidence_source_ids")
        require(len(evidence_ids) == len(set(evidence_ids)), f"{scope_id}: duplicate evidence source for {path}")
        require(set(evidence_ids) <= source_ids, f"{scope_id}: fact {path} references an unlocked source")
        normalized_facts.append(copy.deepcopy(dict(fact)))

    return {
        "schema_version": payload["schema_version"],
        "scope_id": scope_id,
        "status": payload["status"],
        "authority": payload["authority"],
        "scope_kind": payload["scope_kind"],
        "applicability": {
            "mode": "explicit_exact_icpns",
            "exact_icpns": list(exact_icpns),
        },
        "catalog_constraints": dict(constraints),
        "source_locks": normalized_locks,
        "facts": normalized_facts,
    }


def compose_manufacturer_facts(
    target: Mapping[str, Any],
    artifacts: Iterable[Mapping[str, Any]],
    *,
    expected_source_locks: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    require(isinstance(target, Mapping), "target must be an object")
    required_target = {"icpn", "manufacturer", "family", "base_device", "package", "flash_size"}
    require(required_target <= set(target), f"target missing fields {sorted(required_target - set(target))}")
    for key in required_target:
        require(isinstance(target[key], str) and target[key], f"target.{key} must be non-empty")

    expected_source_locks = expected_source_locks or {}
    applied_scopes: list[str] = []
    merged: dict[str, Any] = {}
    merged_evidence: dict[str, list[str]] = {}

    for raw in artifacts:
        artifact = validate_scope_artifact(raw)
        if target["icpn"] not in artifact["applicability"]["exact_icpns"]:
            continue

        scope_id = artifact["scope_id"]
        for key, expected in artifact["catalog_constraints"].items():
            actual = target.get(key)
            require(
                actual == expected,
                f"{scope_id}: target catalog constraint mismatch for {key}: expected {expected!r}, got {actual!r}",
            )

        for lock in artifact["source_locks"]:
            expected = expected_source_locks.get(lock["source_id"])
            if expected is None:
                continue
            require(
                expected.get("revision") == lock["revision"],
                f"{scope_id}: source revision drift for {lock['source_id']}",
            )
            require(
                expected.get("sha256") == lock["sha256"],
                f"{scope_id}: source digest drift for {lock['source_id']}",
            )

        for fact in artifact["facts"]:
            path = fact["path"]
            value = copy.deepcopy(fact["value"])
            if path in merged:
                require(
                    merged[path] == value,
                    f"{scope_id}: conflicting manufacturer fact {path}",
                )
                merged_evidence[path] = sorted(set(merged_evidence[path]) | set(fact["evidence_source_ids"]))
            else:
                merged[path] = value
                merged_evidence[path] = sorted(fact["evidence_source_ids"])
        applied_scopes.append(scope_id)

    return {
        "icpn": target["icpn"],
        "authority": "manufacturer_official_only",
        "applied_scopes": applied_scopes,
        "facts": merged,
        "fact_evidence": merged_evidence,
    }
