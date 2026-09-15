#!/usr/bin/env python3
"""Render the STM32L5 exact-ICPN Production catalog publication.

Catalog admission is independent from PPU/Socket physical validation. This
transaction admits exact commercial ICPN identity and a deterministic backend
route only; it does not authorize target execution or claim physical support.
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

from stm32l5_admission_policy import build_canonical_row, read_route_rows
from stm32l5_metadata_policy import build_candidate_inputs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION_MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
ADMISSION_POLICY = ROOT / "docs/architecture/icpn-catalog-admission-policy.json"

FAMILY = "STM32L5"
MANUFACTURER = "STMicroelectronics"
EXPECTED_ROWS = 49
EXPECTED_BASES = 17
EXPECTED_PRESTATE_EXACT = 1968
EXPECTED_POSTSTATE_EXACT = 2017
EXPECTED_PRESTATE_FAMILIES = 14
EXPECTED_POSTSTATE_FAMILIES = 15
EXPECTED_STATUS_COUNTS = {"Active": 49}
EXPECTED_EXACT_SET_SHA256 = "f9a74a7badfb39f8fc52753fc3904cd63a8b3e0a2e4dcc37dee759809aaa68b1"
EXPECTED_PRESTATE_MANIFEST_SHA256 = "6f77133bffe0fa5fbd5b059d1c89fdfb681a3ad08da09bc8d38f975d0fec7f31"
CANONICAL_VERIFICATION_STATUS = "verified_st_datasheet_ordering_information_plus_retained_exact_identity"

PRODUCTION_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package",
    "pin_count", "flash_size", "temperature_grade", "option_suffix",
    "cmsis_device_name", "existing_identifier", "existing_identifier_kind",
    "mapping_status", "openocd_target_config", "source_type", "source_reference",
    "source_authority", "verification_status",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: expected JSON object")
    return value


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


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


def _derive_prestate(current: dict[str, Any]) -> tuple[dict[str, Any], bytes, dict[str, Any] | None]:
    sources = current.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("Production manifest sources missing")
    l5_sources = [source for source in sources if isinstance(source, dict) and source.get("family") == FAMILY]
    if len(l5_sources) > 1:
        raise RuntimeError("duplicate STM32L5 Production sources")
    retained_sources = [
        source for source in sources
        if not (isinstance(source, dict) and source.get("family") == FAMILY)
    ]
    prestate = {**current, "sources": retained_sources}
    prestate_bytes = _json_bytes(prestate)
    if _sha256(prestate_bytes) != EXPECTED_PRESTATE_MANIFEST_SHA256:
        raise RuntimeError("STM32L5 frozen Production prestate drifted")
    exact, families, family_set = _production_snapshot(prestate)
    if exact != EXPECTED_PRESTATE_EXACT or families != EXPECTED_PRESTATE_FAMILIES or FAMILY in family_set:
        raise RuntimeError(f"Production prestate drifted: exact={exact} families={families}")
    return prestate, prestate_bytes, l5_sources[0] if l5_sources else None


def _publication_rows() -> tuple[list[dict[str, str]], Counter[str]]:
    routes = read_route_rows()
    rows = [build_canonical_row(candidate, routes) for candidate in build_candidate_inputs()]
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"STM32L5 canonical row count drifted: {len(rows)}")
    icpns = {row["icpn"] for row in rows}
    bases = {row["base_device"] for row in rows}
    if len(icpns) != EXPECTED_ROWS or _set_sha(icpns) != EXPECTED_EXACT_SET_SHA256:
        raise RuntimeError("STM32L5 exact ICPN retained set drifted")
    if len(bases) != EXPECTED_BASES:
        raise RuntimeError("STM32L5 Base Device count drifted")
    statuses = Counter({"Active": EXPECTED_ROWS})

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
    current = _read_json(PRODUCTION_MANIFEST)
    if (
        current.get("schema_version") != 1
        or current.get("status") != "production"
        or current.get("selection_policy") != "admitted_exact_manufacturer_part_number_only"
    ):
        raise RuntimeError("Production manifest contract drifted")
    prestate, prestate_bytes, existing_l5_source = _derive_prestate(current)

    rows, statuses = _publication_rows()
    canonical = _render_csv(rows)
    l5_source = {
        "manufacturer": MANUFACTURER,
        "family": FAMILY,
        "path": "../research/stm32l5-commercial-icpn.csv",
        "row_count": EXPECTED_ROWS,
        "git_blob_sha": _git_blob_sha(canonical),
        "sha256": _sha256(canonical),
    }
    if existing_l5_source is not None and existing_l5_source != l5_source:
        raise RuntimeError("checked-in STM32L5 Production source binding drifted")

    post_manifest = {**prestate, "sources": [*prestate["sources"], l5_source]}
    manifest_bytes = _json_bytes(post_manifest)
    after_exact, after_family_count, after_families = _production_snapshot(post_manifest)
    if (
        after_exact != EXPECTED_POSTSTATE_EXACT
        or after_family_count != EXPECTED_POSTSTATE_FAMILIES
        or FAMILY not in after_families
    ):
        raise RuntimeError("STM32L5 proposed Production poststate drifted")
    if existing_l5_source is not None and PRODUCTION_MANIFEST.read_bytes() != manifest_bytes:
        raise RuntimeError("checked-in Production manifest is not deterministic STM32L5 poststate")

    proposal = {
        "schema_version": 1,
        "transaction": "stm32l5-production-catalog-publication",
        "family": FAMILY,
        "manufacturer": MANUFACTURER,
        "status": "publication_ready",
        "catalog_admission_policy": "icpn-catalog-admission-separation",
        "published_exact_icpns": EXPECTED_ROWS,
        "published_base_devices": EXPECTED_BASES,
        "marketing_status_observed": dict(statuses),
        "exact_icpn_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "canonical_csv_sha256": _sha256(canonical),
        "canonical_csv_git_blob_sha": _git_blob_sha(canonical),
        "production_manifest_sha256_before": _sha256(prestate_bytes),
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
        (args.output_dir / "stm32l5-commercial-icpn.csv").write_bytes(canonical)
        (args.output_dir / "icpn-v1-manifest.json").write_bytes(manifest)
        (args.output_dir / "stm32l5-production-publication-proposal.json").write_text(
            json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(proposal, sort_keys=True) if args.json else json.dumps(proposal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
