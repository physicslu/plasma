#!/usr/bin/env python3
"""Reconcile STM32WBA6X research identifiers with current official commercial scope."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from stm32_post_u0_evidence_probe import base_from_ordering_pattern

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE / "openocd-parts-canonical.csv"
BLOCK_GATE = HERE / "stm32wba6x-evidence-accessibility-gate.json"
SUMMARY = HERE / "evidence/stm32wba6x-accessibility-live-2026-09-22/probe-summary.json"
TARGETS = HERE / "evidence/stm32wba6x-accessibility-live-2026-09-22/targets.json"
PROVENANCE = HERE / "evidence/stm32wba6x-accessibility-live-2026-09-22/provenance.json"
PRESTATE = HERE / "stm32wba6x-commercial-scope-production-prestate.json"

EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_BLOCK_GATE_BLOB = "3b30521db5cdf2b7e4348cd4e8ae479ea2d6a8e9"
EXPECTED_SUMMARY_BLOB = "a21bda977a6b1ca9e2069a579f1968e8eb6e1acc"
EXPECTED_TARGETS_BLOB = "628141e5175bacad44e70d6e04db2dffebce4d5a"
EXPECTED_PROVENANCE_BLOB = "3575323db9110ac23e5d4aa123244a875bc2feff"
EXPECTED_PRODUCTION_BLOB = "5ddd901e6827a6c0a7f7fd2b0286c79411965777"
EXCLUDED = {("STM32WBA6MOIHx", "ordering_pattern")}
EXPECTED_BASES = (
    "STM32WBA62CG","STM32WBA62CI","STM32WBA62MG","STM32WBA62MI","STM32WBA62PG","STM32WBA62PI",
    "STM32WBA63CG","STM32WBA63CI",
    "STM32WBA64CG","STM32WBA64CI",
    "STM32WBA65CG","STM32WBA65CI","STM32WBA65MG","STM32WBA65MI","STM32WBA65PG","STM32WBA65PI","STM32WBA65RG","STM32WBA65RI",
)
EXPECTED_SUBFAMILIES = ("STM32WBA62","STM32WBA63","STM32WBA64","STM32WBA65")

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git_blob_sha(path: Path) -> str:
    data=path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data,usedforsecurity=False).hexdigest()

def load_json(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value,dict),f"{path.name}: expected object")
    return value

def render() -> dict[str, Any]:
    req(sha256(SOURCE)==EXPECTED_SOURCE_SHA256,"candidate source digest drifted")
    req(git_blob_sha(BLOCK_GATE)==EXPECTED_BLOCK_GATE_BLOB,"blocked gate blob drifted")
    req(git_blob_sha(SUMMARY)==EXPECTED_SUMMARY_BLOB,"summary blob drifted")
    req(git_blob_sha(TARGETS)==EXPECTED_TARGETS_BLOB,"targets blob drifted")
    req(git_blob_sha(PROVENANCE)==EXPECTED_PROVENANCE_BLOB,"provenance blob drifted")
    req(git_blob_sha(PRESTATE)==EXPECTED_PRODUCTION_BLOB,"Production prestate blob drifted")

    gate=load_json(BLOCK_GATE)
    req(gate.get("decision")=="defer_frontier_pending_official_product_evidence","blocked gate decision drifted")
    req(gate.get("family")=="STM32WBA6X","blocked gate family drifted")
    req(gate.get("catalog_admission_ready") is False,"blocked gate prematurely admitted catalog")

    summary=load_json(SUMMARY)
    req(summary.get("status")=="blocked_manual_review","retained blocker status drifted")
    req(summary.get("attempted_targets")==5 and summary.get("successful_targets")==4 and summary.get("manual_review_targets")==1,"retained accessibility counts drifted")
    results=summary.get("results")
    req(isinstance(results,list) and len(results)==5,"retained accessibility results drifted")
    observed={row.get("base_device"):row for row in results if isinstance(row,dict)}
    failed=observed.get("STM32WBA6MOI") or {}
    req(
        failed.get("acquisition_status")=="failure"
        and failed.get("error")=="browser navigation returned HTTP 404"
        and failed.get("manual_intervention_required") is True,
        "retained STM32WBA6MOI blocker drifted",
    )
    for base in ("STM32WBA62CG","STM32WBA63CG","STM32WBA64CG","STM32WBA65CG"):
        row=observed.get(base) or {}
        req(row.get("acquisition_status")=="success" and row.get("commercial_identity_status")=="verified_active",f"{base}: retained representative accessibility drifted")

    targets=load_json(TARGETS)
    req(targets.get("target_count")==5,"retained target count drifted")
    req(any(x.get("base_device")=="STM32WBA6MOI" for x in targets.get("targets",[]) if isinstance(x,dict)),"retained STM32WBA6MOI target missing")

    provenance=load_json(PROVENANCE)
    req(provenance.get("probe_id")=="stm32wba6x-bounded-official-st-evidence-accessibility-v1","retained provenance probe id drifted")
    req(provenance.get("browser_version")=="151.0.7922.34","retained browser version drifted")
    req(provenance.get("candidate_source_sha256")==EXPECTED_SOURCE_SHA256,"retained provenance source digest drifted")
    req(provenance.get("selection_sha256")=="6243c80f97b2c159bc964935fc2f87371a596ee9f2d2e397e1c7ee9c3b6a178d","retained provenance selection digest drifted")
    live=gate.get("live_acquisition") or {}
    req(live.get("workflow_run_id")==35694311469,"retained workflow run drifted")
    req(live.get("executed_head")=="3982be122a43be062054f0be25f6f897e3b2a498","retained executed head drifted")
    req(live.get("artifact_id")==10680295411,"retained artifact id drifted")

    prod=load_json(PRESTATE)
    sources=prod.get("sources")
    req(isinstance(sources,list) and sum(int(x["row_count"]) for x in sources)==2644 and len(sources)==22,"Production boundary drifted")
    req(all(x.get("family")!="STM32WBA6X" for x in sources),"STM32WBA6X unexpectedly in Production")

    with SOURCE.open(newline="",encoding="utf-8") as handle:
        rows=[
            row for row in csv.DictReader(handle)
            if row.get("vendor")=="STMicroelectronics" and row.get("plasma_series")=="STM32WBA6X"
        ]
    req(len(rows)==19,"STM32WBA6X source row count drifted")
    req(Counter(row["identifier_kind"] for row in rows)==Counter({"ordering_pattern":19}),"source identifier mix drifted")
    found={(row["part_number"],row["identifier_kind"]) for row in rows if (row["part_number"],row["identifier_kind"]) in EXCLUDED}
    req(found==EXCLUDED,"expected STM32WBA6M research candidate missing")
    retained=[row for row in rows if (row["part_number"],row["identifier_kind"]) not in EXCLUDED]
    req(len(retained)==18,"reconciled retained row count drifted")
    req(Counter(row["identifier_kind"] for row in retained)==Counter({"ordering_pattern":18}),"reconciled identifier mix drifted")
    bases=tuple(sorted(base_from_ordering_pattern(row) for row in retained))
    req(bases==EXPECTED_BASES,f"reconciled Base Device set drifted: {bases}")
    subfamilies=tuple(sorted({row["subfamily"] for row in retained}))
    req(subfamilies==EXPECTED_SUBFAMILIES,f"reconciled subfamily set drifted: {subfamilies}")

    return json.loads(r'''{
  "catalog_admission_ready": false,
  "claims": {
    "debug_attach_supported": false,
    "excluded_candidate_never_existed": false,
    "full_exact_icpn_discovery_completed": false,
    "hil_required_for_catalog_admission": false,
    "icpn_admission_authorized": false,
    "physical_validation_claimed": false,
    "production_write_authorized": false,
    "programming_algorithm_equivalence_claimed": false,
    "remaining_wireless_families_rejected": false,
    "runtime_programming_support_claimed": false,
    "security_mutation_authorized": false,
    "stm32w108_rejected": false,
    "stm32wba6x_admission_ready": false,
    "target_execution_authorized": false,
    "wireless_radio_operation_authorized": false,
    "wireless_security_operation_authorized": false
  },
  "decision": "current_commercial_scope_reconciled",
  "evidence_accessibility_ready": true,
  "excluded_research_candidates": [
    {
      "base_device": "STM32WBA6MOI",
      "identifier_kind": "ordering_pattern",
      "part_number": "STM32WBA6MOIHx",
      "reason": "current_official_st_wba6x_product_portfolio_omits_wba6m_and_canonical_product_url_returns_http_404",
      "subfamily": "STM32WBA6M"
    }
  ],
  "family": "STM32WBA6X",
  "manufacturer": "STMicroelectronics",
  "next_gate": "stm32wba6x-bounded-exact-icpn-discovery-gate",
  "official_manufacturer_evidence": {
    "absent_candidate_subfamily": "STM32WBA6M",
    "blocked_live_result": "browser navigation returned HTTP 404",
    "blocked_product_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32wba6moi.html",
    "current_product_subfamilies": [
      "STM32WBA62",
      "STM32WBA63",
      "STM32WBA64",
      "STM32WBA65"
    ],
    "interpretation": "current-commercial scope excludes STM32WBA6M; historical existence is not denied",
    "observed_at": "2026-09-23",
    "product_portfolio_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32wba6x/products.html"
  },
  "production_boundary": {
    "exact_icpns": 2644,
    "families": 22,
    "frozen_manifest_git_blob_sha": "5ddd901e6827a6c0a7f7fd2b0286c79411965777",
    "wba6x_published": false
  },
  "reconciled_surface": {
    "base_device_count": 18,
    "base_devices": [
      "STM32WBA62CG",
      "STM32WBA62CI",
      "STM32WBA62MG",
      "STM32WBA62MI",
      "STM32WBA62PG",
      "STM32WBA62PI",
      "STM32WBA63CG",
      "STM32WBA63CI",
      "STM32WBA64CG",
      "STM32WBA64CI",
      "STM32WBA65CG",
      "STM32WBA65CI",
      "STM32WBA65MG",
      "STM32WBA65MI",
      "STM32WBA65PG",
      "STM32WBA65PI",
      "STM32WBA65RG",
      "STM32WBA65RI"
    ],
    "cmsis_device_name_rows": 0,
    "ordering_pattern_rows": 18,
    "retained_rows": 18,
    "subfamilies": [
      "STM32WBA62",
      "STM32WBA63",
      "STM32WBA64",
      "STM32WBA65"
    ],
    "subfamily_count": 4
  },
  "reconciliation_id": "stm32wba6x-current-commercial-scope-reconciliation-v1",
  "retained_accessibility_evidence": {
    "manual_review_count_after_reconciliation": 0,
    "retained_active_exact_icpns_observed": 7,
    "retained_non_active_exclusions_observed": 1,
    "successful_representative_count": 4,
    "successful_subfamilies": [
      "STM32WBA62",
      "STM32WBA63",
      "STM32WBA64",
      "STM32WBA65"
    ]
  },
  "schema_version": 1,
  "scope": "research_only",
  "source_surface": {
    "cmsis_device_name_rows": 0,
    "ordering_pattern_rows": 19,
    "source_rows": 19,
    "source_sha256": "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3",
    "subfamilies": [
      "STM32WBA62",
      "STM32WBA63",
      "STM32WBA64",
      "STM32WBA65",
      "STM32WBA6M"
    ]
  },
  "upstream": {
    "blocked_decision": "defer_frontier_pending_official_product_evidence",
    "blocked_gate_git_blob_sha": "3b30521db5cdf2b7e4348cd4e8ae479ea2d6a8e9",
    "blocked_gate_id": "stm32wba6x-bounded-official-st-evidence-accessibility-v1",
    "probe_summary_git_blob_sha": "a21bda977a6b1ca9e2069a579f1968e8eb6e1acc",
    "provenance_git_blob_sha": "3575323db9110ac23e5d4aa123244a875bc2feff",
    "targets_git_blob_sha": "628141e5175bacad44e70d6e04db2dffebce4d5a"
  }
}''')

def main() -> int:
    print(json.dumps(render(),indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
