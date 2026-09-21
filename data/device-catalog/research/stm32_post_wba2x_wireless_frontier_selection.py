#!/usr/bin/env python3
"""Select the next bounded STM32 wireless research frontier after WBA2X publication.

Research-only sequencing transaction. Already-published wireless families are
removed from the remaining candidate set before applying the frozen wireless
sequencing policy. Selection authorizes only the next bounded official-ST
commercial identity/lifecycle evidence-accessibility gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FROZEN_PRODUCTION = HERE / "stm32-post-wba2x-production-prestate.json"
PRIOR_SELECTION = HERE / "stm32-post-h7-wireless-frontier-selection.json"
PRIORITIZATION = HERE / "stm32-cross-family-prioritization-baseline.json"

EXPECTED_PRODUCTION_BLOB = "b2c6850e0c9246a8cf344ac7090b3f3d01573f1e"
EXPECTED_PRIOR_SELECTION_BLOB = "3397b44d97216625ce3fcf5235f6ae05e260ac59"
EXPECTED_PRIORITIZATION_BLOB = "f445bc7938eee1a0453fcebe6bf81d77879aeaca"

EXPECTED_PRODUCTION_EXACT = 2523
EXPECTED_PRODUCTION_FAMILIES = 19
PUBLISHED_WIRELESS = {"STM32WBA2X": 14}

WIRELESS_IDS = [
    "STM32W108",
    "STM32WBA2X",
    "STM32WBA5X",
    "STM32WBA6X",
    "STM32WBX",
    "STM32WLX",
]
SELECTED = "STM32WLX"
NEXT_GATE = "stm32wlx-bounded-official-manufacturer-evidence-accessibility-gate"


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


def _production_boundary() -> tuple[dict[str, Any], set[str]]:
    frozen_bytes = FROZEN_PRODUCTION.read_bytes()
    _require(
        _git_blob_sha(frozen_bytes) == EXPECTED_PRODUCTION_BLOB,
        "frozen post-WBA2X Production prestate drifted",
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
    for family, rows in PUBLISHED_WIRELESS.items():
        _require(family in by_family, f"{family}: expected wireless publication missing")
        _require(by_family[family].get("row_count") == rows, f"{family}: Production row count drifted")

    other_wireless = set(WIRELESS_IDS) - set(PUBLISHED_WIRELESS)
    _require(
        all(family not in by_family for family in other_wireless),
        "unexpected additional wireless Production family present",
    )
    return (
        {
            "exact_icpns": exact,
            "families": len(sources),
            "production_series": sorted(by_family),
            "published_wireless_families": dict(sorted(PUBLISHED_WIRELESS.items())),
            "standard_nonwireless_frontier_exhausted": True,
        },
        set(PUBLISHED_WIRELESS),
    )


def _remaining_candidates(published: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    prior_bytes = PRIOR_SELECTION.read_bytes()
    _require(
        _git_blob_sha(prior_bytes) == EXPECTED_PRIOR_SELECTION_BLOB,
        "prior wireless frontier selection drifted",
    )
    prior = json.loads(prior_bytes)
    _require(
        prior.get("selection_id") == "stm32-post-h7-wireless-frontier-selection-v1",
        "prior wireless selection id drifted",
    )
    _require(prior.get("selected_wireless_frontier") == "STM32WBA2X", "prior selected frontier drifted")
    _require(
        prior.get("next_gate") == "stm32wba2x-bounded-official-manufacturer-evidence-accessibility-gate",
        "prior WBA2X evidence-accessibility gate drifted",
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
    already_published: list[dict[str, Any]] = []

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

        if wireless_id in published:
            already_published.append({
                **compact,
                "publication_status": "published_in_production",
                "production_row_count": PUBLISHED_WIRELESS[wireless_id],
            })
            continue

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
    already_published.sort(key=lambda item: item["plasma_series"])

    _require(
        [item["plasma_series"] for item in eligible]
        == ["STM32WLX", "STM32WBA6X", "STM32WBX", "STM32WBA5X"],
        "remaining eligible wireless sequence drifted",
    )
    _require(
        [(item["row_count"], item["subfamily_count"]) for item in eligible]
        == [(17, 4), (19, 5), (23, 8), (34, 5)],
        "remaining wireless candidate sizing drifted",
    )
    _require(
        len(deferred) == 1
        and deferred[0]["plasma_series"] == "STM32W108"
        and deferred[0]["defer_reasons"]
        == ["structural_gate_fail", "no_bounded_subfamilies", "no_ordering_pattern_rows"],
        "STM32W108 deferred boundary drifted",
    )
    _require(
        len(already_published) == 1
        and already_published[0]["plasma_series"] == "STM32WBA2X"
        and already_published[0]["production_row_count"] == 14,
        "published wireless exclusion boundary drifted",
    )
    return eligible, deferred, already_published


def build_selection() -> dict[str, Any]:
    production, published = _production_boundary()
    eligible, deferred, already_published = _remaining_candidates(published)
    selected = eligible[0]

    _require(selected["plasma_series"] == SELECTED, "selected wireless frontier drifted")
    _require(selected["row_count"] == 17, "STM32WLX row count drifted")
    _require(selected["subfamily_count"] == 4, "STM32WLX subfamily count drifted")
    _require(
        selected["subfamilies"] == ["STM32WL54", "STM32WL55", "STM32WLE4", "STM32WLE5"],
        "STM32WLX subfamilies drifted",
    )
    _require(
        selected["target_configs"] == ["tcl/target/stm32wlx.cfg"],
        "STM32WLX target config drifted",
    )
    _require(
        selected["identifier_kind_counts"] == {"ordering_pattern": 17},
        "STM32WLX identifier mix drifted",
    )

    return {
        "schema_version": 1,
        "selection_id": "stm32-post-wba2x-wireless-frontier-selection-v1",
        "scope": "wireless_frontier_reselection_research_only",
        "status": "selected_for_bounded_manufacturer_evidence_only",
        "production_boundary": {
            **production,
            "frozen_manifest_git_blob_sha": EXPECTED_PRODUCTION_BLOB,
        },
        "upstream": {
            "prior_wireless_selection_id": "stm32-post-h7-wireless-frontier-selection-v1",
            "prior_wireless_selection_git_blob_sha": EXPECTED_PRIOR_SELECTION_BLOB,
            "cross_family_prioritization_id": "stm32-cross-family-prioritization-v1",
            "cross_family_prioritization_git_blob_sha": EXPECTED_PRIORITIZATION_BLOB,
            "original_wireless_backlog_count": len(WIRELESS_IDS),
            "published_wireless_count": len(already_published),
            "remaining_structurally_eligible_count": len(eligible),
            "deferred_wireless_count": len(deferred),
        },
        "selection_policy": {
            "eligibility": [
                "cohort == wireless_requires_dedicated_scope",
                "not already published in Production",
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
        "already_published_wireless_frontiers": already_published,
        "eligible_wireless_frontiers": eligible,
        "deferred_wireless_frontiers": deferred,
        "selected_wireless_frontier": selected["plasma_series"],
        "selected_target_config": selected["target_configs"][0],
        "selected_row_count": selected["row_count"],
        "selected_subfamily_count": selected["subfamily_count"],
        "selected_subfamilies": selected["subfamilies"],
        "selected_identifier_kind_counts": selected["identifier_kind_counts"],
        "selection_basis": [
            "STM32WBA2X is already published and is excluded from remaining frontier selection",
            "remaining wireless STM32 candidates stay under the dedicated wireless scope boundary",
            "STM32WLX is the smallest remaining structurally eligible bounded wireless candidate by the frozen sequencing policy",
            "selection is sequencing only and does not reject the other remaining wireless families",
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
            "stm32wlx_admission_ready": False,
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
