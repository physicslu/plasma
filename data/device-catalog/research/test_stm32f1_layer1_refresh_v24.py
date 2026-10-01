#!/usr/bin/env python3
from stm32f1_layer1_refresh_v24 import build

def main()->int:
    proposal,summary=build()
    assert len(proposal)==205
    assert summary["proposal_unique_base_device_count"]==77
    assert summary["backend_state_counts"]=={"mapping_candidate":205,"no_mapping":0}
    assert summary["backend_mapping_kind"]=="cmsis_device_name"
    assert summary["programming_profile_binding_claimed"] is False
    assert summary["programming_profile_scope_expanded"] is False
    assert summary["metadata_exception_exact_icpns"]==["STM32F101RBH6"]
    assert summary["production_f1_exact_after_if_approved"]==280
    assert summary["production_write_authorized"] is False

    by={r["icpn"]:r for r in proposal}
    assert by["STM32F100C4T6B"]["option_suffix"]=="B"
    assert by["STM32F100R4H6B"]["package"]=="TFBGA"
    assert by["STM32F101RBH6"]["package"]=="TFBGA"
    assert by["STM32F101RBH6"]["metadata_exception"]=="F101_RBH6_TFBGA64_ORDERING_TABLE_OMISSION"
    assert by["STM32F103V8H6"]["package"]=="LFBGA"
    assert by["STM32F103RDY6TR"]["package"]=="WLCSP64"
    assert by["STM32F103ZGH6"]["flash_size"]=="1024 KiB"
    assert all(r["backend_mapping_state"]=="mapping_candidate" for r in proposal)
    assert all(r["existing_identifier"]==r["base_device"] for r in proposal)
    assert all(r["existing_identifier_kind"]=="cmsis_device_name" for r in proposal)
    assert all(r["programming_profile_state"]=="unresolved_no_new_applicability_binding" for r in proposal)
    print("STM32F1 Layer-1 refresh v2.4 tests: PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
