#!/usr/bin/env python3
"""Render the STM32U3 exact-ICPN Production catalog publication.

Catalog admission is intentionally independent from PPU/Socket physical
validation. This transaction admits exact commercial ICPN identity and a
deterministic backend route only; it does not authorize target execution or
claim physical programming support.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from stm32u3_admission_policy import build_canonical_rows

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION_MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
ADMISSION_POLICY = ROOT / "docs/architecture/icpn-catalog-admission-policy.json"

FAMILY = "STM32U3"
MANUFACTURER = "STMicroelectronics"
EXPECTED_ROWS = 106
EXPECTED_BASES = 33
EXPECTED_PRESTATE_EXACT = 1862
EXPECTED_POSTSTATE_EXACT = 1968
EXPECTED_PRESTATE_FAMILIES = 13
EXPECTED_POSTSTATE_FAMILIES = 14
EXPECTED_STATUS_COUNTS = {"Active": 100, "Evaluation": 6}
EXPECTED_EXACT_SET_SHA256 = "6ff4f01a009e28aff1a6ebf3f74544c973ce9e2a229bc72f4574f71c47ea4918"
CANONICAL_VERIFICATION_STATUS = "verified_st_datasheet_ordering_information_plus_retained_exact_identity"

PRODUCTION_FIELDS = (
    "manufacturer",
    "icpn",
    "family",
    "series",
    "base_device",
    "package",
    "pin_count",
    "flash_size",
    "temperature_grade",
    "option_suffix",
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
    "source_type",
    "source_reference",
    "source_authority",
    "verification_status",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: expected JSON object")
    return value


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data, usedforsecurity=False).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _set_sha(values: set[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode("utf-8")).hexdigest()


def _validate_architecture_policy() -> None:
    policy = _read_json(ADMISSION_POLICY)
    admission = policy.get("catalog_admission")
    physical = policy.get("physical_validation")
    execution = policy.get("execution_policy")
    if (
        policy.get("policy_id") != "icpn-catalog-admission-separation"
        or not isinstance(admission, dict)
        or admission.get("requires_ppu_hil") is not False
        or admission.get("requires_socket_hil") is not False
        or admission.get("requires_physical_programming_success") is not False
        or admission.get("admits_not_verified_physical_state") is not True
        or not isinstance(physical, dict)
        or physical.get("independent_from_catalog_admission") is not True
        or not isinstance(execution, dict)
        or execution.get("independent_from_catalog_admission") is not True
        or execution.get("catalog_presence_does_not_authorize_target_execution") is not True
    ):
        raise RuntimeError("ICPN catalog-admission separation policy drifted")


def _production_snapshot(manifest: dict[str, Any]) -> tuple[int, int, set[str]]:
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("Production manifest sources missing")
    exact_count = 0
    families: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise RuntimeError("Production manifest source must be object")
        family = source.get("family")
        rows = source.get("row_count")
        if not isinstance(family, str) or not isinstance(rows, int):
            raise RuntimeError("Production manifest source identity/count invalid")
        if family in families:
            raise RuntimeError(f"duplicate Production family source: {family}")
        families.add(family)
        exact_count += rows
    return exact_count, len(families), families


def _publication_rows() -> tuple[list[dict[str, str]], Counter[str]]:
    rows = build_canonical_rows()
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"STM32U3 canonical row count drifted: {len(rows)}")
    icpns = {row["icpn"] for row in rows}
    bases = {row["base_device"] for row in rows}
    statuses = Counter(row["marketing_status_observed"] for row in rows)
    if len(icpns) != EXPECTED_ROWS or _set_sha(icpns) != EXPECTED_EXACT_SET_SHA256:
        raise RuntimeError("STM32U3 exact ICPN retained set drifted")
    if len(bases) != EXPECTED_BASES:
        raise RuntimeError("STM32U3 Base Device count drifted")
    if dict(statuses) != EXPECTED_STATUS_COUNTS:
        raise RuntimeError(f"STM32U3 marketing-status observation drifted: {dict(statuses)}")

    published: list[dict[str, str]] = []
    for row in rows:
        kind = row["existing_identifier_kind"]
        if kind == "ordering_pattern":
            mapping_method = "deterministic_ordering_pattern"
        elif kind == "cmsis_device_name":
            mapping_method = "deterministic_cmsis_device_name"
        else:
            raise RuntimeError(f"{row['icpn']}: unsupported mapping evidence kind {kind}")
        value = {field: row[field] for field in PRODUCTION_FIELDS}
        value["mapping_status"] = mapping_method
        value["verification_status"] = CANONICAL_VERIFICATION_STATUS
        if not value["source_reference"] or not value["source_authority"]:
            raise RuntimeError(f"{row['icpn']}: authoritative provenance missing")
        published.append(value)
    published.sort(key=lambda row: (row["manufacturer"], row["base_device"], row["icpn"]))
    return published, statuses


def _render_csv(rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(PRODUCTION_FIELDS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def render_publication() -> tuple[bytes, bytes, dict[str, Any]]:
    _validate_architecture_policy()
    manifest = _read_json(PRODUCTION_MANIFEST)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("status") != "production"
        or manifest.get("selection_policy") != "admitted_exact_manufacturer_part_number_only"
    ):
        raise RuntimeError("Production manifest contract drifted")
    before_exact, before_family_count, families = _production_snapshot(manifest)
    if before_exact != EXPECTED_PRESTATE_EXACT or before_family_count != EXPECTED_PRESTATE_FAMILIES:
        raise RuntimeError(
            f"Production prestate drifted: exact={before_exact} families={before_family_count}"
        )
    if FAMILY in families:
        raise RuntimeError("STM32U3 is already present in Production manifest")

    rows, statuses = _publication_rows()
    canonical = _render_csv(rows)
    sources = list(manifest["sources"])
    sources.append(
        {
            "manufacturer": MANUFACTURER,
            "family": FAMILY,
            "path": "../research/stm32u3-commercial-icpn.csv",
            "row_count": EXPECTED_ROWS,
            "git_blob_sha": _git_blob_sha(canonical),
            "sha256": _sha256(canonical),
        }
    )
    post_manifest = {**manifest, "sources": sources}
    manifest_bytes = (json.dumps(post_manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    after_exact, after_family_count, after_families = _production_snapshot(post_manifest)
    if (
        after_exact != EXPECTED_POSTSTATE_EXACT
        or after_family_count != EXPECTED_POSTSTATE_FAMILIES
        or FAMILY not in after_families
    ):
        raise RuntimeError("STM32U3 proposed Production poststate drifted")

    proposal = {
        "schema_version": 1,
        "transaction": "stm32u3-production-catalog-publication",
        "family": FAMILY,
        "manufacturer": MANUFACTURER,
        "status": "publication_ready",
        "catalog_admission_policy": "icpn-catalog-admission-separation",
        "published_exact_icpns": EXPECTED_ROWS,
        "published_base_devices": EXPECTED_BASES,
        "marketing_status_observed": dict(statuses),
        "evaluation_status_is_identity_observation_not_execution_authorization": True,
        "exact_icpn_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "canonical_csv_sha256": _sha256(canonical),
        "canonical_csv_git_blob_sha": _git_blob_sha(canonical),
        "production_manifest_sha256_before": _sha256(PRODUCTION_MANIFEST.read_bytes()),
        "production_manifest_sha256_after": _sha256(manifest_bytes),
        "production_manifest_git_blob_sha_after": _git_blob_sha(manifest_bytes),
        "production_exact_icpns_before": EXPECTED_PRESTATE_EXACT,
        "production_exact_icpns_after": EXPECTED_POSTSTATE_EXACT,
        "production_family_count_before": EXPECTED_PRESTATE_FAMILIES,
        "production_family_count_after": EXPECTED_POSTSTATE_FAMILIES,
        "ppu_hil_required_for_catalog_admission": False,
        "socket_hil_required_for_catalog_admission": False,
        "physical_programming_success_required_for_catalog_admission": False,
        "physical_validation_claimed": False,
        "runtime_programming_support_claimed": False,
        "security_mutation_support_claimed": False,
        "debug_attach_support_claimed": False,
        "catalog_membership_authorizes_target_execution": False,
    }
    return canonical, manifest_bytes, proposal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    canonical, manifest, proposal = render_publication()
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "stm32u3-commercial-icpn.csv").write_bytes(canonical)
        (args.output_dir / "icpn-v1-manifest.json").write_bytes(manifest)
        (args.output_dir / "stm32u3-production-publication-proposal.json").write_text(
            json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(proposal, sort_keys=True) if args.json else json.dumps(proposal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
