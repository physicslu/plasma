#!/usr/bin/env python3
"""Validate STM32WBA6X Production publication transaction."""
from __future__ import annotations
import json
from pathlib import Path
from publish_stm32wba6x_catalog import (
    FAMILY,
    EXPECTED_POSTSTATE_EXACT,
    EXPECTED_POSTSTATE_FAMILIES,
    EXPECTED_PRESTATE_EXACT,
    EXPECTED_PRESTATE_FAMILIES,
    PRODUCTION_MANIFEST,
    render,
)

HERE=Path(__file__).resolve().parent
PROPOSAL=HERE/"stm32wba6x-production-publication-proposal.json"

def req(ok: bool,msg: str)->None:
    if not ok: raise SystemExit(msg)

def main()->int:
    expected_manifest,expected_proposal=render()
    checked_manifest=json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    checked_proposal=json.loads(PROPOSAL.read_text(encoding="utf-8"))
    req(checked_manifest==expected_manifest,"checked-in Production manifest differs from deterministic WBA6X poststate")
    req(checked_proposal==expected_proposal,"checked-in publication proposal differs from deterministic renderer")

    sources=checked_manifest.get("sources")
    req(isinstance(sources,list),"Production sources missing")
    wba=[s for s in sources if isinstance(s,dict) and s.get("family")==FAMILY]
    req(len(wba)==1,"WBA6X Production source missing or duplicated")
    req(wba[0]=={
      "manufacturer":"STMicroelectronics",
      "family":"STM32WBA6X",
      "path":"../research/stm32wba6x-commercial-icpn.csv",
      "row_count":39,
      "git_blob_sha":"0ab09918b2d845c0f21f10c5edb4a150d0c8c4f5",
      "sha256":"87e5bde7efc3fd3aee7397a80e9f4f972eb5ff42370b8d54cf1a333b3252004d",
    },"WBA6X source binding drifted")
    req(sum(int(s["row_count"]) for s in sources)==EXPECTED_POSTSTATE_EXACT==2683,"Production exact poststate drifted")
    req(len(sources)==EXPECTED_POSTSTATE_FAMILIES==23,"Production family poststate drifted")

    req(checked_proposal.get("production_exact_icpns_before")==EXPECTED_PRESTATE_EXACT==2644,"prestate exact count drifted")
    req(checked_proposal.get("production_exact_icpns_after")==EXPECTED_POSTSTATE_EXACT,"poststate exact count drifted")
    req(checked_proposal.get("production_family_count_before")==EXPECTED_PRESTATE_FAMILIES==22,"prestate family count drifted")
    req(checked_proposal.get("production_family_count_after")==EXPECTED_POSTSTATE_FAMILIES,"poststate family count drifted")
    req(checked_proposal.get("published_exact_icpns")==39,"published count drifted")
    req(checked_proposal.get("published_active_base_devices")==18,"Base Device count drifted")
    req(checked_proposal.get("route_assignment_kind_counts")=={"ordering_pattern":39},"route counts drifted")
    req(checked_proposal.get("mapping_status_counts")=={"deterministic_ordering_pattern":39},"mapping counts drifted")
    req(checked_proposal.get("route_bridge_count")==0,"route bridge unexpectedly opened")
    req(checked_proposal.get("metadata_exception_count")==0,"metadata exception opened")
    req(checked_proposal.get("excluded_non_active_part_numbers")==2,"non-Active exclusion count drifted")
    req(checked_proposal.get("excluded_non_active_identities")==["STM32WBA63CGU6TR","STM32WBA65MGF6"],"excluded identity set drifted")

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
      "stm32w108_rejected",
      "cmsis_bridge_authorizes_production_route",
    ):
      req(checked_proposal.get(key) is False,f"unsafe publication claim enabled: {key}")

    print("STM32WBA6X Production publication validation: PASS")
    print("Production 2644/22 -> 2683/23; published=39; direct=39; bridge=0")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
