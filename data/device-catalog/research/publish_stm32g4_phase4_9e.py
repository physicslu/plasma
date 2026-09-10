#!/usr/bin/env python3
"""Controlled STM32G4 Phase 4.9E canonical + Production publication transaction.

The publisher consumes only the frozen Phase 4.9D admission plan. A clean
publication changes catalog identity availability; it does not establish Flash
algorithm/geometry equivalence, option/security semantics, physical/HIL
qualification, or runtime programming support.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import file_sha256, write_canonical_dataset
from stm32g4_admission_policy import CANONICAL_FIELDS
from stm32g4_metadata_policy import EXPECTED_PROPOSAL_EXCLUSIONS, SOURCE_UNAVAILABLE_BASES
from stm32g4_phase4_9d_admission import admission_plan_is_clean

HERE = Path(__file__).resolve().parent
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PLAN_PATH = HERE / "stm32g4-phase4.9d-admission-plan.json"
CANONICAL_PATH = HERE / "stm32g4-commercial-icpn.csv"
PROPOSAL_PATH = HERE / "stm32g4-phase4.9e-publication-proposal.json"
AUDIT_PATH = HERE / "stm32g4-phase4.9e-publication-audit.json"

EXPECTED_PLAN_SHA256 = "4ba41c97414ca4eb45b069f08b0200e2e53faaaed2cd5e4e57e7ac260d3d1291"
EXPECTED_PRESTATE_MANIFEST_SHA256 = "0dbb7df5a3ddc771326507fb42a47416d892d1d17f4e4141dde37cde23e95ddf"
EXPECTED_PRESTATE_EXACT = 610
EXPECTED_PRESTATE_BASES = 209
EXPECTED_PRESTATE_FAMILIES = 7
EXPECTED_PUBLISHED_ROWS = 25
EXPECTED_PUBLISHED_BASES = 8
EXPECTED_POSTSTATE_EXACT = 635
EXPECTED_POSTSTATE_BASES = 217
EXPECTED_POSTSTATE_FAMILIES = 8


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _write_empty_canonical(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS), lineterminator="\n").writeheader()


def _read_plan() -> dict[str, Any]:
    if file_sha256(PLAN_PATH) != EXPECTED_PLAN_SHA256:
        raise RuntimeError("Phase 4.9D frozen admission-plan digest drifted")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if not admission_plan_is_clean(plan):
        raise RuntimeError("Phase 4.9D frozen admission plan is not clean")
    if plan.get("candidate_count") != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("Phase 4.9D candidate count drifted")
    if plan.get("capability_unresolved_count") != 0 or plan.get("capability_unresolved") != []:
        raise RuntimeError("Phase 4.9D capability-unresolved boundary drifted")
    if plan.get("bounded_commercial_surface_complete") is not False:
        raise RuntimeError("Phase 4.9B current-source gaps were incorrectly erased")
    if plan.get("source_unavailable_base_devices") != sorted(SOURCE_UNAVAILABLE_BASES):
        raise RuntimeError("source-unavailable Base Device set drifted")
    if plan.get("proposal_exact_identity_exclusions") != sorted(EXPECTED_PROPOSAL_EXCLUSIONS):
        raise RuntimeError("Proposal exclusion set drifted")
    return plan


def _production_snapshot(manifest: dict[str, Any], manifest_path: Path) -> tuple[int, int, dict[str, int]]:
    family_counts: dict[str, int] = {}
    bases: set[tuple[str, str]] = set()
    for source in manifest.get("sources", []):
        family = source["family"]
        path = (manifest_path.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        data = path.read_bytes()
        if len(rows) != source["row_count"]:
            raise RuntimeError(f"{family}: manifest row count mismatch")
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise RuntimeError(f"{family}: manifest source SHA-256 mismatch")
        if _git_blob_sha(data) != source["git_blob_sha"]:
            raise RuntimeError(f"{family}: manifest source Git blob mismatch")
        family_counts[family] = len(rows)
        bases.update((family, row["base_device"]) for row in rows)
    return sum(family_counts.values()), len(bases), family_counts


def _proposed_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows = [
        item.get("proposed_canonical_row")
        for item in plan["candidates"]
        if item.get("decision") == "admit"
    ]
    if len(rows) != EXPECTED_PUBLISHED_ROWS or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("Phase 4.9D proposed canonical row set drifted")
    if len({row["icpn"] for row in rows}) != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("proposed STM32G4 exact identities are duplicated")
    if len({row["base_device"] for row in rows}) != EXPECTED_PUBLISHED_BASES:
        raise RuntimeError("proposed STM32G4 Base Device count drifted")
    if any(row["family"] != "STM32G4" for row in rows):
        raise RuntimeError("foreign family leaked into STM32G4 publication")
    if any(row["openocd_target_config"] != "tcl/target/stm32g4x.cfg" for row in rows):
        raise RuntimeError("proposed STM32G4 route target drifted")
    if any(row["existing_identifier_kind"] != "ordering_pattern" for row in rows):
        raise RuntimeError("non-ordering-pattern mapping leaked into publication")
    if any(row["cmsis_device_name"] != "" for row in rows):
        raise RuntimeError("CMSIS alias leaked into canonical commercial identity")
    return rows  # type: ignore[return-value]


def _render_canonical(plan: dict[str, Any]) -> tuple[bytes, str, str]:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "stm32g4-commercial-icpn.csv"
        _write_empty_canonical(path)
        result = write_canonical_dataset(plan=plan, canonical_path=path)
        if result.get("status") != "written" or result.get("rows_after") != EXPECTED_PUBLISHED_ROWS:
            raise RuntimeError("canonical writer did not render exactly 25 STM32G4 rows")
        data = path.read_bytes()
    return data, hashlib.sha256(data).hexdigest(), _git_blob_sha(data)


def _build_post_manifest(
    manifest: dict[str, Any], *, canonical_sha: str, canonical_blob: str
) -> tuple[dict[str, Any], bytes, str]:
    post = json.loads(json.dumps(manifest))
    post["sources"].append({
        "manufacturer": "STMicroelectronics",
        "family": "STM32G4",
        "path": "../research/stm32g4-commercial-icpn.csv",
        "row_count": EXPECTED_PUBLISHED_ROWS,
        "git_blob_sha": canonical_blob,
        "sha256": canonical_sha,
    })
    data = (json.dumps(post, indent=2) + "\n").encode("utf-8")
    return post, data, hashlib.sha256(data).hexdigest()


def build_proposal() -> dict[str, Any]:
    plan = _read_plan()
    if file_sha256(PRODUCTION_MANIFEST) != EXPECTED_PRESTATE_MANIFEST_SHA256:
        raise RuntimeError("Production manifest prestate drifted before Phase 4.9E")
    if CANONICAL_PATH.exists():
        raise RuntimeError("Phase 4.9E proposal requires STM32G4 canonical dataset absent")
    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    if any(source.get("family") == "STM32G4" for source in manifest.get("sources", [])):
        raise RuntimeError("STM32G4 already exists in Production prestate")
    before_exact, before_bases, before_families = _production_snapshot(manifest, PRODUCTION_MANIFEST)
    if (
        before_exact != EXPECTED_PRESTATE_EXACT
        or before_bases != EXPECTED_PRESTATE_BASES
        or len(before_families) != EXPECTED_PRESTATE_FAMILIES
    ):
        raise RuntimeError("Production aggregate prestate drifted")

    rows = _proposed_rows(plan)
    canonical_bytes, canonical_sha, canonical_blob = _render_canonical(plan)
    post_manifest, manifest_bytes, manifest_sha = _build_post_manifest(
        manifest, canonical_sha=canonical_sha, canonical_blob=canonical_blob
    )

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        canonical_tmp = root / "stm32g4-commercial-icpn.csv"
        manifest_tmp_dir = root / "production"
        manifest_tmp_dir.mkdir()
        manifest_tmp = manifest_tmp_dir / "icpn-v1-manifest.json"
        research_tmp = root / "research"
        research_tmp.mkdir()
        canonical_for_manifest = research_tmp / "stm32g4-commercial-icpn.csv"
        canonical_for_manifest.write_bytes(canonical_bytes)
        # Snapshot poststate structurally without trusting guessed totals. Existing source
        # paths cannot resolve in the temporary tree, so compute new totals from verified prestate.
        after_family_counts = dict(before_families)
        after_family_counts["STM32G4"] = EXPECTED_PUBLISHED_ROWS
        after_exact = before_exact + EXPECTED_PUBLISHED_ROWS
        after_bases = before_bases + EXPECTED_PUBLISHED_BASES
        after_family_count = len(after_family_counts)
        canonical_tmp.write_bytes(canonical_bytes)
        manifest_tmp.write_bytes(manifest_bytes)
        _ = post_manifest

    if (
        after_exact != EXPECTED_POSTSTATE_EXACT
        or after_bases != EXPECTED_POSTSTATE_BASES
        or after_family_count != EXPECTED_POSTSTATE_FAMILIES
    ):
        raise RuntimeError("proposed Production aggregate poststate drifted")

    return {
        "schema_version": 1,
        "phase": "4.9E",
        "family": "STM32G4",
        "status": "publication_proposal_clean",
        "admission_plan_sha256": EXPECTED_PLAN_SHA256,
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "canonical_csv_file_sha256_proposed": canonical_sha,
        "canonical_csv_git_blob_sha_proposed": canonical_blob,
        "production_manifest_sha256_proposed": manifest_sha,
        "manufacturer_verified_identity_count": 25,
        "published_exact_icpn_count_proposed": EXPECTED_PUBLISHED_ROWS,
        "published_base_device_count_proposed": EXPECTED_PUBLISHED_BASES,
        "added_exact_icpns": sorted(row["icpn"] for row in rows),
        "source_unavailable_base_devices": sorted(SOURCE_UNAVAILABLE_BASES),
        "proposal_exact_identity_exclusions": sorted(EXPECTED_PROPOSAL_EXCLUSIONS),
        "bounded_commercial_surface_complete": False,
        "capability_unresolved_count": 0,
        "production_exact_icpns_before": before_exact,
        "production_exact_icpns_after_proposed": after_exact,
        "production_base_devices_before": before_bases,
        "production_base_devices_after_proposed": after_bases,
        "production_family_count_before": len(before_families),
        "production_family_count_after_proposed": after_family_count,
        "canonical_write_applied": False,
        "production_write_applied": False,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_equivalence_claimed": False,
        "option_security_semantics_claimed": False,
        "physical_target_qualification_claimed": False,
        "hil_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
        "full_stm32g4_surface_covered": False,
    }


def _proposal_digest(proposal: dict[str, Any]) -> str:
    payload = json.dumps(proposal, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def publish() -> dict[str, Any]:
    proposal = build_proposal()
    if not PROPOSAL_PATH.exists():
        raise RuntimeError("frozen Phase 4.9E publication proposal is missing")
    frozen_proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
    if proposal != frozen_proposal:
        raise RuntimeError("Phase 4.9E publication proposal drifted before apply")
    proposal_sha = file_sha256(PROPOSAL_PATH)

    plan = _read_plan()
    canonical_bytes, canonical_sha, canonical_blob = _render_canonical(plan)
    if canonical_sha != proposal["canonical_csv_file_sha256_proposed"]:
        raise RuntimeError("canonical rendering drifted from frozen proposal")
    if canonical_blob != proposal["canonical_csv_git_blob_sha_proposed"]:
        raise RuntimeError("canonical Git blob drifted from frozen proposal")

    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    before_exact, before_bases, before_families = _production_snapshot(manifest, PRODUCTION_MANIFEST)
    post_manifest, manifest_bytes, manifest_sha = _build_post_manifest(
        manifest, canonical_sha=canonical_sha, canonical_blob=canonical_blob
    )
    if manifest_sha != proposal["production_manifest_sha256_proposed"]:
        raise RuntimeError("Production manifest rendering drifted from frozen proposal")

    CANONICAL_PATH.write_bytes(canonical_bytes)
    PRODUCTION_MANIFEST.write_bytes(manifest_bytes)
    after_exact, after_bases, after_families = _production_snapshot(post_manifest, PRODUCTION_MANIFEST)
    if (
        after_exact != EXPECTED_POSTSTATE_EXACT
        or after_bases != EXPECTED_POSTSTATE_BASES
        or len(after_families) != EXPECTED_POSTSTATE_FAMILIES
        or after_families.get("STM32G4") != EXPECTED_PUBLISHED_ROWS
    ):
        raise RuntimeError("Production poststate is not expected 635/217/8-family state")

    audit = {
        "schema_version": 1,
        "phase": "4.9E",
        "family": "STM32G4",
        "status": "published",
        "admission_plan_sha256": EXPECTED_PLAN_SHA256,
        "publication_proposal_sha256": proposal_sha,
        "canonical_csv_file_sha256": canonical_sha,
        "canonical_csv_git_blob_sha": canonical_blob,
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "production_manifest_sha256_after": manifest_sha,
        "manufacturer_verified_identity_count": 25,
        "published_exact_icpn_count": EXPECTED_PUBLISHED_ROWS,
        "added_exact_icpns": proposal["added_exact_icpns"],
        "stm32g4_rows_before": 0,
        "stm32g4_rows_after": EXPECTED_PUBLISHED_ROWS,
        "stm32g4_base_devices_after": EXPECTED_PUBLISHED_BASES,
        "production_exact_icpns_before": before_exact,
        "production_exact_icpns_after": after_exact,
        "production_base_devices_before": before_bases,
        "production_base_devices_after": after_bases,
        "production_family_count_before": len(before_families),
        "production_family_count_after": len(after_families),
        "source_unavailable_base_devices": sorted(SOURCE_UNAVAILABLE_BASES),
        "proposal_exact_identity_exclusions": sorted(EXPECTED_PROPOSAL_EXCLUSIONS),
        "bounded_commercial_surface_complete": False,
        "capability_unresolved_count": 0,
        "capability_unresolved": [],
        "canonical_write_applied": True,
        "production_write_applied": True,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_equivalence_claimed": False,
        "option_security_semantics_claimed": False,
        "physical_target_qualification_claimed": False,
        "hil_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
        "full_stm32g4_surface_covered": False,
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", action="store_true", help="print deterministic publication proposal without repository writes")
    parser.add_argument("--write-proposal", action="store_true", help="write deterministic proposal JSON only")
    args = parser.parse_args()
    if args.proposal or args.write_proposal:
        proposal = build_proposal()
        payload = json.dumps(proposal, indent=2, sort_keys=True) + "\n"
        if args.write_proposal:
            PROPOSAL_PATH.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0
    print(json.dumps(publish(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
