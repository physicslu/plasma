#!/usr/bin/env python3
"""Controlled STM32C0 C0.5 canonical + Production publication transaction.

C0.5 publishes only the 209 exact ICPNs admitted by the frozen C0.4 plan.
The 11 capability-unresolved identities remain manufacturer-verified and
metadata-ready but are deliberately excluded from Production. Publication is
catalog identity availability only; it does not establish programming,
Flash/security, physical/HIL, or runtime support.
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
from stm32c0_admission_policy import CANONICAL_FIELDS
from stm32c0_phase_c0_4_admission import (
    EXPECTED_CAPABILITY_UNRESOLVED,
    EXPECTED_CAPABILITY_UNRESOLVED_SHA256,
    admission_plan_is_clean,
    admission_summary,
    build_admission_plan,
)

HERE = Path(__file__).resolve().parent
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST = HERE / "stm32c0-phase-c0.3-production-manifest-prestate.json"
PLAN_PATH = HERE / "stm32c0-phase-c0.4-admission-plan.json"
CANONICAL_PATH = HERE / "stm32c0-commercial-icpn.csv"
PROPOSAL_PATH = HERE / "stm32c0-phase-c0.5-publication-proposal.json"
AUDIT_PATH = HERE / "stm32c0-phase-c0.5-publication-audit.json"

EXPECTED_PLAN_SHA256 = "36db8e0c34fdbaf46a2ee6dc8df5a09171f6a4434572f9b2cf49cabf63361056"
EXPECTED_PRESTATE_MANIFEST_SHA256 = "903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0"
EXPECTED_PRESTATE_MANIFEST_BLOB = "89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc"
EXPECTED_CANONICAL_SHA256 = "d473c7a1b3b72b75314732ffd59bf8a8b0a39eaf8d632ba935e9e1b71509f96b"
EXPECTED_CANONICAL_BLOB = "0bf125dd071312cf31c57cfa7ebe3b29ffdda845"
EXPECTED_PROPOSAL_SHA256 = "af207b92efc84d37c04755d0512b521392185f26c4b971f52ed6a7fb9644cf9f"
EXPECTED_AUDIT_SHA256 = "b351bb5b1a27c62899b23473001caacc4e8a42e4f2395051ad68468d547e9953"
EXPECTED_POST_MANIFEST_SHA256 = "15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420"
EXPECTED_POST_MANIFEST_BLOB = "8abfcc870e51ac4232cdf8d807828cfe4ff5662d"
EXPECTED_PUBLISHED_ROWS = 209
EXPECTED_PUBLISHED_BASES = 50
EXPECTED_MANUFACTURER_VERIFIED = 220
EXPECTED_METADATA_READY = 220
EXPECTED_UNRESOLVED = 11
EXPECTED_PRESTATE = (703, 243, 9)
EXPECTED_POSTSTATE = (912, 293, 10)


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
        raise RuntimeError("frozen C0.4 admission-plan digest drifted")
    if file_sha256(PRESTATE_MANIFEST) != EXPECTED_PRESTATE_MANIFEST_SHA256:
        raise RuntimeError("C0.3 Production prestate digest drifted")
    if _git_blob_sha(PRESTATE_MANIFEST.read_bytes()) != EXPECTED_PRESTATE_MANIFEST_BLOB:
        raise RuntimeError("C0.3 Production prestate Git blob drifted")
    frozen = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        canonical = Path(td) / "stm32c0-commercial-icpn.csv"
        plan = build_admission_plan(
            canonical_path=canonical,
            production_manifest_path=PRESTATE_MANIFEST,
        )
    if not admission_plan_is_clean(plan):
        raise RuntimeError("historical C0.4 admission plan is not clean")
    if admission_summary(plan) != frozen:
        raise RuntimeError("historical C0.4 semantic replay drifted")
    if set(plan.get("capability_unresolved_exact_icpns", [])) != set(EXPECTED_CAPABILITY_UNRESOLVED):
        raise RuntimeError("C0.4 unresolved identity set drifted")
    if plan.get("capability_unresolved_exact_set_sha256") != EXPECTED_CAPABILITY_UNRESOLVED_SHA256:
        raise RuntimeError("C0.4 unresolved identity digest drifted")
    return plan


def _render_canonical(plan: dict[str, Any]) -> tuple[bytes, list[dict[str, str]]]:
    with tempfile.TemporaryDirectory() as td:
        canonical = Path(td) / "stm32c0-commercial-icpn.csv"
        _write_empty_canonical(canonical)
        result = write_canonical_dataset(plan=plan, canonical_path=canonical)
        if result.get("status") != "written" or result.get("rows_after") != EXPECTED_PUBLISHED_ROWS:
            raise RuntimeError("canonical writer did not render exactly 209 STM32C0 rows")
        data = canonical.read_bytes()
        with canonical.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    if hashlib.sha256(data).hexdigest() != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("canonical rendering SHA-256 drifted")
    if _git_blob_sha(data) != EXPECTED_CANONICAL_BLOB:
        raise RuntimeError("canonical rendering Git blob drifted")
    identities = {row["icpn"] for row in rows}
    if len(identities) != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("published STM32C0 exact identities are duplicated")
    if identities & set(EXPECTED_CAPABILITY_UNRESOLVED):
        raise RuntimeError("capability-unresolved STM32C0 identity escaped into publication")
    if len({row["base_device"] for row in rows}) != EXPECTED_PUBLISHED_BASES:
        raise RuntimeError("published STM32C0 Base Device count drifted")
    return data, rows


def _build_post_manifest(canonical_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    manifest = json.loads(PRESTATE_MANIFEST.read_text(encoding="utf-8"))
    if any(source.get("family") == "STM32C0" for source in manifest.get("sources", [])):
        raise RuntimeError("STM32C0 already exists in frozen Production prestate")
    manifest["sources"].append({
        "manufacturer": "STMicroelectronics",
        "family": "STM32C0",
        "path": "../research/stm32c0-commercial-icpn.csv",
        "row_count": EXPECTED_PUBLISHED_ROWS,
        "git_blob_sha": _git_blob_sha(canonical_bytes),
        "sha256": hashlib.sha256(canonical_bytes).hexdigest(),
    })
    data = _json_bytes(manifest, sort_keys=False)
    if hashlib.sha256(data).hexdigest() != EXPECTED_POST_MANIFEST_SHA256:
        raise RuntimeError("post-publication manifest SHA-256 drifted")
    if _git_blob_sha(data) != EXPECTED_POST_MANIFEST_BLOB:
        raise RuntimeError("post-publication manifest Git blob drifted")
    return data, manifest


def build_proposal() -> dict[str, Any]:
    before_exact, before_bases, before_families = _production_snapshot(PRESTATE_MANIFEST)
    if (before_exact, len(before_bases), len(before_families)) != EXPECTED_PRESTATE:
        raise RuntimeError("Production aggregate prestate drifted")
    if "STM32C0" in before_families:
        raise RuntimeError("STM32C0 unexpectedly exists in Production prestate")

    plan = _historical_plan()
    canonical_bytes, rows = _render_canonical(plan)
    manifest_bytes, _ = _build_post_manifest(canonical_bytes)
    added_bases = {("STM32C0", row["base_device"]) for row in rows}
    poststate = (before_exact + len(rows), len(before_bases | added_bases), len(before_families) + 1)
    if poststate != EXPECTED_POSTSTATE:
        raise RuntimeError(f"proposed Production poststate drifted: {poststate}")
    unresolved = sorted(EXPECTED_CAPABILITY_UNRESOLVED)
    return {
        "schema_version": 1,
        "phase": "C0.5",
        "family": "STM32C0",
        "status": "publication_proposal_clean",
        "admission_plan_sha256": EXPECTED_PLAN_SHA256,
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "production_manifest_git_blob_sha_before": EXPECTED_PRESTATE_MANIFEST_BLOB,
        "canonical_csv_file_sha256_proposed": hashlib.sha256(canonical_bytes).hexdigest(),
        "canonical_csv_git_blob_sha_proposed": _git_blob_sha(canonical_bytes),
        "production_manifest_sha256_proposed": hashlib.sha256(manifest_bytes).hexdigest(),
        "production_manifest_git_blob_sha_proposed": _git_blob_sha(manifest_bytes),
        "manufacturer_verified_identity_count": EXPECTED_MANUFACTURER_VERIFIED,
        "metadata_ready_identity_count": EXPECTED_METADATA_READY,
        "capability_admittable_count": EXPECTED_PUBLISHED_ROWS,
        "published_exact_icpn_count_proposed": len(rows),
        "published_base_device_count_proposed": len(added_bases),
        "added_exact_icpns": sorted(row["icpn"] for row in rows),
        "bounded_commercial_surface_complete": True,
        "published_surface_partial_due_to_capability": True,
        "capability_unresolved_count": EXPECTED_UNRESOLVED,
        "capability_unresolved_exact_icpns": unresolved,
        "capability_unresolved_exact_set_sha256": EXPECTED_CAPABILITY_UNRESOLVED_SHA256,
        "capability_unresolved_is_identity_rejection": False,
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
        "full_stm32c0_surface_covered": False,
    }


def _build_audit(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "C0.5",
        "family": "STM32C0",
        "status": "published",
        "admission_plan_sha256": EXPECTED_PLAN_SHA256,
        "publication_proposal_sha256": hashlib.sha256(_json_bytes(proposal, sort_keys=True)).hexdigest(),
        "canonical_csv_file_sha256": EXPECTED_CANONICAL_SHA256,
        "canonical_csv_git_blob_sha": EXPECTED_CANONICAL_BLOB,
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "production_manifest_git_blob_sha_before": EXPECTED_PRESTATE_MANIFEST_BLOB,
        "production_manifest_sha256_after": EXPECTED_POST_MANIFEST_SHA256,
        "production_manifest_git_blob_sha_after": EXPECTED_POST_MANIFEST_BLOB,
        "manufacturer_verified_identity_count": EXPECTED_MANUFACTURER_VERIFIED,
        "metadata_ready_identity_count": EXPECTED_METADATA_READY,
        "capability_admittable_count": EXPECTED_PUBLISHED_ROWS,
        "published_exact_icpn_count": EXPECTED_PUBLISHED_ROWS,
        "published_base_device_count": EXPECTED_PUBLISHED_BASES,
        "added_exact_icpns": proposal["added_exact_icpns"],
        "stm32c0_rows_before": 0,
        "stm32c0_rows_after": EXPECTED_PUBLISHED_ROWS,
        "stm32c0_base_devices_after": EXPECTED_PUBLISHED_BASES,
        "production_exact_icpns_before": EXPECTED_PRESTATE[0],
        "production_exact_icpns_after": EXPECTED_POSTSTATE[0],
        "production_base_devices_before": EXPECTED_PRESTATE[1],
        "production_base_devices_after": EXPECTED_POSTSTATE[1],
        "production_family_count_before": EXPECTED_PRESTATE[2],
        "production_family_count_after": EXPECTED_POSTSTATE[2],
        "bounded_commercial_surface_complete": True,
        "published_surface_partial_due_to_capability": True,
        "capability_unresolved_count": EXPECTED_UNRESOLVED,
        "capability_unresolved_exact_icpns": sorted(EXPECTED_CAPABILITY_UNRESOLVED),
        "capability_unresolved_exact_set_sha256": EXPECTED_CAPABILITY_UNRESOLVED_SHA256,
        "capability_unresolved_is_identity_rejection": False,
        "canonical_write_applied": True,
        "production_write_applied": True,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_equivalence_claimed": False,
        "option_security_semantics_claimed": False,
        "physical_target_qualification_claimed": False,
        "hil_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
        "full_stm32c0_surface_covered": False,
    }


def verify_current_publication() -> dict[str, Any]:
    proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
    if file_sha256(PROPOSAL_PATH) != EXPECTED_PROPOSAL_SHA256 or proposal != build_proposal():
        raise RuntimeError("frozen C0.5 publication proposal drifted")
    if file_sha256(CANONICAL_PATH) != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("published STM32C0 canonical CSV drifted")
    if _git_blob_sha(CANONICAL_PATH.read_bytes()) != EXPECTED_CANONICAL_BLOB:
        raise RuntimeError("published STM32C0 canonical Git blob drifted")
    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    c0_sources = [source for source in manifest.get("sources", []) if source.get("family") == "STM32C0"]
    if len(c0_sources) != 1:
        raise RuntimeError("current Production manifest must contain exactly one STM32C0 source")
    expected_source = {
        "manufacturer": "STMicroelectronics",
        "family": "STM32C0",
        "path": "../research/stm32c0-commercial-icpn.csv",
        "row_count": EXPECTED_PUBLISHED_ROWS,
        "git_blob_sha": EXPECTED_CANONICAL_BLOB,
        "sha256": EXPECTED_CANONICAL_SHA256,
    }
    if c0_sources[0] != expected_source:
        raise RuntimeError("current STM32C0 Production source drifted")
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    if file_sha256(AUDIT_PATH) != EXPECTED_AUDIT_SHA256 or audit != _build_audit(proposal):
        raise RuntimeError("C0.5 publication audit drifted")

    exact, bases, families = _production_snapshot(PRODUCTION_MANIFEST)
    if exact < EXPECTED_POSTSTATE[0] or len(bases) < EXPECTED_POSTSTATE[1] or len(families) < EXPECTED_POSTSTATE[2]:
        raise RuntimeError("current Production state regressed below C0.5 publication poststate")
    if families.get("STM32C0") != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("published STM32C0 Production row count drifted")
    return {
        "status": "valid",
        "phase": "C0.5",
        "published_exact_icpns": EXPECTED_PUBLISHED_ROWS,
        "published_base_devices": EXPECTED_PUBLISHED_BASES,
        "capability_unresolved": EXPECTED_UNRESOLVED,
        "production_exact_icpns": exact,
        "production_base_devices": len(bases),
        "production_family_count": len(families),
        "canonical_sha256": EXPECTED_CANONICAL_SHA256,
        "production_manifest_sha256": file_sha256(PRODUCTION_MANIFEST),
    }


def publish() -> dict[str, Any]:
    proposal = build_proposal()
    if not PROPOSAL_PATH.exists() or json.loads(PROPOSAL_PATH.read_text(encoding="utf-8")) != proposal:
        raise RuntimeError("frozen C0.5 publication proposal is missing or drifted")
    if CANONICAL_PATH.exists():
        verify_current_publication()
        return {"status": "no_op_already_published", "published_exact_icpns": EXPECTED_PUBLISHED_ROWS}
    if file_sha256(PRODUCTION_MANIFEST) != EXPECTED_PRESTATE_MANIFEST_SHA256:
        raise RuntimeError("Production manifest is neither C0.5 prestate nor expected poststate")
    if _git_blob_sha(PRODUCTION_MANIFEST.read_bytes()) != EXPECTED_PRESTATE_MANIFEST_BLOB:
        raise RuntimeError("Production prestate Git blob drifted before apply")

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
