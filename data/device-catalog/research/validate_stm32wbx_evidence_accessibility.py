#!/usr/bin/env python3
"""Fail-closed validator for retained STM32WBX official-ST accessibility evidence."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wbx_evidence_accessibility_probe import (
    EXPECTED_SERIES, EXPECTED_SUBFAMILIES, EXPECTED_TARGET_CONFIG, PROBE_ID,
    deterministic_targets, target_manifest,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE_DIR = HERE / "evidence" / "stm32wbx-accessibility-live-2026-09-22"
TARGETS = EVIDENCE_DIR / "targets.json"
SUMMARY = EVIDENCE_DIR / "probe-summary.json"
PROVENANCE = EVIDENCE_DIR / "provenance.json"
GATE = HERE / "stm32wbx-evidence-accessibility-gate.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_BASES = (
    "STM32WB10CC","STM32WB15CC","STM32WB1MMC","STM32WB30CE",
    "STM32WB35CC","STM32WB50CG","STM32WB55CC","STM32WB5MMG",
)
EXPECTED_ACTIVE = {
    "STM32WB10CC":["STM32WB10CCU5"],
    "STM32WB15CC":["STM32WB15CCU6","STM32WB15CCU6E","STM32WB15CCU7","STM32WB15CCU7E","STM32WB15CCY6TR"],
    "STM32WB1MMC":["STM32WB1MMCH6TR"],
    "STM32WB30CE":["STM32WB30CEU5A","STM32WB30CEU5ATR"],
    "STM32WB35CC":["STM32WB35CCU6A","STM32WB35CCU6ATR","STM32WB35CCU7A"],
    "STM32WB50CG":["STM32WB50CGU5"],
    "STM32WB55CC":["STM32WB55CCU6","STM32WB55CCU6TR","STM32WB55CCU7"],
    "STM32WB5MMG":["STM32WB5MMGH6TR"],
}
EXPECTED_SOURCE_SHA256="43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SELECTION_SHA256="6ab706fc91bd2631f66a43f83618a7a66fadc7eaeced6ef0e2fcd05423419768"

def req(ok: bool, message: str) -> None:
    if not ok: raise SystemExit(message)

def load(path: Path) -> dict[str, Any]:
    req(path.is_file(), f"missing retained file: {path}")
    value=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value,dict), f"{path.name}: expected object")
    return value

def main() -> int:
    targets,summary,prov,gate=map(load,(TARGETS,SUMMARY,PROVENANCE,GATE))
    req(targets == target_manifest(deterministic_targets()), "target manifest is not deterministic replay")
    req(targets.get("probe_id")==PROBE_ID and targets.get("target_count")==8, "target manifest identity/count drifted")
    req(targets.get("candidate_source_sha256")==EXPECTED_SOURCE_SHA256, "candidate source digest drifted")
    req(targets.get("selection_sha256")==EXPECTED_SELECTION_SHA256, "selection digest drifted")
    rows=targets.get("targets")
    req(isinstance(rows,list) and tuple(x.get("subfamily") for x in rows)==EXPECTED_SUBFAMILIES, "subfamily target order drifted")
    req(tuple(x.get("base_device") for x in rows)==EXPECTED_BASES, "representative Base Device order drifted")

    req(summary.get("selected_wireless_frontier")==EXPECTED_SERIES, "summary series drifted")
    req(summary.get("target_config")==EXPECTED_TARGET_CONFIG, "summary target drifted")
    req(summary.get("attempted_targets")==8 and summary.get("successful_targets")==8, "not all representative targets succeeded")
    req(summary.get("manual_review_targets")==0, "manual review opened")
    req(summary.get("active_exact_icpns_observed_on_representative_pages")==17, "Active observation count drifted")
    req(summary.get("excluded_non_active_part_numbers_observed")==1, "lifecycle exclusion count drifted")
    req(summary.get("bounded_probe_complete") is True, "bounded probe closed")
    req(summary.get("official_st_evidence_accessible_for_all_subfamilies") is True, "all-subfamily accessibility closed")
    req(summary.get("status")=="accessible", "accessibility status drifted")
    req(summary.get("next_gate")=="stm32wbx-bounded-exact-icpn-discovery-gate", "next gate drifted")
    claims=summary.get("claims")
    req(isinstance(claims,dict) and all(v is False for v in claims.values()), "summary fail-closed claim escaped")
    req(claims.get("stm32wbx_admission_ready") is False, "WBX admission prematurely opened")

    results=summary.get("results")
    req(isinstance(results,list) and len(results)==8, "result cardinality drifted")
    by_base={x.get("base_device"):x for x in results if isinstance(x,dict)}
    req(set(by_base)==set(EXPECTED_BASES), "representative result set drifted")
    for base,exact in EXPECTED_ACTIVE.items():
        row=by_base[base]
        req(row.get("acquisition_status")=="success", f"{base}: acquisition failed")
        req(row.get("manual_intervention_required") is False, f"{base}: manual intervention opened")
        evidence=row.get("evidence")
        req(isinstance(evidence,dict), f"{base}: evidence missing")
        req(evidence.get("acquisition_transport")==BROWSER_TRANSPORT, f"{base}: transport drifted")
        req(evidence.get("exact_icpns")==exact, f"{base}: exact identity set drifted")
        req(load(EVIDENCE_DIR / f"{base.lower()}.json")==evidence, f"{base}: standalone evidence differs")

    excluded=by_base["STM32WB5MMG"]["evidence"].get("excluded_non_active_part_numbers")
    req(isinstance(excluded,list) and len(excluded)==1, "WB5M exclusion count drifted")
    req(excluded[0].get("icpn")=="STM32WB5MMGH6", "WB5M excluded identity drifted")
    req(str(excluded[0].get("marketing_status","")).startswith("Preview"), "WB5M exclusion is no longer Preview")

    req(prov.get("browser_version")=="151.0.7922.34", "browser version drifted")
    req(prov.get("candidate_source_sha256")==EXPECTED_SOURCE_SHA256, "provenance source digest drifted")
    req(prov.get("selection_sha256")==EXPECTED_SELECTION_SHA256, "provenance selection digest drifted")

    req(gate.get("decision")=="accessible_for_bounded_exact_icpn_discovery", "gate decision drifted")
    req(gate.get("catalog_admission_ready") is False, "accessibility gate improperly admitted WBX")
    req(gate.get("next_gate")=="stm32wbx-bounded-exact-icpn-discovery-gate", "gate sequencing drifted")
    bridge=gate.get("cmsis_evidence_bridge") or {}
    req(bridge.get("production_route_authorized") is False, "CMSIS evidence bridge leaked into Production routing")
    req(all(v is False for v in (gate.get("claims") or {}).values()), "gate fail-closed claim escaped")

    production=load(PRODUCTION)
    sources=production.get("sources")
    req(isinstance(sources,list), "Production sources missing")
    req(sum(int(s.get("row_count",0)) for s in sources)==2554, "Production exact count changed")
    req(len(sources)==20, "Production family count changed")
    req(all(s.get("family")!="STM32WBX" for s in sources), "WBX leaked into Production")

    print("STM32WBX bounded official-ST evidence accessibility validation: PASS")
    print("targets=8 active_observed=17 excluded_preview=1 manual_review=0")
    print("Production unchanged at 2554 / 20; next=exact discovery")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
