#!/usr/bin/env python3
"""Render current STM32 wireless frontier exhaustion state."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PRIOR = HERE / "stm32-post-wbx-wireless-frontier-selection.json"
WBA5_GATE = HERE / "stm32wba5x-evidence-accessibility-gate.json"
WBA6_GATE = HERE / "stm32wba6x-evidence-accessibility-gate.json"
PRESTATE = HERE / "stm32-wireless-frontier-exhaustion-production-prestate.json"

EXPECTED_PRIOR_BLOB = "849488b36d398a7e8f8da83b3aa93fbe320f8dc3"
EXPECTED_WBA5_GATE_BLOB = "26c0d55a4d0e1f85025134b0c9bda38049b5b3a4"
EXPECTED_WBA6_GATE_BLOB = "3b30521db5cdf2b7e4348cd4e8ae479ea2d6a8e9"
EXPECTED_PRODUCTION_BLOB = "6e0fc69bec067259a1c52e150a313591cf4523e8"

REPORT_TEMPLATE = r'''{
  "already_published_wireless_frontiers": [
    {
      "cmsis_device_name_rows": 4,
      "cohort": "wireless_requires_dedicated_scope",
      "complete_mapping_metadata": true,
      "identifier_kind_counts": {
        "cmsis_device_name": 4,
        "ordering_pattern": 4
      },
      "ordering_pattern_rows": 4,
      "plasma_series": "STM32WBA2X",
      "production_row_count": 14,
      "publication_status": "published_in_production",
      "row_count": 8,
      "structural_gate_pass": true,
      "subfamilies": [
        "STM32WBA23",
        "STM32WBA25"
      ],
      "subfamily_count": 2,
      "target_configs": [
        "tcl/target/stm32wba2x.cfg"
      ]
    },
    {
      "cmsis_device_name_rows": 0,
      "cohort": "wireless_requires_dedicated_scope",
      "complete_mapping_metadata": true,
      "identifier_kind_counts": {
        "ordering_pattern": 17
      },
      "ordering_pattern_rows": 17,
      "plasma_series": "STM32WLX",
      "production_row_count": 31,
      "publication_status": "published_in_production",
      "row_count": 17,
      "structural_gate_pass": true,
      "subfamilies": [
        "STM32WL54",
        "STM32WL55",
        "STM32WLE4",
        "STM32WLE5"
      ],
      "subfamily_count": 4,
      "target_configs": [
        "tcl/target/stm32wlx.cfg"
      ]
    },
    {
      "cmsis_device_name_rows": 4,
      "cohort": "wireless_requires_dedicated_scope",
      "complete_mapping_metadata": true,
      "identifier_kind_counts": {
        "cmsis_device_name": 4,
        "ordering_pattern": 19
      },
      "ordering_pattern_rows": 19,
      "plasma_series": "STM32WBX",
      "production_row_count": 50,
      "publication_status": "published_in_production",
      "row_count": 23,
      "structural_gate_pass": true,
      "subfamilies": [
        "STM32WB10",
        "STM32WB15",
        "STM32WB1M",
        "STM32WB30",
        "STM32WB35",
        "STM32WB50",
        "STM32WB55",
        "STM32WB5M"
      ],
      "subfamily_count": 8,
      "target_configs": [
        "tcl/target/stm32wbx.cfg"
      ]
    }
  ],
  "claims": {
    "debug_attach_supported": false,
    "exact_icpn_discovery_completed": false,
    "hil_required_for_catalog_admission": false,
    "icpn_admission_authorized": false,
    "physical_validation_claimed": false,
    "production_write_authorized": false,
    "programming_algorithm_equivalence_claimed": false,
    "remaining_wireless_families_rejected": false,
    "runtime_programming_support_claimed": false,
    "security_mutation_authorized": false,
    "stm32w108_rejected": false,
    "stm32wba5x_rejected": false,
    "stm32wba6x_rejected": false,
    "target_execution_authorized": false,
    "wireless_radio_operation_authorized": false,
    "wireless_security_operation_authorized": false
  },
  "current_blockers": [
    {
      "base_device": "STM32WBA50KE",
      "blocker": "official_st_product_page_http_404",
      "evidence_gate": "stm32wba5x-bounded-official-st-evidence-accessibility-v1",
      "plasma_series": "STM32WBA5X",
      "subfamily": "STM32WBA50"
    },
    {
      "base_device": "STM32WBA6MOI",
      "blocker": "official_st_product_page_http_404",
      "evidence_gate": "stm32wba6x-bounded-official-st-evidence-accessibility-v1",
      "plasma_series": "STM32WBA6X",
      "subfamily": "STM32WBA6M"
    },
    {
      "blocker": "structural_gate_fail",
      "plasma_series": "STM32W108"
    }
  ],
  "deferred_wireless_frontiers": [
    {
      "cmsis_device_name_rows": 1,
      "cohort": "wireless_requires_dedicated_scope",
      "complete_mapping_metadata": true,
      "defer_reasons": [
        "structural_gate_fail",
        "no_bounded_subfamilies",
        "no_ordering_pattern_rows"
      ],
      "identifier_kind_counts": {
        "cmsis_device_name": 1
      },
      "ordering_pattern_rows": 0,
      "plasma_series": "STM32W108",
      "row_count": 1,
      "structural_gate_pass": false,
      "subfamilies": [],
      "subfamily_count": 0,
      "target_configs": [
        "tcl/target/stm32w108xx.cfg"
      ]
    },
    {
      "cmsis_device_name_rows": 0,
      "cohort": "wireless_requires_dedicated_scope",
      "complete_mapping_metadata": true,
      "defer_reasons": [
        "official_st_evidence_incomplete",
        "stm32wba6m_product_page_http_404"
      ],
      "evidence_gate": "stm32wba6x-bounded-official-st-evidence-accessibility-v1",
      "evidence_gate_decision": "defer_frontier_pending_official_product_evidence",
      "identifier_kind_counts": {
        "ordering_pattern": 19
      },
      "ordering_pattern_rows": 19,
      "plasma_series": "STM32WBA6X",
      "row_count": 19,
      "structural_gate_pass": true,
      "subfamilies": [
        "STM32WBA62",
        "STM32WBA63",
        "STM32WBA64",
        "STM32WBA65",
        "STM32WBA6M"
      ],
      "subfamily_count": 5,
      "target_configs": [
        "tcl/target/stm32wba6x.cfg"
      ]
    },
    {
      "cmsis_device_name_rows": 17,
      "cohort": "wireless_requires_dedicated_scope",
      "complete_mapping_metadata": true,
      "defer_reasons": [
        "official_st_evidence_incomplete",
        "stm32wba50ke_product_page_http_404"
      ],
      "evidence_gate": "stm32wba5x-bounded-official-st-evidence-accessibility-v1",
      "evidence_gate_decision": "defer_frontier_pending_official_product_evidence",
      "identifier_kind_counts": {
        "cmsis_device_name": 17,
        "ordering_pattern": 17
      },
      "ordering_pattern_rows": 17,
      "plasma_series": "STM32WBA5X",
      "row_count": 34,
      "structural_gate_pass": true,
      "subfamilies": [
        "STM32WBA50",
        "STM32WBA52",
        "STM32WBA54",
        "STM32WBA55",
        "STM32WBA5M"
      ],
      "subfamily_count": 5,
      "target_configs": [
        "tcl/target/stm32wba5x.cfg"
      ]
    }
  ],
  "eligible_wireless_frontiers": [],
  "next_gate": null,
  "production_boundary": {
    "exact_icpns": 2604,
    "families": 21,
    "frozen_manifest_git_blob_sha": "6e0fc69bec067259a1c52e150a313591cf4523e8",
    "published_wireless_families": {
      "STM32WBA2X": 14,
      "STM32WBX": 50,
      "STM32WLX": 31
    },
    "standard_nonwireless_frontier_exhausted": true
  },
  "report_id": "stm32-wireless-frontier-exhaustion-after-wba5x-block-v1",
  "resume_conditions": [
    "an authoritative official-ST evidence transaction resolves STM32WBA50KE accessibility or formally reclassifies its frozen candidate identity",
    "an authoritative official-ST evidence transaction resolves STM32WBA6MOI accessibility or formally reclassifies its frozen candidate identity",
    "a new wireless frontier enters the canonical inventory and passes structural and evidence eligibility"
  ],
  "schema_version": 1,
  "scope": "wireless_frontier_reselection_research_only",
  "selected_identifier_kind_counts": {},
  "selected_row_count": 0,
  "selected_subfamilies": [],
  "selected_subfamily_count": 0,
  "selected_target_config": null,
  "selected_wireless_frontier": null,
  "selection_policy": {
    "eligibility": [
      "cohort == wireless_requires_dedicated_scope",
      "not already published in Production",
      "structural_gate_pass == true",
      "complete_mapping_metadata == true",
      "exactly one target_config",
      "row_count > 0",
      "subfamily_count > 0",
      "ordering_pattern_rows > 0"
    ],
    "evidence_eligibility": [
      "no unresolved official-ST evidence accessibility blocker"
    ],
    "sequencing": [
      "fewest row_count",
      "then fewest subfamily_count",
      "then lexical plasma_series"
    ],
    "sequencing_only": true
  },
  "status": "no_currently_eligible_wireless_frontier",
  "upstream": {
    "prior_selection_git_blob_sha": "849488b36d398a7e8f8da83b3aa93fbe320f8dc3",
    "prior_selection_id": "stm32-post-wbx-wireless-frontier-selection-v1",
    "wba5x_evidence_decision": "defer_frontier_pending_official_product_evidence",
    "wba5x_evidence_gate_git_blob_sha": "26c0d55a4d0e1f85025134b0c9bda38049b5b3a4",
    "wba5x_evidence_gate_id": "stm32wba5x-bounded-official-st-evidence-accessibility-v1",
    "wba6x_evidence_decision": "defer_frontier_pending_official_product_evidence",
    "wba6x_evidence_gate_git_blob_sha": "3b30521db5cdf2b7e4348cd4e8ae479ea2d6a8e9",
    "wba6x_evidence_gate_id": "stm32wba6x-bounded-official-st-evidence-accessibility-v1"
  }
}'''

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()

def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value

def render() -> dict[str, Any]:
    req(blob(PRIOR) == EXPECTED_PRIOR_BLOB, "prior selection blob drifted")
    req(blob(WBA5_GATE) == EXPECTED_WBA5_GATE_BLOB, "WBA5X evidence gate blob drifted")
    req(blob(WBA6_GATE) == EXPECTED_WBA6_GATE_BLOB, "WBA6X evidence gate blob drifted")
    req(blob(PRESTATE) == EXPECTED_PRODUCTION_BLOB, "Production prestate blob drifted")

    prior = load(PRIOR)
    g5 = load(WBA5_GATE)
    g6 = load(WBA6_GATE)
    prod = load(PRESTATE)

    sources = prod.get("sources")
    req(
        isinstance(sources, list)
        and sum(int(x["row_count"]) for x in sources) == 2604
        and len(sources) == 21,
        "Production boundary drifted",
    )
    req(prior.get("selected_wireless_frontier") == "STM32WBA5X", "prior WBA5X selection drifted")
    eligible = prior.get("eligible_wireless_frontiers")
    req(
        isinstance(eligible, list)
        and len(eligible) == 1
        and eligible[0].get("plasma_series") == "STM32WBA5X",
        "prior eligible surface drifted",
    )
    req(
        g5.get("decision") == "defer_frontier_pending_official_product_evidence"
        and g5.get("catalog_admission_ready") is False,
        "WBA5X block drifted",
    )
    req(
        g6.get("decision") == "defer_frontier_pending_official_product_evidence"
        and g6.get("catalog_admission_ready") is False,
        "WBA6X block drifted",
    )

    wba5 = {
        **eligible[0],
        "defer_reasons": [
            "official_st_evidence_incomplete",
            "stm32wba50ke_product_page_http_404",
        ],
        "evidence_gate": g5["gate_id"],
        "evidence_gate_decision": g5["decision"],
    }

    report = json.loads(REPORT_TEMPLATE)
    report["already_published_wireless_frontiers"] = prior["already_published_wireless_frontiers"]
    report["deferred_wireless_frontiers"] = [*prior["deferred_wireless_frontiers"], wba5]
    report["upstream"]["prior_selection_git_blob_sha"] = EXPECTED_PRIOR_BLOB
    report["upstream"]["wba5x_evidence_gate_git_blob_sha"] = EXPECTED_WBA5_GATE_BLOB
    report["upstream"]["wba6x_evidence_gate_git_blob_sha"] = EXPECTED_WBA6_GATE_BLOB
    report["production_boundary"]["frozen_manifest_git_blob_sha"] = EXPECTED_PRODUCTION_BLOB
    return report

def main() -> int:
    print(json.dumps(render(), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
