#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from contract import (
    build_pack,
    canonical_sha256,
    catalog_digest,
    resolve_target_bundle,
    validate_applicability_binding,
)
from preprocessing import (
    DEFAULT_NORMALIZATION,
    extract_pdf_text,
    load_json,
    normalize_page_text,
    preprocess_locked_pdf,
    sha256_file,
    split_physical_pages,
    validate_manifest,
)

HERE = Path(__file__).resolve().parent
DEFAULT_TAXONOMY = HERE / "taxonomy-v0.json"
DEFAULT_RULES = HERE / "rules-v0.json"
POLICY_SCHEMA_VERSION = "0.1.0"
CLASSIFICATION_PRECEDENCE = {
    "EXCLUDE": 0,
    "OPTIONAL": 1,
    "UNKNOWN": 2,
    "MUST_INCLUDE": 3,
}
_REFERENCE_RE = re.compile(
    r"\b(?:see|refer(?:\s+to)?|shown\s+in|described\s+in)\s+"
    r"(?P<kind>Section|Table|Figure)\s+(?P<label>\d+(?:\.\d+){0,5}[A-Za-z]?)\b",
    re.IGNORECASE,
)
_TOC_LEADER_RE = re.compile(r"(?:\.\s*){3,}\s*\d+\s*$")


class SemanticPackError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticPackError(message)


def policy_digest(policy: dict[str, Any]) -> str:
    return canonical_sha256(policy)


def _source_lock_entry(source_lock: dict[str, Any], source_id: str) -> dict[str, Any]:
    matches = [
        item for item in source_lock.get("sources", [])
        if isinstance(item, dict) and item.get("source_id") == source_id
    ]
    require(len(matches) == 1, f"{source_id}: exact source-lock entry required")
    return matches[0]


def _validate_rule_shape(rule: dict[str, Any], taxonomy: dict[str, Any], *, prefix: str) -> None:
    categories = set(taxonomy.get("categories", []))
    require(isinstance(rule.get("rule_id"), str) and rule["rule_id"], f"{prefix}: rule_id required")
    rule_categories = rule.get("categories")
    require(isinstance(rule_categories, list) and rule_categories, f"{prefix}: categories required")
    require(set(rule_categories) <= categories, f"{prefix}: unknown taxonomy category")
    require(rule.get("classification") in CLASSIFICATION_PRECEDENCE, f"{prefix}: invalid classification")


