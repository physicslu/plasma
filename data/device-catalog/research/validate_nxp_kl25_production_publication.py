#!/usr/bin/env python3
"""Fail-closed validation of staged NXP KL25 Production Catalog publication."""
from __future__ import annotations

import json
from pathlib import Path
from publish_nxp_kl25_catalog import MANIFEST,source_entry,render,counts

HERE=Path(__file__).resolve().parent
PROPOSAL=HERE/"nxp-kl25-production-publication-proposal.json"

def req(ok:bool,msg:str)->None:
    if not ok:raise SystemExit(msg)

def main()->int:
    expected_manifest,expected_proposal=render()
    actual_manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual_proposal=json.loads(PROPOSAL.read_text(encoding="utf-8"))
    req(actual_manifest==expected_manifest,"checked-in Production manifest differs from deterministic KL25 poststate")
    req(actual_proposal==expected_proposal,"publication proposal differs from deterministic renderer")
    req(counts(actual_manifest)==(2695,24),"Production poststate count/families drifted")
    nxp=[s for s in actual_manifest["sources"] if s.get("manufacturer")=="NXP"]
    req(nxp==[source_entry()],"NXP KL25 source binding missing or duplicated")
    req(actual_proposal["production_exact_icpns_before"]==2683
        and actual_proposal["production_exact_icpns_after"]==2695
        and actual_proposal["production_family_count_before"]==23
        and actual_proposal["production_family_count_after"]==24,
        "Production transition drifted")
    req(actual_proposal["published_exact_icpns"]==12
        and actual_proposal["published_active_base_devices"]==3,
        "published exact/base count drifted")
    req(actual_proposal["excluded_non_active_part_numbers"]==0,"non-Active lifecycle exclusion drifted")
    req(actual_proposal["route_assignment_kind_counts"]=={"ordering_pattern":12},"route count drifted")
    req(actual_proposal["mapping_status_counts"]=={"deterministic_ordering_pattern":12},"mapping count drifted")
    req(actual_proposal["metadata_exception_count"]==0 and actual_proposal["route_bridge_count"]==0,"admission exception or bridge reopened")
    req(actual_proposal["status"]=="publication_ready_pending_explicit_merge_approval","approval boundary drifted")

    unsafe=[
      "ppu_hil_required_for_catalog_admission",
      "socket_hil_required_for_catalog_admission",
      "physical_programming_success_required_for_catalog_admission",
      "physical_validation_claimed",
      "programming_algorithm_equivalence_claimed",
      "runtime_programming_support_claimed",
      "software_executor_admission_implies_catalog_admission",
      "security_mutation_support_claimed",
      "debug_attach_support_claimed",
      "catalog_membership_authorizes_target_execution",
      "cmsis_bridge_authorizes_production_route",
    ]
    req(all(actual_proposal.get(key) is False for key in unsafe),"an unsafe publication claim was enabled")
    print("NXP KL25 Production publication validation: PASS")
    print("Production 2683/23 -> 2695/24; NXP KL25 Active=12 direct=12 CMSIS bridge=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
