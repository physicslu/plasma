#!/usr/bin/env python3
"""Fail-closed validation for the post-STM32 bounded NXP KL25 pilot."""
from __future__ import annotations

import json
from pathlib import Path
from select_post_stm32_vendor_pilot import render

HERE = Path(__file__).resolve().parent
RECORD = HERE / "post-stm32-cross-vendor-pilot-selection.json"

def main() -> int:
    expected = render()
    actual = json.loads(RECORD.read_text(encoding="utf-8"))
    if actual != expected:
        raise SystemExit("Post-STM32 pilot does not match deterministic rendered inputs.")
    if actual["selected"]["reviewed_exact_representative"] != "MKL25Z128VLK4":
        raise SystemExit("NXP exact pilot exemplar drifted")
    if actual["next_gate"] != "nxp-kl25-bounded-official-manufacturer-current-commercial-evidence-accessibility-gate":
        raise SystemExit("NXP official evidence gate drifted")
    if not actual["policy"]["not_a_global_vendor_ranking"]:
        raise SystemExit("Pilot incorrectly claims global prioritization")
    if any(value is not False for value in actual["claims"].values()):
        raise SystemExit("Pilot escaped fail-closed trust boundary")
    if actual["selected"]["current_public_product_reference"]["retained_live_acquisition_completed"] is not False:
        raise SystemExit("Pilot prematurely claims live acquisition")
    print("Post-STM32 NXP KL25 cross-vendor selection: PASS")
    print("Production=2683/23; KL25 patterns=3; exact exemplar=MKL25Z128VLK4")
    print("STM32W108=deferred; next=manufacturer evidence accessibility")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
