#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32U0 Phase U0.2 evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    validate_core_provenance,
    validate_manifest,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32u0-phase-u0.2-discovery-baseline.json"
DISCOVERY = HERE / "stm32u0-phase-u0.2-discovery-manifest.json"
U0_1_BASELINE = HERE / "stm32u0-phase-u0.1-foundation-baseline.json"
EVIDENCE = HERE / "evidence/stm32u0-u0.2-official-st-discovery-live-2026-09-11"
TARGETS = EVIDENCE / "targets.csv"

EXPECTED_EVIDENCE_ID = "stm32u0-u0.2-official-st-discovery-2026-09-11-retained-20260911T002533Z-80a6312e"
EXPECTED_BASELINE_SHA = "3583553d75d204ccf684544ba6622c913690d2eacf059c27f9b5d88be9ddc0b1"
EXPECTED_SUMMARY_SHA = "81a5d6b5dbbb141e840cff8bc38e8c664d785a6568ae565fa676c559181c876c"
EXPECTED_PROVENANCE_SHA = "36a9806019e82bcd26ccfd3e4969a9c539b2f03848e31a7a1b20fad184abf3e8"
EXPECTED_MANIFEST_SHA = "3e71f5bd646f7074f2705113190cdc06ac007fd19f4fd838183d0585816aeba7"
EXPECTED_README_SHA = "c710f1e562375c6f46076d01b3b3f745a71fd9162d5ce9356130d41c3fc7af54"
EXPECTED_TARGETS_SHA = "4133860a090b1c5cc01449041fb49e0b5dd60d686e1338a343f8ea18d577e2e0"
EXPECTED_LIVE_SHA = "10adcbb137842a7d9e4ead7fc1007ba25284b84c8e5aba1c76de76772e1a948a"
EXPECTED_PR_HEAD = "d08b4fe2d6b9de772204e9530af5410f71351f18"
EXPECTED_EXEC_SHA = "80a6312e04db2876ff68f64125b99dda11b53691"
EXPECTED_RUN = 34545996184
EXPECTED_ARTIFACT = 10179167672
EXPECTED_ARTIFACT_SHA = "2296dca761deaee6a72895bf9ba489fb70295d11654a7c69df339b91a9ea995a"

EXPECTED_AGG = {
    "acquisition_failure": 0,
    "acquisition_success": 26,
    "active_candidate_targets": 26,
    "active_exact_icpn_candidates": 68,
    "attempted": 26,
    "bounded_discovery_clean": True,
    "commercial_identity_clean": True,
    "commercial_identity_unresolved_targets": 0,
    "commercial_identity_verified_targets": 26,
    "dispositioned_targets": 26,
    "excluded_non_active_part_numbers": 0,
    "identity_manual_intervention_required": 0,
    "lifecycle_excluded_targets": 0,
    "openocd_routing": {
        "ambiguous": 0,
        "gates_commercial_identity": False,
        "not_applicable": 0,
        "unique": 26,
        "unmapped": 0,
    },
    "routing_followup_required": 0,
    "source_unavailable_exclusions": 0,
}

EXPECTED_BINDINGS = {
    "browser_acquisition_git_blob_sha": "925b6d3044584302c2b3c88d1fde382c34cd67fb",
    "discovery_manifest_git_blob_sha": "a0643d5d0103969d7ea835859bac5fc93aac27d5",
    "discovery_script_git_blob_sha": "39d202da027be6299ca4d84fa2fee6838a4476ff",
    "evidence_adapter_git_blob_sha": "ca23a1b3079f52499611dee7ae20f7c2af857150",
    "live_workflow_git_blob_sha": "77bcaabc23a20c4b0d8692c6a702debc45c67453",
    "openocd_catalog_git_blob_sha": "0ef056e3363e20bb527590c4a4cc1cc0d7afb810",
    "product_page_acquisition_git_blob_sha": "7a0aaa5e6e5fbac3968e4b47dd1ee3c4e05bc01f",
    "production_exact_icpn_count": 635,
    "production_family_counts": {
        "STM32F0": 42,
        "STM32F1": 75,
        "STM32F2": 33,
        "STM32F3": 10,
        "STM32F4": 384,
        "STM32F7": 19,
        "STM32G0": 47,
        "STM32G4": 25,
    },
    "production_manifest_git_blob_sha": "34ad9299ff0c063a8c8b5de1c253dfee47b63428",
    "stm32u0_production_prestate_count": 0,
    "u0_1_foundation_baseline_git_blob_sha": "4c0036b1fb66ce393a53134de8ce724c0ba0be50",
}


