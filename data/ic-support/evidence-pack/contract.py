from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any, Iterable

SCHEMA_VERSION = "0.1.0"
AUTHORITATIVE_DEPENDENCIES = {"DOCUMENT_EXPLICIT", "DETERMINISTIC_RULE"}


class EvidenceContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceContractError(message)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _without_identity(payload: dict[str, Any], *fields: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in set(fields)}


def catalog_digest(catalog: dict[str, Any]) -> str:
    return canonical_sha256(_without_identity(catalog, "catalog_id", "catalog_digest"))


def pack_digest(pack: dict[str, Any]) -> str:
    return canonical_sha256(_without_identity(pack, "pack_id", "pack_digest"))


def bundle_digest(bundle: dict[str, Any]) -> str:
    return canonical_sha256(_without_identity(bundle, "bundle_id", "bundle_digest"))


def locked_source_fingerprints(source_lock: dict[str, Any]) -> dict[str, dict[str, str]]:
    source_lock_id = source_lock.get("source_lock_id")
    require(isinstance(source_lock_id, str) and source_lock_id, "source lock requires source_lock_id")
    sources = source_lock.get("sources")
    require(isinstance(sources, list) and sources, "source lock requires sources")

    fingerprints: dict[str, dict[str, str]] = {}
    for source in sources:
        require(isinstance(source, dict), "source-lock source entry must be object")
        source_id = source.get("source_id")
        integrity = source.get("integrity")
        require(isinstance(source_id, str) and source_id, "source-lock source_id required")
        require(source_id not in fingerprints, f"duplicate source-lock source_id: {source_id}")
        require(isinstance(integrity, dict), f"{source_id}: source-lock integrity required")
        algorithm = integrity.get("algorithm")
        digest = integrity.get("digest")
        require(isinstance(algorithm, str) and algorithm, f"{source_id}: source-lock algorithm required")
        require(isinstance(digest, str) and digest, f"{source_id}: source-lock digest required")
        fingerprints[source_id] = {"algorithm": algorithm, "digest": digest}
    return fingerprints


