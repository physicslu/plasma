#!/usr/bin/env python3
"""Deterministically select STM32WBA5X after STM32WBX Production publication."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = HERE / "stm32-post-wba6x-blocked-wireless-frontier-selection.json"
PRESTATE = HERE / "stm32-post-wbx-production-prestate.json"

EXPECTED_PRIOR_BLOB = "5bfebad83abc48d5301d89ef1a05892fce2653ca"
EXPECTED_PRODUCTION_BLOB = "6e0fc69bec067259a1c52e150a313591cf4523e8"
SELECTED = "STM32WBA5X"
NEXT_GATE = "stm32wba5x-bounded-official-manufacturer-evidence-accessibility-gate"

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()

def load(path: Path) -> dict[str, Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(v,dict), f"{path.name}: expected object")
    return v

def render() -> dict[str, Any]:
    prior_bytes=PRIOR.read_bytes()
    pre_bytes=PRESTATE.read_bytes()
    req(git_blob(prior_bytes)==EXPECTED_PRIOR_BLOB, "prior selection blob drifted")
    req(git_blob(pre_bytes)==EXPECTED_PRODUCTION_BLOB, "Production prestate blob drifted")
    prior=json.loads(prior_bytes)
    prod=json.loads(pre_bytes)
    sources=prod.get("sources")
    req(isinstance(sources,list), "Production sources missing")
    req(sum(int(s["row_count"]) for s in sources)==2604 and len(sources)==21, "Production boundary drifted")
    req(any(s.get("family")=="STM32WBX" and s.get("row_count")==50 for s in sources), "STM32WBX Production publication missing")

    eligible=prior.get("eligible_wireless_frontiers")
    req(isinstance(eligible,list) and [x.get("plasma_series") for x in eligible]==["STM32WBX","STM32WBA5X"], "prior eligible sequence drifted")
    wbx,wba5=eligible
    req(wba5.get("row_count")==34 and wba5.get("subfamily_count")==5, "STM32WBA5X sizing drifted")
    req(wba5.get("target_configs")==["tcl/target/stm32wba5x.cfg"], "STM32WBA5X target drifted")
    published=[*prior["already_published_wireless_frontiers"], {**wbx, "publication_status":"published_in_production", "production_row_count":50}]
    return {
      "schema_version":1,
      "selection_id":"stm32-post-wbx-wireless-frontier-selection-v1",
      "scope":"wireless_frontier_reselection_research_only",
      "status":"selected_for_bounded_manufacturer_evidence_only",
      "production_boundary":{
        "exact_icpns":2604,"families":21,
        "frozen_manifest_git_blob_sha":EXPECTED_PRODUCTION_BLOB,
        "published_wireless_families":{"STM32WBA2X":14,"STM32WLX":31,"STM32WBX":50},
        "standard_nonwireless_frontier_exhausted":True,
      },
      "upstream":{
        "prior_selection_id":prior["selection_id"],
        "prior_selection_git_blob_sha":EXPECTED_PRIOR_BLOB,
        "published_wireless_count":3,
        "remaining_structurally_eligible_count":1,
        "deferred_wireless_count":2,
        "blocked_frontier":"STM32WBA6X",
        "blocked_evidence_gate_id":"stm32wba6x-bounded-official-st-evidence-accessibility-v1",
        "blocked_evidence_gate_decision":"defer_frontier_pending_official_product_evidence",
        "blocked_evidence_gate_git_blob_sha":"3b30521db5cdf2b7e4348cd4e8ae479ea2d6a8e9",
      },
      "selection_policy":prior["selection_policy"],
      "already_published_wireless_frontiers":published,
      "deferred_wireless_frontiers":prior["deferred_wireless_frontiers"],
      "eligible_wireless_frontiers":[wba5],
      "selected_wireless_frontier":SELECTED,
      "selected_target_config":"tcl/target/stm32wba5x.cfg",
      "selected_row_count":34,
      "selected_subfamily_count":5,
      "selected_subfamilies":["STM32WBA50","STM32WBA52","STM32WBA54","STM32WBA55","STM32WBA5M"],
      "selected_identifier_kind_counts":{"cmsis_device_name":17,"ordering_pattern":17},
      "selection_basis":[
        "STM32WBA2X, STM32WLX, and STM32WBX are already published and excluded from remaining frontier selection",
        "STM32WBA6X remains deferred because bounded official-ST evidence accessibility is incomplete at STM32WBA6M",
        "STM32WBA6X and STM32W108 remain deferred, not rejected",
        "STM32WBA5X is the only remaining structurally eligible bounded wireless candidate under the frozen sequencing policy",
        "selection does not authorize radio, security, debug, programming, HIL, or target execution operations",
      ],
      "next_gate":NEXT_GATE,
      "claims":{
        "debug_attach_supported":False,"exact_icpn_discovery_completed":False,
        "hil_required_for_catalog_admission":False,"icpn_admission_authorized":False,
        "physical_validation_claimed":False,"production_write_authorized":False,
        "programming_algorithm_equivalence_claimed":False,
        "remaining_wireless_families_rejected":False,
        "runtime_programming_support_claimed":False,"security_mutation_authorized":False,
        "stm32w108_rejected":False,"stm32wba6x_rejected":False,
        "stm32wba5x_admission_ready":False,"target_execution_authorized":False,
        "wireless_radio_operation_authorized":False,"wireless_security_operation_authorized":False,
      },
    }

def main() -> int:
    print(json.dumps(render(), indent=2, sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
