#!/usr/bin/env python3
from stm32f0_layer1_refresh_v22 import build

def main()->int:
    proposal,summary=build()
    assert len(proposal)==221
    assert summary["proposal_unique_base_device_count"]==60
    assert summary["backend_state_counts"]=={"mapping_candidate":221}
    assert summary["production_write_authorized"] is False
    assert summary["engineering_verified_claimed"] is False
    assert summary["field_evidence_claimed"] is False
    assert summary["ps_hil_claimed"] is False
    by={r["icpn"]:r for r in proposal}
    assert by["STM32F031E6Y6TR"]["package"]=="WLCSP"
    assert by["STM32F031E6Y6TR"]["pin_count"]=="25"
    assert by["STM32F042T6Y6TR"]["pin_count"]=="36"
    assert by["STM32F071CBY6TR"]["pin_count"]=="49"
    assert by["STM32F072CBY7TR"]["pin_count"]=="49"
    assert by["STM32F091RCY6TR"]["pin_count"]=="64"
    assert all(r["backend_mapping_state"]=="mapping_candidate" for r in proposal)
    assert all(r["openocd_target_config"]=="tcl/target/stm32f0x.cfg" for r in proposal)
    print("STM32F0 Layer-1 refresh v2.2 tests: PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
