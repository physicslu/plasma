#!/usr/bin/env python3
"""Fail-closed validation for the frozen STM32H7 partition selection."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from stm32h7_partitioned_scope_selection import SOURCE, build_selection

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32h7-partitioned-scope-selection.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate(value: dict) -> None:
    req(value.get("selection_id") == "stm32h7-partitioned-scope-selection-v1", "selection id drifted")
    req(value.get("scope") == "partition_selection_research_only", "scope drifted")
    req(value.get("status") == "selected_for_bounded_manufacturer_evidence_only", "status drifted")
    req(value.get("selected_partition") == "STM32H7RS", "selected partition drifted")
    req(value.get("selected_target_config") == "tcl/target/stm32h7rsx.cfg", "selected target config drifted")
    req(value.get("next_gate") == "stm32h7rs-bounded-official-manufacturer-evidence-accessibility-gate", "next gate drifted")

    upstream = value.get("upstream") or {}
    req(upstream.get("selected_frontier") == "STM32H7", "upstream frontier drifted")
    req(upstream.get("frontier_row_count") == 200, "frontier row count drifted")
    req(upstream.get("frontier_subfamily_count") == 20, "frontier subfamily count drifted")

    source = value.get("source") or {}
    req(source.get("frozen_row_count") == 200, "frozen row count drifted")
    req(source.get("frozen_duplicate_resolution_count") == 34, "frozen duplicate-resolution count drifted")
    req(source.get("frozen_partition_source_sha256") == hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "frozen source digest drifted")

    policy = value.get("partition_policy") or {}
    req(policy.get("primary_boundary") == "target_config_and_family_label", "partition boundary drifted")
    req(policy.get("selection_order") == ["fewest frozen source rows", "fewest subfamilies", "lexical partition_id tie-break"], "partition ordering drifted")

    partitions = value.get("partitions") or []
    req(len(partitions) == 2, "partition count drifted")
    by_id = {item.get("partition_id"): item for item in partitions}
    req(set(by_id) == {"STM32H7RS", "STM32H7-classic"}, "partition ids drifted")

    rs = by_id["STM32H7RS"]
    req(rs.get("family_label") == "STM32H7RS Series", "H7RS family label drifted")
    req(rs.get("target_config") == "tcl/target/stm32h7rsx.cfg", "H7RS target config drifted")
    req(rs.get("row_count") == 34, "H7RS row count drifted")
    req(rs.get("subfamily_count") == 4, "H7RS subfamily count drifted")
    req(rs.get("subfamilies") == ["STM32H7R3", "STM32H7R7", "STM32H7S3", "STM32H7S7"], "H7RS subfamilies drifted")
    req(rs.get("identifier_kind_counts") == {"cmsis_device_name": 4, "ordering_pattern": 30}, "H7RS identifier kinds drifted")
    req(rs.get("duplicate_resolution_count") == 34, "H7RS duplicate-resolution count drifted")
    req(rs.get("bounded_research_eligible") is True, "H7RS bounded eligibility drifted")
    req(rs.get("admission_ready") is False, "H7RS admission opened")

    classic = by_id["STM32H7-classic"]
    req(classic.get("family_label") == "STM32H7 Series", "classic family label drifted")
    req(classic.get("target_config") == "tcl/target/stm32h7x.cfg", "classic target config drifted")
    req(classic.get("row_count") == 166, "classic row count drifted")
    req(classic.get("subfamily_count") == 16, "classic subfamily count drifted")
    req(classic.get("identifier_kind_counts") == {"cmsis_device_name": 28, "ordering_pattern": 138}, "classic identifier kinds drifted")
    req(classic.get("duplicate_resolution_count") == 0, "classic duplicate-resolution count drifted")
    req(classic.get("bounded_research_eligible") is True, "classic bounded eligibility drifted")
    req(classic.get("admission_ready") is False, "classic admission opened")
    req(rs["row_count"] + classic["row_count"] == 200, "partition row total drifted")
    req(rs["subfamily_count"] + classic["subfamily_count"] == 20, "partition subfamily total drifted")

    claims = value.get("claims") or {}
    for key in [
        "production_write_authorized",
        "exact_icpn_discovery_completed",
        "icpn_admission_authorized",
        "programming_algorithm_equivalence_claimed",
        "runtime_programming_support_claimed",
        "physical_validation_claimed",
        "hil_required_for_catalog_admission",
        "stm32h7rs_admission_ready",
        "stm32h7_classic_rejected",
    ]:
        req(claims.get(key) is False, f"fail-closed claim opened: {key}")


def expect_rejected(name: str, mutate) -> None:
    candidate = copy.deepcopy(json.loads(SELECTION.read_text(encoding="utf-8")))
    mutate(candidate)
    try:
        validate(candidate)
    except AssertionError:
        return
    raise AssertionError(f"negative control was accepted: {name}")


def main() -> int:
    frozen = json.loads(SELECTION.read_text(encoding="utf-8"))
    validate(frozen)
    regenerated = build_selection()
    req(regenerated == frozen, "frozen selection does not replay byte-semantically")

    controls = [
        ("select-classic-first", lambda v: v.__setitem__("selected_partition", "STM32H7-classic")),
        ("route-selected-via-classic-config", lambda v: v.__setitem__("selected_target_config", "tcl/target/stm32h7x.cfg")),
        ("open-h7rs-admission", lambda v: next(x for x in v["partitions"] if x["partition_id"] == "STM32H7RS").__setitem__("admission_ready", True)),
        ("claim-exact-icpn-discovery", lambda v: v["claims"].__setitem__("exact_icpn_discovery_completed", True)),
        ("authorize-production-write", lambda v: v["claims"].__setitem__("production_write_authorized", True)),
        ("reject-classic-partition", lambda v: v["claims"].__setitem__("stm32h7_classic_rejected", True)),
        ("skip-manufacturer-evidence-gate", lambda v: v.__setitem__("next_gate", "stm32h7rs-production-publication-gate")),
        ("lose-specific-conflict-resolution", lambda v: next(x for x in v["partitions"] if x["partition_id"] == "STM32H7RS").__setitem__("duplicate_resolution_count", 0)),
    ]
    for name, mutate in controls:
        expect_rejected(name, mutate)

    print("STM32H7 partitioned scope selection: PASS")
    print("partitions=2 rows=200 subfamilies=20 selected=STM32H7RS")
    print(f"negative_controls={len(controls)} rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
