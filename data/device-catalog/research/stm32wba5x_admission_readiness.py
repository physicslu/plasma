#!/usr/bin/env python3
"""Qualify STM32WBA5X exact-ICPN catalog admission readiness."""
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
SOURCE = HERE / "openocd-parts-canonical.csv"
RECONCILIATION = HERE / "stm32wba5x-commercial-scope-reconciliation-v2.json"
DISCOVERY = HERE / "evidence/stm32wba5x-exact-icpn-live-2026-09-23/discovery-summary.json"
EXACT = HERE / "evidence/stm32wba5x-exact-icpn-live-2026-09-23/exact-icpns.json"
AUTHORITY = HERE / "stm32wba5x-metadata-authority.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32WBA5X"
SERIES = "STM32WBA5X"
TARGET_CONFIG = "tcl/target/stm32wba5x.cfg"

EXPECTED_EXACT_COUNT = 40
EXPECTED_EXACT_SHA256 = "de7b479493688ad5ac4417682f384da64af391850e876b45a649823fbe395485"
EXPECTED_BASE_COUNT = 15
EXPECTED_SOURCE_ROWS = 34
EXPECTED_RECONCILED_ROWS = 31
EXPECTED_ORDERING_ROWS = 15
EXPECTED_CMSIS_ROWS = 16
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 40}
EXPECTED_MAPPING_COUNTS = {"deterministic_ordering_pattern": 40}
EXPECTED_PRODUCTION_COUNT = 2604
EXPECTED_PRODUCTION_FAMILIES = 21
EXPECTED_RECONCILIATION_BLOB = "bdf1cb00f895b19e2bf16653357068c46a90dd24"
EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"

PRODUCTION_FIELDS = (
    "manufacturer","icpn","family","series","base_device","package",
    "pin_count","flash_size","temperature_grade","option_suffix",
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config","source_type","source_reference",
    "source_authority","verification_status",
)

EXCLUDED = {
    ("STM32WBA50KEUx", "ordering_pattern"),
    ("STM32WBA50KEUxT", "cmsis_device_name"),
    ("STM32WBA55HEFx", "ordering_pattern"),
}

