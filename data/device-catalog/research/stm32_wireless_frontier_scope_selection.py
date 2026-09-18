#!/usr/bin/env python3
"""Select the first bounded STM32 wireless research frontier after H7 publication.

This is a research-only sequencing transaction. Wireless cohorts remain
separate from the standard non-wireless path. Selection authorizes only the
next bounded official-manufacturer commercial identity/lifecycle evidence
accessibility gate; it does not authorize radio/security operations, target
execution, runtime programming, Catalog admission, or Production publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FROZEN_PRODUCTION = HERE / "stm32-post-h7-production-prestate.json"
UPSTREAM_FRONTIER = HERE / "stm32-post-u5-frontier-selection.json"
PRIORITIZATION = HERE / "stm32-cross-family-prioritization-baseline.json"

EXPECTED_PRODUCTION_BLOB = "3b59475ad7a45710e9015a8d1cfbb38d8dee7ece"
EXPECTED_UPSTREAM_FRONTIER_BLOB = "712e1162fba526d88d92e61e3b979e0b1a69f876"
EXPECTED_PRIORITIZATION_BLOB = "f445bc7938eee1a0453fcebe6bf81d77879aeaca"
EXPECTED_PRODUCTION_EXACT = 2509
EXPECTED_PRODUCTION_FAMILIES = 18

WIRELESS_IDS = [
    "STM32W108",
    "STM32WBA2X",
    "STM32WBA5X",
    "STM32WBA6X",
    "STM32WBX",
    "STM32WLX",
]
SELECTED = "STM32WBA2X"
NEXT_GATE = "stm32wba2x-bounded-official-manufacturer-evidence-accessibility-gate"


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name}: expected object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _production_boundary() -> dict[str, Any]:
    frozen_bytes = FROZEN_PRODUCTION.read_bytes()
    _require(
        _git_blob_sha(frozen_bytes) == EXPECTED_PRODUCTION_BLOB,
        "frozen post-H7 Production prestate drifted",
    )
    manifest = json.loads(frozen_bytes)
    _require(manifest.get("status") == "production", "Production status drifted")
    _require(
        manifest.get("selection_policy")
        == "admitted_exact_manufacturer_part_number_only",
        "Production selection policy drifted",
    )
    sources = manifest.get("sources")
    _require(isinstance(sources, list), "Production sources missing")
    exact = sum(
        int(source.get("row_count", 0))
        for source in sources
        if isinstance(source, dict)
    )
    _require(exact == EXPECTED_PRODUCTION_EXACT, f"Production exact count drifted: {exact}")
    _require(
        len(sources) == EXPECTED_PRODUCTION_FAMILIES,
        f"Production family count drifted: {len(sources)}",
    )
    by_family = {
        source.get("family"): source
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("family"), str)
    }
    _require("STM32H7RS" in by_family, "STM32H7RS publication missing")
    _require("STM32H7" in by_family, "STM32H7 publication missing")
    _require(by_family["STM32H7RS"].get("row_count") == 36, "STM32H7RS row count drifted")
    _require(by_family["STM32H7"].get("row_count") == 191, "STM32H7 row count drifted")
    _require(
        all(family not in by_family for family in WIRELESS_IDS),
        "wireless family already present in frozen Production boundary",
    )
    return {
        "exact_icpns": exact,
        "families": len(sources),
        "production_series": sorted(by_family),
        "stm32h7rs_published": True,
        "stm32h7_published": True,
        "stm32h7rs_exact_icpns": 36,
        "stm32h7_exact_icpns": 191,
    }


def _wireless_candidates() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    upstream_bytes = UPSTREAM_FRONTIER.read_bytes()
    _require(
        _git_blob_sha(upstream_bytes) == EXPECTED_UPSTREAM_FRONTIER_BLOB,
        "upstream post-U5 frontier selection drifted",
    )
    upstream = json.loads(upstream_bytes)
    _require(
        upstream.get("selection_id") == "stm32-post-u5-frontier-selection-v1",
        "upstream frontier selection id drifted",
    )
    _require(
        upstream.get("selected_next_research_frontier") == "STM32H7",
        "historical non-wireless frontier drifted",
    )
    backlog = upstream.get("wireless_frontier_backlog")
    _require(isinstance(backlog, list), "wireless backlog missing")
    _require(
        [item.get("plasma_series") for item in backlog if isinstance(item, dict)]
        == WIRELESS_IDS,
        "wireless backlog identity/order drifted",
    )

    prioritization_bytes = PRIORITIZATION.read_bytes()
    _require(
        _git_blob_sha(prioritization_bytes) == EXPECTED_PRIORITIZATION_BLOB,
        "cross-family prioritization baseline drifted",
    )
    prioritization = json.loads(prioritization_bytes)
    _require(
        prioritization.get("policy_id") == "stm32-cross-family-prioritization-v1",
        "cross-family prioritization policy drifted",
    )
    candidates = prioritization.get("candidates")
    _require(isinstance(candidates, list), "prioritization candidates missing")
    by_id = {
        item.get("plasma_series"): item
        for item in candidates
        if isinstance(item, dict) and item.get("plasma_series") in WIRELESS_IDS
    }
    _require(set(by_id) == set(WIRELESS_IDS), "wireless candidate inventory drifted")

    eligible: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for wireless_id in WIRELESS_IDS:
        item = by_id[wireless_id]
        _require(
            item.get("cohort") == "wireless_requires_dedicated_scope",
            f"{wireless_id}: dedicated wireless classification drifted",
        )
        _require(
            item.get("expected_openocd_candidate_contract") is True,
            f"{wireless_id}: OpenOCD candidate contract drifted",
        )
        _require(
            item.get("complete_mapping_metadata") is True,
            f"{wireless_id}: mapping metadata incomplete",
        )
        target_configs = item.get("target_configs")
        _require(
            isinstance(target_configs, list) and len(target_configs) == 1,
            f"{wireless_id}: target config cardinality drifted",
        )

        compact = {
            "plasma_series": wireless_id,
            "row_count": item["row_count"],
            "ordering_pattern_rows": item["ordering_pattern_rows"],
            "cmsis_device_name_rows": item["cmsis_device_name_rows"],
            "subfamily_count": item["subfamily_count"],
            "subfamilies": item["subfamilies"],
            "target_configs": target_configs,
            "identifier_kind_counts": item["identifier_kind_counts"],
            "structural_gate_pass": item["structural_gate_pass"],
            "complete_mapping_metadata": item["complete_mapping_metadata"],
            "cohort": item["cohort"],
        }

        structurally_eligible = (
            item.get("structural_gate_pass") is True
            and isinstance(item.get("row_count"), int)
            and item["row_count"] > 0
            and isinstance(item.get("subfamily_count"), int)
            and item["subfamily_count"] > 0
            and isinstance(item.get("ordering_pattern_rows"), int)
            and item["ordering_pattern_rows"] > 0
        )
        if structurally_eligible:
            eligible.append(compact)
        else:
            reasons = []
            if item.get("structural_gate_pass") is not True:
                reasons.append("structural_gate_fail")
            if not item.get("subfamilies"):
                reasons.append("no_bounded_subfamilies")
            if int(item.get("ordering_pattern_rows", 0)) <= 0:
                reasons.append("no_ordering_pattern_rows")
            deferred.append({**compact, "defer_reasons": reasons})

    eligible.sort(
        key=lambda item: (
            item["row_count"],
            item["subfamily_count"],
            item["plasma_series"],
        )
    )
    deferred.sort(key=lambda item: item["plasma_series"])
    _require(
        [item["plasma_series"] for item in eligible]
        == ["STM32WBA2X", "STM32WLX", "STM32WBA6X", "STM32WBX", "STM32WBA5X"],
        "wireless eligible sequence drifted",
    )
    _require(
        len(deferred) == 1
        and deferred[0]["plasma_series"] == "STM32W108"
        and deferred[0]["defer_reasons"]
        == ["structural_gate_fail", "no_bounded_subfamilies", "no_ordering_pattern_rows"],
        "STM32W108 deferred boundary drifted",
    )
    return eligible, deferred


def build_selection() -> dict[str, Any]:
    production = _production_boundary()
    eligible, deferred = _wireless_candidates()
    selected = eligible[0]
    _require(selected["plasma_series"] == SELECTED, "selected wireless frontier drifted")
    _require(selected["row_count"] == 8, "STM32WBA2X row count drifted")
    _require(selected["subfamily_count"] == 2, "STM32WBA2X subfamily count drifted")
    _require(
        selected["subfamilies"] == ["STM32WBA23", "STM32WBA25"],
        "STM32WBA2X subfamilies drifted",
    )
    _require(
        selected["target_configs"] == ["tcl/target/stm32wba2x.cfg"],
        "STM32WBA2X target config drifted",
    )
    _require(
        selected["identifier_kind_counts"]
        == {"cmsis_device_name": 4, "ordering_pattern": 4},
        "STM32WBA2X identifier mix drifted",
    )

    return {
        "schema_version": 1,
        "selection_id": "stm32-post-h7-wireless-frontier-selection-v1",
        "scope": "wireless_frontier_scope_selection_research_only",
        "status": "selected_for_bounded_manufacturer_evidence_only",
        "production_boundary": {
            **production,
            "frozen_manifest_git_blob_sha": EXPECTED_PRODUCTION_BLOB,
            "standard_nonwireless_frontier_exhausted": True,
        },
        "upstream": {
            "post_u5_frontier_selection_id": "stm32-post-u5-frontier-selection-v1",
            "post_u5_frontier_git_blob_sha": EXPECTED_UPSTREAM_FRONTIER_BLOB,
            "cross_family_prioritization_id": "stm32-cross-family-prioritization-v1",
            "cross_family_prioritization_git_blob_sha": EXPECTED_PRIORITIZATION_BLOB,
            "wireless_backlog_count": len(WIRELESS_IDS),
        },
        "selection_policy": {
            "eligibility": [
                "cohort == wireless_requires_dedicated_scope",
                "structural_gate_pass == true",
                "complete_mapping_metadata == true",
                "exactly one target_config",
                "row_count > 0",
                "subfamily_count > 0",
                "ordering_pattern_rows > 0",
            ],
            "sequencing": [
                "fewest row_count",
                "then fewest subfamily_count",
                "then lexical plasma_series",
            ],
            "sequencing_only": True,
        },
        "eligible_wireless_frontiers": eligible,
        "deferred_wireless_frontiers": deferred,
        "selected_wireless_frontier": selected["plasma_series"],
        "selected_target_config": selected["target_configs"][0],
        "selected_row_count": selected["row_count"],
        "selected_subfamily_count": selected["subfamily_count"],
        "selected_subfamilies": selected["subfamilies"],
        "selected_identifier_kind_counts": selected["identifier_kind_counts"],
        "selection_basis": [
            "STM32H7RS and STM32H7 are now published, exhausting the retained non-wireless STM32 frontier",
            "wireless STM32 candidates remain under a dedicated scope boundary",
            "STM32WBA2X is the smallest structurally eligible bounded wireless candidate by the frozen sequencing policy",
            "selection is sequencing only and does not reject the remaining wireless families",
            "selection does not authorize radio, security, debug, programming, HIL, or target execution operations",
        ],
        "next_gate": NEXT_GATE,
        "claims": {
            "production_write_authorized": False,
            "exact_icpn_discovery_completed": False,
            "icpn_admission_authorized": False,
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
            "stm32w108_rejected": False,
            "stm32wba2x_admission_ready": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(build_selection(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
