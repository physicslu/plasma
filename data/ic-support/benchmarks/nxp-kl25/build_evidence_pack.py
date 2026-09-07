#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1.0"
BUILDER_VERSION = "0.1.0"


class KL25EvidencePackError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise KL25EvidencePackError(message)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_page(text: str) -> str:
    return "\n".join(
        line.rstrip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()


def extract_pages(pdf: Path) -> list[str]:
    proc = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    pages = [normalize_page(page) for page in proc.stdout.split("\f")]
    while pages and pages[-1] == "":
        pages.pop()
    require(bool(pages), f"{pdf}: no PDF pages extracted")
    return pages


def _without_digest(payload: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != field}


def _by_id(items: list[dict[str, Any]], key: str, *, context: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        require(isinstance(item, dict), f"{context}: item must be object")
        item_id = item.get(key)
        require(isinstance(item_id, str) and item_id, f"{context}: {key} required")
        require(item_id not in result, f"{context}: duplicate {key}: {item_id}")
        result[item_id] = item
    return result


def validate_contract(
    *,
    contract: dict[str, Any],
    definitions: dict[str, Any],
    binding: dict[str, Any],
    source_lock: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], dict[str, dict[str, Any]]]:
    require(contract.get("schema_version") == SCHEMA_VERSION, "evidence-pack contract schema mismatch")
    require(contract.get("artifact_type") == "kl25_evidence_pack_contract", "evidence-pack contract artifact mismatch")
    require(contract.get("source_lock_id") == source_lock.get("source_lock_id"), "contract/source-lock mismatch")
    require(contract.get("definition_set_id") == definitions.get("definition_set_id"), "contract/definition-set mismatch")
    require(contract.get("binding_id") == binding.get("binding_id"), "contract/binding mismatch")
    require(contract.get("target") == definitions.get("target") == binding.get("target"), "target mismatch")
    require(definitions.get("status") == "admitted_evidence_unit_catalog", "Evidence Unit Catalog not admitted")
    require(
        definitions.get("trust_boundary", {}).get("evidence_unit_catalog_admission") is True,
        "Evidence Unit Catalog admission missing",
    )
    require(
        definitions.get("trust_boundary", {}).get("applicability_binding_admission") is True,
        "Applicability Binding admission missing",
    )
    require(binding.get("scope_bridge", {}).get("status") == "BOUND", "scope bridge must be BOUND")
    require(binding.get("applicability_exclusions_reviewed") is True, "applicability exclusions must be reviewed")
    require(binding.get("admission", {}).get("applicability_binding") is True, "Applicability Binding must be admitted")
    require(binding.get("admission", {}).get("semantic_extraction") is False, "semantic extraction must remain denied")

    units = _by_id(definitions.get("units", []), "unit_id", context="definitions")
    unit_bindings = binding.get("unit_bindings")
    require(isinstance(unit_bindings, dict), "unit_bindings required")
    require(set(unit_bindings) == set(units), "binding/catalog unit set mismatch")
    for unit_id, item in unit_bindings.items():
        require(item.get("status") == "BOUND", f"{unit_id}: unit must be BOUND")
        definition = units[unit_id]
        require(item.get("source_id") == definition.get("source_id"), f"{unit_id}: source mismatch")
        require(item.get("pdf_page_range") == definition.get("pdf_page_range"), f"{unit_id}: page range mismatch")

    dependencies = contract.get("unit_dependencies")
    require(isinstance(dependencies, dict), "unit_dependencies required")
    require(set(dependencies) == set(units), "dependency/catalog unit set mismatch")
    normalized_dependencies: dict[str, list[str]] = {}
    for unit_id, dependency_ids in dependencies.items():
        require(isinstance(dependency_ids, list), f"{unit_id}: dependencies must be list")
        require(len(dependency_ids) == len(set(dependency_ids)), f"{unit_id}: duplicate dependency")
        require(unit_id not in dependency_ids, f"{unit_id}: self-dependency forbidden")
        require(set(dependency_ids) <= set(units), f"{unit_id}: unknown dependency")
        normalized_dependencies[unit_id] = sorted(dependency_ids)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(unit_id: str) -> None:
        if unit_id in visited:
            return
        require(unit_id not in visiting, f"dependency cycle detected at {unit_id}")
        visiting.add(unit_id)
        for dependency_id in normalized_dependencies[unit_id]:
            visit(dependency_id)
        visiting.remove(unit_id)
        visited.add(unit_id)

    for unit_id in sorted(units):
        visit(unit_id)

    sources = _by_id(source_lock.get("sources", []), "source_id", context="source lock")
    for unit in units.values():
        require(unit.get("source_id") in sources, f"{unit['unit_id']}: source absent from source lock")
        page_range = unit.get("pdf_page_range")
        require(
            isinstance(page_range, list)
            and len(page_range) == 2
            and all(isinstance(value, int) and value >= 1 for value in page_range)
            and page_range[0] <= page_range[1],
            f"{unit['unit_id']}: invalid physical PDF page range",
        )

    return units, normalized_dependencies, sources


def dependency_closure(primary_unit_id: str, dependencies: dict[str, list[str]]) -> list[str]:
    require(primary_unit_id in dependencies, f"unknown primary unit: {primary_unit_id}")
    included: set[str] = set()

    def add(unit_id: str) -> None:
        if unit_id in included:
            return
        for dependency_id in dependencies[unit_id]:
            add(dependency_id)
        included.add(unit_id)

    add(primary_unit_id)
    return sorted(included)


def required_page_map(
    *,
    included_unit_ids: list[str],
    units: dict[str, dict[str, Any]],
) -> dict[tuple[str, int], set[str]]:
    pages: dict[tuple[str, int], set[str]] = {}
    for unit_id in included_unit_ids:
        unit = units[unit_id]
        start, end = unit["pdf_page_range"]
        for page_number in range(start, end + 1):
            pages.setdefault((unit["source_id"], page_number), set()).add(unit_id)
    return pages


def build_pack_set(
    *,
    contract: dict[str, Any],
    definitions: dict[str, Any],
    binding: dict[str, Any],
    source_lock: dict[str, Any],
    pages_by_source: dict[str, list[str]],
    builder_sha256: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    units, dependencies, sources = validate_contract(
        contract=contract,
        definitions=definitions,
        binding=binding,
        source_lock=source_lock,
    )
    require(isinstance(builder_sha256, str) and len(builder_sha256) == 64, "builder_sha256 required")
    definition_set_digest = canonical_sha256(definitions)
    binding_digest = canonical_sha256(binding)
    contract_digest = canonical_sha256(contract)

    packs: dict[str, dict[str, Any]] = {}
    for primary_unit_id in sorted(units):
        included_unit_ids = dependency_closure(primary_unit_id, dependencies)
        page_map = required_page_map(included_unit_ids=included_unit_ids, units=units)
        page_refs: list[dict[str, Any]] = []
        for (source_id, page_number), required_by in sorted(page_map.items()):
            pages = pages_by_source.get(source_id)
            require(isinstance(pages, list), f"{source_id}: extracted page set required")
            require(1 <= page_number <= len(pages), f"{source_id}: missing physical PDF page {page_number}")
            normalized = normalize_page(pages[page_number - 1])
            require(normalized != "", f"{source_id}: physical PDF page {page_number} is empty")
            page_refs.append(
                {
                    "source_id": source_id,
                    "pdf_page_number": page_number,
                    "page_text_sha256": sha256_text(normalized),
                    "required_by_unit_ids": sorted(required_by),
                }
            )

        pack_id = f"{primary_unit_id}-pack-v0"
        pack: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "kl25_evidence_pack",
            "pack_id": pack_id,
            "primary_unit_id": primary_unit_id,
            "target": contract["target"],
            "source_lock_id": source_lock["source_lock_id"],
            "source_fingerprints": {
                source_id: {
                    "algorithm": sources[source_id]["integrity"]["algorithm"],
                    "digest": sources[source_id]["integrity"]["digest"],
                    "byte_length": sources[source_id]["integrity"]["byte_length"],
                }
                for source_id in sorted({units[unit_id]["source_id"] for unit_id in included_unit_ids})
            },
            "definition_set_id": definitions["definition_set_id"],
            "definition_set_digest": definition_set_digest,
            "binding_id": binding["binding_id"],
            "binding_digest": binding_digest,
            "contract_id": contract["contract_id"],
            "contract_digest": contract_digest,
            "builder": {
                "name": "build_evidence_pack.py",
                "version": BUILDER_VERSION,
                "sha256": builder_sha256,
            },
            "included_units": [
                {
                    "unit_id": unit_id,
                    "origin": "PRIMARY" if unit_id == primary_unit_id else "DETERMINISTIC_DEPENDENCY",
                    "role": units[unit_id]["role"],
                    "source_id": units[unit_id]["source_id"],
                    "pdf_page_range": units[unit_id]["pdf_page_range"],
                }
                for unit_id in included_unit_ids
            ],
            "page_refs": page_refs,
            "admission": {
                "evidence_pack": bool(contract.get("admission", {}).get("evidence_pack", False)),
                "semantic_extraction": False,
                "canonical_dataset": False,
                "hil": False,
                "production": False,
                "destructive_security_operation": False,
            },
        }
        pack["pack_digest"] = canonical_sha256(_without_digest(pack, "pack_digest"))
        packs[pack_id] = pack

    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "kl25_target_evidence_bundle",
        "bundle_id": "mkl25z128vlk4-target-evidence-bundle-v0",
        "target": contract["target"],
        "source_lock_id": source_lock["source_lock_id"],
        "binding_id": binding["binding_id"],
        "binding_digest": binding_digest,
        "contract_id": contract["contract_id"],
        "contract_digest": contract_digest,
        "pack_digests": {pack_id: packs[pack_id]["pack_digest"] for pack_id in sorted(packs)},
        "admission": {
            "evidence_pack": bool(contract.get("admission", {}).get("evidence_pack", False)),
            "semantic_extraction": False,
            "canonical_dataset": False,
            "hil": False,
            "production": False,
        },
    }
    bundle["bundle_digest"] = canonical_sha256(_without_digest(bundle, "bundle_digest"))
    return packs, bundle


