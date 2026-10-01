#!/usr/bin/env python3
from __future__ import annotations

from stm32g4_layer1_refresh_v20 import (
    EXPECTED_GAP_SHA256,
    EXPECTED_NO_MAPPING,
    build,
)

def main() -> int:
    proposal,summary=build()
    assert len(proposal)==248
    assert summary["proposal_exact_set_sha256"]==EXPECTED_GAP_SHA256
    assert summary["backend_state_counts"]=={"mapping_candidate":247,"no_mapping":1}
    assert set(summary["no_mapping_exact_icpns"])==EXPECTED_NO_MAPPING
    assert summary["metadata_exception_exact_icpns"]==["STM32G484PEI6"]
    assert summary["production_write_authorized"] is False
    assert summary["engineering_verified_claimed"] is False
    assert summary["field_evidence_claimed"] is False
    assert summary["ps_hil_claimed"] is False

    by={row["icpn"]:row for row in proposal}
    assert by["STM32G484PEI6"]["package"]=="UFBGA"
    assert by["STM32G484PEI6"]["pin_count"]=="121"
    assert by["STM32G484PEI6"]["metadata_exception"]=="G484_UFBGA121_ORDERING_TABLE_OMISSION"
    assert by["STM32G491RCY6TR"]["backend_mapping_state"]=="no_mapping"
    assert by["STM32G491RCY6TR"]["openocd_target_config"]==""
    assert all(
        row["backend_mapping_state"]=="mapping_candidate"
        for icpn,row in by.items() if icpn!="STM32G491RCY6TR"
    )
    print("STM32G4 Layer-1 refresh v2.0 tests: PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
