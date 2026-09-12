#!/usr/bin/env python3
"""Controlled STM32L0 L0.5 canonical + Production publication transaction.

L0.5 publishes only the 360 exact ICPNs frozen as capability-admittable by
L0.4. Publication changes Device Catalog identity availability only. It does
not establish Flash algorithm/geometry equivalence, option/security semantics,
PPU/Socket/electrical/HIL qualification, or runtime programming support.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import file_sha256
from stm32l0_admission_policy import CANONICAL_FIELDS, TARGET_CONFIG, build_canonical_row
from stm32l0_metadata_policy import build_candidate_inputs
from stm32l0_phase_l0_1_foundation import DEFAULT_CATALOG, read_catalog
from stm32l0_phase_l0_2_discovery import resolve_mapping

HERE = Path(__file__).resolve().parent
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST = HERE / "stm32l0-phase-l0.4-production-manifest-prestate.json"
PLAN_PATH = HERE / "stm32l0-phase-l0.4-admission-plan.json"
CANONICAL_PATH = HERE / "stm32l0-commercial-icpn.csv"
PROPOSAL_PATH = HERE / "stm32l0-phase-l0.5-publication-proposal.json"
AUDIT_PATH = HERE / "stm32l0-phase-l0.5-publication-audit.json"
BASELINE_PATH = HERE / "stm32l0-phase-l0.5-publication-baseline.json"

PHASE = "L0.5"
FAMILY = "STM32L0"
EXPECTED_PLAN_GIT_BLOB = "d46b7491ca34fa9d5c8b3adfb16709e9698e417e"
EXPECTED_PRESTATE_MANIFEST_SHA256 = "15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420"
EXPECTED_PRESTATE_MANIFEST_BLOB = "8abfcc870e51ac4232cdf8d807828cfe4ff5662d"
EXPECTED_MAPPING_CATALOG_GIT_BLOB = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_EXACT_SET_SHA256 = "8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b"
EXPECTED_PUBLISHED_ROWS = 360
EXPECTED_PUBLISHED_BASES = 99
EXPECTED_PRESTATE = (912, 293, 10)
EXPECTED_POSTSTATE = (1272, 392, 11)


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()


def _json_bytes(value: dict[str, Any], *, sort_keys: bool = True) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=sort_keys) + "\n").encode("utf-8")


def _set_sha(values: list[str] | set[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name}: expected JSON object")
    return value


def _production_snapshot(manifest_path: Path) -> tuple[int, set[tuple[str, str]], dict[str, int]]:
    manifest = _read_json(manifest_path)
    family_counts: dict[str, int] = {}
    bases: set[tuple[str, str]] = set()
    for source in manifest.get("sources", []):
        if not isinstance(source, dict):
            raise RuntimeError("Production manifest source must be object")
        family = source.get("family")
        path_value = source.get("path")
        if not isinstance(family, str) or not isinstance(path_value, str):
            raise RuntimeError("Production manifest source identity is incomplete")
        path = (manifest_path.parent / path_value).resolve()
        data = path.read_bytes()
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != source.get("row_count"):
            raise RuntimeError(f"{family}: manifest row_count mismatch")
        if hashlib.sha256(data).hexdigest() != source.get("sha256"):
            raise RuntimeError(f"{family}: manifest source SHA-256 mismatch")
        if _git_blob_sha(data) != source.get("git_blob_sha"):
            raise RuntimeError(f"{family}: manifest source Git blob mismatch")
        if any(row.get("family") != family for row in rows):
            raise RuntimeError(f"{family}: source contains foreign-family row")
        if family in family_counts:
            raise RuntimeError(f"{family}: duplicate Production source")
        family_counts[family] = len(rows)
        bases.update((family, row["base_device"]) for row in rows)
    return sum(family_counts.values()), bases, family_counts


def _validate_frozen_inputs() -> dict[str, Any]:
    if _git_blob_sha(PLAN_PATH.read_bytes()) != EXPECTED_PLAN_GIT_BLOB:
        raise RuntimeError("frozen L0.4 admission-plan bytes drifted")
    frozen = _read_json(PLAN_PATH)
    if (
        frozen.get("phase") != "L0.4"
        or frozen.get("family") != FAMILY
        or frozen.get("capability_admittable_count") != EXPECTED_PUBLISHED_ROWS
        or frozen.get("capability_unresolved_count") != 0
        or frozen.get("current_mapping_replay") != {"ambiguous": 0, "unique": 360, "unmapped": 0}
        or frozen.get("decision_counts") != {
            "admit": 360,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        }
    ):
        raise RuntimeError("frozen L0.4 admission semantics drifted")
    inputs = frozen.get("inputs") or {}
    if inputs.get("policy_ready_exact_icpn_set_sha256") != EXPECTED_EXACT_SET_SHA256:
        raise RuntimeError("L0.4 admitted exact-set binding drifted")
    if inputs.get("mapping_catalog_git_blob_sha") != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
        raise RuntimeError("L0.4 OpenOCD catalog binding drifted")
    if inputs.get("production_manifest_git_blob_sha") != EXPECTED_PRESTATE_MANIFEST_BLOB:
        raise RuntimeError("L0.4 Production prestate binding drifted")
    if file_sha256(PRESTATE_MANIFEST) != EXPECTED_PRESTATE_MANIFEST_SHA256:
        raise RuntimeError("L0.5 frozen Production prestate SHA-256 drifted")
    if _git_blob_sha(PRESTATE_MANIFEST.read_bytes()) != EXPECTED_PRESTATE_MANIFEST_BLOB:
        raise RuntimeError("L0.5 frozen Production prestate Git blob drifted")
    if _git_blob_sha(DEFAULT_CATALOG.read_bytes()) != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
        raise RuntimeError("current OpenOCD catalog bytes drifted before publication")
    return frozen


def _historical_canonical_rows() -> list[dict[str, str]]:
    _validate_frozen_inputs()
    catalog_rows = read_catalog(DEFAULT_CATALOG)
    rows: list[dict[str, str]] = []
    identities: set[str] = set()
    for source_candidate in build_candidate_inputs():
        candidate = dict(source_candidate)
        icpn = candidate.get("icpn")
        if not isinstance(icpn, str) or icpn in identities:
            raise RuntimeError(f"invalid/duplicate retained L0 candidate: {icpn}")
        identities.add(icpn)
        mapping = resolve_mapping(icpn, catalog_rows)
        if mapping.get("status") != "unique" or mapping.get("target_config") != TARGET_CONFIG:
            raise RuntimeError(f"{icpn}: L0.4 positive OpenOCD route no longer replays")
        candidate["base_mapping"] = mapping
        row = build_canonical_row(candidate, list(CANONICAL_FIELDS))
        if row.get("icpn") != icpn:
            raise RuntimeError(f"{icpn}: canonical identity changed during rendering")
        rows.append(row)
    rows.sort(key=lambda row: (row["manufacturer"], row["base_device"], row["icpn"]))
    if len(rows) != EXPECTED_PUBLISHED_ROWS or len(identities) != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("L0.5 canonical render cardinality drifted")
    if len({row["base_device"] for row in rows}) != EXPECTED_PUBLISHED_BASES:
        raise RuntimeError("L0.5 Base Device cardinality drifted")
    if _set_sha(identities) != EXPECTED_EXACT_SET_SHA256:
        raise RuntimeError("L0.5 exact published set drifted from L0.4")
    if any(row["family"] != FAMILY for row in rows):
        raise RuntimeError("L0.5 canonical render contains foreign-family row")
    return rows


def _render_canonical_bytes(rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(CANONICAL_FIELDS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _build_post_manifest(canonical_bytes: bytes) -> bytes:
    manifest = _read_json(PRESTATE_MANIFEST)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("Production prestate sources missing")
    if any(isinstance(source, dict) and source.get("family") == FAMILY for source in sources):
        raise RuntimeError("STM32L0 unexpectedly exists in frozen Production prestate")
    sources.append({
        "manufacturer": "STMicroelectronics",
        "family": FAMILY,
        "path": "../research/stm32l0-commercial-icpn.csv",
        "row_count": EXPECTED_PUBLISHED_ROWS,
        "git_blob_sha": _git_blob_sha(canonical_bytes),
        "sha256": hashlib.sha256(canonical_bytes).hexdigest(),
    })
    return _json_bytes(manifest, sort_keys=False)


def build_proposal() -> dict[str, Any]:
    before_exact, before_bases, before_families = _production_snapshot(PRESTATE_MANIFEST)
    if (before_exact, len(before_bases), len(before_families)) != EXPECTED_PRESTATE:
        raise RuntimeError("Production aggregate prestate drifted")
    if FAMILY in before_families:
        raise RuntimeError("STM32L0 unexpectedly exists in Production prestate")
    rows = _historical_canonical_rows()
    canonical_bytes = _render_canonical_bytes(rows)
    manifest_bytes = _build_post_manifest(canonical_bytes)
    added_bases = {(FAMILY, row["base_device"]) for row in rows}
    poststate = (before_exact + len(rows), len(before_bases | added_bases), len(before_families) + 1)
    if poststate != EXPECTED_POSTSTATE:
        raise RuntimeError(f"proposed Production poststate drifted: {poststate}")
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "status": "publication_proposal_clean",
        "admission_plan_git_blob_sha": EXPECTED_PLAN_GIT_BLOB,
        "admission_plan_sha256": file_sha256(PLAN_PATH),
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "production_manifest_git_blob_sha_before": EXPECTED_PRESTATE_MANIFEST_BLOB,
        "canonical_csv_file_sha256_proposed": hashlib.sha256(canonical_bytes).hexdigest(),
        "canonical_csv_git_blob_sha_proposed": _git_blob_sha(canonical_bytes),
        "production_manifest_sha256_proposed": hashlib.sha256(manifest_bytes).hexdigest(),
        "production_manifest_git_blob_sha_proposed": _git_blob_sha(manifest_bytes),
        "manufacturer_verified_identity_count": EXPECTED_PUBLISHED_ROWS,
        "metadata_ready_identity_count": EXPECTED_PUBLISHED_ROWS,
        "capability_admittable_count": EXPECTED_PUBLISHED_ROWS,
        "published_exact_icpn_count_proposed": EXPECTED_PUBLISHED_ROWS,
        "published_base_device_count_proposed": EXPECTED_PUBLISHED_BASES,
        "added_exact_icpns": [row["icpn"] for row in rows],
        "added_exact_icpn_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "bounded_commercial_surface_complete": True,
        "published_surface_partial_due_to_capability": False,
        "capability_unresolved_count": 0,
        "capability_unresolved_exact_icpns": [],
        "production_exact_icpns_before": EXPECTED_PRESTATE[0],
        "production_exact_icpns_after_proposed": EXPECTED_POSTSTATE[0],
        "production_base_devices_before": EXPECTED_PRESTATE[1],
        "production_base_devices_after_proposed": EXPECTED_POSTSTATE[1],
        "production_family_count_before": EXPECTED_PRESTATE[2],
        "production_family_count_after_proposed": EXPECTED_POSTSTATE[2],
        "canonical_write_applied": False,
        "production_write_applied": False,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_equivalence_claimed": False,
        "option_security_semantics_claimed": False,
        "physical_target_qualification_claimed": False,
        "ppu_physical_validation_claimed": False,
        "socket_physical_validation_claimed": False,
        "hil_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
    }


def _build_audit(proposal: dict[str, Any], canonical_bytes: bytes, manifest_bytes: bytes) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "status": "published",
        "admission_plan_git_blob_sha": EXPECTED_PLAN_GIT_BLOB,
        "admission_plan_sha256": file_sha256(PLAN_PATH),
        "publication_proposal_sha256": hashlib.sha256(_json_bytes(proposal)).hexdigest(),
        "canonical_csv_file_sha256": hashlib.sha256(canonical_bytes).hexdigest(),
        "canonical_csv_git_blob_sha": _git_blob_sha(canonical_bytes),
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "production_manifest_git_blob_sha_before": EXPECTED_PRESTATE_MANIFEST_BLOB,
        "production_manifest_sha256_after": hashlib.sha256(manifest_bytes).hexdigest(),
        "production_manifest_git_blob_sha_after": _git_blob_sha(manifest_bytes),
        "manufacturer_verified_identity_count": EXPECTED_PUBLISHED_ROWS,
        "metadata_ready_identity_count": EXPECTED_PUBLISHED_ROWS,
        "capability_admittable_count": EXPECTED_PUBLISHED_ROWS,
        "published_exact_icpn_count": EXPECTED_PUBLISHED_ROWS,
        "published_base_device_count": EXPECTED_PUBLISHED_BASES,
        "added_exact_icpns": proposal["added_exact_icpns"],
        "added_exact_icpn_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "stm32l0_rows_before": 0,
        "stm32l0_rows_after": EXPECTED_PUBLISHED_ROWS,
        "stm32l0_base_devices_after": EXPECTED_PUBLISHED_BASES,
        "production_exact_icpns_before": EXPECTED_PRESTATE[0],
        "production_exact_icpns_after": EXPECTED_POSTSTATE[0],
        "production_base_devices_before": EXPECTED_PRESTATE[1],
        "production_base_devices_after": EXPECTED_POSTSTATE[1],
        "production_family_count_before": EXPECTED_PRESTATE[2],
        "production_family_count_after": EXPECTED_POSTSTATE[2],
        "bounded_commercial_surface_complete": True,
        "published_surface_partial_due_to_capability": False,
        "capability_unresolved_count": 0,
        "capability_unresolved_exact_icpns": [],
        "canonical_write_applied": True,
        "production_write_applied": True,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_equivalence_claimed": False,
        "option_security_semantics_claimed": False,
        "physical_target_qualification_claimed": False,
        "ppu_physical_validation_claimed": False,
        "socket_physical_validation_claimed": False,
        "hil_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
    }


def _build_baseline(proposal_bytes: bytes, audit_bytes: bytes, canonical_bytes: bytes, manifest_bytes: bytes) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "status": "publication_hard_lock",
        "admission_plan_git_blob_sha": EXPECTED_PLAN_GIT_BLOB,
        "admission_plan_sha256": file_sha256(PLAN_PATH),
        "prestate_manifest_git_blob_sha": EXPECTED_PRESTATE_MANIFEST_BLOB,
        "prestate_manifest_sha256": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "mapping_catalog_git_blob_sha": EXPECTED_MAPPING_CATALOG_GIT_BLOB,
        "published_exact_icpn_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "published_exact_icpn_count": EXPECTED_PUBLISHED_ROWS,
        "published_base_device_count": EXPECTED_PUBLISHED_BASES,
        "canonical_csv_git_blob_sha": _git_blob_sha(canonical_bytes),
        "canonical_csv_sha256": hashlib.sha256(canonical_bytes).hexdigest(),
        "publication_proposal_git_blob_sha": _git_blob_sha(proposal_bytes),
        "publication_proposal_sha256": hashlib.sha256(proposal_bytes).hexdigest(),
        "publication_audit_git_blob_sha": _git_blob_sha(audit_bytes),
        "publication_audit_sha256": hashlib.sha256(audit_bytes).hexdigest(),
        "production_manifest_git_blob_sha_after": _git_blob_sha(manifest_bytes),
        "production_manifest_sha256_after": hashlib.sha256(manifest_bytes).hexdigest(),
        "production_prestate": {"exact_icpns": 912, "base_devices": 293, "families": 10, "stm32l0": 0},
        "production_poststate": {"exact_icpns": 1272, "base_devices": 392, "families": 11, "stm32l0": 360},
        "claims": {
            "programming_algorithm_equivalence_claimed": False,
            "flash_geometry_equivalence_claimed": False,
            "option_security_semantics_claimed": False,
            "physical_target_qualification_claimed": False,
            "ppu_physical_validation_claimed": False,
            "socket_physical_validation_claimed": False,
            "hil_qualification_claimed": False,
            "runtime_programming_support_claimed": False,
        },
    }


def _expected_publication_bytes() -> tuple[bytes, bytes, bytes, bytes, bytes]:
    proposal = build_proposal()
    rows = _historical_canonical_rows()
    canonical_bytes = _render_canonical_bytes(rows)
    manifest_bytes = _build_post_manifest(canonical_bytes)
    proposal_bytes = _json_bytes(proposal)
    audit = _build_audit(proposal, canonical_bytes, manifest_bytes)
    audit_bytes = _json_bytes(audit)
    baseline = _build_baseline(proposal_bytes, audit_bytes, canonical_bytes, manifest_bytes)
    baseline_bytes = _json_bytes(baseline)
    return canonical_bytes, proposal_bytes, audit_bytes, baseline_bytes, manifest_bytes


def verify_current_publication() -> dict[str, Any]:
    canonical_bytes, proposal_bytes, audit_bytes, baseline_bytes, historical_manifest_bytes = _expected_publication_bytes()
    expected_files = {
        CANONICAL_PATH: canonical_bytes,
        PROPOSAL_PATH: proposal_bytes,
        AUDIT_PATH: audit_bytes,
        BASELINE_PATH: baseline_bytes,
    }
    for path, expected in expected_files.items():
        if not path.exists() or path.read_bytes() != expected:
            raise RuntimeError(f"{path.name}: published bytes drifted")

    current = _read_json(PRODUCTION_MANIFEST)
    sources = current.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("current Production manifest sources missing")
    l0_sources = [source for source in sources if isinstance(source, dict) and source.get("family") == FAMILY]
    if len(l0_sources) != 1:
        raise RuntimeError("current Production manifest must contain exactly one STM32L0 source")
    expected_source = {
        "manufacturer": "STMicroelectronics",
        "family": FAMILY,
        "path": "../research/stm32l0-commercial-icpn.csv",
        "row_count": EXPECTED_PUBLISHED_ROWS,
        "git_blob_sha": _git_blob_sha(canonical_bytes),
        "sha256": hashlib.sha256(canonical_bytes).hexdigest(),
    }
    if l0_sources[0] != expected_source:
        raise RuntimeError("current STM32L0 Production source drifted")

    exact, bases, families = _production_snapshot(PRODUCTION_MANIFEST)
    if exact < EXPECTED_POSTSTATE[0] or len(bases) < EXPECTED_POSTSTATE[1] or len(families) < EXPECTED_POSTSTATE[2]:
        raise RuntimeError("current Production state regressed below L0.5 poststate")
    if families.get(FAMILY) != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("published STM32L0 Production row count drifted")
    if (exact, len(bases), len(families)) == EXPECTED_POSTSTATE and PRODUCTION_MANIFEST.read_bytes() != historical_manifest_bytes:
        raise RuntimeError("L0.5 exact poststate manifest bytes drifted")
    return {
        "status": "valid",
        "phase": PHASE,
        "published_exact_icpns": EXPECTED_PUBLISHED_ROWS,
        "published_base_devices": EXPECTED_PUBLISHED_BASES,
        "production_exact_icpns": exact,
        "production_base_devices": len(bases),
        "production_family_count": len(families),
        "stm32l0_production": families.get(FAMILY),
    }


def publish() -> dict[str, Any]:
    current = _read_json(PRODUCTION_MANIFEST)
    if any(isinstance(source, dict) and source.get("family") == FAMILY for source in current.get("sources", [])):
        verify_current_publication()
        return {"status": "no_op_already_published", "published_exact_icpns": EXPECTED_PUBLISHED_ROWS}
    if PRODUCTION_MANIFEST.read_bytes() != PRESTATE_MANIFEST.read_bytes():
        raise RuntimeError("current Production manifest drifted from L0.5 frozen prestate")

    canonical_bytes, proposal_bytes, audit_bytes, baseline_bytes, manifest_bytes = _expected_publication_bytes()
    CANONICAL_PATH.write_bytes(canonical_bytes)
    PROPOSAL_PATH.write_bytes(proposal_bytes)
    AUDIT_PATH.write_bytes(audit_bytes)
    BASELINE_PATH.write_bytes(baseline_bytes)
    PRODUCTION_MANIFEST.write_bytes(manifest_bytes)
    summary = verify_current_publication()
    return {"status": "published", **summary}


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--publish", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.publish:
        result = publish()
    elif args.verify:
        result = verify_current_publication()
    else:
        result = build_proposal()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
