#!/usr/bin/env python3
"""Fail-closed validator for STM32WBA2X exact-ICPN admission readiness."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from stm32wba2x_admission_readiness import (
    EXPECTED_EXACT_COUNT,
    EXPECTED_EXACT_SHA256,
    EXPECTED_EXCLUDED_COUNT,
    EXPECTED_PRODUCTION_COUNT,
    EXPECTED_PRODUCTION_FAMILIES,
    EXPECTED_ROUTE_KIND_COUNTS,
    FAMILY,
    NEXT_GATE,
    SERIES,
    TARGET_CONFIG,
    build_readiness,
    build_rows,
    csv_text,
    pattern_matches,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32wba2x-admission-readiness.json"
CSV_PATH = HERE / "stm32wba2x-commercial-icpn.csv"
AUTHORITY = HERE / "stm32wba2x-metadata-authority.json"
PRODUCTION = HERE.parents[2] / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_CSV_SHA256 = "8d21112ab6d9c8a865e5ce6ccda221b1fee17cbac750ceb042ea41111379fe8d"
EXPECTED_CSV_GIT_BLOB = "15a0d57b7f94c05f745a1768036fef9f01ec1fd9"
EXPECTED_READINESS_GIT_BLOB = "1038b32f0dc9e81958e42eb9df6478bf393c60f3"


def req(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def parse_csv(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(text)))
    req(rows, "canonical candidate CSV is empty")
    return rows


def validate_static(
    baseline: dict[str, Any],
    rows: list[dict[str, str]],
    actual_csv: str,
    authority: dict[str, Any],
    production: dict[str, Any],
) -> None:
    req(baseline.get("gate_id") == "stm32wba2x-bounded-exact-icpn-admission-readiness-v1", "gate id drifted")
    req(baseline.get("research_series") == SERIES, "research series drifted")
    req(baseline.get("family") == FAMILY, "canonical family drifted")
    req(baseline.get("frozen_exact_icpn_count") == EXPECTED_EXACT_COUNT, "frozen exact count drifted")
    req(baseline.get("frozen_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "frozen exact digest drifted")
    req(baseline.get("excluded_non_active_part_number_count") == EXPECTED_EXCLUDED_COUNT, "excluded lifecycle count drifted")
    req(baseline.get("identity_ready_count") == EXPECTED_EXACT_COUNT, "identity readiness drifted")
    req(baseline.get("lifecycle_ready_count") == EXPECTED_EXACT_COUNT, "lifecycle readiness drifted")
    req(baseline.get("metadata_ready_count") == EXPECTED_EXACT_COUNT, "metadata readiness drifted")
    req(baseline.get("route_ready_count") == EXPECTED_EXACT_COUNT, "route readiness drifted")
    req(baseline.get("manual_review_count") == 0, "manual review opened")
    req(baseline.get("metadata_exception_count") == 0, "metadata exception count drifted")
    req(baseline.get("route_bridge_count") == 0, "route bridge count drifted")
    req(baseline.get("route_assignment_kind_counts") == EXPECTED_ROUTE_KIND_COUNTS, "route kind counts drifted")
    req(baseline.get("required_target_config") == TARGET_CONFIG, "target config drifted")
    req(baseline.get("canonical_candidate_csv_sha256") == EXPECTED_CSV_SHA256, "candidate digest baseline drifted")
    req(baseline.get("catalog_admission_ready") is True, "Catalog admission readiness closed")
    req(baseline.get("next_gate") == NEXT_GATE, "next gate drifted")
    req(baseline.get("production_exact_icpn_count") == EXPECTED_PRODUCTION_COUNT, "Production exact prestate drifted")
    req(baseline.get("production_family_count") == EXPECTED_PRODUCTION_FAMILIES, "Production family prestate drifted")

    claims = baseline.get("claims")
    expected_claims = {
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
    }
    req(isinstance(claims, dict) and set(claims) == expected_claims, "claim surface drifted")
    req(all(claims[key] is False for key in expected_claims), "fail-closed claim escaped")

    req(len(rows) == EXPECTED_EXACT_COUNT, "canonical candidate row count drifted")
    req(len({row["icpn"] for row in rows}) == EXPECTED_EXACT_COUNT, "candidate ICPNs are not unique")
    req([row["icpn"] for row in rows] == sorted(row["icpn"] for row in rows), "candidate ICPNs are not sorted")
    req(all(row["manufacturer"] == "STMicroelectronics" for row in rows), "candidate manufacturer drifted")
    req(all(row["family"] == FAMILY for row in rows), "candidate family drifted")
    req({row["series"] for row in rows} == {"STM32WBA23", "STM32WBA25"}, "candidate subfamily series drifted")
    req(all(row["openocd_target_config"] == TARGET_CONFIG for row in rows), "candidate target config drifted")
    req(all(row["existing_identifier_kind"] == "ordering_pattern" for row in rows), "non-ordering route retained")
    req(all(row["mapping_status"] == "deterministic_ordering_pattern" for row in rows), "mapping status drifted")
    req(all(row["cmsis_device_name"] == "" for row in rows), "CMSIS identifier unexpectedly used as commercial route")
    req(all(row["flash_size"] == "512 KiB" for row in rows), "flash metadata drifted")
    req(all(row["source_reference"] == "DS15003 Rev 2 Ordering Information" for row in rows), "metadata source reference drifted")
    req(all(row["source_authority"] == "https://www.st.com/resource/en/datasheet/stm32wba23ce.pdf" for row in rows), "metadata authority URL drifted")

    expected_base_meta = {
        "STM32WBA23CE": ("UFQFPN", "48"),
        "STM32WBA23KE": ("UFQFPN", "32"),
        "STM32WBA25CE": ("UFQFPN", "48"),
        "STM32WBA25HE": ("Thin WLCSP", "37"),
    }
    for row in rows:
        package, pins = expected_base_meta[row["base_device"]]
        req((row["package"], row["pin_count"]) == (package, pins), f'{row["icpn"]}: package/pin metadata drifted')
        if row["icpn"].endswith("6") or row["icpn"].endswith("6TR"):
            req(row["temperature_grade"] == "-40..85 C", f'{row["icpn"]}: temperature grade 6 drifted')
        elif row["icpn"].endswith("7") or row["icpn"].endswith("7TR"):
            req(row["temperature_grade"] == "-40..105 C", f'{row["icpn"]}: temperature grade 7 drifted')
        else:
            req(False, f'{row["icpn"]}: unexpected temperature code')
        req(row["option_suffix"] == ("TR" if row["icpn"].endswith("TR") else ""), f'{row["icpn"]}: packing suffix drifted')

    req(sum(row["series"] == "STM32WBA23" for row in rows) == 8, "WBA23 row count drifted")
    req(sum(row["series"] == "STM32WBA25" for row in rows) == 6, "WBA25 row count drifted")
    req(sum(row["package"] == "UFQFPN" for row in rows) == 12, "UFQFPN row count drifted")
    req(sum(row["package"] == "Thin WLCSP" for row in rows) == 2, "WLCSP row count drifted")
    req(sum(row["temperature_grade"] == "-40..85 C" for row in rows) == 7, "temperature-6 count drifted")
    req(sum(row["temperature_grade"] == "-40..105 C" for row in rows) == 7, "temperature-7 count drifted")

    req(pattern_matches("STM32WBA23CEUx", "STM32WBA23CEU6"), "lowercase-x route positive regression")
    req(not pattern_matches("STM32WBA23CEUxT", "STM32WBA23CEU6"), "CMSIS xT token incorrectly matched commercial core")

    req(hashlib.sha256(actual_csv.encode("utf-8")).hexdigest() == EXPECTED_CSV_SHA256, "candidate CSV digest drifted")
    req(git_blob_sha(actual_csv.encode("utf-8")) == EXPECTED_CSV_GIT_BLOB, "candidate CSV Git blob drifted")
    req(git_blob_sha(BASELINE.read_bytes()) == EXPECTED_READINESS_GIT_BLOB, "readiness Git blob drifted")

    req(authority.get("authority_id") == "stm32wba2x-ordering-information-v1", "metadata authority id drifted")
    req(authority.get("family") == FAMILY and authority.get("research_series") == SERIES, "metadata authority scope drifted")
    docs = authority.get("documents")
    req(isinstance(docs, list) and len(docs) == 1, "metadata document count drifted")
    req(docs[0].get("document_id") == "DS15003" and docs[0].get("revision") == "Rev 2", "metadata document revision drifted")
    req(set(docs[0].get("scope") or []) == {"STM32WBA23", "STM32WBA25"}, "metadata document coverage drifted")
    req(all(value is False for value in (authority.get("claims") or {}).values()), "metadata authority fail-closed claim escaped")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(source.get("row_count", 0)) for source in sources) == EXPECTED_PRODUCTION_COUNT, "Production Catalog changed")
    req(len(sources) == EXPECTED_PRODUCTION_FAMILIES, "Production family count changed")
    req(all(source.get("family") != FAMILY for source in sources), "STM32WBA2X leaked into Production")


def expect_reject(name: str, mutate) -> None:
    baseline = load(BASELINE)
    authority = load(AUTHORITY)
    production = load(PRODUCTION)
    actual_csv = CSV_PATH.read_text(encoding="utf-8")
    rows = parse_csv(actual_csv)
    mutate(baseline, rows, authority, production)
    try:
        validate_static(baseline, rows, actual_csv, authority, production)
    except SystemExit:
        return
    raise SystemExit(f"negative control accepted: {name}")


def main() -> None:
    baseline = load(BASELINE)
    authority = load(AUTHORITY)
    production = load(PRODUCTION)
    actual_csv = CSV_PATH.read_text(encoding="utf-8")
    rows = parse_csv(actual_csv)

    req(baseline == build_readiness(), "readiness baseline differs from deterministic replay")
    req(actual_csv == csv_text(build_rows()), "canonical candidate CSV differs from deterministic replay")
    validate_static(baseline, rows, actual_csv, authority, production)

    controls = [
        ("Production authorization", lambda b,r,a,p: b["claims"].__setitem__("production_write_authorized", True)),
        ("publication authorization", lambda b,r,a,p: b["claims"].__setitem__("production_publication_authorized", True)),
        ("programming equivalence", lambda b,r,a,p: b["claims"].__setitem__("programming_algorithm_equivalence_claimed", True)),
        ("runtime support", lambda b,r,a,p: b["claims"].__setitem__("runtime_programming_support_claimed", True)),
        ("radio operation", lambda b,r,a,p: b["claims"].__setitem__("wireless_radio_operation_authorized", True)),
        ("wireless security", lambda b,r,a,p: b["claims"].__setitem__("wireless_security_operation_authorized", True)),
        ("security mutation", lambda b,r,a,p: b["claims"].__setitem__("security_mutation_authorized", True)),
        ("debug attach", lambda b,r,a,p: b["claims"].__setitem__("debug_attach_supported", True)),
        ("target execution", lambda b,r,a,p: b["claims"].__setitem__("target_execution_authorized", True)),
        ("HIL coupling", lambda b,r,a,p: b["claims"].__setitem__("hil_required_for_catalog_admission", True)),
        ("reject remaining wireless", lambda b,r,a,p: b["claims"].__setitem__("remaining_wireless_families_rejected", True)),
        ("manual review", lambda b,r,a,p: b.__setitem__("manual_review_count", 1)),
        ("route coverage loss", lambda b,r,a,p: b.__setitem__("route_ready_count", EXPECTED_EXACT_COUNT - 1)),
        ("metadata coverage loss", lambda b,r,a,p: b.__setitem__("metadata_ready_count", EXPECTED_EXACT_COUNT - 1)),
        ("metadata exception introduced", lambda b,r,a,p: b.__setitem__("metadata_exception_count", 1)),
        ("route bridge introduced", lambda b,r,a,p: b.__setitem__("route_bridge_count", 1)),
        ("skip publication gate", lambda b,r,a,p: b.__setitem__("next_gate", "stm32wba2x-target-execution-gate")),
        ("exact digest mutation", lambda b,r,a,p: b.__setitem__("frozen_exact_icpn_set_sha256", "0"*64)),
        ("Production mutation", lambda b,r,a,p: p["sources"][0].__setitem__("row_count", int(p["sources"][0]["row_count"])+1)),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print(
        "PASS: STM32WBA2X admission readiness: "
        f"{EXPECTED_EXACT_COUNT}/{EXPECTED_EXACT_COUNT} ready, "
        "14 ordering-pattern routes, 0 exceptions, 0 bridges, "
        f"Production unchanged at {EXPECTED_PRODUCTION_COUNT}, "
        f"{len(controls)} negative controls"
    )


if __name__ == "__main__":
    main()
