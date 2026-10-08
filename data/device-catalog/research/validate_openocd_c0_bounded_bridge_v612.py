#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import probe_openocd_c0_one_char_generalization_v611 as v611

HERE=Path(__file__).resolve().parent
POLICY=HERE/"openocd-c0-bounded-identifier-bridge-v6.12.json"

EXPECTED={
  "STM32C051K8U3":"STM32C051K8Tx",
  "STM32C051K8U3TR":"STM32C051K8Tx",
  "STM32C051K8U6":"STM32C051K8Tx",
  "STM32C051K8U6TR":"STM32C051K8Tx",
  "STM32C051K8U7":"STM32C051K8Tx",
  "STM32C051K8U7TR":"STM32C051K8Tx",
  "STM32C071FBY6TR":"STM32C071FBPx",
  "STM32C071R8I6N":"STM32C071R8Tx",
  "STM32C071RBI6N":"STM32C071RBTx",
  "STM32C091RBI6":"STM32C091RBTx",
  "STM32C092RBI6":"STM32C092RBTx",
}

def req(ok,msg):
    if not ok:
        raise SystemExit(msg)

def main()->int:
    policy=json.loads(POLICY.read_text(encoding="utf-8"))
    rows,_,summary=v611.build()
    req(summary["unique_under_one_char_generalization_exact_count"]==11,
        "v6.11 unique count drift")
    live={r["icpn"]:r["resolved_identifier"] for r in rows
          if r["probe_state"]=="unique_under_one_char_generalization"}
    req(live==EXPECTED,"v6.11 resolved identifier set drift")
    req(policy["scope"]["exact_icpn_count"]==11,"v6.12 scope count drift")
    req(policy["scope"]["exact_icpns"]==sorted(EXPECTED),"v6.12 exact scope drift")
    req(policy["bridges"]==EXPECTED,"v6.12 bridge mapping drift")
    req(policy["openocd_target_config"]=="tcl/target/stm32c0x.cfg","target config drift")
    req(policy["identifier_kind"]=="ordering_pattern","identifier kind drift")
    gov=policy["governance"]
    req(gov["generic_one_char_generalization_authorized"] is False,
        "generic C0 one-char policy was accidentally authorized")
    req(gov["exact_set_bridge_only"] is True,"bounded bridge scope opened")
    for key in (
      "production_mapping_write_authorized","programming_profile_binding_claimed",
      "programming_verified_claimed","engineering_verified_claimed","hil_verified_claimed"
    ):
      req(gov[key] is False,f"v6.12 overclaim: {key}")
    cov=policy["coverage_projection_if_later_promoted"]
    req(cov["potential_active_openocd_route_exact_count"]==3958,"coverage numerator drift")
    req(cov["remaining_gap"]==592,"remaining gap drift")
    req(cov["potential_coverage_percent"]==86.989,"coverage percent drift")
    print("OPENOCD_C0_BOUNDED_IDENTIFIER_BRIDGE_V612_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
