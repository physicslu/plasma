#!/usr/bin/env python3
"""Assess STM32WBA2X exact-ICPN Catalog admission readiness.

Research-only. Validates the frozen Active identity set, lifecycle, official-ST
metadata authority, and deterministic Catalog backend routing. It does not
write Production and does not authorize runtime programming, radio/security
operations, security mutation, debug attach, target execution, physical
validation, HIL, or programming-algorithm equivalence.
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
DISCOVERY_DIR = HERE / "evidence/stm32wba2x-exact-icpn-live-2026-09-18"
DISCOVERY = DISCOVERY_DIR / "discovery-summary.json"
EXACT = DISCOVERY_DIR / "exact-icpns.json"
SOURCE = HERE / "openocd-parts-canonical.csv"
AUTHORITY = HERE / "stm32wba2x-metadata-authority.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

SERIES = "STM32WBA2X"
FAMILY = "STM32WBA2X"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32wba2x.cfg"
EXPECTED_EXACT_COUNT = 14
EXPECTED_EXACT_SHA256 = "56efc2b0fe64354ba9bdb626e592aae0cc2f2ae4208cadd7cbe6e08f9585887e"
EXPECTED_EXCLUDED_COUNT = 0
EXPECTED_BASE_COUNT = 4
EXPECTED_SOURCE_ROWS = 8
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 14}
EXPECTED_PRODUCTION_COUNT = 2509
EXPECTED_PRODUCTION_FAMILIES = 18
NEXT_GATE = "stm32wba2x-production-publication-gate"

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
    expression = "".join("[A-Z0-9]" if c == "x" else re.escape(c) for c in pattern)
    return re.fullmatch(expression, value) is not None


def retained_identity_record(icpn: str) -> dict[str, Any]:
    base = commercial_core(icpn)[:12]
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


def validate_inputs() -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    discovery = load(DISCOVERY)
    exact_obj = load(EXACT)
    authority = load(AUTHORITY)
    production = load(PRODUCTION)

    req(discovery.get("discovery_id") == "stm32wba2x-bounded-exact-icpn-discovery-v1", "discovery id drifted")
    req(discovery.get("selected_wireless_frontier") == SERIES, "discovery frontier drifted")
    req(discovery.get("target_config") == TARGET_CONFIG, "discovery target config drifted")
    req(discovery.get("bounded_exact_discovery_complete") is True, "exact discovery incomplete")
    req(discovery.get("base_device_count") == EXPECTED_BASE_COUNT, "Base Device boundary drifted")
    req(discovery.get("successful_targets") == EXPECTED_BASE_COUNT, "discovery success count drifted")
    req(discovery.get("manual_review_targets") == 0, "discovery manual review opened")
    req(discovery.get("active_exact_icpn_count") == EXPECTED_EXACT_COUNT, "discovery exact count drifted")
    req(discovery.get("active_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "discovery exact digest drifted")
    req(discovery.get("excluded_non_active_part_number_count") == EXPECTED_EXCLUDED_COUNT, "lifecycle exclusion count drifted")
    req(discovery.get("next_gate") == "stm32wba2x-bounded-exact-icpn-admission-readiness-gate", "upstream next gate drifted")
    claims = discovery.get("claims") or {}
    req(claims.get("production_write_authorized") is False, "upstream Production fence opened")
    req(claims.get("icpn_admission_authorized") is False, "upstream admission fence opened")
    req(claims.get("wireless_radio_operation_authorized") is False, "upstream radio fence opened")
    req(claims.get("wireless_security_operation_authorized") is False, "upstream wireless-security fence opened")

    exact = exact_obj.get("exact_icpns")
    req(isinstance(exact, list) and len(exact) == EXPECTED_EXACT_COUNT, "exact snapshot malformed")
    req(exact == sorted(set(exact)), "exact snapshot not sorted unique")
    req(exact_obj.get("exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "exact snapshot digest drifted")
    req(sha256_text("\n".join(exact) + "\n") == EXPECTED_EXACT_SHA256, "exact snapshot recompute failed")

    with SOURCE.open(newline="", encoding="utf-8") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row.get("vendor") == MANUFACTURER
            and row.get("plasma_series") == SERIES
            and row.get("target_config") == TARGET_CONFIG
        ]
    req(len(rows) == EXPECTED_SOURCE_ROWS, "STM32WBA2X frozen route row count drifted")
    req(Counter(row.get("identifier_kind") for row in rows) == Counter({"ordering_pattern": 4, "cmsis_device_name": 4}), "route evidence surface drifted")
    req({row.get("subfamily") for row in rows} == {"STM32WBA23", "STM32WBA25"}, "subfamily surface drifted")
    req(all(row.get("mapping_status") == "mapping_candidate" for row in rows), "route mapping status drifted")

    req(authority.get("authority_id") == "stm32wba2x-ordering-information-v1", "metadata authority id drifted")
    req(authority.get("manufacturer") == MANUFACTURER, "metadata manufacturer drifted")
    req(authority.get("family") == FAMILY and authority.get("research_series") == SERIES, "metadata authority scope drifted")
    docs = authority.get("documents")
    req(isinstance(docs, list) and len(docs) == 1, "metadata authority document count drifted")
    req(docs[0].get("document_id") == "DS15003" and docs[0].get("revision") == "Rev 2", "metadata authority revision drifted")
    req(set(docs[0].get("scope") or []) == {"STM32WBA23", "STM32WBA25"}, "metadata document scope drifted")
    req(all(value is False for value in (authority.get("claims") or {}).values()), "metadata authority fail-closed claims escaped")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(item.get("row_count", 0)) for item in sources) == EXPECTED_PRODUCTION_COUNT, "Production count drifted")
    req(len(sources) == EXPECTED_PRODUCTION_FAMILIES, "Production family count drifted")
    req(all(item.get("family") != FAMILY for item in sources), "STM32WBA2X already present in Production")
    return exact, rows, authority


def decode_metadata(icpn: str, authority: dict[str, Any]) -> dict[str, str]:
    core = commercial_core(icpn)
    req(len(core) == 14 and core.startswith("STM32WBA"), f"{icpn}: unexpected ordering length")
    series = core[:10]
    pin_code, flash_code, package_code, temp_code = core[10], core[11], core[12], core[13]
    req(series in {"STM32WBA23", "STM32WBA25"}, f"{icpn}: unsupported WBA2 subfamily")
    semantics = authority["semantics"]

    pins = semantics["pin_count"].get(pin_code)
    flash = semantics["flash_size"].get(flash_code)
    package = semantics["package"].get(package_code)
    temp = semantics["temperature_grade"].get(temp_code)
    req(isinstance(pins, str), f"{icpn}: pin-count code unresolved")
    req(isinstance(flash, str), f"{icpn}: flash-size code unresolved")
    req(isinstance(package, str), f"{icpn}: package code unresolved")
    req(isinstance(temp, str), f"{icpn}: temperature code unresolved")
    if icpn.endswith("TR"):
        req(semantics["packing"].get("TR") == "tape and reel", f"{icpn}: TR packing unresolved")

    return {
        "series": series,
        "base_device": core[:12],
        "package": package,
        "pin_count": pins,
        "flash_size": flash,
        "temperature_grade": temp,
        "option_suffix": "TR" if icpn.endswith("TR") else "",
        "source_type": "official_st_datasheet_ordering_information_plus_retained_exact_identity",
        "source_reference": "DS15003 Rev 2 Ordering Information",
        "source_authority": str(authority["documents"][0]["url"]),
        "verification_status": "verified_st_datasheet_ordering_information_plus_retained_exact_identity",
    }


def resolve_route(icpn: str, rows: list[dict[str, str]]) -> dict[str, str]:
    core = commercial_core(icpn)
    matches = [row for row in rows if pattern_matches(str(row["part_number"]), core)]
    req(len(matches) == 1, f"{icpn}: expected one deterministic route, got {len(matches)}")
    row = matches[0]
    req(row["identifier_kind"] == "ordering_pattern", f"{icpn}: expected ordering-pattern commercial route")
    return {
        "cmsis_device_name": "",
        "existing_identifier": str(row["part_number"]),
        "existing_identifier_kind": "ordering_pattern",
        "mapping_status": "deterministic_ordering_pattern",
        "openocd_target_config": str(row["target_config"]),
    }


def build_rows() -> list[dict[str, str]]:
    exact, route_rows, authority = validate_inputs()
    output: list[dict[str, str]] = []
    for icpn in exact:
        retained_identity_record(icpn)
        metadata = decode_metadata(icpn, authority)
        route = resolve_route(icpn, route_rows)
        values = {
            "manufacturer": MANUFACTURER,
            "icpn": icpn,
            "family": FAMILY,
            **metadata,
            **route,
        }
        output.append({field: values[field] for field in CSV_FIELDS})

    req(len(output) == EXPECTED_EXACT_COUNT and len({row["icpn"] for row in output}) == EXPECTED_EXACT_COUNT, "canonical row cardinality drifted")
    req(Counter(row["existing_identifier_kind"] for row in output) == Counter(EXPECTED_ROUTE_KIND_COUNTS), "route assignment kinds drifted")
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
    temps = Counter(row["temperature_grade"] for row in rows)
    return {
        "schema_version": 1,
        "gate_id": "stm32wba2x-bounded-exact-icpn-admission-readiness-v1",
        "authority": "research_only",
        "manufacturer": MANUFACTURER,
        "research_series": SERIES,
        "family": FAMILY,
        "production_exact_icpn_count": EXPECTED_PRODUCTION_COUNT,
        "production_family_count": EXPECTED_PRODUCTION_FAMILIES,
        "frozen_exact_icpn_count": EXPECTED_EXACT_COUNT,
        "frozen_exact_icpn_set_sha256": EXPECTED_EXACT_SHA256,
        "excluded_non_active_part_number_count": EXPECTED_EXCLUDED_COUNT,
        "identity_ready_count": EXPECTED_EXACT_COUNT,
        "lifecycle_ready_count": EXPECTED_EXACT_COUNT,
        "metadata_ready_count": EXPECTED_EXACT_COUNT,
        "route_ready_count": EXPECTED_EXACT_COUNT,
        "manual_review_count": 0,
        "metadata_exception_count": 0,
        "route_bridge_count": 0,
        "route_assignment_kind_counts": dict(sorted(route_kinds.items())),
        "required_target_config": TARGET_CONFIG,
        "series_counts": dict(sorted(series.items())),
        "package_counts": dict(sorted(packages.items())),
        "temperature_grade_counts": dict(sorted(temps.items())),
        "canonical_candidate_csv": "stm32wba2x-commercial-icpn.csv",
        "canonical_candidate_csv_sha256": sha256_text(payload),
        "metadata_authority": "stm32wba2x-metadata-authority.json",
        "catalog_admission_ready": True,
        "next_gate": NEXT_GATE,
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
