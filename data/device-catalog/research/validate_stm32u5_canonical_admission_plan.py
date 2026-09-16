#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, CandidateManualReview
from stm32u5_admission_policy import (
    BRIDGE_ICPN,
    BRIDGE_KIND,
    EXPECTED_ACTIVE_COUNT,
    EXPECTED_ASSIGNMENT_KIND_COUNTS,
    EXPECTED_ROUTE_BINDING_SHA256,
    EXPECTED_ROUTE_EVIDENCE_SHA256,
    EXPECTED_ROUTE_KIND_COUNTS,
    EXPECTED_ROUTE_ROWS,
    EXPECTED_U5A5_ROUTE_EVIDENCE_SHA256,
    EXPECTED_U5A5_ROUTE_ROWS,
    QUARANTINED_PREVIEW,
    TARGET_CONFIG,
    build_canonical_rows,
    build_plan,
    load_bridge,
    pattern_matches,
    plan_is_clean,
    read_route_rows,
    resolve_route,
    route_evidence_sha,
    validate_bridge_payload,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32u5-canonical-admission-plan.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def expect_manual(fn, message: str) -> None:
    try:
        fn()
    except CandidateManualReview:
        return
    raise SystemExit(message)


def expect_admission_error(fn, message: str) -> None:
    try:
        fn()
    except AdmissionError:
        return
    raise SystemExit(message)


def main() -> int:
    frozen = json.loads(BASELINE.read_text(encoding="utf-8"))
    plan = build_plan()
    req(plan == frozen, "STM32U5 canonical admission frozen plan drifted")
    req(plan_is_clean(plan), "STM32U5 canonical admission plan is not fail-closed clean")
    req(plan["production_exact_icpn_count"] == 2017, "Production exact ICPN count drifted")
    req(plan["route_evidence_rows"] == EXPECTED_ROUTE_ROWS == 162, "route row count drifted")
    req(plan["route_evidence_kind_counts"] == EXPECTED_ROUTE_KIND_COUNTS, "route kind counts drifted")
    req(plan["route_evidence_sha256"] == EXPECTED_ROUTE_EVIDENCE_SHA256, "route evidence digest drifted")
    req(plan["route_assignment_kind_counts"] == EXPECTED_ASSIGNMENT_KIND_COUNTS, "assignment kind counts drifted")
    req(plan["route_binding_sha256"] == EXPECTED_ROUTE_BINDING_SHA256, "route binding digest drifted")
    req(plan["required_target_config"] == TARGET_CONFIG, "target config drifted")
    req(plan["unique_route_assignments"] == EXPECTED_ACTIVE_COUNT == 265, "route cardinality drifted")
    req(plan["planned_canonical_rows"] == 265 and plan["standard_route_assignments"] == 264, "canonical cardinality drifted")
    req(plan["supplemental_cmsis_bridges"] == 1, "CMSIS bridge count drifted")
    req(plan["quarantined_preview_exact_icpns"] == [QUARANTINED_PREVIEW], "Preview quarantine drifted")
    req(set(plan["claims"].values()) == {False}, "claims escaped fail-closed state")
    req(set(plan["security_fence"].values()) == {False}, "security fence escaped fail-closed state")

    rows = build_canonical_rows()
    req(len(rows) == 265 and len({row["icpn"] for row in rows}) == 265, "canonical output uniqueness drifted")
    req(QUARANTINED_PREVIEW not in {row["icpn"] for row in rows}, "quarantined Preview entered plan")
    req(Counter(row["existing_identifier_kind"] for row in rows) == EXPECTED_ASSIGNMENT_KIND_COUNTS, "canonical route assignment drifted")
    req(all(row["openocd_target_config"] == TARGET_CONFIG for row in rows), "canonical target config drifted")
    bridge_rows = [row for row in rows if row["existing_identifier_kind"] == BRIDGE_KIND]
    req(len(bridge_rows) == 1 and bridge_rows[0]["icpn"] == BRIDGE_ICPN, "CMSIS bridge row drifted")
    req(bridge_rows[0]["mapping_status"] == "deterministic_cmsis_exact_membership_bridge", "CMSIS bridge status drifted")
    req(all(row["mapping_status"] in {"deterministic_openocd_mapping_candidate", "deterministic_cmsis_exact_membership_bridge"} for row in rows), "mapping status overclaimed")

    routes = read_route_rows()
    req(route_evidence_sha(routes) == EXPECTED_ROUTE_EVIDENCE_SHA256, "route evidence replay drifted")
    u5a5 = [row for row in routes if row["subfamily"] == "STM32U5A5"]
    req(len(u5a5) == EXPECTED_U5A5_ROUTE_ROWS and route_evidence_sha(u5a5) == EXPECTED_U5A5_ROUTE_EVIDENCE_SHA256, "U5A5 route evidence replay drifted")

    bridge = load_bridge()
    mutated_bridge = copy.deepcopy(bridge)
    mutated_bridge["manufacturer_cmsis_authority"]["commit"] = "0" * 40
    expect_admission_error(lambda: validate_bridge_payload(mutated_bridge), "negative control failed: mutated CMSIS provenance accepted")

    standard = next(row for row in rows if row["existing_identifier_kind"] != BRIDGE_KIND)
    matching = next(route for route in routes if pattern_matches(route["part_number"], standard["icpn"][:-2] if standard["icpn"].endswith("TR") else standard["icpn"]))
    expect_manual(lambda: resolve_route(standard["icpn"], routes + [dict(matching)], bridge), "negative control failed: ambiguous route admitted")
    reduced = [row for row in routes if row is not matching]
    expect_manual(lambda: resolve_route(standard["icpn"], reduced, bridge), "negative control failed: unmapped non-bridge route admitted")
    expect_manual(lambda: resolve_route("STM32U5A5QII3QX", routes, bridge), "negative control failed: bridge expanded beyond exact ICPN")

    req(plan["claims"]["preview_identity_admission_authorized"] is False, "Preview admission unexpectedly authorized")
    req("not programming equivalence" in plan["route_evidence_semantics"], "route evidence overclaimed as programming equivalence")

    print(json.dumps({
        "retained_exact_icpns": 266,
        "metadata_ready_active_exact_icpns": 265,
        "unique_routes": 265,
        "standard_routes": 264,
        "cmsis_exact_membership_bridges": 1,
        "ordering_pattern_assignments": 117,
        "cmsis_device_name_assignments": 147,
        "quarantined_preview": QUARANTINED_PREVIEW,
        "production_exact_icpns": 2017,
        "production_admission_authorized": False,
    }, sort_keys=True))
    print("STM32U5 canonical admission plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
