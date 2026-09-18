#!/usr/bin/env python3
"""Assess STM32H7RS exact-ICPN Catalog admission readiness.

Research-only. This gate validates commercial identity, lifecycle, metadata and
backend route readiness. It does not write Production and does not authorize
runtime programming, security mutation, physical validation, or HIL.
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
DISCOVERY_DIR = HERE / "evidence/stm32h7rs-exact-icpn-live-2026-09-16"
DISCOVERY = DISCOVERY_DIR / "discovery-summary.json"
EXACT = DISCOVERY_DIR / "exact-icpns.json"
PARTITION = HERE / "stm32h7-partition-source.json"
AUTHORITY = HERE / "stm32h7rs-metadata-authority.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

FAMILY = "STM32H7RS"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32h7rsx.cfg"
EXPECTED_EXACT_COUNT = 36
EXPECTED_EXACT_SHA256 = "82c7aadf665af597bd02b0bfae2a5649bed3407e44ed58074c86b76e2d2e0fce"
EXPECTED_BASE_COUNT = 20
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 31, "cmsis_device_name": 5}
EXPECTED_PRODUCTION_COUNT = 2282
NEXT_GATE = "stm32h7rs-production-publication-gate"

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
    return hashlib.sha256(text.encode()).hexdigest()

def commercial_core(icpn: str) -> str:
    return icpn[:-2] if icpn.endswith("TR") else icpn

def pattern_matches(pattern: str, value: str) -> bool:
    expression = "".join("[A-Z0-9]" if c.lower() == "x" else re.escape(c) for c in pattern)
    return re.fullmatch(expression, value) is not None

def authority_for_series(authority: dict[str, Any], series: str) -> dict[str, Any]:
    matches = [doc for doc in authority["documents"] if series in doc["scope"]]
    req(len(matches) == 1, f"{series}: ordering authority must be unique")
    return matches[0]

def validate_inputs() -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    discovery, exact_obj, partition, authority, production = (
        load(DISCOVERY), load(EXACT), load(PARTITION), load(AUTHORITY), load(PRODUCTION)
    )
    req(discovery.get("discovery_id") == "stm32h7rs-bounded-exact-icpn-discovery-v1", "discovery id drifted")
    req(discovery.get("bounded_exact_discovery_complete") is True, "exact discovery incomplete")
    req(discovery.get("manual_review_targets") == 0, "discovery manual review opened")
    req(discovery.get("excluded_non_active_part_number_count") == 0, "non-active identities retained")
    req(discovery.get("active_exact_icpn_count") == EXPECTED_EXACT_COUNT, "discovery count drifted")
    req(discovery.get("active_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "discovery digest drifted")
    req(discovery.get("next_gate") == "stm32h7rs-bounded-exact-icpn-admission-readiness-gate", "upstream next gate drifted")
    claims = discovery.get("claims") or {}
    req(claims.get("production_write_authorized") is False, "upstream Production fence opened")
    req(claims.get("icpn_admission_authorized") is False, "upstream admission fence opened")

    exact = exact_obj.get("exact_icpns")
    req(isinstance(exact, list) and len(exact) == EXPECTED_EXACT_COUNT, "exact snapshot malformed")
    req(exact == sorted(set(exact)), "exact snapshot not sorted unique")
    req(exact_obj.get("exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "exact snapshot digest drifted")
    req(sha256_text("\n".join(exact) + "\n") == EXPECTED_EXACT_SHA256, "exact snapshot recompute failed")

    rows = [
        row for row in partition.get("rows", [])
        if row.get("family") == "STM32H7RS Series" and row.get("target_config") == TARGET_CONFIG
    ]
    req(len(rows) == 34, "STM32H7RS frozen route row count drifted")
    req(Counter(row.get("identifier_kind") for row in rows) == Counter({"ordering_pattern": 30, "cmsis_device_name": 4}), "route evidence kind surface drifted")
    req(all(row.get("vendor") == MANUFACTURER for row in rows), "foreign manufacturer route row")
    req(all(row.get("mapping_status") == "mapping_candidate" for row in rows), "route mapping status drifted")
    req(all(row.get("validation_status") == "not_verified" for row in rows), "route validation semantics drifted")

    req(authority.get("authority_id") == "stm32h7rs-ordering-information-v1", "metadata authority id drifted")
    req(authority.get("manufacturer") == MANUFACTURER and authority.get("family") == FAMILY, "metadata authority scope drifted")
    req(len(authority.get("documents", [])) == 2, "metadata authority document count drifted")
    req((authority.get("claims") or {}).get("hil_required_for_catalog_admission") is False, "metadata authority HIL fence drifted")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(item.get("row_count", 0)) for item in sources) == EXPECTED_PRODUCTION_COUNT, "Production count drifted")
    req(all(item.get("family") != FAMILY for item in sources), "STM32H7RS already present in Production")
    return exact, rows, authority

def decode(icpn: str, authority: dict[str, Any]) -> dict[str, str]:
    core = commercial_core(icpn)
    req(core.startswith("STM32H7") and len(core) in {13, 14}, f"{icpn}: unexpected ordering length")
    series = core[:9]
    req(series in {"STM32H7R3", "STM32H7R7", "STM32H7S3", "STM32H7S7"}, f"{icpn}: unknown series")
    pin_code, flash_code, package_code, temp_code = core[9], core[10], core[11], core[12]
    suffix = core[13:]

    semantics = authority["ordering_semantics"]
    req(flash_code == "8" and semantics["flash_size"].get(flash_code) == "64 KiB", f"{icpn}: flash code unresolved")
    package = semantics["package"].get(package_code)
    req(isinstance(package, str), f"{icpn}: package code unresolved")
    temp = semantics["temperature_grade"].get(temp_code)
    req(isinstance(temp, str), f"{icpn}: temperature code unresolved")
    pin = semantics["pin_count"].get(pin_code)
    req(isinstance(pin, str), f"{icpn}: pin-count code unresolved")
    if pin_code == "V":
        pin = "101" if package_code == "Y" else "100"
    req(suffix in {"", "H"}, f"{icpn}: unsupported functional suffix {suffix!r}")
    if suffix == "H":
        req(semantics["functional_option"].get("H") == "Hexadeca SPI support", f"{icpn}: H option unresolved")

    full_suffix = icpn[13:]
    req(full_suffix in {"", "H", "TR", "HTR"}, f"{icpn}: unsupported option/packing suffix")
    if full_suffix.endswith("TR"):
        req(semantics["packing"].get("TR") == "tape and reel", f"{icpn}: TR packing unresolved")

    doc = authority_for_series(authority, series)
    return {
        "series": series,
        "base_device": core[:11],
        "package": package,
        "pin_count": pin,
        "flash_size": "64 KiB",
        "temperature_grade": temp,
        "option_suffix": full_suffix,
        "source_reference": f'{doc["document_id"]} {doc["revision"]} Ordering Information',
        "source_authority": doc["url"],
    }

def resolve_route(icpn: str, rows: list[dict[str, Any]]) -> dict[str, str]:
    core = commercial_core(icpn)
    matches = [row for row in rows if pattern_matches(str(row["part_number"]), core)]
    req(len(matches) == 1, f"{icpn}: expected one route, got {len(matches)}")
    row = matches[0]
    kind = str(row["identifier_kind"])
    req(kind in {"ordering_pattern", "cmsis_device_name"}, f"{icpn}: unsupported route kind")
    return {
        "existing_identifier": str(row["part_number"]),
        "existing_identifier_kind": kind,
        "cmsis_device_name": str(row["part_number"]) if kind == "cmsis_device_name" else "",
        "mapping_status": "deterministic_cmsis_device_name" if kind == "cmsis_device_name" else "deterministic_ordering_pattern",
        "openocd_target_config": str(row["target_config"]),
    }

def build_rows() -> list[dict[str, str]]:
    exact, route_rows, authority = validate_inputs()
    output: list[dict[str, str]] = []
    for icpn in exact:
        metadata = decode(icpn, authority)
        route = resolve_route(icpn, route_rows)
        values = {
            "manufacturer": MANUFACTURER,
            "icpn": icpn,
            "family": FAMILY,
            **metadata,
            **route,
            "source_type": "official_st_datasheet_ordering_information_plus_retained_exact_identity",
            "verification_status": "verified_st_datasheet_ordering_information_plus_retained_exact_identity",
        }
        output.append({field: values[field] for field in CSV_FIELDS})
    req(len(output) == EXPECTED_EXACT_COUNT and len({row["icpn"] for row in output}) == EXPECTED_EXACT_COUNT, "canonical row cardinality drifted")
    kinds = Counter(row["existing_identifier_kind"] for row in output)
    req(dict(kinds) == EXPECTED_ROUTE_KIND_COUNTS, f"route assignment kinds drifted: {dict(kinds)}")
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
    csv_payload = csv_text(rows)
    suffixes = Counter(row["option_suffix"] for row in rows)
    packages = Counter(row["package"] for row in rows)
    series = Counter(row["series"] for row in rows)
    kinds = Counter(row["existing_identifier_kind"] for row in rows)
    return {
        "schema_version": 1,
        "gate_id": "stm32h7rs-bounded-exact-icpn-admission-readiness-v1",
        "authority": "research_only",
        "manufacturer": MANUFACTURER,
        "family": FAMILY,
        "production_exact_icpn_count": EXPECTED_PRODUCTION_COUNT,
        "frozen_exact_icpn_count": EXPECTED_EXACT_COUNT,
        "frozen_exact_icpn_set_sha256": EXPECTED_EXACT_SHA256,
        "identity_ready_count": EXPECTED_EXACT_COUNT,
        "lifecycle_ready_count": EXPECTED_EXACT_COUNT,
        "metadata_ready_count": EXPECTED_EXACT_COUNT,
        "route_ready_count": EXPECTED_EXACT_COUNT,
        "manual_review_count": 0,
        "route_assignment_kind_counts": dict(sorted(kinds.items())),
        "required_target_config": TARGET_CONFIG,
        "series_counts": dict(sorted(series.items())),
        "package_counts": dict(sorted(packages.items())),
        "option_suffix_counts": dict(sorted(suffixes.items())),
        "canonical_candidate_csv": "stm32h7rs-commercial-icpn.csv",
        "canonical_candidate_csv_sha256": sha256_text(csv_payload),
        "metadata_authority": "stm32h7rs-metadata-authority.json",
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
