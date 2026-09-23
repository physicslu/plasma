#!/usr/bin/env python3
"""Validate STM32WBA6X current commercial-scope reconciliation."""
from __future__ import annotations

import json
from pathlib import Path

from stm32wba6x_commercial_scope_reconciliation import render

HERE=Path(__file__).resolve().parent
OUT=HERE/"stm32wba6x-commercial-scope-reconciliation.json"

def req(ok: bool,msg: str)->None:
    if not ok: raise SystemExit(msg)

def main()->int:
    checked=json.loads(OUT.read_text(encoding="utf-8"))
    expected=render()
    req(checked==expected,"checked-in reconciliation differs from deterministic renderer")
    req(checked.get("decision")=="current_commercial_scope_reconciled","decision drifted")
    req(checked.get("evidence_accessibility_ready") is True,"accessibility not reopened")
    req(checked.get("catalog_admission_ready") is False,"catalog prematurely admitted")

    source=checked.get("source_surface") or {}
    reconciled=checked.get("reconciled_surface") or {}
    req(source.get("source_rows")==19 and source.get("ordering_pattern_rows")==19,"source surface drifted")
    req(reconciled.get("retained_rows")==18,"retained row count drifted")
    req(reconciled.get("ordering_pattern_rows")==18,"retained ordering count drifted")
    req(reconciled.get("cmsis_device_name_rows")==0,"unexpected CMSIS rows")
    req(reconciled.get("base_device_count")==18,"Base Device count drifted")
    req(reconciled.get("subfamily_count")==4,"subfamily count drifted")
    req(reconciled.get("subfamilies")==["STM32WBA62","STM32WBA63","STM32WBA64","STM32WBA65"],"subfamily set drifted")
    req("STM32WBA6MOI" not in reconciled.get("base_devices",[]),"STM32WBA6MOI leaked into current-commercial scope")

    excluded=checked.get("excluded_research_candidates")
    req(isinstance(excluded,list) and [(x.get("part_number"),x.get("identifier_kind")) for x in excluded]==[("STM32WBA6MOIHx","ordering_pattern")],"excluded candidate drifted")

    evidence=checked.get("official_manufacturer_evidence") or {}
    req(evidence.get("absent_candidate_subfamily")=="STM32WBA6M","official portfolio evidence drifted")
    req(evidence.get("blocked_live_result")=="browser navigation returned HTTP 404","blocked live result drifted")

    retained=checked.get("retained_accessibility_evidence") or {}
    req(retained.get("successful_representative_count")==4,"retained representative count drifted")
    req(retained.get("manual_review_count_after_reconciliation")==0,"manual review remains after reconciliation")

    req(checked.get("next_gate")=="stm32wba6x-bounded-exact-icpn-discovery-gate","exact discovery gate not opened")
    claims=checked.get("claims") or {}
    req(claims and all(v is False for v in claims.values()),"fail-closed claim escaped")

    print("STM32WBA6X current commercial-scope reconciliation: PASS")
    print("source=19 retained=18 excluded=1 bases=18 subfamilies=4")
    print("excluded=STM32WBA6MOIHx next=exact-discovery")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
