#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import classify_stm32g0_active_gap_v15 as triage

HERE=Path(__file__).resolve().parent
LOCK=HERE/"stm32g0-active-gap-triage-v1.5.json"

def main():
    frozen=json.loads(LOCK.read_text(encoding="utf-8"))
    live=triage.classify()
    if live != frozen:
        raise SystemExit("STM32G0 v1.5 triage lock drifted")
    print("STM32G0_ACTIVE_GAP_TRIAGE_V15_LOCK_PASS")
    print("gap=359 new_base_exact=357 new_bases=87 existing_base_exact=2")
    print("route_unique=317 route_unmapped=42")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