def materialize_evidence_text(pack: dict[str, Any], pages_by_source: dict[str, list[str]]) -> str:
    chunks: list[str] = []
    seen: set[tuple[str, int]] = set()
    for page_ref in pack["page_refs"]:
        key = (page_ref["source_id"], page_ref["pdf_page_number"])
        require(key not in seen, f"duplicate materialized page: {key}")
        seen.add(key)
        page = normalize_page(pages_by_source[key[0]][key[1] - 1])
        require(sha256_text(page) == page_ref["page_text_sha256"], f"page content drift: {key}")
        chunks.append(
            f"=== BEGIN {key[0]} PDF_PAGE {key[1]} SHA256 {page_ref['page_text_sha256']} ===\n"
            f"{page}\n"
            f"=== END {key[0]} PDF_PAGE {key[1]} ==="
        )
    return "\n\n".join(chunks) + "\n"


def build_pre_ai_manifest(
    *,
    bundle: dict[str, Any],
    packs: dict[str, dict[str, Any]],
    evidence_sha256: dict[str, str],
) -> dict[str, Any]:
    require(set(evidence_sha256) == set(packs), "every pack requires exactly one evidence payload")
    require(bundle.get("admission", {}).get("semantic_extraction") is False, "semantic extraction must remain denied")
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "pre_ai_input_manifest",
        "target": bundle["target"],
        "source_lock_id": bundle["source_lock_id"],
        "bundle_id": bundle["bundle_id"],
        "bundle_digest": bundle["bundle_digest"],
        "packs": [
            {
                "pack_id": pack_id,
                "pack_digest": packs[pack_id]["pack_digest"],
                "evidence_sha256": evidence_sha256[pack_id],
            }
            for pack_id in sorted(packs)
        ],
        "authority_boundary": {
            "input_is_manufacturer_evidence_only": True,
            "canonical_ground_truth_allowed": False,
            "production_profile_allowed": False,
            "ai_may_change_applicability_binding": False,
            "ai_may_remove_deterministic_evidence": False,
        },
        "execution": {
            "repository_ci_validates_through_context_assembly": True,
            "model_inference_required_in_repository_ci": False,
            "semantic_extraction_admission": False,
        },
    }
    manifest["manifest_digest"] = canonical_sha256(_without_digest(manifest, "manifest_digest"))
    return manifest


