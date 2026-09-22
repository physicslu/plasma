#!/usr/bin/env python3
"""Reselect the STM32 wireless frontier after STM32WBA6X evidence accessibility blocks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FROZEN_PRODUCTION = HERE / "stm32-post-wba6x-block-production-prestate.json"
PRIOR_SELECTION = HERE / "stm32-post-wlx-wireless-frontier-selection.json"
BLOCK_GATE = HERE / "stm32wba6x-evidence-accessibility-gate.json"

EXPECTED_PRODUCTION_BLOB = "4174f665a1a8ef7801dec7785c7d3853850cad4a"
EXPECTED_PRIOR_BLOB = "9a744b4b6eea9f040bd53f3a1f595fe14e186042"
EXPECTED_BLOCK_BLOB = "3b30521db5cdf2b7e4348cd4e8ae479ea2d6a8e9"
SELECTED = "STM32WBX"
NEXT_GATE = "stm32wbx-bounded-official-manufacturer-evidence-accessibility-gate"

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data, usedforsecurity=False).hexdigest()

def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name}: expected object")
    return value

def req(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)

def build_selection() -> dict[str, Any]:
    prod_bytes = FROZEN_PRODUCTION.read_bytes()
    req(git_blob_sha(prod_bytes) == EXPECTED_PRODUCTION_BLOB, "frozen Production prestate drifted")
    production = json.loads(prod_bytes)
    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(s.get("row_count", 0)) for s in sources) == 2554, "Production exact count drifted")
    req(len(sources) == 20, "Production family count drifted")
    req(all(s.get("family") != "STM32WBA6X" for s in sources), "blocked WBA6X leaked into Production")

    prior_bytes = PRIOR_SELECTION.read_bytes()
    req(git_blob_sha(prior_bytes) == EXPECTED_PRIOR_BLOB, "prior wireless selection drifted")
    prior = json.loads(prior_bytes)
    req(prior.get("selection_id") == "stm32-post-wlx-wireless-frontier-selection-v1", "prior selection id drifted")
    req(prior.get("selected_wireless_frontier") == "STM32WBA6X", "prior selected frontier drifted")
    eligible = prior.get("eligible_wireless_frontiers")
    req(isinstance(eligible, list), "prior eligible list missing")
    req([x.get("plasma_series") for x in eligible] == ["STM32WBA6X", "STM32WBX", "STM32WBA5X"], "prior eligible sequence drifted")

    gate_bytes = BLOCK_GATE.read_bytes()
    req(git_blob_sha(gate_bytes) == EXPECTED_BLOCK_BLOB, "WBA6X block gate drifted")
    gate = json.loads(gate_bytes)
    req(gate.get("gate_id") == "stm32wba6x-bounded-official-st-evidence-accessibility-v1", "block gate id drifted")
    req(gate.get("decision") == "defer_frontier_pending_official_product_evidence", "WBA6X defer decision drifted")
    req(gate.get("catalog_admission_ready") is False, "WBA6X unexpectedly admission-ready")
    req(gate.get("representative_results", {}).get("STM32WBA6M", {}).get("error") == "browser navigation returned HTTP 404", "WBA6M blocker drifted")

    wba6 = eligible[0]
    remaining = eligible[1:]
    req([x.get("plasma_series") for x in remaining] == ["STM32WBX", "STM32WBA5X"], "remaining eligible sequence drifted")
    selected = remaining[0]
    req(selected.get("row_count") == 23 and selected.get("subfamily_count") == 8, "STM32WBX sizing drifted")
    req(selected.get("target_configs") == ["tcl/target/stm32wbx.cfg"], "STM32WBX target drifted")
    req(selected.get("identifier_kind_counts") == {"cmsis_device_name": 4, "ordering_pattern": 19}, "STM32WBX identifier mix drifted")

    deferred = list(prior.get("deferred_wireless_frontiers") or [])
    deferred.append({
        **wba6,
        "defer_reasons": ["official_st_evidence_incomplete", "stm32wba6m_product_page_http_404"],
        "evidence_gate": gate["gate_id"],
        "evidence_gate_decision": gate["decision"],
    })
    deferred.sort(key=lambda x: x["plasma_series"])

    return {
        "schema_version": 1,
        "selection_id": "stm32-post-wba6x-evidence-block-wireless-frontier-selection-v1",
        "scope": "wireless_frontier_reselection_research_only",
        "status": "selected_for_bounded_manufacturer_evidence_only",
        "production_boundary": {
            "exact_icpns": 2554,
            "families": 20,
            "frozen_manifest_git_blob_sha": EXPECTED_PRODUCTION_BLOB,
            "published_wireless_families": {"STM32WBA2X": 14, "STM32WLX": 31},
            "standard_nonwireless_frontier_exhausted": True,
        },
        "upstream": {
            "prior_selection_id": prior["selection_id"],
            "prior_selection_git_blob_sha": EXPECTED_PRIOR_BLOB,
            "blocked_frontier": "STM32WBA6X",
            "blocked_evidence_gate_id": gate["gate_id"],
            "blocked_evidence_gate_git_blob_sha": EXPECTED_BLOCK_BLOB,
            "blocked_evidence_decision": gate["decision"],
            "published_wireless_count": 2,
            "remaining_structurally_eligible_count": 2,
            "deferred_wireless_count": 2,
        },
        "selection_policy": prior["selection_policy"],
        "already_published_wireless_frontiers": prior["already_published_wireless_frontiers"],
        "eligible_wireless_frontiers": remaining,
        "deferred_wireless_frontiers": deferred,
        "selected_wireless_frontier": selected["plasma_series"],
        "selected_target_config": selected["target_configs"][0],
        "selected_row_count": selected["row_count"],
        "selected_subfamily_count": selected["subfamily_count"],
        "selected_subfamilies": selected["subfamilies"],
        "selected_identifier_kind_counts": selected["identifier_kind_counts"],
        "selection_basis": [
            "STM32WBA2X and STM32WLX remain published and excluded from remaining frontier selection",
            "STM32WBA6X is deferred because bounded official-ST evidence accessibility is incomplete at STM32WBA6M",
            "STM32WBA6X is deferred, not rejected",
            "STM32WBX is the smallest remaining structurally eligible bounded wireless candidate by the frozen sequencing policy",
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
            "stm32wba6x_rejected": False,
            "stm32wbx_admission_ready": False,
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
