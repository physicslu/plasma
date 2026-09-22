#!/usr/bin/env python3
"""Build research-only STM32WBX Catalog admission-readiness artifacts."""
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
DISCOVERY = HERE / "evidence/stm32wbx-exact-icpn-live-2026-09-22/discovery-summary.json"
EXACT = HERE / "evidence/stm32wbx-exact-icpn-live-2026-09-22/exact-icpns.json"
SOURCE = HERE / "openocd-parts-canonical.csv"
AUTHORITY = HERE / "stm32wbx-metadata-authority.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32WBX"
SERIES = "STM32WBX"
TARGET_CONFIG = "tcl/target/stm32wbx.cfg"
EXPECTED_EXACT_COUNT = 50
EXPECTED_EXACT_SHA256 = "faaa262a535e5397894d2ecfdd4589a044371fdeb6926ffc3dfaab63f219fe96"
EXPECTED_EXCLUDED = ["STM32WB5MMGH6"]
EXPECTED_BASE_COUNT = 18
EXPECTED_SOURCE_ROWS = 23
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 41, "cmsis_device_name": 9}
EXPECTED_PRODUCTION_COUNT = 2554
EXPECTED_PRODUCTION_FAMILIES = 20
NEXT_GATE = "stm32wbx-production-publication-gate"

CSV_FIELDS = (
    "manufacturer","icpn","family","series","base_device","package",
    "pin_count","flash_size","temperature_grade","option_suffix",
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config","source_type","source_reference",
    "source_authority","verification_status",
)

DOC_BY_SUBFAMILY = {
    "STM32WB10": ("DS13259", "Rev 7"),
    "STM32WB15": ("DS13258", "Rev 10"),
    "STM32WB1M": ("DS14096", "Rev 8"),
    "STM32WB30": ("DS13047", "Rev 9"),
    "STM32WB35": ("DS11929", "Rev 17"),
    "STM32WB50": ("DS13047", "Rev 9"),
    "STM32WB55": ("DS11929", "Rev 17"),
    "STM32WB5M": ("DS13252", "Rev 8"),
}

def req(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)

def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value

def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def git_blob_sha(value: str) -> str:
    data = value.encode("utf-8")
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data, usedforsecurity=False).hexdigest()

def canonical_rows() -> list[dict[str, str]]:
    with SOURCE.open(newline="", encoding="utf-8") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row.get("vendor") == MANUFACTURER
            and row.get("plasma_series") == SERIES
            and row.get("target_config") == TARGET_CONFIG
        ]
    req(len(rows) == EXPECTED_SOURCE_ROWS, f"frozen route row count drifted: {len(rows)}")
    req(Counter(row.get("identifier_kind") for row in rows) == Counter({"ordering_pattern":19,"cmsis_device_name":4}), "identifier surface drifted")
    req(all(row.get("mapping_status") == "mapping_candidate" for row in rows), "route mapping status drifted")
    return rows