def validate_pre_ai_manifest(
    manifest: dict[str, Any],
    *,
    bundle: dict[str, Any],
    packs: dict[str, dict[str, Any]],
    evidence_text: dict[str, str],
) -> None:
    require(manifest.get("artifact_type") == "pre_ai_input_manifest", "pre-AI manifest artifact mismatch")
    require(manifest.get("target") == bundle.get("target"), "pre-AI target mismatch")
    require(manifest.get("bundle_digest") == bundle.get("bundle_digest"), "pre-AI bundle digest mismatch")
    require(
        manifest.get("manifest_digest") == canonical_sha256(_without_digest(manifest, "manifest_digest")),
        "pre-AI manifest digest mismatch",
    )
    listed = _by_id(manifest.get("packs", []), "pack_id", context="pre-AI packs")
    require(set(listed) == set(packs), "pre-AI pack set mismatch")
    require(set(evidence_text) == set(packs), "pre-AI evidence text set mismatch")
    for pack_id, pack in packs.items():
        require(listed[pack_id].get("pack_digest") == pack.get("pack_digest"), f"{pack_id}: pack digest mismatch")
        require(
            listed[pack_id].get("evidence_sha256") == sha256_text(evidence_text[pack_id]),
            f"{pack_id}: evidence digest mismatch",
        )
    boundary = manifest.get("authority_boundary", {})
    require(boundary.get("canonical_ground_truth_allowed") is False, "canonical ground truth must be forbidden")
    require(boundary.get("production_profile_allowed") is False, "production profile must be forbidden")
    require(boundary.get("ai_may_change_applicability_binding") is False, "AI may not change applicability")
    require(boundary.get("ai_may_remove_deterministic_evidence") is False, "AI may not remove deterministic evidence")


