#!/usr/bin/env python3
"""Validate STM32WBA5X Production publication transaction."""
from __future__ import annotations
import json
from pathlib import Path
from publish_stm32wba5x_catalog import (
    FAMILY,
    EXPECTED_POSTSTATE_EXACT,
    EXPECTED_POSTSTATE_FAMILIES,
    EXPECTED_PRESTATE_EXACT,
    EXPECTED_PRESTATE_FAMILIES,
    PRODUCTION_MANIFEST,
    render,
)

HERE=Path(__file__).resolve().parent
PROPOSAL=HERE/"stm32wba5x-production-publication-proposal.json"

def req(ok: bool,msg: str)->None:
    if not ok: raise SystemExit(msg)

def main()->int:
    expected_manifest,expected_proposal=render()
    checked_manifest=json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    checked_proposal=json.loads(PROPOSAL.read_text(encoding="utf-8"))
    req(checked_manifest==expected_manifest,"checked-in Production manifest differs from deterministic WBA5X poststate")
    req(checked_proposal==expected_proposal,"checked-in publication proposal differs from deterministic renderer")

    sources=checked_manifest.get("sources")
    req(isinstance(sources,list),"Production sources missing")
    wba=[s for s in sources if isinstance(s,dict) and s.get("family")==FAMILY]
    req(len(wba)==1,"WBA5X Production source missing or duplicated")
    req(wba[0]=={
      "manufacturer":"STMicroelectronics",
      "family":"STM32WBA5X",
      "path":"../research/stm32wba5x-commercial-icpn.csv",
      "row_count":40,
      "git_blob_sha":"21cd808371f4d6f05a813e35b06cb1227f96195a",
      "sha256":"653dca4184eab05c3a0c8e6714e73adacf3d6927310855faf064b7d8d0b322d6",
    },"WBA5X source binding drifted")
    req(sum(int(s["row_count"]) for s in sources)==EXPECTED_POSTSTATE_EXACT==2644,"Production exact poststate drifted")
    req(len(sources)==EXPECTED_POSTSTATE_FAMILIES==22,"Production family poststate drifted")

    req(checked_proposal.get("production_exact_icpns_before")==EXPECTED_PRESTATE_EXACT==2604,"prestate exact count drifted")
    req(checked_proposal.get("production_exact_icpns_after")==EXPECTED_POSTSTATE_EXACT,"poststate exact count drifted")
    req(checked_proposal.get("production_family_count_before")==EXPECTED_PRESTATE_FAMILIES==21,"prestate family count drifted")
    req(checked_proposal.get("production_family_count_after")==EXPECTED_POSTSTATE_FAMILIES,"poststate family count drifted")
    req(checked_proposal.get("published_exact_icpns")==40,"published count drifted")
    req(checked_proposal.get("published_active_base_devices")==15,"Base Device count drifted")
    req(checked_proposal.get("route_assignment_kind_counts")=={"ordering_pattern":40},"route counts drifted")
    req(checked_proposal.get("mapping_status_counts")=={"deterministic_ordering_pattern":40},"mapping counts drifted")
    req(checked_proposal.get("route_bridge_count")==0,"route bridge unexpectedly opened")
    req(checked_proposal.get("metadata_exception_count")==0,"metadata exception opened")
    req(checked_proposal.get("excluded_non_active_part_numbers")==0,"non-Active exclusion count drifted")

    for key in (
      "ppu_hil_required_for_catalog_admission",
      "socket_hil_required_for_catalog_admission",
      "physical_programming_success_required_for_catalog_admission",
      "physical_validation_claimed",
      "programming_algorithm_equivalence_claimed",
      "runtime_programming_support_claimed",
      "wireless_radio_operation_authorized",
      "wireless_security_operation_authorized",
      "security_mutation_support_claimed",
      "debug_attach_support_claimed",
      "catalog_membership_authorizes_target_execution",
      "remaining_wireless_families_rejected",
      "stm32wba6x_rejected",
      "cmsis_bridge_authorizes_production_route",
    ):
      req(checked_proposal.get(key) is False,f"unsafe publication claim enabled: {key}")

    print("STM32WBA5X Production publication validation: PASS")
    print("Production 2604/21 -> 2644/22; published=40; direct=40; bridge=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