def validate_catalog(
    catalog: dict[str, Any],
    taxonomy: dict[str, Any],
    source_lock: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    require(catalog.get("artifact_type") == "evidence_unit_catalog", "catalog artifact_type mismatch")
    require(catalog.get("schema_version") == SCHEMA_VERSION, "catalog schema_version mismatch")
    require(catalog.get("source_lock_id") == source_lock.get("source_lock_id"), "catalog/source-lock ID mismatch")
    require(catalog.get("catalog_digest") == catalog_digest(catalog), "catalog digest mismatch")

    source = catalog.get("source")
    require(isinstance(source, dict), "catalog source object required")
    source_id = source.get("source_id")
    require(isinstance(source_id, str) and source_id, "catalog source_id required")
    locked = locked_source_fingerprints(source_lock)
    require(source_id in locked, f"{source_id}: source not present in source lock")
    require(
        {"algorithm": source.get("algorithm"), "digest": source.get("digest")} == locked[source_id],
        f"{source_id}: catalog source fingerprint does not match source lock",
    )

    categories = set(taxonomy.get("categories", []))
    require(categories, "taxonomy categories required")

    units = catalog.get("units")
    require(isinstance(units, list) and units, "catalog units must be non-empty")
    by_id: dict[str, dict[str, Any]] = {}
    for unit in units:
        require(isinstance(unit, dict), "catalog unit must be an object")
        unit_id = unit.get("unit_id")
        require(isinstance(unit_id, str) and unit_id, "unit_id required")
        require(unit_id not in by_id, f"duplicate unit_id: {unit_id}")
        require(unit.get("source_id") == source_id, f"{unit_id}: source_id mismatch")
        unit_categories = unit.get("categories")
        require(isinstance(unit_categories, list) and unit_categories, f"{unit_id}: categories required")
        require(set(unit_categories) <= categories, f"{unit_id}: unknown taxonomy category")
        require(
            unit.get("classification") in {"MUST_INCLUDE", "OPTIONAL", "EXCLUDE", "UNKNOWN"},
            f"{unit_id}: invalid classification",
        )
        by_id[unit_id] = unit
    return by_id


def _deterministic_seed_reason(unit: dict[str, Any], rules: dict[str, Any]) -> str | None:
    classification = unit["classification"]
    policy = rules["classification_policy"][classification]
    mandatory = set(rules.get("mandatory_categories", []))
    categories = set(unit["categories"])

    if "UNKNOWN" in categories or policy == "INCLUDE_FAIL_CLOSED":
        return "UNKNOWN_FAIL_CLOSED"
    if categories & mandatory:
        return "MANDATORY_CATEGORY"
    if policy == "INCLUDE":
        return "MUST_INCLUDE"
    return None


def resolve_dependency_closure(
    seed_ids: Iterable[str],
    edges: Iterable[dict[str, Any]],
    unit_ids: set[str],
) -> tuple[set[str], dict[str, set[str]]]:
    included = set(seed_ids)
    reasons: dict[str, set[str]] = {unit_id: set() for unit_id in included}
    adjacency: dict[str, list[str]] = {}

    for edge in edges:
        edge_type = edge.get("edge_type")
        if edge_type not in AUTHORITATIVE_DEPENDENCIES:
            continue
        source = edge.get("from_unit_id")
        target = edge.get("to_unit_id")
        require(source in unit_ids and target in unit_ids, "dependency edge references unknown unit")
        adjacency.setdefault(str(source), []).append(str(target))

    queue = deque(sorted(included))
    while queue:
        source = queue.popleft()
        for target in sorted(adjacency.get(source, [])):
            reasons.setdefault(target, set()).add(f"DEPENDENCY_FROM:{source}")
            if target not in included:
                included.add(target)
                queue.append(target)
    return included, reasons


def build_pack(
    *,
    pack_id: str,
    purpose: str,
    source_lock: dict[str, Any],
    catalogs: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    rules: dict[str, Any],
    builder: dict[str, str],
    dependency_edges: list[dict[str, Any]],
    ai_supplemental_unit_ids: Iterable[str] = (),
) -> dict[str, Any]:
    require(catalogs, "at least one Evidence Unit catalog is required")
    source_lock_id = source_lock.get("source_lock_id")
    require(isinstance(source_lock_id, str) and source_lock_id, "source lock requires source_lock_id")
    all_units: dict[str, dict[str, Any]] = {}
    catalog_ids: list[str] = []
    catalog_digests: dict[str, str] = {}

    for catalog in catalogs:
        units = validate_catalog(catalog, taxonomy, source_lock)
        overlap = set(all_units) & set(units)
        require(not overlap, f"duplicate unit IDs across catalogs: {sorted(overlap)}")
        all_units.update(units)
        catalog_id = catalog["catalog_id"]
        catalog_ids.append(catalog_id)
        catalog_digests[catalog_id] = catalog["catalog_digest"]

    seed_reasons: dict[str, set[str]] = {}
    for unit_id, unit in all_units.items():
        reason = _deterministic_seed_reason(unit, rules)
        if reason:
            seed_reasons.setdefault(unit_id, set()).add(reason)

    included, dependency_reasons = resolve_dependency_closure(seed_reasons, dependency_edges, set(all_units))
    for unit_id, reasons in dependency_reasons.items():
        seed_reasons.setdefault(unit_id, set()).update(reasons)

    supplemental = set(ai_supplemental_unit_ids)
    require(supplemental <= set(all_units), "AI supplemental unit references unknown unit")

    entries: list[dict[str, Any]] = []
    for unit_id in sorted(included | supplemental):
        deterministic = unit_id in included
        reasons = seed_reasons.get(unit_id, set())
        if not deterministic:
            reasons = {"AI_SUPPLEMENTAL"}
        entries.append(
            {
                "unit_id": unit_id,
                "inclusion_reasons": sorted(reasons),
                "origin": "DETERMINISTIC" if deterministic else "AI_SUPPLEMENTAL",
            }
        )

    pack: dict[str, Any] = {
        "artifact_type": "evidence_pack",
        "schema_version": SCHEMA_VERSION,
        "pack_id": pack_id,
        "purpose": purpose,
        "source_lock_id": source_lock_id,
        "catalog_ids": sorted(catalog_ids),
        "catalog_digests": dict(sorted(catalog_digests.items())),
        "builder": builder,
        "taxonomy_digest": canonical_sha256(taxonomy),
        "rules_digest": canonical_sha256(rules),
        "included_units": entries,
        "dependency_edges": sorted(
            dependency_edges,
            key=lambda item: (item["from_unit_id"], item["to_unit_id"], item["edge_type"]),
        ),
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    pack["pack_digest"] = pack_digest(pack)
    return pack


def validate_applicability_binding(
    binding: dict[str, Any],
    *,
    packs: dict[str, dict[str, Any]],
) -> None:
    require(binding.get("artifact_type") == "applicability_binding", "binding artifact_type mismatch")
    require(binding.get("schema_version") == SCHEMA_VERSION, "binding schema_version mismatch")
    require(binding.get("canonical_dataset_admission") is False, "binding must deny canonical admission")
    require(binding.get("production_admission") is False, "binding must deny production admission")

    claims = binding.get("claims")
    require(isinstance(claims, dict) and claims, "applicability claims required")
    for claim_id, claim in claims.items():
        require(isinstance(claim, dict), f"{claim_id}: claim must be object")
        pack_id = claim.get("pack_id")
        require(pack_id in packs, f"{claim_id}: unknown pack")
        evidence_ids = claim.get("evidence_unit_ids")
        require(isinstance(evidence_ids, list) and evidence_ids, f"{claim_id}: evidence required")
        pack_units = {item["unit_id"] for item in packs[pack_id]["included_units"]}
        require(set(evidence_ids) <= pack_units, f"{claim_id}: applicability evidence must be included in pack")

    targets = binding.get("targets")
    require(isinstance(targets, list) and targets, "binding targets required")
    seen: set[str] = set()
    for target in targets:
        icpn = target.get("icpn")
        require(isinstance(icpn, str) and icpn, "target ICPN required")
        require(icpn not in seen, f"duplicate target ICPN: {icpn}")
        seen.add(icpn)
        pack_ids = target.get("pack_ids")
        claim_ids = target.get("applicability_claim_ids")
        require(isinstance(pack_ids, list) and pack_ids, f"{icpn}: pack_ids required")
        require(isinstance(claim_ids, list) and claim_ids, f"{icpn}: applicability claims required")
        require(set(pack_ids) <= set(packs), f"{icpn}: unknown pack")
        require(set(claim_ids) <= set(claims), f"{icpn}: unknown applicability claim")
        covered = {claims[claim_id]["pack_id"] for claim_id in claim_ids}
        require(set(pack_ids) <= covered, f"{icpn}: each pack requires evidence-backed applicability")


def resolve_target_bundle(
    *,
    target_icpn: str,
    binding: dict[str, Any],
    packs: dict[str, dict[str, Any]],
    source_lock_id: str,
) -> dict[str, Any]:
    validate_applicability_binding(binding, packs=packs)
    matches = [target for target in binding["targets"] if target["icpn"] == target_icpn]
    require(len(matches) == 1, f"{target_icpn}: exact applicability binding required")
    target = matches[0]
    selected = {pack_id: packs[pack_id]["pack_digest"] for pack_id in target["pack_ids"]}
    require(
        all(packs[pack_id]["source_lock_id"] == source_lock_id for pack_id in selected),
        "pack/source-lock mismatch",
    )

    bundle: dict[str, Any] = {
        "artifact_type": "target_evidence_bundle",
        "schema_version": SCHEMA_VERSION,
        "bundle_id": f"{target_icpn.lower()}-evidence-bundle-v0",
        "target_icpn": target_icpn,
        "source_lock_id": source_lock_id,
        "pack_digests": dict(sorted(selected.items())),
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    bundle["bundle_digest"] = bundle_digest(bundle)
    return bundle
