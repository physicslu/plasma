#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from stm32h7_classic_admission_readiness import (
    EXPECTED_EXACT_COUNT,
    EXPECTED_EXACT_SHA256,
    EXPECTED_EXCLUDED_COUNT,
    EXPECTED_METADATA_EXCEPTION_COUNT,
    EXPECTED_PRODUCTION_COUNT,
    EXPECTED_ROUTE_BRIDGE_COUNT,
    EXPECTED_ROUTE_KIND_COUNTS,
    FAMILY,
    NEXT_GATE,
    PARTITION_ID,
    TARGET_CONFIG,
    build_readiness,
    build_rows,
    csv_text,
    pattern_matches,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASELINE = HERE / "stm32h7-classic-admission-readiness.json"
CSV_PATH = HERE / "stm32h7-classic-commercial-icpn.csv"
AUTHORITY = HERE / "stm32h7-classic-metadata-authority.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_CSV_SHA256 = "35b9d2bc13da3a01809ea62b62557f5419b8d6f7139574ca4715a127f1e86465"
EXPECTED_DOCUMENTS = {
    "STM32H723": ("DS13313", "Rev 5"),
    "STM32H725": ("DS13311", "Rev 5"),
    "STM32H730": ("DS13315", "Rev 5"),
    "STM32H733": ("DS13314", "Rev 4"),
    "STM32H735": ("DS13312", "Rev 4"),
    "STM32H742": ("DS12110", "Rev 11"),
    "STM32H743": ("DS12110", "Rev 11"),
    "STM32H745": ("DS12923", "Rev 3"),
    "STM32H747": ("DS12930", "Rev 3"),
    "STM32H750": ("DS12556", "Rev 8"),
    "STM32H753": ("DS12117", "Rev 10"),
    "STM32H755": ("DS12919", "Rev 3"),
    "STM32H757": ("DS12931", "Rev 5"),
    "STM32H7A3": ("DS13195", "Rev 8"),
    "STM32H7B0": ("DS13196", "Rev 7"),
    "STM32H7B3": ("DS13139", "Rev 8"),
}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value


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
    req(baseline.get("gate_id") == "stm32h7-classic-bounded-exact-icpn-admission-readiness-v1", "gate id drifted")
    req(baseline.get("partition") == PARTITION_ID, "partition drifted")
    req(baseline.get("family") == FAMILY, "canonical family drifted")
    req(baseline.get("frozen_exact_icpn_count") == EXPECTED_EXACT_COUNT, "frozen exact count drifted")
    req(baseline.get("frozen_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA256, "frozen exact digest drifted")
    req(baseline.get("excluded_non_active_part_number_count") == EXPECTED_EXCLUDED_COUNT, "excluded lifecycle count drifted")
    req(baseline.get("identity_ready_count") == EXPECTED_EXACT_COUNT, "identity readiness drifted")
    req(baseline.get("lifecycle_ready_count") == EXPECTED_EXACT_COUNT, "lifecycle readiness drifted")
    req(baseline.get("metadata_ready_count") == EXPECTED_EXACT_COUNT, "metadata readiness drifted")
    req(baseline.get("route_ready_count") == EXPECTED_EXACT_COUNT, "route readiness drifted")
    req(baseline.get("manual_review_count") == 0, "manual review opened")
    req(baseline.get("metadata_exception_count") == EXPECTED_METADATA_EXCEPTION_COUNT, "metadata exception count drifted")
    req(baseline.get("route_functional_option_bridge_count") == EXPECTED_ROUTE_BRIDGE_COUNT, "route bridge count drifted")
    req(baseline.get("route_assignment_kind_counts") == EXPECTED_ROUTE_KIND_COUNTS, "route kind counts drifted")
    req(baseline.get("required_target_config") == TARGET_CONFIG, "target config drifted")
    req(baseline.get("canonical_candidate_csv_sha256") == EXPECTED_CSV_SHA256, "candidate digest baseline drifted")
    req(baseline.get("catalog_admission_ready") is True, "Catalog admission readiness closed")
    req(baseline.get("next_gate") == NEXT_GATE, "next gate drifted")

    claims = baseline.get("claims")
    req(isinstance(claims, dict), "claims missing")
    req(all(value is False for value in claims.values()), "fail-closed claim escaped")
    req(set(claims) == {
        "production_write_authorized",
        "production_publication_authorized",
        "programming_algorithm_equivalence_claimed",
        "runtime_programming_support_claimed",
        "security_mutation_authorized",
        "debug_attach_supported",
        "physical_validation_claimed",
        "hil_required_for_catalog_admission",
    }, "claim surface drifted")

    req(len(rows) == EXPECTED_EXACT_COUNT, "canonical candidate row count drifted")
    req(len({row["icpn"] for row in rows}) == EXPECTED_EXACT_COUNT, "candidate ICPNs are not unique")
    req([row["icpn"] for row in rows] == sorted(row["icpn"] for row in rows), "candidate ICPNs are not sorted")
    req(all(row["manufacturer"] == "STMicroelectronics" for row in rows), "candidate manufacturer drifted")
    req(all(row["family"] == FAMILY for row in rows), "candidate family drifted")
    req(all(row["openocd_target_config"] == TARGET_CONFIG for row in rows), "candidate target config drifted")
    req(all(row["existing_identifier_kind"] in {"ordering_pattern", "cmsis_device_name"} for row in rows), "unsupported route kind retained")
    req(all(row["source_authority"].startswith(("https://www.st.com/", "https://estore.st.com/")) for row in rows), "non-ST metadata authority retained")

    route_counts: dict[str, int] = {}
    for row in rows:
        route_counts[row["existing_identifier_kind"]] = route_counts.get(row["existing_identifier_kind"], 0) + 1
    req(route_counts == EXPECTED_ROUTE_KIND_COUNTS, "candidate route kind counts drifted")

    bridges = [row for row in rows if row["mapping_status"].endswith("_via_functional_option_bridge")]
    req(len(bridges) == 1, "functional-option bridge cardinality drifted")
    bridge = bridges[0]
    req(bridge["icpn"] == "STM32H757XIH6A", "functional-option bridge identity drifted")
    req(bridge["existing_identifier"] == "STM32H757XIHx", "functional-option bridge route drifted")
    req(bridge["option_suffix"] == "A", "functional-option bridge metadata drifted")

    exceptions = [row for row in rows if row["verification_status"] == "verified_st_official_exception_plus_retained_exact_identity"]
    req(len(exceptions) == 1, "metadata exception row count drifted")
    exception = exceptions[0]
    req(exception["icpn"] == "STM32H747IIT3", "metadata exception identity drifted")
    req(exception["package"] == "LQFP" and exception["pin_count"] == "176", "H747IIT3 package metadata drifted")
    req(exception["flash_size"] == "2048 KiB", "H747IIT3 flash metadata drifted")
    req(exception["temperature_grade"] == "-40..125 C", "H747IIT3 temperature metadata drifted")
    req(exception["source_authority"].startswith("https://estore.st.com/"), "H747IIT3 exception is not pinned to official ST store")

    by_icpn = {row["icpn"]: row for row in rows}
    for icpn, pins in {
        "STM32H725VGY6TR": "115",
        "STM32H735VGY6TR": "115",
        "STM32H747ZIY6TR": "156",
        "STM32H757ZIY6TR": "156",
    }.items():
        req(by_icpn[icpn]["package"] == "WLCSP" and by_icpn[icpn]["pin_count"] == pins, f"{icpn}: WLCSP pin-count metadata drifted")

    req(pattern_matches("STM32H742XGHx", "STM32H742XGH6"), "literal-uppercase-X positive regression")
    req(not pattern_matches("STM32H742XGHx", "STM32H742VGH6"), "uppercase X incorrectly became wildcard")

    q_rows = [row for row in rows if row["option_suffix"] in {"Q", "QTR"}]
    req(len(q_rows) == 13, "Q-option route population drifted")
    req(all(row["existing_identifier_kind"] == "cmsis_device_name" for row in q_rows), "Q option bypassed CMSIS route")
    req(all(not row["mapping_status"].endswith("_via_functional_option_bridge") for row in q_rows), "Q option was incorrectly stripped for route resolution")

    req(hashlib.sha256(actual_csv.encode("utf-8")).hexdigest() == EXPECTED_CSV_SHA256, "candidate CSV digest drifted")
    req(baseline.get("canonical_candidate_csv_sha256") == hashlib.sha256(actual_csv.encode("utf-8")).hexdigest(), "baseline/candidate digest mismatch")

    req(authority.get("authority_id") == "stm32h7-classic-ordering-information-v1", "metadata authority id drifted")
    req(authority.get("family") == FAMILY and authority.get("partition") == PARTITION_ID, "metadata authority scope drifted")
    req(len(authority.get("documents", [])) == 15, "metadata document count drifted")
    for series, expected in EXPECTED_DOCUMENTS.items():
        docs = [d for d in authority["documents"] if series in d.get("scope", [])]
        req(len(docs) == 1, f"{series}: metadata document coverage drifted")
        req((docs[0].get("document_id"), docs[0].get("revision")) == expected, f"{series}: metadata document revision drifted")
        req(str(docs[0].get("url", "")).startswith("https://www.st.com/"), f"{series}: metadata document is not official ST")
    meta_exc = authority.get("metadata_exceptions")
    req(isinstance(meta_exc, dict) and set(meta_exc) == {"STM32H747IIT3"}, "metadata exception set drifted")
    req(meta_exc["STM32H747IIT3"].get("temperature_grade") == "-40..125 C", "metadata exception temperature drifted")
    req(meta_exc["STM32H747IIT3"].get("source_authority", "").startswith("https://estore.st.com/"), "metadata exception authority drifted")
    req((authority.get("route_semantics") or {}).get("wildcard", "").startswith("Only lowercase x"), "lowercase-only wildcard contract drifted")
    req(all(value is False for value in (authority.get("claims") or {}).values()), "metadata authority fail-closed claim escaped")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(source.get("row_count", 0)) for source in sources) == EXPECTED_PRODUCTION_COUNT, "Production Catalog changed")
    req(all(source.get("family") != FAMILY for source in sources), "STM32H7 leaked into Production")


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

    replay = build_readiness()
    req(baseline == replay, "readiness baseline differs from deterministic replay")
    expected_csv = csv_text(build_rows())
    req(actual_csv == expected_csv, "canonical candidate CSV differs from deterministic replay")
    validate_static(baseline, rows, actual_csv, authority, production)

    controls = [
        ("Production authorization", lambda b,r,a,p: b["claims"].__setitem__("production_write_authorized", True)),
        ("publication authorization", lambda b,r,a,p: b["claims"].__setitem__("production_publication_authorized", True)),
        ("programming equivalence", lambda b,r,a,p: b["claims"].__setitem__("programming_algorithm_equivalence_claimed", True)),
        ("runtime support", lambda b,r,a,p: b["claims"].__setitem__("runtime_programming_support_claimed", True)),
        ("security mutation", lambda b,r,a,p: b["claims"].__setitem__("security_mutation_authorized", True)),
        ("debug attach", lambda b,r,a,p: b["claims"].__setitem__("debug_attach_supported", True)),
        ("physical validation", lambda b,r,a,p: b["claims"].__setitem__("physical_validation_claimed", True)),
        ("HIL coupling", lambda b,r,a,p: b["claims"].__setitem__("hil_required_for_catalog_admission", True)),
        ("manual review", lambda b,r,a,p: b.__setitem__("manual_review_count", 1)),
        ("route coverage loss", lambda b,r,a,p: b.__setitem__("route_ready_count", EXPECTED_EXACT_COUNT - 1)),
        ("metadata coverage loss", lambda b,r,a,p: b.__setitem__("metadata_ready_count", EXPECTED_EXACT_COUNT - 1)),
        ("metadata exception loss", lambda b,r,a,p: b.__setitem__("metadata_exception_count", 0)),
        ("functional bridge loss", lambda b,r,a,p: b.__setitem__("route_functional_option_bridge_count", 0)),
        ("skip publication gate", lambda b,r,a,p: b.__setitem__("next_gate", "stm32h7-classic-target-execution-gate")),
        ("exact digest mutation", lambda b,r,a,p: b.__setitem__("frozen_exact_icpn_set_sha256", "0" * 64)),
        ("Production mutation", lambda b,r,a,p: p["sources"][0].__setitem__("row_count", int(p["sources"][0]["row_count"]) + 1)),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print(
        "PASS: STM32H7-classic admission readiness: "
        f"{EXPECTED_EXACT_COUNT}/{EXPECTED_EXACT_COUNT} ready, "
        "178 ordering + 13 CMSIS routes, 1 metadata exception, "
        "1 functional-option bridge, Production unchanged at 2318, "
        f"{len(controls)} negative controls"
    )


if __name__ == "__main__":
    main()