def assemble_model_context(
    manifest: dict[str, Any],
    *,
    packs: dict[str, dict[str, Any]],
    evidence_text: dict[str, str],
) -> str:
    validate_pre_ai_manifest(
        manifest,
        bundle={"target": manifest["target"], "bundle_digest": manifest["bundle_digest"]},
        packs=packs,
        evidence_text=evidence_text,
    )
    chunks = [
        "PLASMA PRE-AI MANUFACTURER EVIDENCE CONTEXT",
        f"TARGET: {manifest['target']}",
        f"BUNDLE_DIGEST: {manifest['bundle_digest']}",
        "AUTHORITY: manufacturer evidence only; applicability is deterministic and immutable to AI",
    ]
    for item in manifest["packs"]:
        pack_id = item["pack_id"]
        chunks.extend(
            [
                "",
                f"--- PACK {pack_id} DIGEST {item['pack_digest']} ---",
                evidence_text[pack_id].rstrip("\n"),
            ]
        )
    return "\n".join(chunks) + "\n"


def verify_and_extract_sources(
    *,
    source_dir: Path,
    definitions: dict[str, Any],
    source_lock: dict[str, Any],
) -> dict[str, list[str]]:
    units = _by_id(definitions.get("units", []), "unit_id", context="definitions")
    sources = _by_id(source_lock.get("sources", []), "source_id", context="source lock")
    required_source_ids = sorted({unit["source_id"] for unit in units.values()})
    pages_by_source: dict[str, list[str]] = {}
    for source_id in required_source_ids:
        source = sources[source_id]
        pdf = source_dir / source["local_filename"]
        require(pdf.is_file(), f"missing locked source: {pdf}")
        require(pdf.stat().st_size == source["integrity"]["byte_length"], f"{source_id}: byte length mismatch")
        require(sha256_file(pdf) == source["integrity"]["digest"], f"{source_id}: sha256 mismatch")
        pages_by_source[source_id] = extract_pages(pdf)
    return pages_by_source


