#!/usr/bin/env python3
"""Controlled STM32U0 U0.5 canonical + Production publication transaction.

U0.5 consumes only the frozen U0.4 admission plan and the immutable U0.3
Production prestate. Publication changes Device Catalog identity availability;
it does not establish Flash algorithm/geometry equivalence, option/security
semantics, physical/HIL qualification, or runtime programming support.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import file_sha256, write_canonical_dataset
from stm32u0_admission_policy import CANONICAL_FIELDS
from stm32u0_phase_u0_4_admission import (
    admission_plan_is_clean,
    admission_summary,
    build_admission_plan,
)

HERE = Path(__file__).resolve().parent
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST = HERE / "stm32u0-phase-u0.3-production-manifest-prestate.json"
PLAN_PATH = HERE / "stm32u0-phase-u0.4-admission-plan.json"
CANONICAL_PATH = HERE / "stm32u0-commercial-icpn.csv"
PROPOSAL_PATH = HERE / "stm32u0-phase-u0.5-publication-proposal.json"
AUDIT_PATH = HERE / "stm32u0-phase-u0.5-publication-audit.json"

EXPECTED_PLAN_SHA256 = "525fc7301c470fbf3f38b4ddb5d1a4effac5c47da343b1ca43654d6278bbbe94"
EXPECTED_PRESTATE_MANIFEST_SHA256 = "93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d"
EXPECTED_PRESTATE_MANIFEST_BLOB = "34ad9299ff0c063a8c8b5de1c253dfee47b63428"
EXPECTED_CANONICAL_SHA256 = "6a18ec5c8501e08a3bedd3a7bc21fdb8ece1afb4c92464aadc0d7aecfc944a75"
EXPECTED_CANONICAL_BLOB = "df9f8901e0d455dd2da497c5c0ec347f8052eb1b"
EXPECTED_PROPOSAL_SHA256 = "3518b3c8f42f670e5b50c46ebe7daa42b3eb58452d9c00fd9fd2e313a5900bda"
EXPECTED_AUDIT_SHA256 = "67995a36adef4ceeac91ea3afb1bf505941f6e0d36a0748da935e314133a4ef5"
EXPECTED_POST_MANIFEST_SHA256 = "903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0"
EXPECTED_POST_MANIFEST_BLOB = "89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc"
EXPECTED_PUBLISHED_ROWS = 68
EXPECTED_PUBLISHED_BASES = 26
EXPECTED_PRESTATE = (635, 217, 8)
EXPECTED_POSTSTATE = (703, 243, 9)


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _json_bytes(value: dict[str, Any], *, sort_keys: bool) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=sort_keys) + "\n").encode("utf-8")


def _write_empty_canonical(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS), lineterminator="\n").writeheader()


def _production_snapshot(manifest_path: Path) -> tuple[int, set[tuple[str, str]], dict[str, int]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    family_counts: dict[str, int] = {}
    bases: set[tuple[str, str]] = set()
    for source in manifest.get("sources", []):
        family = source["family"]
        path = (manifest_path.parent / source["path"]).resolve()
        data = path.read_bytes()
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != source["row_count"]:
            raise RuntimeError(f"{family}: manifest row_count mismatch")
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise RuntimeError(f"{family}: manifest source SHA-256 mismatch")
        if _git_blob_sha(data) != source["git_blob_sha"]:
            raise RuntimeError(f"{family}: manifest source Git blob mismatch")
        if any(row.get("family") != family for row in rows):
            raise RuntimeError(f"{family}: source contains foreign-family row")
        family_counts[family] = len(rows)
        bases.update((family, row["base_device"]) for row in rows)
    return sum(family_counts.values()), bases, family_counts


def _historical_plan() -> dict[str, Any]:
    if file_sha256(PLAN_PATH) != EXPECTED_PLAN_SHA256:
        raise RuntimeError("frozen U0.4 admission-plan digest drifted")
    if file_sha256(PRESTATE_MANIFEST) != EXPECTED_PRESTATE_MANIFEST_SHA256:
        raise RuntimeError("U0.3 Production prestate digest drifted")
    if _git_blob_sha(PRESTATE_MANIFEST.read_bytes()) != EXPECTED_PRESTATE_MANIFEST_BLOB:
        raise RuntimeError("U0.3 Production prestate Git blob drifted")
    frozen = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        canonical = Path(td) / "stm32u0-commercial-icpn.csv"
        plan = build_admission_plan(
            canonical_path=canonical,
            production_manifest_path=PRESTATE_MANIFEST,
        )
    if not admission_plan_is_clean(plan):
        raise RuntimeError("historical U0.4 admission plan is not clean")
    if admission_summary(plan) != frozen:
        raise RuntimeError("historical U0.4 semantic replay drifted")
    return plan


def _render_canonical(plan: dict[str, Any]) -> tuple[bytes, list[dict[str, str]]]:
    with tempfile.TemporaryDirectory() as td:
        canonical = Path(td) / "stm32u0-commercial-icpn.csv"
        _write_empty_canonical(canonical)
        result = write_canonical_dataset(plan=plan, canonical_path=canonical)
        if result.get("status") != "written" or result.get("rows_after") != EXPECTED_PUBLISHED_ROWS:
            raise RuntimeError("canonical writer did not render exactly 68 STM32U0 rows")
        data = canonical.read_bytes()
        with canonical.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    if hashlib.sha256(data).hexdigest() != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("canonical rendering SHA-256 drifted")
    if _git_blob_sha(data) != EXPECTED_CANONICAL_BLOB:
        raise RuntimeError("canonical rendering Git blob drifted")
    if len({row["icpn"] for row in rows}) != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("published STM32U0 exact identities are duplicated")
    if len({row["base_device"] for row in rows}) != EXPECTED_PUBLISHED_BASES:
        raise RuntimeError("published STM32U0 Base Device count drifted")
    return data, rows


def _build_post_manifest(canonical_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    manifest = json.loads(PRESTATE_MANIFEST.read_text(encoding="utf-8"))
    if any(source.get("family") == "STM32U0" for source in manifest.get("sources", [])):
        raise RuntimeError("STM32U0 already exists in frozen Production prestate")
    manifest["sources"].append({
        "manufacturer": "STMicroelectronics",
        "family": "STM32U0",
        "path": "../research/stm32u0-commercial-icpn.csv",
        "row_count": EXPECTED_PUBLISHED_ROWS,
        "git_blob_sha": _git_blob_sha(canonical_bytes),
        "sha256": hashlib.sha256(canonical_bytes).hexdigest(),
    })
    data = _json_bytes(manifest, sort_keys=False)
    if hashlib.sha256(data).hexdigest() != EXPECTED_POST_MANIFEST_SHA256:
        raise RuntimeError("post-Publication manifest SHA-256 drifted")
    if _git_blob_sha(data) != EXPECTED_POST_MANIFEST_BLOB:
        raise RuntimeError("post-Publication manifest Git blob drifted")
    return data, manifest


def build_proposal() -> dict[str, Any]:
    before_exact, before_bases, before_families = _production_snapshot(PRESTATE_MANIFEST)
    if (before_exact, len(before_bases), len(before_families)) != EXPECTED_PRESTATE:
        raise RuntimeError("Production aggregate prestate drifted")
    if "STM32U0" in before_families:
        raise RuntimeError("STM32U0 unexpectedly exists in Production prestate")

    plan = _historical_plan()
    canonical_bytes, rows = _render_canonical(plan)
    manifest_bytes, _ = _build_post_manifest(canonical_bytes)
    added_bases = {("STM32U0", row["base_device"]) for row in rows}
    post_bases = before_bases | added_bases
    post_families = dict(before_families)
    post_families["STM32U0"] = len(rows)
    poststate = (before_exact + len(rows), len(post_bases), len(post_families))
    if poststate != EXPECTED_POSTSTATE:
        raise RuntimeError(f"proposed Production poststate drifted: {poststate}")

    return {
        "schema_version": 1,
        "phase": "U0.5",
        "family": "STM32U0",
        "status": "publication_proposal_clean",
        "admission_plan_sha256": EXPECTED_PLAN_SHA256,
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "production_manifest_git_blob_sha_before": EXPECTED_PRESTATE_MANIFEST_BLOB,
        "canonical_csv_file_sha256_proposed": hashlib.sha256(canonical_bytes).hexdigest(),
        "canonical_csv_git_blob_sha_proposed": _git_blob_sha(canonical_bytes),
        "production_manifest_sha256_proposed": hashlib.sha256(manifest_bytes).hexdigest(),
        "production_manifest_git_blob_sha_proposed": _git_blob_sha(manifest_bytes),
        "manufacturer_verified_identity_count": EXPECTED_PUBLISHED_ROWS,
        "published_exact_icpn_count_proposed": len(rows),
        "published_base_device_count_proposed": len(added_bases),
        "added_exact_icpns": sorted(row["icpn"] for row in rows),
        "bounded_commercial_surface_complete": True,
        "capability_unresolved_count": 0,
        "production_exact_icpns_before": before_exact,
        "production_exact_icpns_after_proposed": poststate[0],
        "production_base_devices_before": len(before_bases),
        "production_base_devices_after_proposed": poststate[1],
        "production_family_count_before": len(before_families),
        "production_family_count_after_proposed": poststate[2],
        "canonical_write_applied": False,
        "production_write_applied": False,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_equivalence_claimed": False,
        "option_security_semantics_claimed": False,
        "physical_target_qualification_claimed": False,
        "hil_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
        "full_stm32u0_surface_covered": False,
    }


def _build_audit(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "U0.5",
        "family": "STM32U0",
        "status": "published",
        "admission_plan_sha256": EXPECTED_PLAN_SHA256,
        "publication_proposal_sha256": hashlib.sha256(_json_bytes(proposal, sort_keys=True)).hexdigest(),
        "canonical_csv_file_sha256": EXPECTED_CANONICAL_SHA256,
        "canonical_csv_git_blob_sha": EXPECTED_CANONICAL_BLOB,
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "production_manifest_git_blob_sha_before": EXPECTED_PRESTATE_MANIFEST_BLOB,
        "production_manifest_sha256_after": EXPECTED_POST_MANIFEST_SHA256,
        "production_manifest_git_blob_sha_after": EXPECTED_POST_MANIFEST_BLOB,
        "manufacturer_verified_identity_count": EXPECTED_PUBLISHED_ROWS,
        "published_exact_icpn_count": EXPECTED_PUBLISHED_ROWS,
        "published_base_device_count": EXPECTED_PUBLISHED_BASES,
        "added_exact_icpns": proposal["added_exact_icpns"],
        "stm32u0_rows_before": 0,
        "stm32u0_rows_after": EXPECTED_PUBLISHED_ROWS,
        "stm32u0_base_devices_after": EXPECTED_PUBLISHED_BASES,
        "production_exact_icpns_before": EXPECTED_PRESTATE[0],
        "production_exact_icpns_after": EXPECTED_POSTSTATE[0],
        "production_base_devices_before": EXPECTED_PRESTATE[1],
        "production_base_devices_after": EXPECTED_POSTSTATE[1],
        "production_family_count_before": EXPECTED_PRESTATE[2],
        "production_family_count_after": EXPECTED_POSTSTATE[2],
        "bounded_commercial_surface_complete": True,
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
        "full_stm32u0_surface_covered": False,
    }


def verify_current_publication() -> dict[str, Any]:
    proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
    if file_sha256(PROPOSAL_PATH) != EXPECTED_PROPOSAL_SHA256 or proposal != build_proposal():
        raise RuntimeError("frozen U0.5 publication proposal drifted")
    if file_sha256(CANONICAL_PATH) != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("published STM32U0 canonical CSV drifted")
    if _git_blob_sha(CANONICAL_PATH.read_bytes()) != EXPECTED_CANONICAL_BLOB:
        raise RuntimeError("published STM32U0 canonical Git blob drifted")
    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    u0_sources = [source for source in manifest.get("sources", []) if source.get("family") == "STM32U0"]
    if len(u0_sources) != 1:
        raise RuntimeError("current Production manifest must contain exactly one STM32U0 source")
    expected_source = {
        "manufacturer": "STMicroelectronics",
        "family": "STM32U0",
        "path": "../research/stm32u0-commercial-icpn.csv",
        "row_count": EXPECTED_PUBLISHED_ROWS,
        "git_blob_sha": EXPECTED_CANONICAL_BLOB,
        "sha256": EXPECTED_CANONICAL_SHA256,
    }
    if u0_sources[0] != expected_source:
        raise RuntimeError("current STM32U0 Production source drifted")
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    if file_sha256(AUDIT_PATH) != EXPECTED_AUDIT_SHA256 or audit != _build_audit(proposal):
        raise RuntimeError("U0.5 publication audit drifted")

    exact, bases, families = _production_snapshot(PRODUCTION_MANIFEST)
    if exact < EXPECTED_POSTSTATE[0] or len(bases) < EXPECTED_POSTSTATE[1] or len(families) < EXPECTED_POSTSTATE[2]:
        raise RuntimeError("current Production state regressed below U0.5 publication poststate")
    if families.get("STM32U0") != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("published STM32U0 Production row count drifted")
    return {
        "status": "valid",
        "phase": "U0.5",
        "published_exact_icpns": EXPECTED_PUBLISHED_ROWS,
        "published_base_devices": EXPECTED_PUBLISHED_BASES,
        "production_exact_icpns": exact,
        "production_base_devices": len(bases),
        "production_family_count": len(families),
        "canonical_sha256": EXPECTED_CANONICAL_SHA256,
        "production_manifest_sha256": file_sha256(PRODUCTION_MANIFEST),
    }


def publish() -> dict[str, Any]:
    proposal = build_proposal()
    if not PROPOSAL_PATH.exists() or json.loads(PROPOSAL_PATH.read_text(encoding="utf-8")) != proposal:
        raise RuntimeError("frozen U0.5 publication proposal is missing or drifted")

    if CANONICAL_PATH.exists():
        verify_current_publication()
        return {"status": "no_op_already_published", "published_exact_icpns": EXPECTED_PUBLISHED_ROWS}

    if file_sha256(PRODUCTION_MANIFEST) != EXPECTED_PRESTATE_MANIFEST_SHA256:
        raise RuntimeError("Production manifest is neither U0.5 prestate nor expected poststate")
    if _git_blob_sha(PRODUCTION_MANIFEST.read_bytes()) != EXPECTED_PRESTATE_MANIFEST_BLOB:
        raise RuntimeError("Production prestate Git blob drifted before apply")
    if CANONICAL_PATH.exists():
        raise RuntimeError("U0.5 apply requires STM32U0 canonical dataset absent")

    plan = _historical_plan()
    canonical_bytes, _ = _render_canonical(plan)
    manifest_bytes, _ = _build_post_manifest(canonical_bytes)
    CANONICAL_PATH.write_bytes(canonical_bytes)
    PRODUCTION_MANIFEST.write_bytes(manifest_bytes)
    audit = _build_audit(proposal)
    AUDIT_PATH.write_bytes(_json_bytes(audit, sort_keys=True))
    verify_current_publication()
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", action="store_true")
    parser.add_argument("--write-proposal", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    selected = sum((args.proposal, args.write_proposal, args.apply, args.verify))
    if selected != 1:
        parser.error("choose exactly one of --proposal, --write-proposal, --apply, --verify")
    try:
        if args.proposal:
            value = build_proposal()
        elif args.write_proposal:
            value = build_proposal()
            PROPOSAL_PATH.write_bytes(_json_bytes(value, sort_keys=True))
        elif args.apply:
            value = publish()
        else:
            value = verify_current_publication()
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