class Error(RuntimeError):
    pass


def req(condition: bool, message: str) -> None:
    if not condition:
        raise Error(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def read_targets() -> list[dict[str, str]]:
    with TARGETS.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    req(len(rows) == 26, "retained target row count drift")
    return rows


def main() -> int:
    baseline = read_json(BASELINE)
    summary = read_json(EVIDENCE / "pilot-summary.json")
    provenance = read_json(EVIDENCE / "provenance.json")
    discovery = read_json(DISCOVERY)
    u0_1 = read_json(U0_1_BASELINE)

    req(sha(BASELINE) == EXPECTED_BASELINE_SHA, "baseline byte drift")
    req(sha(EVIDENCE / "pilot-summary.json") == EXPECTED_SUMMARY_SHA, "summary byte drift")
    req(sha(EVIDENCE / "provenance.json") == EXPECTED_PROVENANCE_SHA, "provenance byte drift")
    req(sha(EVIDENCE / "manifest.json") == EXPECTED_MANIFEST_SHA, "manifest byte drift")
    req(sha(EVIDENCE / "README.md") == EXPECTED_README_SHA, "README byte drift")
    req(sha(TARGETS) == EXPECTED_TARGETS_SHA, "target projection byte drift")

    manifest = validate_manifest(
        EVIDENCE,
        expected_files={"README.md", "pilot-summary.json", "provenance.json", "targets.csv"},
    )
    req(manifest.get("evidence_id") == EXPECTED_EVIDENCE_ID, "manifest evidence ID drift")
    core = validate_core_provenance(
        provenance,
        evidence_id=EXPECTED_EVIDENCE_ID,
        expected_repository="physicslu/plasma",
        expected_manufacturer="STMicroelectronics",
    )
    req(core["evaluator_result"] == "clean", "retained evaluator must remain clean")

    req(baseline.get("aggregate") == EXPECTED_AGG, "baseline aggregate drift")
    req(summary.get("aggregate") == EXPECTED_AGG, "summary aggregate drift")
    req(baseline.get("source_bindings") == EXPECTED_BINDINGS, "baseline source bindings drift")
    req(provenance.get("source_bindings") == EXPECTED_BINDINGS, "provenance source bindings drift")
    req(git_blob(DISCOVERY) == EXPECTED_BINDINGS["discovery_manifest_git_blob_sha"], "discovery manifest drift")

    projection = baseline.get("retained_target_projection")
    req(
        projection
        == {
            "active_exact_icpn_count": 68,
            "path": "evidence/stm32u0-u0.2-official-st-discovery-live-2026-09-11/targets.csv",
            "row_count": 26,
            "sha256": EXPECTED_TARGETS_SHA,
            "u0_1_representative_drift": False,
        },
        "baseline target-projection binding drift",
    )
    req(
        summary.get("target_projection")
        == {
            "active_exact_icpn_count": 68,
            "path": "targets.csv",
            "row_count": 26,
            "sha256": EXPECTED_TARGETS_SHA,
        },
        "summary target-projection binding drift",
    )

    execution = baseline.get("discovery_execution")
    req(
        execution == {
            "artifact_id": EXPECTED_ARTIFACT,
            "artifact_zip_sha256": EXPECTED_ARTIFACT_SHA,
            "executed_git_sha": EXPECTED_EXEC_SHA,
            "live_summary_sha256": EXPECTED_LIVE_SHA,
            "pr_head_sha": EXPECTED_PR_HEAD,
            "workflow_run_id": EXPECTED_RUN,
        },
        "execution binding drift",
    )
    req(provenance.get("workflow_run_id") == EXPECTED_RUN, "workflow run drift")
    req(provenance.get("artifact_id") == EXPECTED_ARTIFACT, "artifact ID drift")
    req(provenance.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_SHA, "artifact digest drift")
    req(provenance.get("pr_head_sha") == EXPECTED_PR_HEAD, "PR head drift")
    req(provenance.get("executed_git_sha") == EXPECTED_EXEC_SHA, "execution SHA drift")
    req(provenance.get("live_artifact_summary_sha256") == EXPECTED_LIVE_SHA, "live summary digest drift")
    req(provenance.get("baseline_sha256") == EXPECTED_BASELINE_SHA, "baseline digest drift")

    req(
        provenance.get("acquisition_time_utc")
        == {"first": "2026-09-11T00:20:01Z", "last": "2026-09-11T00:25:33Z"},
        "acquisition time drift",
    )
    req(provenance.get("evidence_profile") == "stm32u0_quality_reliability_v1", "evidence profile drift")
    req(provenance.get("playwright_version") == "1.62.0", "Playwright version drift")
    req(provenance.get("chromium_version") == "151.0.7922.34", "Chromium version drift")
    req(provenance.get("headed") is True, "retained run must remain headed")
    req(provenance.get("sample_buy_gates_commercial_identity") is False, "Sample & Buy cannot gate identity")
    req(provenance.get("u0_1_representative_validation") == "success", "U0.1 continuity must remain successful")

    req(all_false(baseline.get("claims")), "baseline claims must remain false")
    req(all_false(summary.get("claims")), "summary claims must remain false")
    req(baseline["claims"].get("cmsis_alias_is_commercial_identity") is False, "CMSIS identity boundary violated")
    req(baseline["claims"].get("manufacturer_evidence_is_admission") is False, "evidence/admission boundary violated")

    rows = read_targets()
    source_targets = discovery.get("targets")
    req(isinstance(source_targets, list) and len(source_targets) == 26, "discovery target list drift")

    active: list[str] = []
    routing = Counter()
    retained_by_base: dict[str, list[str]] = {}
    for row, source in zip(rows, source_targets):
        base = row["base_device"]
        req(base == source.get("base_device"), "target Base Device drift")
        req(row["subfamily"] == source.get("subfamily"), f"{base}: subfamily drift")
        req(row["source_url"] == source.get("source_url"), f"{base}: source URL drift")
        req(row["disposition"] == "active_candidates", f"{base}: Active disposition drift")
        req(row["commercial_identity_status"] == "verified_active", f"{base}: identity status drift")
        exact = [value for value in row["exact_icpns"].split(";") if value]
        req(exact and all(value.startswith(base) for value in exact), f"{base}: foreign/missing exact ICPN")
        req(row["excluded_non_active_part_numbers"] == "", f"{base}: unexpected lifecycle exclusions")
        req(row["parser_profile"] == "stm32u0_quality_reliability_v1", f"{base}: parser profile drift")
        req(row["parser_version"] == "2", f"{base}: parser version drift")
        req(row["evidence_surface"] == "quality_and_reliability_part_number", f"{base}: evidence surface drift")
        req(row["sample_buy_gates_commercial_identity"] == "false", f"{base}: Sample & Buy boundary drift")
        req(row["routing_gates_commercial_identity"] == "false", f"{base}: routing boundary drift")
        req(row["historical_openocd_routing_status"] == "unique", f"{base}: routing status drift")
        req(row["historical_openocd_target_configs"] == "tcl/target/stm32u0x.cfg", f"{base}: target config drift")
        for key in ("evidence_section_sha256", "raw_sha256"):
            req(re.fullmatch(r"[0-9a-f]{64}", row[key]) is not None, f"{base}: invalid {key}")
        active.extend(exact)
        retained_by_base[base] = exact
        routing["unique"] += 1

    req(len(active) == len(set(active)) == 68, "Active exact ICPN count/uniqueness drift")
    req(routing == Counter({"unique": 26}), f"routing count drift: {routing}")

    representatives = u0_1.get("evidence_foundation", {}).get("representatives")
    req(isinstance(representatives, list) and len(representatives) == 3, "U0.1 representatives missing")
    for rep in representatives:
        base = rep.get("base_device")
        req(retained_by_base.get(base) == rep.get("exact_icpns"), f"{base}: U0.1 continuity drift")

    req(provenance.get("target_count") == 26, "provenance target count drift")
    req(provenance.get("exact_icpn_candidate_count") == 68, "provenance Active count drift")
    req(provenance.get("excluded_non_active_part_number_count") == 0, "provenance exclusion count drift")
    req(provenance.get("source_unavailable_exclusion_count") == 0, "provenance source-unavailable count drift")
    req(provenance.get("bounded_discovery_clean") is True, "bounded discovery must remain clean")
    req(provenance.get("commercial_identity_clean") is True, "commercial identity must remain clean")
    req(provenance.get("routing_gates_commercial_identity") is False, "routing cannot gate identity")
    req(provenance.get("canonical_dataset_admission") is False, "retained evidence cannot admit canonical data")
    req(provenance.get("production_admission_ready") is False, "retained evidence cannot authorize Production")

    print("STM32U0 Phase U0.2 retained evidence validation: PASS")
    print(
        json.dumps(
            {
                "active_exact_icpns": 68,
                "canonical_admission_authorized": False,
                "production_write_authorized": False,
                "routing_unique_targets": 26,
                "target_count": 26,
                "u0_1_representative_controls": 3,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Error, EvidenceFrameworkError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