def write_artifacts(
    *,
    output_dir: Path,
    packs: dict[str, dict[str, Any]],
    bundle: dict[str, Any],
    pages_by_source: dict[str, list[str]],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pack_dir = output_dir / "packs"
    evidence_dir = output_dir / "evidence"
    pack_dir.mkdir(exist_ok=True)
    evidence_dir.mkdir(exist_ok=True)

    evidence_text: dict[str, str] = {}
    evidence_sha256: dict[str, str] = {}
    for pack_id, pack in sorted(packs.items()):
        (pack_dir / f"{pack_id}.json").write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
        text = materialize_evidence_text(pack, pages_by_source)
        evidence_text[pack_id] = text
        evidence_sha256[pack_id] = sha256_text(text)
        (evidence_dir / f"{pack_id}.txt").write_text(text, encoding="utf-8")

    (output_dir / "target-bundle.json").write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    pre_ai = build_pre_ai_manifest(bundle=bundle, packs=packs, evidence_sha256=evidence_sha256)
    validate_pre_ai_manifest(pre_ai, bundle=bundle, packs=packs, evidence_text=evidence_text)
    (output_dir / "pre-ai-input.json").write_text(json.dumps(pre_ai, indent=2) + "\n", encoding="utf-8")
    context = assemble_model_context(pre_ai, packs=packs, evidence_text=evidence_text)
    (output_dir / "model-context.txt").write_text(context, encoding="utf-8")

    report = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "kl25_evidence_pack_build_report",
        "target": bundle["target"],
        "bundle_id": bundle["bundle_id"],
        "bundle_digest": bundle["bundle_digest"],
        "pack_count": len(packs),
        "pack_digests": {pack_id: pack["pack_digest"] for pack_id, pack in sorted(packs.items())},
        "evidence_sha256": dict(sorted(evidence_sha256.items())),
        "model_context_sha256": sha256_text(context),
        "manufacturer_text_in_report": False,
        "semantic_extraction_executed": False,
        "canonical_dataset_admission": False,
        "production_admission": False,
    }
    (output_dir / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic NXP KL25 Evidence Packs and the pre-AI TargetEvidenceBundle"
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--benchmark-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    here = args.benchmark_dir
    source_lock = json.loads((here / "source-lock.json").read_text(encoding="utf-8"))
    definitions = json.loads((here / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
    binding = json.loads((here / "applicability-binding.json").read_text(encoding="utf-8"))
    contract = json.loads((here / "evidence-pack-contract.json").read_text(encoding="utf-8"))
    pages_by_source = verify_and_extract_sources(
        source_dir=args.source_dir,
        definitions=definitions,
        source_lock=source_lock,
    )
    builder_sha256 = sha256_file(Path(__file__).resolve())
    packs, bundle = build_pack_set(
        contract=contract,
        definitions=definitions,
        binding=binding,
        source_lock=source_lock,
        pages_by_source=pages_by_source,
        builder_sha256=builder_sha256,
    )
    report = write_artifacts(
        output_dir=args.output_dir,
        packs=packs,
        bundle=bundle,
        pages_by_source=pages_by_source,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError, KL25EvidencePackError) as exc:
        raise SystemExit(f"KL25 Evidence Pack build FAIL: {exc}")
