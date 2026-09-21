#!/usr/bin/env python3
"""Render the STM32WBA2X exact-ICPN Production catalog publication.

Catalog publication is independent from PPU/Socket HIL and physical programming
success. This transaction publishes the already-admitted exact commercial ICPN
identity set and its Catalog backend route only. It does not authorize runtime
programming, programming-algorithm equivalence, wireless radio/security
operations, security mutation, debug attach, target execution, physical
validation, or HIL.
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION_MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
ADMISSION_POLICY = ROOT / "docs/architecture/icpn-catalog-admission-policy.json"
READINESS = HERE / "stm32wba2x-admission-readiness.json"
CANONICAL = HERE / "stm32wba2x-commercial-icpn.csv"

SERIES = "STM32WBA2X"
FAMILY = "STM32WBA2X"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32wba2x.cfg"

EXPECTED_ROWS = 14
EXPECTED_ACTIVE_BASES = 4
EXPECTED_DISCOVERY_BASES = 4
EXPECTED_EXCLUDED_NON_ACTIVE = 0
EXPECTED_PRESTATE_EXACT = 2509
EXPECTED_POSTSTATE_EXACT = 2523
EXPECTED_PRESTATE_FAMILIES = 18
EXPECTED_POSTSTATE_FAMILIES = 19

EXPECTED_CANONICAL_SHA256 = "8d21112ab6d9c8a865e5ce6ccda221b1fee17cbac750ceb042ea41111379fe8d"
EXPECTED_CANONICAL_GIT_BLOB_SHA = "15a0d57b7f94c05f745a1768036fef9f01ec1fd9"
EXPECTED_READINESS_GIT_BLOB_SHA = "1038b32f0dc9e81958e42eb9df6478bf393c60f3"
EXPECTED_EXACT_SET_SHA256 = "56efc2b0fe64354ba9bdb626e592aae0cc2f2ae4208cadd7cbe6e08f9585887e"
EXPECTED_PRESTATE_MANIFEST_GIT_BLOB_SHA = "3b59475ad7a45710e9015a8d1cfbb38d8dee7ece"

EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 14}
EXPECTED_MAPPING_COUNTS = {"deterministic_ordering_pattern": 14}
EXPECTED_VERIFICATION_COUNTS = {
    "verified_st_datasheet_ordering_information_plus_retained_exact_identity": 14
}

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
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _set_sha(values: set[str]) -> str:
    return hashlib.sha256(
        ("\n".join(sorted(values)) + "\n").encode("utf-8")
    ).hexdigest()


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


def _validate_governance() -> None:
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

    readiness_bytes = READINESS.read_bytes()
    if _git_blob_sha(readiness_bytes) != EXPECTED_READINESS_GIT_BLOB_SHA:
        raise RuntimeError("STM32WBA2X admission-readiness baseline Git blob drifted")
    readiness = json.loads(readiness_bytes.decode("utf-8"))
    claims = readiness.get("claims")
    if (
        readiness.get("gate_id") != "stm32wba2x-bounded-exact-icpn-admission-readiness-v1"
        or readiness.get("research_series") != SERIES
        or readiness.get("family") != FAMILY
        or readiness.get("manufacturer") != MANUFACTURER
        or readiness.get("catalog_admission_ready") is not True
        or readiness.get("next_gate") != "stm32wba2x-production-publication-gate"
        or readiness.get("frozen_exact_icpn_count") != EXPECTED_ROWS
        or readiness.get("frozen_exact_icpn_set_sha256") != EXPECTED_EXACT_SET_SHA256
        or readiness.get("excluded_non_active_part_number_count") != EXPECTED_EXCLUDED_NON_ACTIVE
        or readiness.get("canonical_candidate_csv_sha256") != EXPECTED_CANONICAL_SHA256
        or readiness.get("identity_ready_count") != EXPECTED_ROWS
        or readiness.get("lifecycle_ready_count") != EXPECTED_ROWS
        or readiness.get("metadata_ready_count") != EXPECTED_ROWS
        or readiness.get("route_ready_count") != EXPECTED_ROWS
        or readiness.get("manual_review_count") != 0
        or readiness.get("metadata_exception_count") != 0
        or readiness.get("route_bridge_count") != 0
        or readiness.get("route_assignment_kind_counts") != EXPECTED_ROUTE_KIND_COUNTS
        or readiness.get("production_exact_icpn_count") != EXPECTED_PRESTATE_EXACT
        or readiness.get("production_family_count") != EXPECTED_PRESTATE_FAMILIES
        or not isinstance(claims, dict)
    ):
        raise RuntimeError("STM32WBA2X admission-readiness baseline drifted")

    for key in (
        "production_write_authorized",
        "production_publication_authorized",
        "programming_algorithm_equivalence_claimed",
        "runtime_programming_support_claimed",
        "wireless_radio_operation_authorized",
        "wireless_security_operation_authorized",
        "security_mutation_authorized",
        "debug_attach_supported",
        "target_execution_authorized",
        "physical_validation_claimed",
        "hil_required_for_catalog_admission",
        "remaining_wireless_families_rejected",
    ):
        if claims.get(key) is not False:
            raise RuntimeError(f"unsafe STM32WBA2X readiness claim enabled: {key}")


def _derive_prestate(current: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if (
        current.get("schema_version") != 1
        or current.get("status") != "production"
        or current.get("selection_policy") != "admitted_exact_manufacturer_part_number_only"
    ):
        raise RuntimeError("Production manifest contract drifted")

    sources = current.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("Production manifest sources missing")
    family_sources = [
        source for source in sources
        if isinstance(source, dict) and source.get("family") == FAMILY
    ]
    if len(family_sources) > 1:
        raise RuntimeError("duplicate STM32WBA2X Production sources")

    retained = [
        source for source in sources
        if not (isinstance(source, dict) and source.get("family") == FAMILY)
    ]
    prestate = {**current, "sources": retained}
    prestate_bytes = _json_bytes(prestate)
    if _git_blob_sha(prestate_bytes) != EXPECTED_PRESTATE_MANIFEST_GIT_BLOB_SHA:
        raise RuntimeError("STM32WBA2X frozen Production prestate drifted")

    exact, families, family_set = _production_snapshot(prestate)
    if (
        exact != EXPECTED_PRESTATE_EXACT
        or families != EXPECTED_PRESTATE_FAMILIES
        or FAMILY in family_set
    ):
        raise RuntimeError(
            f"Production prestate drifted: exact={exact} families={families}"
        )
    return prestate, family_sources[0] if family_sources else None


def _canonical_bytes() -> bytes:
    canonical = CANONICAL.read_bytes()
    if _sha256(canonical) != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("STM32WBA2X canonical candidate SHA-256 drifted")
    if _git_blob_sha(canonical) != EXPECTED_CANONICAL_GIT_BLOB_SHA:
        raise RuntimeError("STM32WBA2X canonical candidate Git blob drifted")

    rows = list(csv.DictReader(io.StringIO(canonical.decode("utf-8"))))
    if tuple(rows[0].keys()) != PRODUCTION_FIELDS if rows else True:
        raise RuntimeError("STM32WBA2X canonical schema drifted")
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"STM32WBA2X canonical row count drifted: {len(rows)}")

    icpns = {row["icpn"] for row in rows}
    bases = {row["base_device"] for row in rows}
    if len(icpns) != EXPECTED_ROWS or _set_sha(icpns) != EXPECTED_EXACT_SET_SHA256:
        raise RuntimeError("STM32WBA2X exact ICPN set drifted")
    if len(bases) != EXPECTED_ACTIVE_BASES:
        raise RuntimeError(f"STM32WBA2X Active Base Device count drifted: {len(bases)}")
    if {row["family"] for row in rows} != {FAMILY}:
        raise RuntimeError("STM32WBA2X canonical file contains foreign family")
    if {row["manufacturer"] for row in rows} != {MANUFACTURER}:
        raise RuntimeError("STM32WBA2X manufacturer drifted")
    if Counter(row["existing_identifier_kind"] for row in rows) != Counter(EXPECTED_ROUTE_KIND_COUNTS):
        raise RuntimeError("STM32WBA2X route-assignment kind counts drifted")
    if Counter(row["mapping_status"] for row in rows) != Counter(EXPECTED_MAPPING_COUNTS):
        raise RuntimeError("STM32WBA2X mapping method counts drifted")
    if Counter(row["verification_status"] for row in rows) != Counter(EXPECTED_VERIFICATION_COUNTS):
        raise RuntimeError("STM32WBA2X verification status counts drifted")
    if any(row["openocd_target_config"] != TARGET_CONFIG for row in rows):
        raise RuntimeError("STM32WBA2X target config drifted")
    if any(row["cmsis_device_name"] for row in rows):
        raise RuntimeError("STM32WBA2X commercial route unexpectedly uses CMSIS identity")
    if any(not row["source_reference"] or not row["source_authority"] for row in rows):
        raise RuntimeError("STM32WBA2X authoritative provenance missing")
    return canonical


def render_publication() -> tuple[bytes, bytes, dict[str, Any]]:
    _validate_governance()
    canonical = _canonical_bytes()
    current = _read_json(PRODUCTION_MANIFEST)
    prestate, existing = _derive_prestate(current)

    source = {
        "manufacturer": MANUFACTURER,
        "family": FAMILY,
        "path": "../research/stm32wba2x-commercial-icpn.csv",
        "row_count": EXPECTED_ROWS,
        "git_blob_sha": EXPECTED_CANONICAL_GIT_BLOB_SHA,
        "sha256": EXPECTED_CANONICAL_SHA256,
    }
    if existing is not None and existing != source:
        raise RuntimeError("checked-in STM32WBA2X Production source binding drifted")

    post_manifest = {**prestate, "sources": [*prestate["sources"], source]}
    manifest_bytes = _json_bytes(post_manifest)
    after_exact, after_family_count, after_families = _production_snapshot(post_manifest)
    if (
        after_exact != EXPECTED_POSTSTATE_EXACT
        or after_family_count != EXPECTED_POSTSTATE_FAMILIES
        or FAMILY not in after_families
    ):
        raise RuntimeError("STM32WBA2X proposed Production poststate drifted")
    if existing is not None and PRODUCTION_MANIFEST.read_bytes() != manifest_bytes:
        raise RuntimeError("checked-in Production manifest is not deterministic STM32WBA2X poststate")

    proposal = {
        "schema_version": 1,
        "transaction": "stm32wba2x-production-catalog-publication",
        "status": "publication_ready",
        "manufacturer": MANUFACTURER,
        "research_series": SERIES,
        "family": FAMILY,
        "readiness_baseline": READINESS.name,
        "readiness_git_blob_sha": EXPECTED_READINESS_GIT_BLOB_SHA,
        "canonical_csv_git_blob_sha": EXPECTED_CANONICAL_GIT_BLOB_SHA,
        "canonical_csv_sha256": EXPECTED_CANONICAL_SHA256,
        "exact_icpn_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "published_exact_icpns": EXPECTED_ROWS,
        "published_active_base_devices": EXPECTED_ACTIVE_BASES,
        "discovery_base_devices": EXPECTED_DISCOVERY_BASES,
        "excluded_non_active_part_numbers": EXPECTED_EXCLUDED_NON_ACTIVE,
        "marketing_status_observed": {"Active": EXPECTED_ROWS},
        "route_assignment_kind_counts": EXPECTED_ROUTE_KIND_COUNTS,
        "mapping_status_counts": EXPECTED_MAPPING_COUNTS,
        "metadata_exception_count": 0,
        "route_bridge_count": 0,
        "production_exact_icpns_before": EXPECTED_PRESTATE_EXACT,
        "production_exact_icpns_after": EXPECTED_POSTSTATE_EXACT,
        "production_family_count_before": EXPECTED_PRESTATE_FAMILIES,
        "production_family_count_after": EXPECTED_POSTSTATE_FAMILIES,
        "production_manifest_git_blob_before": EXPECTED_PRESTATE_MANIFEST_GIT_BLOB_SHA,
        "catalog_admission_policy": "icpn-catalog-admission-separation",
        "ppu_hil_required_for_catalog_admission": False,
        "socket_hil_required_for_catalog_admission": False,
        "physical_programming_success_required_for_catalog_admission": False,
        "physical_validation_claimed": False,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_programming_support_claimed": False,
        "wireless_radio_operation_authorized": False,
        "wireless_security_operation_authorized": False,
        "security_mutation_support_claimed": False,
        "debug_attach_support_claimed": False,
        "catalog_membership_authorizes_target_execution": False,
        "remaining_wireless_families_rejected": False,
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
        (args.output_dir / "stm32wba2x-commercial-icpn.csv").write_bytes(canonical)
        (args.output_dir / "icpn-v1-manifest.json").write_bytes(manifest)
        (args.output_dir / "stm32wba2x-production-publication-proposal.json").write_text(
            json.dumps(proposal, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(proposal, sort_keys=True) if args.json else json.dumps(proposal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
