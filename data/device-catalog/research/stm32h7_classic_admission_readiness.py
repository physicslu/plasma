#!/usr/bin/env python3
"""Assess STM32H7-classic exact-ICPN Catalog admission readiness.

Research-only. This gate validates the frozen Active identity set, lifecycle,
official-ST metadata authority, and deterministic Catalog backend routing. It
does not write Production and does not authorize runtime programming, security
mutation, debug attach, physical validation, HIL, or target execution.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DISCOVERY_DIR = HERE / "evidence/stm32h7-classic-exact-icpn-live-2026-09-18"
DISCOVERY = DISCOVERY_DIR / "discovery-summary.json"
EXACT = DISCOVERY_DIR / "exact-icpns.json"
PARTITION = HERE / "stm32h7-partition-source.json"
AUTHORITY = HERE / "stm32h7-classic-metadata-authority.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

PARTITION_ID = "STM32H7-classic"
FAMILY = "STM32H7"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32h7x.cfg"
EXPECTED_EXACT_COUNT = 191
EXPECTED_EXACT_SHA256 = "7ac4feb19ef5a7c75d2eeaf3cc1334b89d28862aceb2702d59fecc71ae0dd6c7"
EXPECTED_EXCLUDED_COUNT = 19
EXPECTED_BASE_COUNT = 102
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 178, "cmsis_device_name": 13}
EXPECTED_ROUTE_BRIDGE_COUNT = 1
EXPECTED_METADATA_EXCEPTION_COUNT = 1
EXPECTED_PRODUCTION_COUNT = 2318
NEXT_GATE = "stm32h7-classic-production-publication-gate"

CSV_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package",
    "pin_count", "flash_size", "temperature_grade", "option_suffix",
    "cmsis_device_name", "existing_identifier", "existing_identifier_kind",
    "mapping_status", "openocd_target_config", "source_type",
    "source_reference", "source_authority", "verification_status",
)


def req(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def commercial_core(icpn: str) -> str:
    return icpn[:-2] if icpn.endswith("TR") else icpn


def pattern_matches(pattern: str, value: str) -> bool:
    # Critical H7-classic rule: uppercase X is a literal device code.
    expression = "".join("[A-Z0-9]" if c == "x" else re.escape(c) for c in pattern)
    return re.fullmatch(expression, value) is not None


def document_for_series(authority: dict[str, Any], series: str) -> dict[str, Any]:
    docs = [
        doc for doc in authority["documents"]
        if series in doc.get("scope", [])
    ]
    req(len(docs) == 1, f"{series}: ordering authority must be unique")
    return docs[0]


def retained_identity_record(icpn: str) -> dict[str, Any]:
    base = commercial_core(icpn)[:11]
    evidence = load(DISCOVERY_DIR / f"{base.lower()}.json")
    req(evidence.get("base_device") == base, f"{icpn}: retained evidence Base Device mismatch")
    req(evidence.get("acquisition_transport") == "chromium_rendered_dom", f"{icpn}: retained transport drifted")
    exact = evidence.get("exact_icpns")
    req(isinstance(exact, list) and icpn in exact, f"{icpn}: missing from retained Active evidence")
    records = evidence.get("part_number_records")
    req(isinstance(records, list), f"{icpn}: retained part-number records missing")
    matches = [row for row in records if isinstance(row, dict) and row.get("icpn") == icpn]
    req(len(matches) == 1 and matches[0].get("active") is True, f"{icpn}: retained lifecycle is not Active")
    return matches[0]


def validate_inputs() -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    discovery = load(DISCOVERY)
    exact_obj = load(EXACT)
    partition = load(PARTITION)
    authority = load(AUTHORITY)
    production = load(PRODUCTION)

    req(discovery.get("discovery_id") == "stm32h7-classic-bounded-exact-icpn-discovery-v1", "discovery id drifted")
    req(discovery.get("selected_partition") == PARTITION_ID, "discovery partition drifted")
    req(discovery.get("bounded_exact_discovery_complete") is True, "exact discovery incomplete")
    req(discovery.get("base_device_count") == EXPECTED_BASE_COUNT, "Base Device boundary drifted")
    req(discovery.get("successful_targets") == EXPECTED_BASE_COUNT, "discovery success count drifted")
    req(discovery.get("manual_review_targets") == 0, "discovery manual review opened")
    req(discovery.get("active_exact_icpn_count") == EXPECTED_EXACT_COUNT, "discovery exact count drifted")
    req(discovery.get("active_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "discovery exact digest drifted")
    req(discovery.get("excluded_non_active_part_number_count") == EXPECTED_EXCLUDED_COUNT, "lifecycle exclusion count drifted")
    req(discovery.get("next_gate") == "stm32h7-classic-bounded-exact-icpn-admission-readiness-gate", "upstream next gate drifted")
    claims = discovery.get("claims") or {}
    req(claims.get("production_write_authorized") is False, "upstream Production fence opened")
    req(claims.get("icpn_admission_authorized") is False, "upstream admission fence opened")

    exact = exact_obj.get("exact_icpns")
    req(isinstance(exact, list) and len(exact) == EXPECTED_EXACT_COUNT, "exact snapshot malformed")
    req(exact == sorted(set(exact)), "exact snapshot not sorted unique")
    req(exact_obj.get("exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "exact snapshot digest drifted")
    req(sha256_text("\n".join(exact) + "\n") == EXPECTED_EXACT_SHA256, "exact snapshot recompute failed")
    excluded = discovery.get("excluded_non_active_part_numbers")
    req(isinstance(excluded, list) and len(excluded) == EXPECTED_EXCLUDED_COUNT, "excluded snapshot malformed")
    req(not (set(exact) & set(excluded)), "Active/excluded identity overlap")

    rows = [
        row for row in partition.get("rows", [])
        if row.get("family") == "STM32H7 Series" and row.get("target_config") == TARGET_CONFIG
    ]
    req(len(rows) == 166, "STM32H7-classic frozen route row count drifted")
    req(Counter(row.get("identifier_kind") for row in rows) == Counter({"ordering_pattern": 138, "cmsis_device_name": 28}), "route evidence kind surface drifted")
    req(all(row.get("vendor") == MANUFACTURER for row in rows), "foreign manufacturer route row")
    req(all(row.get("mapping_status") == "mapping_candidate" for row in rows), "route mapping status drifted")

    req(authority.get("authority_id") == "stm32h7-classic-ordering-information-v1", "metadata authority id drifted")
    req(authority.get("manufacturer") == MANUFACTURER, "metadata manufacturer drifted")
    req(authority.get("family") == FAMILY and authority.get("partition") == PARTITION_ID, "metadata authority scope drifted")
    req(len(authority.get("documents", [])) == 15, "metadata authority document count drifted")
    req(len(authority.get("metadata_exceptions", {})) == EXPECTED_METADATA_EXCEPTION_COUNT, "metadata exception count drifted")
    req(set(authority.get("metadata_exceptions", {})) == {"STM32H747IIT3"}, "metadata exception identity drifted")
    req(all(value is False for value in (authority.get("claims") or {}).values()), "metadata authority fail-closed claims escaped")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(item.get("row_count", 0)) for item in sources) == EXPECTED_PRODUCTION_COUNT, "Production count drifted")
    req(all(item.get("family") != FAMILY for item in sources), "STM32H7 already present in Production")
    return exact, rows, authority


def decode_metadata(icpn: str, authority: dict[str, Any]) -> dict[str, str]:
    core = commercial_core(icpn)
    req(core.startswith("STM32H7") and len(core) in {13, 14}, f"{icpn}: unexpected ordering length")
    series = core[:9]
    pin_code, flash_code, package_code, temp_code = core[9], core[10], core[11], core[12]
    functional = core[13:]

    doc = document_for_series(authority, series)
    common = authority["common_semantics"]
    package = common["package"].get(package_code)
    flash = common["flash_size"].get(flash_code)
    temp = common["temperature_grade"].get(temp_code)
    pins = (authority.get("pin_count_by_series") or {}).get(series, {}).get(pin_code)
    override_key = f"{series}:{pin_code}:{package_code}"
    pins = (authority.get("pin_count_overrides") or {}).get(override_key, pins)

    req(isinstance(package, str), f"{icpn}: package code unresolved")
    req(isinstance(flash, str), f"{icpn}: flash code unresolved")
    req(isinstance(temp, str), f"{icpn}: temperature code unresolved")
    req(isinstance(pins, str), f"{icpn}: pin-count code unresolved")
    req(functional in {"", "A", "Q"}, f"{icpn}: unsupported functional suffix {functional!r}")
    if functional:
        allowed = (authority.get("allowed_functional_options_by_series") or {}).get(series, [])
        req(functional in allowed, f"{icpn}: functional option not authorized for series")
        req(functional in common["functional_option"], f"{icpn}: functional option semantics missing")
    if icpn.endswith("TR"):
        req(common["packing"].get("TR") == "tape and reel", f"{icpn}: TR packing unresolved")

    option_suffix = functional + ("TR" if icpn.endswith("TR") else "")
    source_type = "official_st_datasheet_ordering_information_plus_retained_exact_identity"
    source_reference = f'{doc["document_id"]} {doc["revision"]} Ordering Information'
    source_authority = str(doc["url"])
    verification_status = "verified_st_datasheet_ordering_information_plus_retained_exact_identity"

    exception = (authority.get("metadata_exceptions") or {}).get(icpn)
    if exception is not None:
        req(isinstance(exception, dict), f"{icpn}: malformed metadata exception")
        package = str(exception["package"])
        pins = str(exception["pin_count"])
        flash = str(exception["flash_size"])
        temp = str(exception["temperature_grade"])
        source_type = "official_st_datasheet_plus_official_st_store_exception_plus_retained_exact_identity"
        source_reference = f'{doc["document_id"]} {doc["revision"]} Ordering Information + {exception["source_reference"]}'
        source_authority = str(exception["source_authority"])
        verification_status = "verified_st_official_exception_plus_retained_exact_identity"

    return {
        "series": series,
        "base_device": core[:11],
        "package": package,
        "pin_count": pins,
        "flash_size": flash,
        "temperature_grade": temp,
        "option_suffix": option_suffix,
        "source_type": source_type,
        "source_reference": source_reference,
        "source_authority": source_authority,
        "verification_status": verification_status,
    }


def resolve_route(icpn: str, rows: list[dict[str, Any]], authority: dict[str, Any]) -> dict[str, str]:
    core = commercial_core(icpn)
    matches = [row for row in rows if pattern_matches(str(row["part_number"]), core)]
    bridge = ""

    if not matches and core.endswith("A"):
        series = core[:9]
        allowed = (authority.get("allowed_functional_options_by_series") or {}).get(series, [])
        req("A" in allowed, f"{icpn}: A bridge not authorized")
        bridged = core[:-1]
        matches = [row for row in rows if pattern_matches(str(row["part_number"]), bridged)]
        bridge = "strip_official_functional_option_A"

    req(len(matches) == 1, f"{icpn}: expected one deterministic route, got {len(matches)}")
    row = matches[0]
    kind = str(row["identifier_kind"])
    req(kind in {"ordering_pattern", "cmsis_device_name"}, f"{icpn}: unsupported route kind")
    status = "deterministic_cmsis_device_name" if kind == "cmsis_device_name" else "deterministic_ordering_pattern"
    if bridge:
        status += "_via_functional_option_bridge"
    return {
        "existing_identifier": str(row["part_number"]),
        "existing_identifier_kind": kind,
        "cmsis_device_name": str(row["part_number"]) if kind == "cmsis_device_name" else "",
        "mapping_status": status,
        "openocd_target_config": str(row["target_config"]),
        "_route_bridge": bridge,
    }


def build_rows() -> list[dict[str, str]]:
    exact, route_rows, authority = validate_inputs()
    output: list[dict[str, str]] = []
    bridges = 0
    exceptions = 0
    for icpn in exact:
        retained_identity_record(icpn)
        metadata = decode_metadata(icpn, authority)
        route = resolve_route(icpn, route_rows, authority)
        bridges += bool(route.pop("_route_bridge"))
        exceptions += icpn in (authority.get("metadata_exceptions") or {})
        values = {
            "manufacturer": MANUFACTURER,
            "icpn": icpn,
            "family": FAMILY,
            **metadata,
            **route,
        }
        output.append({field: values[field] for field in CSV_FIELDS})

    req(len(output) == EXPECTED_EXACT_COUNT and len({row["icpn"] for row in output}) == EXPECTED_EXACT_COUNT, "canonical row cardinality drifted")
    kinds = Counter(row["existing_identifier_kind"] for row in output)
    req(dict(kinds) == EXPECTED_ROUTE_KIND_COUNTS, f"route assignment kinds drifted: {dict(kinds)}")
    req(bridges == EXPECTED_ROUTE_BRIDGE_COUNT, f"route bridge count drifted: {bridges}")
    req(exceptions == EXPECTED_METADATA_EXCEPTION_COUNT, f"metadata exception count drifted: {exceptions}")
    req({row["openocd_target_config"] for row in output} == {TARGET_CONFIG}, "route target config drifted")
    return output


def csv_text(rows: list[dict[str, str]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def build_readiness() -> dict[str, Any]:
    rows = build_rows()
    payload = csv_text(rows)
    route_kinds = Counter(row["existing_identifier_kind"] for row in rows)
    series = Counter(row["series"] for row in rows)
    packages = Counter(row["package"] for row in rows)
    suffixes = Counter(row["option_suffix"] for row in rows)
    exception_count = sum(row["verification_status"] == "verified_st_official_exception_plus_retained_exact_identity" for row in rows)
    bridge_count = sum(row["mapping_status"].endswith("_via_functional_option_bridge") for row in rows)
    return {
        "schema_version": 1,
        "gate_id": "stm32h7-classic-bounded-exact-icpn-admission-readiness-v1",
        "authority": "research_only",
        "manufacturer": MANUFACTURER,
        "partition": PARTITION_ID,
        "family": FAMILY,
        "production_exact_icpn_count": EXPECTED_PRODUCTION_COUNT,
        "frozen_exact_icpn_count": EXPECTED_EXACT_COUNT,
        "frozen_exact_icpn_set_sha256": EXPECTED_EXACT_SHA256,
        "excluded_non_active_part_number_count": EXPECTED_EXCLUDED_COUNT,
        "identity_ready_count": EXPECTED_EXACT_COUNT,
        "lifecycle_ready_count": EXPECTED_EXACT_COUNT,
        "metadata_ready_count": EXPECTED_EXACT_COUNT,
        "route_ready_count": EXPECTED_EXACT_COUNT,
        "manual_review_count": 0,
        "metadata_exception_count": exception_count,
        "route_functional_option_bridge_count": bridge_count,
        "route_assignment_kind_counts": dict(sorted(route_kinds.items())),
        "required_target_config": TARGET_CONFIG,
        "series_counts": dict(sorted(series.items())),
        "package_counts": dict(sorted(packages.items())),
        "option_suffix_counts": dict(sorted(suffixes.items())),
        "canonical_candidate_csv": "stm32h7-classic-commercial-icpn.csv",
        "canonical_candidate_csv_sha256": sha256_text(payload),
        "metadata_authority": "stm32h7-classic-metadata-authority.json",
        "catalog_admission_ready": True,
        "next_gate": NEXT_GATE,
        "claims": {
            "production_write_authorized": False,
            "production_publication_authorized": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "security_mutation_authorized": False,
            "debug_attach_supported": False,
            "physical_validation_claimed": False,
            "hil_required_for_catalog_admission": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    rows = build_rows()
    readiness = build_readiness()
    if args.csv_output:
        args.csv_output.write_text(csv_text(rows), encoding="utf-8")
    if args.json_output:
        args.json_output.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not args.csv_output and not args.json_output:
        print(json.dumps(readiness, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
