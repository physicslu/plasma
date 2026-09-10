#!/usr/bin/env python3
"""Controlled STM32G0 Phase 4.8E canonical + Production publication transaction."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import file_sha256, write_canonical_dataset
from stm32g0_admission_policy import CANONICAL_FIELDS
from stm32g0_phase4_8d_admission import EXPECTED_CAPABILITY_UNRESOLVED, admission_plan_is_clean

HERE = Path(__file__).resolve().parent
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PLAN_PATH = HERE / "stm32g0-phase4.8d-admission-plan.json"
CANONICAL_PATH = HERE / "stm32g0-commercial-icpn.csv"
AUDIT_PATH = HERE / "stm32g0-phase4.8e-publication-audit.json"
EXPECTED_PLAN_SHA256 = "d5f83bb3a2417a368e2d0bfb66a146e47b7649675341dc44e9d28c0a5de39801"
EXPECTED_PRESTATE_MANIFEST_SHA256 = "4b05b3e3e7cb8e9b8cc426f9358d758f04d5bc4944b23e44ee0cad1d3bea1cd3"
EXPECTED_PRESTATE_EXACT = 563
EXPECTED_PRESTATE_BASES = 197
EXPECTED_PUBLISHED_ROWS = 47
EXPECTED_PUBLISHED_BASES = 12


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _write_empty_canonical(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS), lineterminator="\n").writeheader()


def _read_plan() -> dict[str, Any]:
    if file_sha256(PLAN_PATH) != EXPECTED_PLAN_SHA256:
        raise RuntimeError("Phase 4.8D frozen admission-plan digest drifted")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if not admission_plan_is_clean(plan):
        raise RuntimeError("Phase 4.8D frozen admission plan is not clean")
    unresolved = plan.get("capability_unresolved")
    if not isinstance(unresolved, list) or {item.get("icpn") for item in unresolved} != set(EXPECTED_CAPABILITY_UNRESOLVED):
        raise RuntimeError("Phase 4.8D capability-unresolved set drifted")
    return plan


def _production_snapshot(manifest: dict[str, Any], manifest_path: Path) -> tuple[int, int, dict[str, int]]:
    family_counts: dict[str, int] = {}
    bases: set[tuple[str, str]] = set()
    for source in manifest.get("sources", []):
        family = source["family"]
        path = (manifest_path.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != source["row_count"]:
            raise RuntimeError(f"{family}: manifest row count mismatch")
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise RuntimeError(f"{family}: manifest source SHA-256 mismatch")
        if _git_blob_sha(path.read_bytes()) != source["git_blob_sha"]:
            raise RuntimeError(f"{family}: manifest source Git blob mismatch")
        family_counts[family] = len(rows)
        bases.update((family, row["base_device"]) for row in rows)
    return sum(family_counts.values()), len(bases), family_counts


def publish(*, dry_run: bool = False) -> dict[str, Any]:
    plan = _read_plan()
    if file_sha256(PRODUCTION_MANIFEST) != EXPECTED_PRESTATE_MANIFEST_SHA256:
        raise RuntimeError("Production manifest prestate drifted before Phase 4.8E")
    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    if any(source.get("family") == "STM32G0" for source in manifest.get("sources", [])):
        raise RuntimeError("STM32G0 already exists in Production prestate")
    before_exact, before_bases, before_families = _production_snapshot(manifest, PRODUCTION_MANIFEST)
    if before_exact != EXPECTED_PRESTATE_EXACT or before_bases != EXPECTED_PRESTATE_BASES or len(before_families) != 6:
        raise RuntimeError("Production aggregate prestate drifted")

    proposed_rows = [item.get("proposed_canonical_row") for item in plan["candidates"] if item.get("decision") == "admit"]
    if len(proposed_rows) != EXPECTED_PUBLISHED_ROWS or any(not isinstance(row, dict) for row in proposed_rows):
        raise RuntimeError("Phase 4.8D proposed canonical row set drifted")
    if {row["icpn"] for row in proposed_rows} & set(EXPECTED_CAPABILITY_UNRESOLVED):
        raise RuntimeError("capability-unresolved N identity leaked into publication")
    if len({row["base_device"] for row in proposed_rows}) != EXPECTED_PUBLISHED_BASES:
        raise RuntimeError("published STM32G0 Base Device count drifted")

    if dry_run:
        return {
            "status": "dry_run_clean", "publish_rows": 47,
            "capability_unresolved": sorted(EXPECTED_CAPABILITY_UNRESOLVED),
            "production_exact_before": before_exact, "production_base_devices_before": before_bases,
        }

    if CANONICAL_PATH.exists():
        raise RuntimeError("Phase 4.8E refuses an existing STM32G0 canonical dataset")
    _write_empty_canonical(CANONICAL_PATH)
    write_result = write_canonical_dataset(plan=plan, canonical_path=CANONICAL_PATH)
    if write_result.get("status") != "written" or write_result.get("rows_after") != EXPECTED_PUBLISHED_ROWS:
        raise RuntimeError("canonical writer did not publish exactly 47 rows")

    canonical_bytes = CANONICAL_PATH.read_bytes()
    canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()
    canonical_blob = _git_blob_sha(canonical_bytes)
    manifest["sources"].append({
        "manufacturer": "STMicroelectronics",
        "family": "STM32G0",
        "path": "../research/stm32g0-commercial-icpn.csv",
        "row_count": EXPECTED_PUBLISHED_ROWS,
        "git_blob_sha": canonical_blob,
        "sha256": canonical_sha,
    })
    PRODUCTION_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_sha = file_sha256(PRODUCTION_MANIFEST)
    after_exact, after_bases, after_families = _production_snapshot(manifest, PRODUCTION_MANIFEST)
    if after_exact != 610 or after_bases != 209 or len(after_families) != 7 or after_families.get("STM32G0") != 47:
        raise RuntimeError("Production aggregate poststate is not expected 610/209/7-family state")

    unresolved = [
        {
            "icpn": item["icpn"],
            "base_device": item["base_device"],
            "identity_status": item["identity_status"],
            "capability_status": item["capability_status"],
            "policy_action": item["policy_action"],
        }
        for item in plan["capability_unresolved"]
    ]
    audit = {
        "schema_version": 1,
        "phase": "4.8E",
        "family": "STM32G0",
        "status": "published",
        "admission_plan_sha256": EXPECTED_PLAN_SHA256,
        "canonical_csv_file_sha256": canonical_sha,
        "canonical_csv_git_blob_sha": canonical_blob,
        "production_manifest_sha256_before": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "production_manifest_sha256_after": manifest_sha,
        "manufacturer_verified_identity_count": 49,
        "published_exact_icpn_count": 47,
        "added_exact_icpns": sorted(row["icpn"] for row in proposed_rows),
        "stm32g0_rows_before": 0,
        "stm32g0_rows_after": 47,
        "stm32g0_base_devices_after": EXPECTED_PUBLISHED_BASES,
        "production_exact_icpns_before": before_exact,
        "production_exact_icpns_after": after_exact,
        "production_base_devices_before": before_bases,
        "production_base_devices_after": after_bases,
        "production_family_count_before": len(before_families),
        "production_family_count_after": len(after_families),
        "capability_unresolved_count": 2,
        "capability_unresolved": unresolved,
        "capability_unresolved_is_identity_rejection": False,
        "canonical_write_applied": True,
        "production_write_applied": True,
        "programming_algorithm_equivalence_claimed": False,
        "n_product_version_capability_equivalence_claimed": False,
        "physical_target_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
        "full_stm32g0_surface_covered": False,
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(publish(dry_run=args.dry_run), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