def validate_inputs() -> tuple[list[str], dict[str,str], list[dict[str,str]], dict[str,Any]]:
    discovery = load_json(DISCOVERY)
    exact_obj = load_json(EXACT)
    authority = load_json(AUTHORITY)
    production = load_json(PRODUCTION)

    req(discovery.get("discovery_id") == "stm32wbx-bounded-exact-icpn-discovery-v1", "discovery id drifted")
    req(discovery.get("base_device_count") == EXPECTED_BASE_COUNT, "Base Device count drifted")
    req(discovery.get("successful_targets") == EXPECTED_BASE_COUNT, "discovery success count drifted")
    req(discovery.get("manual_review_targets") == 0, "manual review opened")
    req(discovery.get("active_exact_icpn_count") == EXPECTED_EXACT_COUNT, "exact count drifted")
    req(discovery.get("active_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "exact digest drifted")
    req(discovery.get("excluded_non_active_part_numbers") == EXPECTED_EXCLUDED, "lifecycle exclusions drifted")
    req(discovery.get("next_gate") == "stm32wbx-bounded-exact-icpn-admission-readiness-gate", "discovery next gate drifted")

    exact = exact_obj.get("exact_icpns")
    req(isinstance(exact, list) and len(exact) == EXPECTED_EXACT_COUNT, "exact snapshot malformed")
    req(exact == discovery.get("active_exact_icpns"), "exact snapshot differs from discovery")
    req(exact_obj.get("exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "exact snapshot digest drifted")
    req(sha256_text("\n".join(exact) + "\n") == EXPECTED_EXACT_SHA256, "exact digest recompute failed")

    owners: dict[str,str] = {}
    for item in discovery.get("results") or []:
        req(isinstance(item, dict), "discovery result malformed")
        base = item.get("base_device")
        req(isinstance(base, str), "discovery base missing")
        for icpn in item.get("active_exact_icpns") or []:
            req(isinstance(icpn, str) and icpn not in owners, f"duplicate exact identity {icpn}")
            owners[icpn] = base
    req(set(owners) == set(exact), "Base Device ownership does not cover exact set")

    req(authority.get("authority_id") == "stm32wbx-ordering-information-v1", "metadata authority id drifted")
    docs = authority.get("documents")
    req(isinstance(docs, list) and len(docs) == 6, "metadata authority document set drifted")
    observed = {(d.get("document_id"), d.get("revision")) for d in docs if isinstance(d, dict)}
    expected = {("DS11929","Rev 17"),("DS13047","Rev 9"),("DS13258","Rev 10"),("DS13259","Rev 7"),("DS13252","Rev 8"),("DS14096","Rev 8")}
    req(observed == expected, "metadata authority revisions drifted")
    req(all(value is False for value in (authority.get("claims") or {}).values()), "metadata authority fail-closed claims escaped")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(item.get("row_count",0)) for item in sources if isinstance(item,dict)) == EXPECTED_PRODUCTION_COUNT, "Production count drifted")
    req(len(sources) == EXPECTED_PRODUCTION_FAMILIES, "Production family count drifted")
    req(all(not (isinstance(item,dict) and item.get("family") == FAMILY) for item in sources), "STM32WBX already present in Production")

    return exact, owners, canonical_rows(), authority

def strip_terminal_tr(icpn: str) -> str:
    return icpn[:-2] if icpn.endswith("TR") else icpn

def pattern_matches(icpn: str, pattern: str) -> bool:
    core = strip_terminal_tr(icpn)
    return len(core) == len(pattern) and all(p == "x" or p == c for c,p in zip(core,pattern))

def resolve_route(icpn: str, rows: list[dict[str,str]]) -> dict[str,str]:
    matches = [row for row in rows if pattern_matches(icpn, row["part_number"])]
    req(len(matches) == 1, f"{icpn}: expected one deterministic route, got {len(matches)}")
    row = matches[0]
    kind = row["identifier_kind"]
    req(kind in {"ordering_pattern","cmsis_device_name"}, f"{icpn}: unsupported route kind")
    mapping = "deterministic_ordering_pattern" if kind == "ordering_pattern" else "deterministic_cmsis_commercial_bridge"
    return {
        "series": row["subfamily"],
        "cmsis_device_name": row["part_number"] if kind == "cmsis_device_name" else "",
        "existing_identifier": row["part_number"],
        "existing_identifier_kind": kind,
        "mapping_status": mapping,
        "openocd_target_config": row["target_config"],
    }

def authority_doc(authority: dict[str,Any], subfamily: str) -> dict[str,Any]:
    wanted = DOC_BY_SUBFAMILY[subfamily]
    for doc in authority["documents"]:
        if (doc.get("document_id"), doc.get("revision")) == wanted:
            return doc
    raise RuntimeError(f"{subfamily}: metadata authority missing")

def split_suffix(icpn: str, base: str, package_chars: int = 1, temp_chars: int = 1) -> tuple[str,str,str]:
    rem = icpn[len(base):]
    req(len(rem) >= package_chars + temp_chars, f"{icpn}: suffix too short")
    package_code = rem[:package_chars]
    temp_code = rem[package_chars:package_chars+temp_chars]
    option = rem[package_chars+temp_chars:]
    return package_code, temp_code, option

def decode_metadata(icpn: str, base: str, subfamily: str, authority: dict[str,Any]) -> dict[str,str]:
    doc = authority_doc(authority, subfamily)
    package = pin = flash = temp = option = ""

    if subfamily == "STM32WB10":
        pkg,t,opt = split_suffix(icpn, base)
        req(pkg == "U" and t == "5", f"{icpn}: WB10 ordering code drifted")
        package,pin,flash,temp,option = "UFQFPN","48","320 KiB","-10..85 C",opt
    elif subfamily == "STM32WB15":
        pkg,t,opt = split_suffix(icpn, base)
        req(pkg in {"U","Y"} and t in {"6","7"}, f"{icpn}: WB15 ordering code drifted")
        package = {"U":"UFQFPN","Y":"WLCSP"}[pkg]
        pin = {"U":"48","Y":"49"}[pkg]
        flash = "320 KiB"
        temp = {"6":"-40..85 C","7":"-40..105 C"}[t]
        option = opt
    elif subfamily == "STM32WB1M":
        pkg,t,opt = split_suffix(icpn, base)
        req(pkg == "H" and t == "6", f"{icpn}: WB1M ordering code drifted")
        package,pin,flash,temp,option = "LGA","77","320 KiB","-40..85 C",opt
    elif subfamily == "STM32WB30":
        pkg,t,opt = split_suffix(icpn, base)
        req(pkg == "U" and t == "5", f"{icpn}: WB30 ordering code drifted")
        package,pin,flash,temp,option = "UFQFPN","48","512 KiB","-10..85 C",opt
    elif subfamily == "STM32WB35":
        pkg,t,opt = split_suffix(icpn, base)
        req(pkg == "U" and t in {"6","7"}, f"{icpn}: WB35 ordering code drifted")
        package,pin = "UFQFPN","48"
        flash = {"C":"256 KiB","E":"512 KiB"}[base[-1]]
        temp = {"6":"-40..85 C","7":"-40..105 C"}[t]
        option = opt
    elif subfamily == "STM32WB50":
        pkg,t,opt = split_suffix(icpn, base)
        req(pkg == "U" and t == "5", f"{icpn}: WB50 ordering code drifted")
        package,pin,flash,temp,option = "UFQFPN","48","1 MiB","-10..85 C",opt
    elif subfamily == "STM32WB55":
        pkg,t,opt = split_suffix(icpn, base)
        req(pkg in {"U","V","Q","Y"} and t in {"6","7"}, f"{icpn}: WB55 ordering code drifted")
        package = {"U":"UFQFPN","V":"VFQFPN","Q":"UFBGA","Y":"WLCSP"}[pkg]
        pin = {"U":"48","V":"68","Q":"129","Y":"100"}[pkg]
        flash = {"C":"256 KiB","E":"512 KiB","G":"1 MiB","Y":"640 KiB"}[base[-1]]
        temp = {"6":"-40..85 C","7":"-40..105 C"}[t]
        option = opt
    elif subfamily == "STM32WB5M":
        pkg,t,opt = split_suffix(icpn, base)
        req(pkg == "H" and t == "6", f"{icpn}: WB5M ordering code drifted")
        package,pin,flash,temp,option = "LGA","86","1 MiB","-40..85 C",opt
    else:
        raise RuntimeError(f"{icpn}: unsupported metadata subfamily {subfamily}")

    return {
        "base_device": base,
        "package": package,
        "pin_count": pin,
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
        route = resolve_route(icpn, route_rows)
        base = owners[icpn]
        metadata = decode_metadata(icpn, base, route["series"], authority)
        values = {
            "manufacturer": MANUFACTURER,
            "icpn": icpn,
            "family": FAMILY,
            **metadata,
            **route,
        }
        output.append({field: values[field] for field in CSV_FIELDS})
    req(len(output) == EXPECTED_EXACT_COUNT and len({row["icpn"] for row in output}) == EXPECTED_EXACT_COUNT, "canonical row cardinality drifted")
    req(Counter(row["existing_identifier_kind"] for row in output) == Counter(EXPECTED_ROUTE_KIND_COUNTS), "route assignment kind counts drifted")
    req(Counter(row["mapping_status"] for row in output) == Counter({"deterministic_ordering_pattern":41,"deterministic_cmsis_commercial_bridge":9}), "mapping status counts drifted")
    req({row["openocd_target_config"] for row in output} == {TARGET_CONFIG}, "target config drifted")
    return output

def csv_text(rows: list[dict[str,str]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

def build_readiness(rows: list[dict[str,str]], canonical: str) -> dict[str,Any]:
    return {
        "schema_version": 1,
        "readiness_id": "stm32wbx-bounded-exact-icpn-admission-readiness-v1",
        "manufacturer": MANUFACTURER,
        "family": FAMILY,
        "research_series": SERIES,
        "authority": "research_only",
        "status": "catalog_admission_ready",
        "catalog_admission_ready": True,
        "production_exact_icpn_count": EXPECTED_PRODUCTION_COUNT,
        "production_family_count": EXPECTED_PRODUCTION_FAMILIES,
        "frozen_exact_icpn_count": EXPECTED_EXACT_COUNT,
        "frozen_exact_icpn_set_sha256": EXPECTED_EXACT_SHA256,
        "excluded_non_active_part_number_count": len(EXPECTED_EXCLUDED),
        "excluded_non_active_part_numbers": EXPECTED_EXCLUDED,
        "identity_ready_count": EXPECTED_EXACT_COUNT,
        "lifecycle_ready_count": EXPECTED_EXACT_COUNT,
        "metadata_ready_count": EXPECTED_EXACT_COUNT,
        "route_ready_count": EXPECTED_EXACT_COUNT,
        "manual_review_count": 0,
        "metadata_exception_count": 0,
        "route_bridge_count": 9,
        "route_assignment_kind_counts": dict(sorted(Counter(row["existing_identifier_kind"] for row in rows).items())),
        "mapping_status_counts": dict(sorted(Counter(row["mapping_status"] for row in rows).items())),
        "target_config": TARGET_CONFIG,
        "package_counts": dict(sorted(Counter(row["package"] for row in rows).items())),
        "temperature_grade_counts": dict(sorted(Counter(row["temperature_grade"] for row in rows).items())),
        "metadata_authority": "stm32wbx-metadata-authority.json",
        "canonical_candidate": "stm32wbx-commercial-icpn.csv",
        "canonical_candidate_sha256": sha256_text(canonical),
        "canonical_candidate_git_blob_sha": git_blob_sha(canonical),
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
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        args.csv_output.write_text(canonical, encoding="utf-8")
    else:
        print(canonical, end="")
    if args.readiness_output:
        args.readiness_output.parent.mkdir(parents=True, exist_ok=True)
        args.readiness_output.write_text(readiness, encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