DOC_BY_SUBFAMILY = {
    "STM32WBA50": ("DS14688", "Rev 2"),
    "STM32WBA52": ("DS14127", "Rev 10"),
    "STM32WBA54": ("DS14127", "Rev 10"),
    "STM32WBA55": ("DS14127", "Rev 10"),
    "STM32WBA5M": ("DS14801", "Rev 4"),
}

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def git_blob_sha_bytes(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()

def git_blob_sha_text(text: str) -> str:
    return git_blob_sha_bytes(text.encode("utf-8"))

def pattern_matches(icpn: str, pattern: str) -> bool:
    value = icpn[:-2] if icpn.endswith("TR") else icpn
    if len(value) != len(pattern):
        return False
    return all(pc == "x" or pc == vc for vc, pc in zip(value, pattern))

def reconciled_rows() -> list[dict[str, str]]:
    req(sha256_bytes(SOURCE.read_bytes()) == EXPECTED_SOURCE_SHA256, "candidate source digest drifted")
    reconciliation_bytes = RECONCILIATION.read_bytes()
    req(git_blob_sha_bytes(reconciliation_bytes) == EXPECTED_RECONCILIATION_BLOB, "reconciliation blob drifted")
    reconciliation = json.loads(reconciliation_bytes)
    req(reconciliation.get("reconciliation_id") == "stm32wba5x-current-commercial-scope-reconciliation-v2", "reconciliation id drifted")
    surface = reconciliation.get("reconciled_surface") or {}
    req(
        surface.get("retained_rows") == EXPECTED_RECONCILED_ROWS
        and surface.get("ordering_pattern_rows") == EXPECTED_ORDERING_ROWS
        and surface.get("cmsis_device_name_rows") == EXPECTED_CMSIS_ROWS
        and surface.get("base_device_count") == EXPECTED_BASE_COUNT,
        "reconciled surface drifted",
    )
    req(reconciliation.get("next_gate") == "stm32wba5x-bounded-exact-icpn-discovery-gate", "reconciliation next gate drifted")

    with SOURCE.open(newline="", encoding="utf-8") as handle:
        all_rows = [
            row for row in csv.DictReader(handle)
            if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == SERIES
        ]
    req(len(all_rows) == EXPECTED_SOURCE_ROWS, "source row count drifted")
    rows = [
        row for row in all_rows
        if (row.get("part_number"), row.get("identifier_kind")) not in EXCLUDED
    ]
    req(len(rows) == EXPECTED_RECONCILED_ROWS, "retained route row count drifted")
    req(Counter(row["identifier_kind"] for row in rows) == Counter({"ordering_pattern":15,"cmsis_device_name":16}), "retained identifier mix drifted")
    req(all(row.get("target_config") == TARGET_CONFIG for row in rows), "target config drifted")
    return rows

def validate_inputs() -> tuple[list[str], dict[str, str], list[dict[str,str]], dict[str,Any]]:
    discovery = load_json(DISCOVERY)
    exact_obj = load_json(EXACT)
    authority = load_json(AUTHORITY)
    production = load_json(PRODUCTION)

    req(discovery.get("discovery_id") == "stm32wba5x-bounded-exact-icpn-discovery-v2", "discovery id drifted")
    req(discovery.get("status") == "discovered", "discovery is not complete")
    req(discovery.get("bounded_exact_discovery_complete") is True, "bounded discovery incomplete")
    req(discovery.get("base_device_count") == EXPECTED_BASE_COUNT, "Base Device count drifted")
    req(discovery.get("successful_targets") == EXPECTED_BASE_COUNT, "discovery success count drifted")
    req(discovery.get("manual_review_targets") == 0, "manual review opened")
    req(discovery.get("active_exact_icpn_count") == EXPECTED_EXACT_COUNT, "exact count drifted")
    req(discovery.get("active_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "exact digest drifted")
    req(discovery.get("excluded_non_active_part_number_count") == 0, "lifecycle exclusions opened")
    req(discovery.get("excluded_non_active_part_numbers") == [], "excluded identity set drifted")
    req(discovery.get("next_gate") == "stm32wba5x-bounded-exact-icpn-admission-readiness-gate", "readiness gate drifted")

    exact = exact_obj.get("exact_icpns")
    req(isinstance(exact, list) and len(exact) == EXPECTED_EXACT_COUNT, "exact snapshot malformed")
    req(exact_obj.get("exact_icpn_count") == EXPECTED_EXACT_COUNT, "exact snapshot count drifted")
    req(exact_obj.get("exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "exact snapshot digest drifted")
    req(sha256_text("\n".join(exact) + "\n") == EXPECTED_EXACT_SHA256, "exact digest recompute failed")
    req(exact == sorted(set(exact)), "exact set is not sorted unique")

    results = discovery.get("results")
    req(isinstance(results, list) and len(results) == EXPECTED_BASE_COUNT, "discovery result surface drifted")
    owners: dict[str,str] = {}
    for item in results:
        req(isinstance(item, dict), "discovery result must be object")
        base = item.get("base_device")
        req(isinstance(base, str), "Base Device missing")
        req(item.get("acquisition_status") == "success", f"{base}: discovery failure retained")
        req(item.get("manual_intervention_required") is False, f"{base}: manual review retained")
        for icpn in item.get("active_exact_icpns") or []:
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: foreign exact ICPN")
            req(icpn not in owners, f"{icpn}: duplicate exact identity")
            owners[icpn] = base
    req(sorted(owners) == exact, "per-Base exact identities differ from exact snapshot")

    req(authority.get("authority_id") == "stm32wba5x-ordering-information-v1", "metadata authority id drifted")
    docs = authority.get("documents")
    req(isinstance(docs, list) and len(docs) == 3, "metadata authority document set drifted")
    observed = {(d.get("document_id"), d.get("revision")) for d in docs if isinstance(d, dict)}
    req(observed == {("DS14688","Rev 2"),("DS14127","Rev 10"),("DS14801","Rev 4")}, "metadata authority revisions drifted")
    req(all(value is False for value in (authority.get("claims") or {}).values()), "metadata authority claims escaped fail-closed state")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(item.get("row_count",0)) for item in sources if isinstance(item,dict)) == EXPECTED_PRODUCTION_COUNT, "Production count drifted")
    req(len(sources) == EXPECTED_PRODUCTION_FAMILIES, "Production family count drifted")
    req(all(not (isinstance(item,dict) and item.get("family") == FAMILY) for item in sources), "STM32WBA5X already present in Production")

    return exact, owners, reconciled_rows(), authority

def resolve_route(icpn: str, rows: list[dict[str,str]]) -> dict[str,str]:
    matches = [row for row in rows if pattern_matches(icpn, row["part_number"])]
    req(len(matches) == 1, f"{icpn}: expected exactly one deterministic route, got {len(matches)}")
    row = matches[0]
    req(row.get("identifier_kind") == "ordering_pattern", f"{icpn}: current exact set unexpectedly requires CMSIS bridge")
    return {
        "series": row["subfamily"],
        "cmsis_device_name": "",
        "existing_identifier": row["part_number"],
        "existing_identifier_kind": "ordering_pattern",
        "mapping_status": "deterministic_ordering_pattern",
        "openocd_target_config": row["target_config"],
    }

def authority_doc(authority: dict[str,Any], subfamily: str) -> dict[str,Any]:
    wanted = DOC_BY_SUBFAMILY[subfamily]
    for doc in authority["documents"]:
        if (doc.get("document_id"), doc.get("revision")) == wanted:
            return doc
    raise RuntimeError(f"{subfamily}: metadata authority missing")

def split_suffix(icpn: str, base: str) -> tuple[str,str,str]:
    rem = icpn[len(base):]
    req(len(rem) >= 2, f"{icpn}: suffix too short")
    return rem[0], rem[1], rem[2:]

def decode_metadata(icpn: str, base: str, subfamily: str, authority: dict[str,Any]) -> dict[str,str]:
    doc = authority_doc(authority, subfamily)

    if subfamily == "STM32WBA5M":
        pkg, temp_code, option = split_suffix(icpn, base)
        req(base == "STM32WBA5MMG", f"{icpn}: unexpected WBA5M Base Device")
        req(pkg == "H" and temp_code == "6", f"{icpn}: WBA5M ordering code drifted")
        package, pin_count, flash, temp = "SIP LGA", "76", "1 MiB", "-40..85 C"
    else:
        req(base.startswith(subfamily) and len(base) == len(subfamily) + 2, f"{icpn}: unexpected Base Device form")
        pin_code, flash_code = base[-2], base[-1]
        pkg, temp_code, option = split_suffix(icpn, base)

        if subfamily == "STM32WBA50":
            req(base == "STM32WBA50KG", f"{icpn}: WBA50 current-commercial Base Device drifted")
            req((pin_code, flash_code, pkg, temp_code) == ("K","G","U","6"), f"{icpn}: WBA50 ordering code drifted")
        else:
            req(subfamily in {"STM32WBA52","STM32WBA54","STM32WBA55"}, f"{icpn}: unsupported subfamily")
            req(pin_code in {"K","H","C","U"}, f"{icpn}: unsupported pin-count code")
            req(flash_code in {"E","G"}, f"{icpn}: unsupported flash code")
            req(pkg in {"U","F","I"}, f"{icpn}: unsupported package code")
            req(temp_code in {"6","7"}, f"{icpn}: unsupported temperature code")

        pin_count = {"K":"32","H":"41","C":"48","U":"59"}[pin_code]
        flash = {"E":"512 KiB","G":"1 MiB"}[flash_code]
        package = {"U":"UFQFPN","F":"Thin WLCSP","I":"UFBGA"}[pkg]
        temp = {"6":"-40..85 C","7":"-40..105 C"}[temp_code]

        expected_pkg_by_pin = {"K":"U","H":"F","C":"U","U":"I"}
        req(pkg == expected_pkg_by_pin[pin_code], f"{icpn}: package/pin-count combination drifted")

    req(option in {"","TR"}, f"{icpn}: unexpected option suffix {option!r}")
    return {
        "base_device": base,
        "package": package,
        "pin_count": pin_count,
        "flash_size": flash,
        "temperature_grade": temp,
        "option_suffix": option,
        "source_type": "official_st_datasheet_ordering_information_plus_retained_exact_identity",
        "source_reference": f"{doc['document_id']} {doc['revision']} {doc['section']}",
        "source_authority": str(doc["url"]),
        "verification_status": "verified_st_datasheet_ordering_information_plus_retained_exact_identity",
    }

def build_rows() -> list[dict[str,str]]:
    exact, owners, route_rows, authority = validate_inputs()
    output: list[dict[str,str]] = []
    for icpn in exact:
        base = owners[icpn]
        route = resolve_route(icpn, route_rows)
        metadata = decode_metadata(icpn, base, route["series"], authority)
        output.append({
            "manufacturer": MANUFACTURER,
            "icpn": icpn,
            "family": FAMILY,
            **route,
            **metadata,
        })
    req(len(output) == EXPECTED_EXACT_COUNT and len({row["icpn"] for row in output}) == EXPECTED_EXACT_COUNT, "canonical row cardinality drifted")
    req(Counter(row["existing_identifier_kind"] for row in output) == Counter(EXPECTED_ROUTE_KIND_COUNTS), "route assignment counts drifted")
    req(Counter(row["mapping_status"] for row in output) == Counter(EXPECTED_MAPPING_COUNTS), "mapping status counts drifted")
    req({row["openocd_target_config"] for row in output} == {TARGET_CONFIG}, "target config drifted")
    req(all(row["cmsis_device_name"] == "" for row in output), "CMSIS bridge unexpectedly opened")
    return output

def csv_text(rows: list[dict[str,str]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=PRODUCTION_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

def build_readiness(rows: list[dict[str,str]], canonical: str) -> dict[str,Any]:
    return {
        "schema_version": 1,
        "readiness_id": "stm32wba5x-bounded-exact-icpn-admission-readiness-v1",
        "scope": "research_only_catalog_admission_readiness",
        "authority": "research_only",
        "manufacturer": MANUFACTURER,
        "research_series": SERIES,
        "family": FAMILY,
        "production_exact_icpn_count": EXPECTED_PRODUCTION_COUNT,
        "production_family_count": EXPECTED_PRODUCTION_FAMILIES,
        "frozen_exact_icpn_count": EXPECTED_EXACT_COUNT,
        "frozen_exact_icpn_set_sha256": EXPECTED_EXACT_SHA256,
        "excluded_non_active_part_number_count": 0,
        "excluded_non_active_part_numbers": [],
        "identity_ready_count": EXPECTED_EXACT_COUNT,
        "lifecycle_ready_count": EXPECTED_EXACT_COUNT,
        "metadata_ready_count": EXPECTED_EXACT_COUNT,
        "route_ready_count": EXPECTED_EXACT_COUNT,
        "manual_review_count": 0,
        "metadata_exception_count": 0,
        "route_bridge_count": 0,
        "route_assignment_kind_counts": dict(sorted(Counter(row["existing_identifier_kind"] for row in rows).items())),
        "mapping_status_counts": dict(sorted(Counter(row["mapping_status"] for row in rows).items())),
        "target_config": TARGET_CONFIG,
        "package_counts": dict(sorted(Counter(row["package"] for row in rows).items())),
        "temperature_grade_counts": dict(sorted(Counter(row["temperature_grade"] for row in rows).items())),
        "metadata_authority": "stm32wba5x-metadata-authority.json",
        "canonical_candidate": "stm32wba5x-commercial-icpn.csv",
        "canonical_candidate_sha256": sha256_text(canonical),
        "canonical_candidate_git_blob_sha": git_blob_sha_text(canonical),
        "catalog_admission_ready": True,
        "next_gate": "stm32wba5x-production-publication-gate",
        "claims": {
            "production_write_authorized": False,
            "production_publication_authorized": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "wireless_radio_operation_authorized": False,
            "wireless_security_operation_authorized": False,
            "security_mutation_authorized": False,
            "debug_attach_supported": False,
            "target_execution_authorized": False,
            "physical_validation_claimed": False,
            "hil_required_for_catalog_admission": False,
            "remaining_wireless_families_rejected": False,
            "stm32wba6x_rejected": False,
            "cmsis_bridge_authorizes_production_route": False,
        },
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--readiness-output", type=Path)
    args = parser.parse_args()

    rows = build_rows()
    canonical = csv_text(rows)
    readiness = json.dumps(build_readiness(rows, canonical), indent=2, sort_keys=True) + "\n"

    if args.csv_output:
        args.csv_output.write_text(canonical, encoding="utf-8")
    else:
        print(canonical, end="")
    if args.readiness_output:
        args.readiness_output.write_text(readiness, encoding="utf-8")
    else:
        print(readiness, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
