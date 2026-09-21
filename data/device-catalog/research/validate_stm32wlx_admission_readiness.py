#!/usr/bin/env python3
"""Fail-closed validator for STM32WLX exact-ICPN admission readiness."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from stm32wlx_admission_readiness import (
    EXPECTED_EXACT_COUNT,
    EXPECTED_EXACT_SHA256,
    EXPECTED_EXCLUDED,
    EXPECTED_PRODUCTION_COUNT,
    EXPECTED_PRODUCTION_FAMILIES,
    EXPECTED_ROUTE_BRIDGES,
    FAMILY,
    NEXT_GATE,
    SERIES,
    TARGET_CONFIG,
    build_readiness,
    build_rows,
    csv_text,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32wlx-admission-readiness.json"
CSV_PATH = HERE / "stm32wlx-commercial-icpn.csv"
AUTHORITY = HERE / "stm32wlx-metadata-authority.json"
PRODUCTION = HERE.parents[2] / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_CSV_SHA256 = "f1caf745d5ef728b415e10886c4caf294dd79364c240d3256901b8432648dc0c"
EXPECTED_CSV_GIT_BLOB = "3b9b7281058ca1248d83880ca96b21d6f02a65a3"
EXPECTED_READINESS_GIT_BLOB = "097e496c333a277162d635a982e73ec024e484f5"

EXPECTED_SERIES_COUNTS = {
    "STM32WL54": 4,
    "STM32WL55": 6,
    "STM32WL5MOC": 2,
    "STM32WLE4": 8,
    "STM32WLE5": 11,
}
EXPECTED_PACKAGE_COUNTS = {"LGA": 2, "UFBGA": 14, "UFQFPN": 15}
EXPECTED_MAPPING_COUNTS = {
    "deterministic_ordering_pattern": 30,
    "deterministic_ordering_pattern_via_stsafe_provisioning_bridge": 1,
}


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
    req(
        baseline.get("gate_id")
        == "stm32wlx-bounded-exact-icpn-admission-readiness-v1",
        "gate id drifted",
    )
    req(baseline.get("research_series") == SERIES, "research series drifted")
    req(baseline.get("family") == FAMILY, "canonical family drifted")
    req(
        baseline.get("frozen_exact_icpn_count") == EXPECTED_EXACT_COUNT,
        "frozen exact count drifted",
    )
    req(
        baseline.get("frozen_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256,
        "frozen exact digest drifted",
    )
    req(
        baseline.get("excluded_non_active_part_numbers") == EXPECTED_EXCLUDED,
        "excluded lifecycle set drifted",
    )
    req(
        baseline.get("excluded_non_active_part_number_count")
        == len(EXPECTED_EXCLUDED),
        "excluded lifecycle count drifted",
    )
    req(
        baseline.get("identity_ready_count") == EXPECTED_EXACT_COUNT,
        "identity readiness drifted",
    )
    req(
        baseline.get("lifecycle_ready_count") == EXPECTED_EXACT_COUNT,
        "lifecycle readiness drifted",
    )
    req(
        baseline.get("metadata_ready_count") == EXPECTED_EXACT_COUNT,
        "metadata readiness drifted",
    )
    req(
        baseline.get("route_ready_count") == EXPECTED_EXACT_COUNT,
        "route readiness drifted",
    )
    req(baseline.get("manual_review_count") == 0, "manual review opened")
    req(
        baseline.get("metadata_exception_count") == 0,
        "metadata exception count drifted",
    )
    req(
        baseline.get("route_bridge_count") == EXPECTED_ROUTE_BRIDGES,
        "route bridge count drifted",
    )
    req(
        baseline.get("mapping_status_counts") == EXPECTED_MAPPING_COUNTS,
        "mapping status counts drifted",
    )
    req(
        baseline.get("route_assignment_kind_counts") == {"ordering_pattern": 31},
        "route kind counts drifted",
    )
    req(
        baseline.get("required_target_config") == TARGET_CONFIG,
        "target config drifted",
    )
    req(
        baseline.get("canonical_candidate_csv_sha256") == EXPECTED_CSV_SHA256,
        "candidate digest baseline drifted",
    )
    req(
        baseline.get("catalog_admission_ready") is True,
        "Catalog admission readiness closed",
    )
    req(baseline.get("next_gate") == NEXT_GATE, "next gate drifted")
    req(
        baseline.get("production_exact_icpn_count") == EXPECTED_PRODUCTION_COUNT,
        "Production exact prestate drifted",
    )
    req(
        baseline.get("production_family_count") == EXPECTED_PRODUCTION_FAMILIES,
        "Production family prestate drifted",
    )
    req(baseline.get("series_counts") == EXPECTED_SERIES_COUNTS, "series counts drifted")
    req(
        baseline.get("package_counts") == EXPECTED_PACKAGE_COUNTS,
        "package counts drifted",
    )

    wl5m = baseline.get("wl5m_non_prefix_boundary")
    req(isinstance(wl5m, dict), "WL5M boundary missing")
    req(
        wl5m.get("commercial_series") == "STM32WL5MOC",
        "WL5M commercial series drifted",
    )
    req(
        wl5m.get("frozen_route_subfamily") == "STM32WL55",
        "WL5M frozen route subfamily drifted",
    )
    req(
        wl5m.get("route_pattern") == "STM32WL5MOCHx",
        "WL5M route pattern drifted",
    )
    req(
        wl5m.get("active_exact_icpns")
        == ["STM32WL5MOCH6STR", "STM32WL5MOCH6TR"],
        "WL5M Active identity set drifted",
    )
    req(
        wl5m.get("stsafe_bridge_identity") == "STM32WL5MOCH6STR",
        "WL5M STSAFE bridge identity drifted",
    )
    req(wl5m.get("alias_normalized") is False, "WL5M alias normalization opened")

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
        "wl5m_alias_normalized",
    }
    req(
        isinstance(claims, dict) and set(claims) == expected_claims,
        "claim surface drifted",
    )
    req(
        all(claims[key] is False for key in expected_claims),
        "fail-closed claim escaped",
    )

    req(len(rows) == EXPECTED_EXACT_COUNT, "candidate row count drifted")
    req(
        len({row["icpn"] for row in rows}) == EXPECTED_EXACT_COUNT,
        "candidate ICPNs are not unique",
    )
    req(
        [row["icpn"] for row in rows] == sorted(row["icpn"] for row in rows),
        "candidate ICPNs are not sorted",
    )
    req(
        not {row["icpn"] for row in rows}.intersection(EXPECTED_EXCLUDED),
        "Proposal identity leaked into candidate CSV",
    )
    req(
        all(row["manufacturer"] == "STMicroelectronics" for row in rows),
        "candidate manufacturer drifted",
    )
    req(all(row["family"] == FAMILY for row in rows), "candidate family drifted")
    req(
        {row["series"] for row in rows}
        == {"STM32WL54", "STM32WL55", "STM32WL5MOC", "STM32WLE4", "STM32WLE5"},
        "candidate commercial series drifted",
    )
    req(
        all(row["openocd_target_config"] == TARGET_CONFIG for row in rows),
        "candidate target config drifted",
    )
    req(
        all(row["existing_identifier_kind"] == "ordering_pattern" for row in rows),
        "non-ordering route retained",
    )
    req(
        all(row["cmsis_device_name"] == "" for row in rows),
        "CMSIS identifier unexpectedly used as commercial route",
    )
    req(
        sum(
            row["mapping_status"]
            == "deterministic_ordering_pattern_via_stsafe_provisioning_bridge"
            for row in rows
        )
        == 1,
        "STSAFE route bridge cardinality drifted",
    )
    req(
        sum(
            row["mapping_status"] == "deterministic_ordering_pattern"
            for row in rows
        )
        == 30,
        "direct route count drifted",
    )

    module_rows = [row for row in rows if row["series"] == "STM32WL5MOC"]
    req(len(module_rows) == 2, "WL5M module row count drifted")
    by_icpn = {row["icpn"]: row for row in module_rows}
    req(
        by_icpn["STM32WL5MOCH6STR"]["option_suffix"] == "STR",
        "WL5M provisioned option suffix drifted",
    )
    req(
        by_icpn["STM32WL5MOCH6STR"]["mapping_status"]
        == "deterministic_ordering_pattern_via_stsafe_provisioning_bridge",
        "WL5M provisioned bridge status drifted",
    )
    req(
        by_icpn["STM32WL5MOCH6TR"]["mapping_status"]
        == "deterministic_ordering_pattern",
        "WL5M unprovisioned direct route drifted",
    )
    for row in module_rows:
        req(row["base_device"] == "STM32WL5MOC", "WL5M Base Device drifted")
        req(row["package"] == "LGA", "WL5M package drifted")
        req(row["pin_count"] == "92", "WL5M pin count drifted")
        req(row["flash_size"] == "256 KiB", "WL5M flash size drifted")
        req(row["temperature_grade"] == "-40..85 C", "WL5M temperature drifted")
        req(
            row["source_reference"] == "DS14084 Rev 5 Table 15 Ordering Information",
            "WL5M source reference drifted",
        )

    req(
        hashlib.sha256(actual_csv.encode("utf-8")).hexdigest()
        == EXPECTED_CSV_SHA256,
        "candidate CSV digest drifted",
    )
    req(
        git_blob_sha(actual_csv.encode("utf-8")) == EXPECTED_CSV_GIT_BLOB,
        "candidate CSV Git blob drifted",
    )
    req(
        git_blob_sha(BASELINE.read_bytes()) == EXPECTED_READINESS_GIT_BLOB,
        "readiness Git blob drifted",
    )

    req(
        authority.get("authority_id") == "stm32wlx-ordering-information-v1",
        "metadata authority id drifted",
    )
    req(
        authority.get("family") == FAMILY
        and authority.get("research_series") == SERIES,
        "metadata authority scope drifted",
    )
    docs = authority.get("documents")
    req(isinstance(docs, list) and len(docs) == 3, "metadata document count drifted")
    req(
        [(doc.get("document_id"), doc.get("revision")) for doc in docs]
        == [("DS13293", "Rev 5"), ("DS13105", "Rev 12"), ("DS14084", "Rev 5")],
        "metadata document revisions drifted",
    )
    req(
        authority.get("route_semantics", {}).get("alias_normalization") is False,
        "metadata authority alias normalization opened",
    )
    req(
        all(value is False for value in (authority.get("claims") or {}).values()),
        "metadata authority fail-closed claim escaped",
    )

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(
        sum(int(source.get("row_count", 0)) for source in sources)
        == EXPECTED_PRODUCTION_COUNT,
        "Production Catalog changed",
    )
    req(
        len(sources) == EXPECTED_PRODUCTION_FAMILIES,
        "Production family count changed",
    )
    req(
        all(source.get("family") != FAMILY for source in sources),
        "STM32WLX leaked into Production",
    )


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

    req(
        baseline == build_readiness(),
        "readiness baseline differs from deterministic replay",
    )
    req(
        actual_csv == csv_text(build_rows()),
        "canonical candidate CSV differs from deterministic replay",
    )
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
        ("normalize WL5M alias", lambda b,r,a,p: b["claims"].__setitem__("wl5m_alias_normalized", True)),
        ("manual review", lambda b,r,a,p: b.__setitem__("manual_review_count", 1)),
        ("route coverage loss", lambda b,r,a,p: b.__setitem__("route_ready_count", EXPECTED_EXACT_COUNT - 1)),
        ("metadata coverage loss", lambda b,r,a,p: b.__setitem__("metadata_ready_count", EXPECTED_EXACT_COUNT - 1)),
        ("metadata exception introduced", lambda b,r,a,p: b.__setitem__("metadata_exception_count", 1)),
        ("route bridge loss", lambda b,r,a,p: b.__setitem__("route_bridge_count", 0)),
        ("route bridge inflation", lambda b,r,a,p: b.__setitem__("route_bridge_count", 2)),
        ("skip publication gate", lambda b,r,a,p: b.__setitem__("next_gate", "stm32wlx-target-execution-gate")),
        ("exact digest mutation", lambda b,r,a,p: b.__setitem__("frozen_exact_icpn_set_sha256", "0"*64)),
        ("excluded lifecycle mutation", lambda b,r,a,p: b["excluded_non_active_part_numbers"].pop()),
        ("WL5M alias boundary mutation", lambda b,r,a,p: b["wl5m_non_prefix_boundary"].__setitem__("alias_normalized", True)),
        ("Production mutation", lambda b,r,a,p: p["sources"][0].__setitem__("row_count", int(p["sources"][0]["row_count"])+1)),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print(
        "PASS: STM32WLX admission readiness: "
        f"{EXPECTED_EXACT_COUNT}/{EXPECTED_EXACT_COUNT} ready, "
        "30 direct ordering-pattern routes, 1 STSAFE bridge, "
        "2 Proposal exclusions retained, 0 metadata exceptions, "
        f"Production unchanged at {EXPECTED_PRODUCTION_COUNT}, "
        f"{len(controls)} negative controls"
    )


if __name__ == "__main__":
    main()