def validate_policy(
    policy: dict[str, Any],
    *,
    source_lock: dict[str, Any],
    taxonomy: dict[str, Any],
) -> None:
    require(policy.get("artifact_type") == "semantic_evidence_policy", "policy artifact_type mismatch")
    require(policy.get("schema_version") == POLICY_SCHEMA_VERSION, "policy schema_version mismatch")
    require(isinstance(policy.get("policy_id"), str) and policy["policy_id"], "policy_id required")
    require(isinstance(policy.get("purpose"), str) and policy["purpose"], "policy purpose required")
    require(policy.get("source_lock_id") == source_lock.get("source_lock_id"), "policy/source-lock ID mismatch")

    source = policy.get("source")
    require(isinstance(source, dict), "policy source required")
    source_id = source.get("source_id")
    require(isinstance(source_id, str) and source_id, "policy source_id required")
    locked = _source_lock_entry(source_lock, source_id)
    integrity = locked.get("integrity")
    require(isinstance(integrity, dict), "locked source integrity required")
    require(source.get("algorithm") == integrity.get("algorithm"), "policy source algorithm mismatch")
    require(source.get("digest") == integrity.get("digest"), "policy source digest mismatch")
    require(source.get("byte_length") == integrity.get("byte_length"), "policy source byte length mismatch")

    expected_page_count = policy.get("expected_physical_page_count")
    require(isinstance(expected_page_count, int) and expected_page_count >= 1, "expected page count required")

    default = policy.get("default")
    require(isinstance(default, dict), "policy default required")
    _validate_rule_shape({"rule_id": "__default__", **default}, taxonomy, prefix="default")

    seen_rules: set[str] = set()
    for index, rule in enumerate(policy.get("page_rules", [])):
        require(isinstance(rule, dict), f"page_rules[{index}] must be object")
        _validate_rule_shape(rule, taxonomy, prefix=f"page_rules[{index}]")
        require(rule["rule_id"] not in seen_rules, f"duplicate policy rule_id: {rule['rule_id']}")
        seen_rules.add(rule["rule_id"])
        page_index = rule.get("pdf_page_index")
        require(isinstance(page_index, int) and 0 <= page_index < expected_page_count, f"{rule['rule_id']}: invalid page index")

    for index, rule in enumerate(policy.get("section_rules", [])):
        require(isinstance(rule, dict), f"section_rules[{index}] must be object")
        _validate_rule_shape(rule, taxonomy, prefix=f"section_rules[{index}]")
        require(rule["rule_id"] not in seen_rules, f"duplicate policy rule_id: {rule['rule_id']}")
        seen_rules.add(rule["rule_id"]
        )
        require(isinstance(rule.get("section_label"), str) and rule["section_label"], f"{rule['rule_id']}: section_label required")
        heading_regex = rule.get("heading_regex")
        require(isinstance(heading_regex, str) and heading_regex, f"{rule['rule_id']}: heading_regex required")
        try:
            re.compile(heading_regex, re.IGNORECASE)
        except re.error as exc:
            raise SemanticPackError(f"{rule['rule_id']}: invalid heading_regex: {exc}") from exc

    applicability = policy.get("applicability")
    require(isinstance(applicability, dict), "policy applicability required")
    claims = applicability.get("claims")
    require(isinstance(claims, list) and claims, "policy applicability claims required")
    seen_claims: set[str] = set()
    for index, claim in enumerate(claims):
        require(isinstance(claim, dict), f"applicability.claims[{index}] must be object")
        claim_id = claim.get("claim_id")
        require(isinstance(claim_id, str) and claim_id, f"applicability.claims[{index}]: claim_id required")
        require(claim_id not in seen_claims, f"duplicate applicability claim_id: {claim_id}")
        seen_claims.add(claim_id)
        require(isinstance(claim.get("manufacturer_expression"), str) and claim["manufacturer_expression"], f"{claim_id}: manufacturer_expression required")
        require(claim.get("anchor_type") in {"TABLE_CANDIDATE", "FIGURE_CANDIDATE", "SECTION_CANDIDATE"}, f"{claim_id}: invalid anchor_type")
        require(isinstance(claim.get("anchor_label"), str) and claim["anchor_label"], f"{claim_id}: anchor_label required")
        require(isinstance(claim.get("anchor_heading_regex"), str) and claim["anchor_heading_regex"], f"{claim_id}: anchor_heading_regex required")
        targets = claim.get("targets")
        require(isinstance(targets, list) and targets, f"{claim_id}: targets required")


