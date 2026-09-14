#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, CandidateManualReview
from stm32l5_admission_policy import (
    EXPECTED_ASSIGNED_KIND_COUNTS,
    EXPECTED_ROUTE_BINDING_SHA256,
    EXPECTED_ROUTE_KIND_COUNTS,
    EXPECTED_ROUTE_ROWS,
    TARGET_CONFIG,
    build_plan,
    plan_is_clean,
    read_route_rows,
    resolve_route,
    validate_route_rows,
)
from stm32l5_metadata_policy import build_candidate_inputs

HERE = Path(__file__).resolve().parent
FROZEN = HERE / "stm32l5-canonical-admission-plan.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def negative_controls() -> None:
    rows = read_route_rows()
    candidates = build_candidate_inputs()
    first = candidates[0]["icpn"]

    duplicate = copy.deepcopy(rows)
    duplicate[-1] = dict(duplicate[0])
    try:
        validate_route_rows(duplicate)
    except AdmissionError:
        pass
    else:
        raise SystemExit("negative control failed: duplicate route evidence admitted")

    ambiguous = copy.deepcopy(rows)
    match = next(row for row in rows if row["part_number"] == "STM32L552CCTx")
    ambiguous.append(dict(match))
    try:
        resolve_route(first, ambiguous)
    except CandidateManualReview:
        pass
    else:
        raise SystemExit("negative control failed: ambiguous route admitted")

    wrong_target = copy.deepcopy(rows)
    wrong_target[0]["target_config"] = "tcl/target/stm32l4x.cfg"
    try:
        validate_route_rows(wrong_target)
    except AdmissionError:
        pass
    else:
        raise SystemExit("negative control failed: wrong target config admitted")


def main() -> int:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    plan = build_plan()
    req(plan_is_clean(plan), "STM32L5 admission plan is not clean")

    for key in (
        "schema_version", "transaction", "authority", "family", "manufacturer",
        "metadata_ready_exact_icpns", "route_evidence_rows", "route_evidence_kind_counts",
        "unique_route_assignments", "route_assignment_kind_counts", "route_binding_sha256",
        "planned_canonical_rows", "required_target_config", "route_evidence_semantics",
        "security_fence", "claims", "next_research_gate",
    ):
        req(plan.get(key) == frozen.get(key), f"STM32L5 frozen admission field drifted: {key}")

    req(plan["route_evidence_rows"] == EXPECTED_ROUTE_ROWS, "route row count drift")
    req(plan["route_evidence_kind_counts"] == EXPECTED_ROUTE_KIND_COUNTS, "route kind count drift")
    req(plan["route_assignment_kind_counts"] == EXPECTED_ASSIGNED_KIND_COUNTS, "assigned kind count drift")
    req(plan["route_binding_sha256"] == EXPECTED_ROUTE_BINDING_SHA256, "route binding digest drift")
    req(plan["required_target_config"] == TARGET_CONFIG, "target config drift")
    req(set(plan["claims"].values()) == {False}, "capability claim escaped fail-closed state")
    req(set(plan["security_fence"].values()) == {False}, "security fence unexpectedly opened")

    negative_controls()
    print(json.dumps({
        "metadata_ready": plan["metadata_ready_exact_icpns"],
        "unique_routes": plan["unique_route_assignments"],
        "planned_canonical_rows": plan["planned_canonical_rows"],
        "route_assignment_kind_counts": plan["route_assignment_kind_counts"],
        "production_write_authorized": plan["claims"]["production_write_authorized"],
        "next_gate": plan["next_research_gate"],
    }, sort_keys=True))
    print("STM32L5 canonical admission plan under security fence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
