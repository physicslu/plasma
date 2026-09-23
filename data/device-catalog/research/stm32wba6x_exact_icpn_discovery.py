#!/usr/bin/env python3
"""Bounded official-ST exact ICPN discovery for reconciled STM32WBA6X."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT, STBrowserAcquirer, build_browser_evidence_record
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32_post_u0_evidence_probe import ProbeTarget, RateLimitedFetcher, base_from_ordering_pattern, source_url_for_base

HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE / "openocd-parts-canonical.csv"
SELECTION_PATH = HERE / "stm32-post-wlx-wireless-frontier-selection.json"
RECONCILIATION = HERE / "stm32wba6x-commercial-scope-reconciliation.json"

DISCOVERY_ID = "stm32wba6x-bounded-exact-icpn-discovery-v1"
EXPECTED_SERIES = "STM32WBA6X"
EXPECTED_TARGET_CONFIG = "tcl/target/stm32wba6x.cfg"
EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SUBFAMILIES = ("STM32WBA62","STM32WBA63","STM32WBA64","STM32WBA65")
EXPECTED_BASES = (
    "STM32WBA62CG","STM32WBA62CI","STM32WBA62MG","STM32WBA62MI","STM32WBA62PG","STM32WBA62PI",
    "STM32WBA63CG","STM32WBA63CI",
    "STM32WBA64CG","STM32WBA64CI",
    "STM32WBA65CG","STM32WBA65CI","STM32WBA65MG","STM32WBA65MI","STM32WBA65PG","STM32WBA65PI","STM32WBA65RG","STM32WBA65RI",
)
EXPECTED_BASE_DEVICE_COUNT = 18
MIN_DELAY_SECONDS = 1.0
NEXT_GATE = "stm32wba6x-bounded-exact-icpn-admission-readiness-gate"
EXCLUDED = {("STM32WBA6MOIHx","ordering_pattern")}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def set_sha(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(values)+"\n").encode("utf-8")).hexdigest()

def load_json(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise AcquisitionError(f"{path.name}: expected JSON object")
    return value

def guard_reconciliation() -> dict[str, Any]:
    payload=load_json(RECONCILIATION)
    if payload.get("reconciliation_id")!="stm32wba6x-current-commercial-scope-reconciliation-v1":
        raise AcquisitionError("unexpected STM32WBA6X reconciliation id")
    if payload.get("decision")!="current_commercial_scope_reconciled":
        raise AcquisitionError("STM32WBA6X reconciliation decision drifted")
    if payload.get("evidence_accessibility_ready") is not True:
        raise AcquisitionError("STM32WBA6X evidence accessibility not reopened")
    if payload.get("catalog_admission_ready") is not False:
        raise AcquisitionError("STM32WBA6X reconciliation prematurely admitted catalog")
    surface=payload.get("reconciled_surface")
    if not isinstance(surface,dict):
        raise AcquisitionError("STM32WBA6X reconciled surface missing")
    if (
        surface.get("retained_rows")!=18
        or surface.get("ordering_pattern_rows")!=18
        or surface.get("cmsis_device_name_rows")!=0
        or surface.get("base_device_count")!=18
        or surface.get("subfamily_count")!=4
        or tuple(surface.get("base_devices") or ())!=EXPECTED_BASES
        or tuple(surface.get("subfamilies") or ())!=EXPECTED_SUBFAMILIES
    ):
        raise AcquisitionError("STM32WBA6X reconciled surface drifted")
    if payload.get("next_gate")!="stm32wba6x-bounded-exact-icpn-discovery-gate":
        raise AcquisitionError("STM32WBA6X reconciliation next gate drifted")
    claims=payload.get("claims")
    if not isinstance(claims,dict) or any(v is not False for v in claims.values()):
        raise AcquisitionError("STM32WBA6X reconciliation claims escaped fail-closed state")
    return payload

def reconciled_rows() -> list[dict[str,str]]:
    guard_reconciliation()
    if sha256(SOURCE_PATH)!=EXPECTED_SOURCE_SHA256:
        raise AcquisitionError("frozen candidate source SHA-256 drifted")
    with SOURCE_PATH.open(newline="",encoding="utf-8") as handle:
        rows=[
            row for row in csv.DictReader(handle)
            if row.get("vendor")=="STMicroelectronics"
            and row.get("plasma_series")==EXPECTED_SERIES
            and row.get("target_config")==EXPECTED_TARGET_CONFIG
        ]
    if len(rows)!=19:
        raise AcquisitionError(f"STM32WBA6X source row count drifted: {len(rows)}")
    retained=[
        row for row in rows
        if (row.get("part_number"),row.get("identifier_kind")) not in EXCLUDED
    ]
    if len(retained)!=18:
        raise AcquisitionError(f"STM32WBA6X retained row count drifted: {len(retained)}")
    if any(row.get("identifier_kind")!="ordering_pattern" for row in retained):
        raise AcquisitionError("STM32WBA6X retained identifier-kind surface drifted")
    return retained

def deterministic_targets() -> list[ProbeTarget]:
    rows=reconciled_rows()
    targets:list[ProbeTarget]=[]
    for row in rows:
        base=base_from_ordering_pattern(row)
        url=source_url_for_base(base)
        validate_source_url(url)
        targets.append(ProbeTarget(
            series=EXPECTED_SERIES,
            subfamily=row["subfamily"],
            base_device=base,
            source_url=url,
            selection_reason="unique current-commercial Base Device derived from reconciled STM32WBA6X ordering-pattern row",
        ))
    targets.sort(key=lambda t:t.base_device)
    observed=tuple(t.base_device for t in targets)
    if observed!=EXPECTED_BASES:
        raise AcquisitionError(f"STM32WBA6X deterministic Base Devices drifted: {observed}")
    if len({t.base_device for t in targets})!=EXPECTED_BASE_DEVICE_COUNT:
        raise AcquisitionError("STM32WBA6X deterministic targets are not unique")
    if {t.subfamily for t in targets}!=set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32WBA6X target subfamily coverage drifted")
    return targets

def target_manifest(targets:list[ProbeTarget])->dict[str,Any]:
    return {
        "schema_version":1,
        "discovery_id":DISCOVERY_ID,
        "scope":"bounded exact ICPN discovery from official ST Q&R surfaces",
        "selected_wireless_frontier":EXPECTED_SERIES,
        "target_config":EXPECTED_TARGET_CONFIG,
        "candidate_source_sha256":sha256(SOURCE_PATH),
        "selection_sha256":sha256(SELECTION_PATH),
        "commercial_scope_reconciliation_sha256":sha256(RECONCILIATION),
        "base_device_count":len(targets),
        "targets":[
            {
                "series":t.series,
                "subfamily":t.subfamily,
                "base_device":t.base_device,
                "source_url":t.source_url,
                "selection_reason":t.selection_reason,
            }
            for t in targets
        ],
    }

def claims(*,complete:bool)->dict[str,bool]:
    return {
        "production_write_authorized":False,
        "icpn_admission_authorized":False,
        "exact_icpn_discovery_completed":complete,
        "programming_algorithm_equivalence_claimed":False,
        "runtime_programming_support_claimed":False,
        "wireless_radio_operation_authorized":False,
        "wireless_security_operation_authorized":False,
        "security_mutation_authorized":False,
        "debug_attach_supported":False,
        "target_execution_authorized":False,
        "physical_validation_claimed":False,
        "hil_required_for_catalog_admission":False,
        "remaining_wireless_families_rejected":False,
        "stm32w108_rejected":False,
        "stm32wba6x_admission_ready":False,
        "cmsis_bridge_authorizes_production_route":False,
    }

def run_live(
    targets:list[ProbeTarget], *,
    headless:bool, delay_seconds:float, timeout_seconds:float
)->tuple[dict[str,Any],str|None]:
    if delay_seconds<MIN_DELAY_SECONDS:
        raise AcquisitionError(f"live discovery delay must be at least {MIN_DELAY_SECONDS:.1f}s")
    results:list[dict[str,Any]]=[]
    browser_version:str|None=None
    with STBrowserAcquirer(headless=headless) as browser:
        browser_version=browser.browser_version
        fetcher=RateLimitedFetcher(delay_seconds=delay_seconds,fetcher=browser.fetch)
        for target in targets:
            result:dict[str,Any]={
                "series":target.series,
                "subfamily":target.subfamily,
                "base_device":target.base_device,
                "source_url":target.source_url,
            }
            try:
                body,final_url,etag,last_modified=fetcher(target.source_url,timeout_seconds)
                evidence=build_browser_evidence_record(
                    body=body,source_url=target.source_url,final_url=final_url,
                    base_device=target.base_device,
                    retrieved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
                    http_etag=etag,http_last_modified=last_modified,
                )
                active=evidence.get("exact_icpns")
                excluded=evidence.get("excluded_non_active_part_numbers")
                if not isinstance(active,list) or not all(isinstance(v,str) for v in active):
                    raise AcquisitionError(f"{target.base_device}: exact_icpns must be a string list")
                if not isinstance(excluded,list):
                    raise AcquisitionError(f"{target.base_device}: excluded list missing")
                if any(not v.startswith(target.base_device) for v in active):
                    raise AcquisitionError(f"{target.base_device}: foreign exact ICPN")
                excluded_ids:list[str]=[]
                for item in excluded:
                    if not isinstance(item,dict):
                        raise AcquisitionError(f"{target.base_device}: invalid lifecycle exclusion")
                    icpn=item.get("icpn")
                    status=item.get("marketing_status")
                    if not isinstance(icpn,str) or not icpn.startswith(target.base_device):
                        raise AcquisitionError(f"{target.base_device}: foreign excluded ICPN")
                    if not isinstance(status,str) or not status.strip():
                        raise AcquisitionError(f"{target.base_device}: excluded ICPN lacks Marketing Status")
                    excluded_ids.append(icpn)
                if not active and not excluded_ids:
                    raise AcquisitionError(f"{target.base_device}: no commercial identity disposition")
                result.update(
                    acquisition_status="success",
                    commercial_identity_status="verified_active" if active else "verified_non_active_only",
                    active_exact_icpns=active,
                    excluded_non_active_icpns=excluded_ids,
                    manual_intervention_required=False,
                    evidence=evidence,
                )
            except (AcquisitionError,OSError) as exc:
                result.update(
                    acquisition_status="failure",
                    commercial_identity_status="unverified",
                    active_exact_icpns=[],
                    excluded_non_active_icpns=[],
                    manual_intervention_required=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            results.append(result)

    success=[x for x in results if x.get("acquisition_status")=="success"]
    manual=[x for x in results if x.get("manual_intervention_required") is True]
    active=sorted({
        icpn for x in results
        for icpn in (x.get("active_exact_icpns") or [])
        if isinstance(icpn,str)
    })
    excluded=sorted({
        icpn for x in results
        for icpn in (x.get("excluded_non_active_icpns") or [])
        if isinstance(icpn,str)
    })
    complete=len(success)==EXPECTED_BASE_DEVICE_COUNT and not manual
    summary={
        "schema_version":1,
        "discovery_id":DISCOVERY_ID,
        "scope":"STM32WBA6X bounded official-ST exact ICPN discovery",
        "selected_wireless_frontier":EXPECTED_SERIES,
        "target_config":EXPECTED_TARGET_CONFIG,
        "base_device_count":EXPECTED_BASE_DEVICE_COUNT,
        "attempted_targets":len(results),
        "successful_targets":len(success),
        "manual_review_targets":len(manual),
        "active_exact_icpn_count":len(active),
        "active_exact_icpns":active,
        "active_exact_icpn_set_sha256":set_sha(active),
        "excluded_non_active_part_number_count":len(excluded),
        "excluded_non_active_part_numbers":excluded,
        "bounded_exact_discovery_complete":complete,
        "browser_version":browser_version,
        "status":"discovered" if complete else "blocked_manual_review",
        "next_gate":NEXT_GATE if complete else None,
        "claims":claims(complete=complete),
        "results":results,
    }
    return summary,browser_version

def write_outputs(
    output_dir:Path, manifest:dict[str,Any], summary:dict[str,Any], browser_version:str|None
)->None:
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"targets.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (output_dir/"discovery-summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    exact={
        "schema_version":1,
        "discovery_id":DISCOVERY_ID,
        "exact_icpn_count":summary["active_exact_icpn_count"],
        "exact_icpn_set_sha256":summary["active_exact_icpn_set_sha256"],
        "exact_icpns":summary["active_exact_icpns"],
    }
    (output_dir/"exact-icpns.json").write_text(json.dumps(exact,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for item in summary.get("results",[]):
        if isinstance(item,dict) and isinstance(item.get("evidence"),dict):
            base=str(item["base_device"]).lower()
            (output_dir/f"{base}.json").write_text(json.dumps(item["evidence"],indent=2,sort_keys=True)+"\n",encoding="utf-8")
    provenance={
        "schema_version":1,
        "discovery_id":DISCOVERY_ID,
        "workflow_role":"authoritative_exact_icpn_discovery",
        "source_repository":"physicslu/plasma",
        "executed_git_sha":os.environ.get("GITHUB_SHA"),
        "workflow_run_id":int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None,
        "workflow_run_attempt":int(os.environ["GITHUB_RUN_ATTEMPT"]) if os.environ.get("GITHUB_RUN_ATTEMPT") else None,
        "acquisition_transport":BROWSER_TRANSPORT,
        "browser_version":browser_version,
        "candidate_source_sha256":sha256(SOURCE_PATH),
        "selection_sha256":sha256(SELECTION_PATH),
        "commercial_scope_reconciliation_sha256":sha256(RECONCILIATION),
        "generated_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
    }
    (output_dir/"provenance.json").write_text(json.dumps(provenance,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--headless",action="store_true")
    parser.add_argument("--delay-seconds",type=float,default=1.0)
    parser.add_argument("--timeout-seconds",type=float,default=90.0)
    args=parser.parse_args()
    targets=deterministic_targets()
    manifest=target_manifest(targets)
    summary,browser_version=run_live(
        targets,headless=args.headless,
        delay_seconds=args.delay_seconds,timeout_seconds=args.timeout_seconds,
    )
    write_outputs(args.output_dir,manifest,summary,browser_version)
    if summary.get("bounded_exact_discovery_complete") is not True:
        raise SystemExit("STM32WBA6X exact ICPN discovery requires manual review")

if __name__=="__main__":
    main()
