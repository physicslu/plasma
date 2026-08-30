"""Generic retained-evidence integrity framework for device catalog research.

This module owns transport/vendor-neutral evidence package mechanics only:
manifest shape, exact file membership, SHA-256 integrity, immutable evidence identity,
Git/repository provenance, acquisition accounting, and the rule that retained evidence
never performs canonical admission by itself.

Manufacturer/family adapters remain responsible for source authority, transport-specific
claims, candidate extraction, deterministic reevaluation, and metadata semantics.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class EvidenceFrameworkError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceFrameworkError(message)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceFrameworkError(f"{path}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceFrameworkError(f"{path}: expected a JSON object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_manifest(
    evidence_dir: Path,
    *,
    expected_files: Iterable[str],
) -> dict[str, Any]:
    """Validate an immutable evidence package manifest without vendor assumptions."""

    require(evidence_dir.is_dir(), f"missing evidence directory: {evidence_dir}")
    expected = set(expected_files)
    require(expected and "manifest.json" not in expected, "expected evidence file set is invalid")

    manifest = read_json(evidence_dir / "manifest.json")
    require(manifest.get("schema_version") == SCHEMA_VERSION, "unsupported manifest schema_version")
    require(
        manifest.get("canonical_dataset_admission") is False,
        "manifest must deny canonical admission",
    )
    evidence_id = manifest.get("evidence_id")
    require(isinstance(evidence_id, str) and evidence_id.strip(), "manifest requires evidence_id")

    declared_files = manifest.get("files")
    require(isinstance(declared_files, list), "manifest files must be a list")
    actual_files = {path.name for path in evidence_dir.iterdir() if path.is_file()}
    require(actual_files == expected | {"manifest.json"}, "evidence directory file set is not exact")

    declared_names: set[str] = set()
    for item in declared_files:
        require(isinstance(item, dict), "manifest file entry must be an object")
        name = item.get("path")
        digest = item.get("sha256")
        require(isinstance(name, str) and name in expected, f"unexpected manifest path: {name!r}")
        require(name not in declared_names, f"duplicate manifest path: {name}")
        require(
            isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None,
            f"invalid manifest SHA-256: {name}",
        )
        path = evidence_dir / name
        require(path.is_file(), f"missing retained file: {name}")
        require(sha256(path) == digest, f"retained file digest mismatch: {name}")
        declared_names.add(name)
    require(declared_names == expected, "manifest file set is incomplete")
    return manifest


def validate_core_provenance(
    provenance: dict[str, Any],
    *,
    evidence_id: str,
    expected_repository: str | None = None,
    expected_manufacturer: str | None = None,
) -> dict[str, Any]:
    """Validate reusable provenance/accounting invariants.

    Transport names, runtime-specific metadata and manufacturer authority are opaque here.
    Adapters may impose stronger requirements after this generic gate passes.
    """

    require(provenance.get("schema_version") == SCHEMA_VERSION, "provenance schema_version mismatch")
    require(provenance.get("evidence_id") == evidence_id, "manifest/provenance evidence_id mismatch")

    manufacturer = provenance.get("manufacturer")
    repository = provenance.get("source_repository")
    git_sha = provenance.get("executed_git_sha")
    transport = provenance.get("acquisition_transport")
    require(isinstance(manufacturer, str) and manufacturer.strip(), "provenance requires manufacturer")
    require(isinstance(repository, str) and repository.strip(), "provenance requires source_repository")
    require(isinstance(git_sha, str) and GIT_SHA_RE.fullmatch(git_sha) is not None, "invalid executed Git SHA")
    require(isinstance(transport, str) and transport.strip(), "provenance requires acquisition_transport")
    require(isinstance(provenance.get("headed"), bool), "provenance headed must be boolean")
    if expected_repository is not None:
        require(repository == expected_repository, "provenance source_repository mismatch")
    if expected_manufacturer is not None:
        require(manufacturer == expected_manufacturer, "provenance manufacturer mismatch")

    target_count = provenance.get("target_count")
    successes = provenance.get("acquisition_success")
    failures = provenance.get("acquisition_failure")
    candidate_count = provenance.get("exact_icpn_candidate_count")
    require(isinstance(target_count, int) and target_count > 0, "provenance target_count must be positive")
    require(isinstance(successes, int) and successes >= 0, "provenance acquisition_success is invalid")
    require(isinstance(failures, int) and failures >= 0, "provenance acquisition_failure is invalid")
    require(successes + failures == target_count, "provenance acquisition accounting mismatch")
    require(isinstance(candidate_count, int) and candidate_count >= 0, "provenance candidate count is invalid")
    require(provenance.get("scale_ready") is True, "provenance scale_ready mismatch")
    require(
        provenance.get("canonical_dataset_admission") is False,
        "provenance canonical_dataset_admission mismatch",
    )
    evaluator_result = provenance.get("evaluator_result")
    require(isinstance(evaluator_result, str) and evaluator_result.strip(), "provenance requires evaluator_result")

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "manufacturer": manufacturer,
        "source_repository": repository,
        "executed_git_sha": git_sha,
        "acquisition_transport": transport,
        "headed": provenance["headed"],
        "target_count": target_count,
        "acquisition_success": successes,
        "acquisition_failure": failures,
        "exact_icpn_candidate_count": candidate_count,
        "evaluator_result": evaluator_result,
        "scale_ready": True,
        "canonical_dataset_admission": False,
    }


def build_manifest(
    evidence_dir: Path,
    *,
    evidence_id: str,
    retained_files: Iterable[str],
) -> dict[str, Any]:
    """Build a deterministic manifest for files already written in evidence_dir."""

    require(isinstance(evidence_id, str) and evidence_id.strip(), "evidence_id must be non-empty")
    names = sorted(set(retained_files))
    require(names and "manifest.json" not in names, "retained file set is invalid")
    entries: list[dict[str, str]] = []
    for name in names:
        path = evidence_dir / name
        require(path.is_file(), f"missing retained file: {name}")
        entries.append({"path": name, "sha256": sha256(path)})
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "canonical_dataset_admission": False,
        "files": entries,
    }
