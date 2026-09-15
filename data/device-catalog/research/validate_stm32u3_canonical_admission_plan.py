#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from device_catalog_admission_framework import CandidateManualReview
from stm32u3_admission_policy import (
    EXPECTED_ASSIGNMENT_KIND_COUNTS,
    EXPECTED_ROUTE_BINDING_SHA256,
    EXPECTED_ROUTE_EVIDENCE_SHA256,
    EXPECTED_ROUTE_KIND_COUNTS,
    EXPECTED_ROUTE_ROWS,
    TARGET_CONFIG,
    build_canonical_rows,
    build_plan,
    pattern_matches,
    plan_is_clean,
    read_route_rows,
    resolve_route,
    route_evidence_sha,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32u3-canonical-admission-plan.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    frozen = json.loads(BASELINE.read_text(encoding="utf-8"))
    plan = build_plan()
    req(plan == frozen, "STM32U3 canonical admission frozen plan drifted")
    req(plan_is_clean(plan), "STM32U3 canonical admission plan is not fail-closed clean")
    req(plan["production_exact_icpn_count"] == 1862, "Production exact ICPN count drifted")
    req(plan["route_evidence_rows"] == EXPECTED_ROUTE_ROWS == 171, "route row count drifted")
    req(plan["route_evidence_kind_counts"] == EXPECTED_ROUTE_KIND_COUNTS, "route kind counts drifted")
    req(plan["route_assignment_kind_counts"] == EXPECTED_ASSIGNMENT_KIND_COUNTS, "assignment kind counts drifted")
    req(plan["route_evidence_sha256"] == EXPECTED_ROUTE_EVIDENCE_SHA256, "route evidence digest drifted")
    req(plan["route_binding_sha256"] == EXPECTED_ROUTE_BINDING_SHA256, "route binding digest drifted")
    req(plan["required_target_config"] == TARGET_CONFIG, "target config drifted")
    req(plan["unique_route_assignments"] == 106 and plan["planned_canonical_rows"] == 106, "canonical cardinality drifted")
    req(plan["marketing_status_counts"] == {"Active": 100, "Evaluation": 6}, "marketing status preservation drifted")
    req(set(plan["claims"].values()) == {False}, "claims escaped fail-closed state")
    req(set(plan["security_fence"].values()) == {False}, "security fence escaped fail-closed state")

    rows = build_canonical_rows()
    req(len(rows) == 106 and len({row["icpn"] for row in rows}) == 106, "canonical output uniqueness drifted")
    req(Counter(row["existing_identifier_kind"] for row in rows) == EXPECTED_ASSIGNMENT_KIND_COUNTS, "canonical route assignment drifted")
    req(all(row["mapping_status"] == "deterministic_openocd_mapping_candidate" for row in rows), "mapping status overclaimed")
    req(all(row["openocd_target_config"] == TARGET_CONFIG for row in rows), "canonical target config drifted")

    routes = read_route_rows()
    # Negative control 1: evidence mutation must invalidate frozen digest.
    mutated = copy.deepcopy(routes)
    mutated[0]["mapping_status"] = "verified"
    req(route_evidence_sha(mutated) != EXPECTED_ROUTE_EVIDENCE_SHA256, "negative control failed: route mutation preserved digest")

    # Negative control 2: duplicate a real matching route and require ambiguity rejection.
    first = rows[0]
    matching = next(row for row in routes if pattern_matches(row["part_number"], first["icpn"][:-2] if first["icpn"].endswith("TR") else first["icpn"]))
    ambiguous = routes + [dict(matching)]
    try:
        resolve_route(first["icpn"], ambiguous)
    except CandidateManualReview:
        pass
    else:
        raise SystemExit("negative control failed: ambiguous STM32U3 route admitted")

    # Negative control 3: remove the sole route and require unmapped rejection.
    reduced = [row for row in routes if row is not matching]
    try:
        resolve_route(first["icpn"], reduced)
    except CandidateManualReview:
        pass
    else:
        raise SystemExit("negative control failed: unmapped STM32U3 route admitted")

    # Negative control 4: Evaluation observation must never become Production authority.
    req(plan["claims"]["evaluation_status_implies_production_admission"] is False, "Evaluation status opened Production admission")
    # Negative control 5: OpenOCD route evidence remains mapping-only.
    req("not programming equivalence" in plan["route_evidence_semantics"], "OpenOCD mapping overclaimed as programming equivalence")

    print(json.dumps({
        "exact_icpns": 106,
        "unique_routes": 106,
        "ordering_pattern_assignments": 49,
        "cmsis_device_name_assignments": 57,
        "unresolved": 0,
        "production_exact_icpns": 1862,
        "production_admission_authorized": False,
    }, sort_keys=True))
    print("STM32U3 canonical admission plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