def _resolve_section_rule(rule: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    pattern = re.compile(rule["heading_regex"], re.IGNORECASE)
    matches = [
        unit for unit in manifest["structural_units"]
        if unit.get("type") == "SECTION_CANDIDATE"
        and unit.get("label") == rule["section_label"]
        and pattern.fullmatch(str(unit.get("heading") or ""))
    ]
    require(len(matches) == 1, f"{rule['rule_id']}: expected exactly one structural section, got {len(matches)}")
    return matches[0]


def _resolve_anchor(claim: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    pattern = re.compile(claim["anchor_heading_regex"], re.IGNORECASE)
    matches = [
        unit for unit in manifest["structural_units"]
        if unit.get("type") == claim["anchor_type"]
        and unit.get("label") == claim["anchor_label"]
        and pattern.fullmatch(str(unit.get("heading") or ""))
    ]
    require(len(matches) == 1, f"{claim['claim_id']}: expected exactly one applicability anchor, got {len(matches)}")
    return matches[0]


def _rule_specificity(rule: dict[str, Any]) -> int:
    if "pdf_page_index" in rule:
        return 100
    label = str(rule.get("section_label", ""))
    return label.count(".") + 1


def _page_assignments(policy: dict[str, Any], manifest: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    assignments: dict[int, list[dict[str, Any]]] = {index: [] for index in range(manifest["page_count"])}

    for rule in policy.get("page_rules", []):
        assignments[rule["pdf_page_index"]].append({**rule, "_specificity": _rule_specificity(rule), "_path": f"page:{rule['pdf_page_index']}"})

    for rule in policy.get("section_rules", []):
        section = _resolve_section_rule(rule, manifest)
        for page_index in range(section["pdf_page_start"], section["pdf_page_end"] + 1):
            assignments[page_index].append({
                **rule,
                "_specificity": _rule_specificity(rule),
                "_path": f"{rule['section_label']} {section['heading']}",
            })

    default = policy["default"]
    for page_index, page_rules in assignments.items():
        if not page_rules:
            assignments[page_index] = [{
                "rule_id": "__default__",
                "categories": list(default["categories"]),
                "classification": default["classification"],
                "_specificity": 0,
                "_path": "document-structure",
            }]
            continue
        maximum = max(rule["_specificity"] for rule in page_rules)
        assignments[page_index] = [rule for rule in page_rules if rule["_specificity"] == maximum]
    return assignments


def build_catalog(
    *,
    manifest: dict[str, Any],
    policy: dict[str, Any],
    source_lock: dict[str, Any],
    taxonomy: dict[str, Any],
    builder_sha256: str,
) -> dict[str, Any]:
    validate_manifest(manifest, source_lock=source_lock)
    validate_policy(policy, source_lock=source_lock, taxonomy=taxonomy)
    require(manifest["page_count"] == policy["expected_physical_page_count"], "manifest page count does not match policy")
    require(manifest["source"]["source_id"] == policy["source"]["source_id"], "manifest/policy source mismatch")
    require(manifest["source"]["digest"] == policy["source"]["digest"], "manifest/policy source digest mismatch")

    assignments = _page_assignments(policy, manifest)
    units: list[dict[str, Any]] = []
    source_id = manifest["source"]["source_id"]
    for page in manifest["pages"]:
        page_index = page["pdf_page_index"]
        applied = assignments[page_index]
        categories = sorted({category for rule in applied for category in rule["categories"]})
        classification = max(
            (rule["classification"] for rule in applied),
            key=lambda value: CLASSIFICATION_PRECEDENCE[value],
        )
        units.append({
            "unit_id": f"{source_id}-page-{page_index:04d}",
            "source_id": source_id,
            "unit_type": "PAGE",
            "pdf_page_index": page_index,
            "pdf_page_end": page_index,
            "printed_page_label": page.get("printed_page_label"),
            "section_path": sorted({str(rule["_path"]) for rule in applied}),
            "categories": categories,
            "classification": classification,
            "content_sha256": page["normalized_content_sha256"],
            "policy_rule_ids": sorted({str(rule["rule_id"]) for rule in applied}),
        })

    catalog: dict[str, Any] = {
        "artifact_type": "evidence_unit_catalog",
        "schema_version": "0.1.0",
        "catalog_id": f"{source_id}-page-catalog-v0",
        "source_lock_id": manifest["source_lock_id"],
        "source": {
            "source_id": source_id,
            "algorithm": manifest["source"]["algorithm"],
            "digest": manifest["source"]["digest"],
        },
        "preprocessor": {
            "name": manifest["preprocessor"]["name"],
            "version": manifest["preprocessor"]["version"],
        },
        "normalization_contract": f"{manifest['normalization']['contract_id']}@{manifest['normalization']['digest']}",
        "semantic_policy": {
            "policy_id": policy["policy_id"],
            "digest": policy_digest(policy),
            "builder_sha256": builder_sha256,
            "structure_manifest_digest": manifest["manifest_digest"],
        },
        "units": units,
    }
    catalog["catalog_digest"] = catalog_digest(catalog)
    return catalog


def _is_toc_like_heading(heading: str) -> bool:
    return bool(_TOC_LEADER_RE.search(heading))


def _structural_targets(manifest: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    targets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    kind_map = {
        "SECTION_CANDIDATE": "Section",
        "TABLE_CANDIDATE": "Table",
        "FIGURE_CANDIDATE": "Figure",
    }
    for unit in manifest["structural_units"]:
        kind = kind_map.get(str(unit.get("type")))
        label = unit.get("label")
        heading = str(unit.get("heading") or "")
        if not kind or not isinstance(label, str) or _is_toc_like_heading(heading):
            continue
        normalized_label = label if kind == "Section" else label.split()[-1]
        targets.setdefault((kind.lower(), normalized_label.lower()), []).append(unit)
    return targets


def build_dependency_edges(
    *,
    manifest: dict[str, Any],
    catalog: dict[str, Any],
    normalized_pages: list[str] | None = None,
) -> list[dict[str, Any]]:
    unit_for_page = {unit["pdf_page_index"]: unit["unit_id"] for unit in catalog["units"]}
    targets = _structural_targets(manifest)
    candidate_refs: set[tuple[int, str, str]] = set()

    for reference in manifest.get("references", []):
        target_label = str(reference.get("target_label") or "")
        words = target_label.split()
        if len(words) == 2 and words[0].lower() in {"table", "figure"}:
            candidate_refs.add((int(reference["pdf_page_index"]), words[0].title(), words[1]))

    if normalized_pages is not None:
        require(len(normalized_pages) == manifest["page_count"], "normalized page count mismatch")
        for page_index, page in enumerate(normalized_pages):
            for match in _REFERENCE_RE.finditer(page):
                candidate_refs.add((page_index, match.group("kind").title(), match.group("label")))

    edges: set[tuple[str, str, str]] = set()
    for from_page, kind, label in sorted(candidate_refs):
        matches = targets.get((kind.lower(), label.lower()), [])
        if len(matches) != 1:
            continue
        target_page = int(matches[0]["pdf_page_start"])
        source_unit = unit_for_page[from_page]
        target_unit = unit_for_page[target_page]
        if source_unit == target_unit:
            continue
        edges.add((source_unit, target_unit, "DOCUMENT_EXPLICIT"))
    return [
        {"from_unit_id": source, "to_unit_id": target, "edge_type": edge_type}
        for source, target, edge_type in sorted(edges)
    ]


def build_binding(
    *,
    policy: dict[str, Any],
    manifest: dict[str, Any],
    pack: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    unit_for_page = {unit["pdf_page_index"]: unit["unit_id"] for unit in catalog["units"]}
    pack_unit_ids = {entry["unit_id"] for entry in pack["included_units"]}
    claims: dict[str, Any] = {}
    target_claims: dict[str, list[str]] = {}

    for claim in policy["applicability"]["claims"]:
        anchor = _resolve_anchor(claim, manifest)
        evidence_unit_id = unit_for_page[int(anchor["pdf_page_start"])]
        require(evidence_unit_id in pack_unit_ids, f"{claim['claim_id']}: applicability anchor page is not included in pack")
        claims[claim["claim_id"]] = {
            "pack_id": pack["pack_id"],
            "manufacturer_expression": claim["manufacturer_expression"],
            "evidence_unit_ids": [evidence_unit_id],
        }
        for target in claim["targets"]:
            target_claims.setdefault(str(target), []).append(claim["claim_id"])

    binding = {
        "artifact_type": "applicability_binding",
        "schema_version": "0.1.0",
        "binding_id": f"{policy['policy_id']}-applicability",
        "claims": claims,
        "targets": [
            {
                "icpn": target,
                "pack_ids": [pack["pack_id"]],
                "applicability_claim_ids": sorted(claim_ids),
            }
            for target, claim_ids in sorted(target_claims.items())
        ],
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    validate_applicability_binding(binding, packs={pack["pack_id"]: pack})
    return binding


def build_semantic_artifacts(
    *,
    manifest: dict[str, Any],
    policy: dict[str, Any],
    source_lock: dict[str, Any],
    taxonomy: dict[str, Any],
    rules: dict[str, Any],
    builder_sha256: str,
    normalized_pages: list[str] | None = None,
) -> dict[str, Any]:
    catalog = build_catalog(
        manifest=manifest,
        policy=policy,
        source_lock=source_lock,
        taxonomy=taxonomy,
        builder_sha256=builder_sha256,
    )
    dependency_edges = build_dependency_edges(
        manifest=manifest,
        catalog=catalog,
        normalized_pages=normalized_pages,
    )
    pack = build_pack(
        pack_id=policy["pack_id"],
        purpose=policy["purpose"],
        source_lock=source_lock,
        catalogs=[catalog],
        taxonomy=taxonomy,
        rules=rules,
        builder={
            "name": "plasma-semantic-pack-builder",
            "version": f"0.1.0+{builder_sha256[:12]}",
        },
        dependency_edges=dependency_edges,
    )
    binding = build_binding(policy=policy, manifest=manifest, pack=pack, catalog=catalog)
    bundles = {
        target["icpn"]: resolve_target_bundle(
            target_icpn=target["icpn"],
            binding=binding,
            packs={pack["pack_id"]: pack},
            source_lock_id=source_lock["source_lock_id"],
        )
        for target in binding["targets"]
    }
    return {
        "catalog": catalog,
        "pack": pack,
        "binding": binding,
        "bundles": bundles,
    }


def materialize_evidence_text(
    *,
    normalized_pages: list[str],
    catalog: dict[str, Any],
    pack: dict[str, Any],
) -> str:
    catalog_by_id = {unit["unit_id"]: unit for unit in catalog["units"]}
    included = [catalog_by_id[entry["unit_id"]] for entry in pack["included_units"]]
    included.sort(key=lambda unit: unit["pdf_page_index"])
    chunks = [
        f"# Plasma Evidence Pack\n# pack_id={pack['pack_id']}\n# pack_digest={pack['pack_digest']}\n"
    ]
    for unit in included:
        page_index = unit["pdf_page_index"]
        chunks.append(
            f"\n===== {unit['source_id']} physical-page {page_index} sha256={unit['content_sha256']} =====\n"
        )
        chunks.append(normalized_pages[page_index])
    return "".join(chunks)


def _normalized_pages_from_pdf(pdf: Path, manifest: dict[str, Any], pdftotext: str) -> list[str]:
    extracted_text, tool = extract_pdf_text(pdf, pdftotext)
    require(tool == manifest["preprocessor"], "pdftotext fingerprint changed between preprocessing and materialization")
    normalization = load_json(DEFAULT_NORMALIZATION)
    pages = [normalize_page_text(page, normalization) for page in split_physical_pages(extracted_text)]
    require(len(pages) == manifest["page_count"], "materialized page count mismatch")
    for page, observed in zip(pages, manifest["pages"]):
        from hashlib import sha256
        actual = sha256(page.encode("utf-8")).hexdigest()
        require(actual == observed["normalized_content_sha256"], f"page {observed['pdf_page_index']}: normalized content drift")
    return pages


def write_artifacts(output_dir: Path, artifacts: dict[str, Any], evidence_text: str | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("catalog", "pack", "binding"):
        (output_dir / f"{name}.json").write_text(json.dumps(artifacts[name], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bundles_dir = output_dir / "bundles"
    bundles_dir.mkdir(exist_ok=True)
    for target, bundle in artifacts["bundles"].items():
        (bundles_dir / f"{target}.json").write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if evidence_text is not None:
        (output_dir / "evidence.txt").write_text(evidence_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic semantic Evidence Pack from a source-locked PDF")
    parser.add_argument("--source-lock", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--pdftotext", default="pdftotext")
    args = parser.parse_args()

    try:
        source_lock = load_json(args.source_lock)
        policy = load_json(args.policy)
        taxonomy = load_json(args.taxonomy)
        rules = load_json(args.rules)
        source_id = str(policy.get("source", {}).get("source_id", ""))
        require(source_id, "policy source_id required")
        manifest = preprocess_locked_pdf(
            pdf=args.pdf,
            source_lock_path=args.source_lock,
            source_id=source_id,
            normalization_path=DEFAULT_NORMALIZATION,
            pdftotext=args.pdftotext,
        )
        normalized_pages = _normalized_pages_from_pdf(args.pdf, manifest, args.pdftotext)
        builder_sha256 = sha256_file(Path(__file__))
        artifacts = build_semantic_artifacts(
            manifest=manifest,
            policy=policy,
            source_lock=source_lock,
            taxonomy=taxonomy,
            rules=rules,
            builder_sha256=builder_sha256,
            normalized_pages=normalized_pages,
        )
        evidence_text = materialize_evidence_text(
            normalized_pages=normalized_pages,
            catalog=artifacts["catalog"],
            pack=artifacts["pack"],
        )
        write_artifacts(args.output_dir, artifacts, evidence_text=evidence_text)
        (args.output_dir / "structure.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(
            f"IC semantic Evidence Pack PASS: {artifacts['pack']['pack_id']} "
            f"({len(artifacts['pack']['included_units'])}/{manifest['page_count']} pages included)"
        )
        return 0
    except (OSError, json.JSONDecodeError, SemanticPackError, Exception) as exc:
        # Preprocessing/contract exceptions are intentionally surfaced through one fail-closed CLI boundary.
        print(f"IC semantic Evidence Pack FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
