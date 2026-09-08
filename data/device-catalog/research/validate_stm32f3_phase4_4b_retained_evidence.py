#!/usr/bin/env python3
"""Validate retained STM32F3 Phase 4.4B evidence offline and fail closed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    sha256,
    validate_core_provenance,
    validate_manifest,
)
from st_product_page_acquisition import AcquisitionError
from stm32f3_dual_surface_evidence import EVIDENCE_SURFACE
from stm32f3_foundation import DEFAULT_CATALOG, read_catalog
from stm32f3_phase4_4b_discovery import (
    DEFAULT_MANIFEST,
    PHASE,
    discovery_is_clean,
    read_manifest,
    resolve_mapping,
)

HERE = Path(__file__).resolve().parent
DEFAULT_BASELINE = HERE / "stm32f3-phase4.4b-discovery-baseline.json"
DEFAULT_EVIDENCE_DIR = (
    HERE / "evidence/stm32f3-phase4.4b-official-st-discovery-live-2026-09-08"
)
EXPECTED_EVIDENCE_ID = (
    "stm32f3-phase4.4b-official-st-discovery-2026-09-08-"
    "retained-20260908T083224Z-0ac86cbf"
)
EXPECTED_EXECUTED_GIT_SHA = "0ac86cbf8da4cfaad6e0201c278cc43cb4c52c75"
EXPECTED_OPENOCD_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_DISCOVERY_MANIFEST_SHA256 = (
    "652476cbbb26a585de73a8d9c2cc130d221b3805dee3682e823c4299f811d59f"
)
EXPECTED_PRODUCTION_MANIFEST_SHA256_AT_DISCOVERY = (
    "40f8d3928aad3a43d017a377ec2a9e41a610fa7bd232942c3e938d8628af6b3"
)
EXPECTED_BASELINE_SHA256 = "bce53ea895b70a12b873259a81603716665496d60a649a6b867928b7d55ff90a"
EXPECTED_SUMMARY_SHA256 = "21bcf53d325d4258e929edcfa09ac9cacf73f06bfa6e248402c79168d72a77b9"
EXPECTED_RUN_ID = 34204938530
EXPECTED_ARTIFACT_ID = 10047381270
EXPECTED_ARTIFACT_ZIP_SHA256 = (
    "c40fcba4e35c3e193c9ca85e1433df352f42b91453d6b68c923fa2eafca4d9eb"
)
EXPECTED_PROFILE = "stm32f3_dual_surface_v1"
EXPECTED_EXACT_COUNT = 10


class STM32F3RetainedEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise STM32F3RetainedEvidenceError(message)


def _validate_historical_prestate(baseline: dict[str, Any]) -> None:
    inputs = baseline.get("inputs")
    snapshot = baseline.get("production_snapshot")
    require(isinstance(inputs, dict), "baseline inputs must be an object")
    require(isinstance(snapshot, dict), "baseline Production snapshot must be an object")
    require(
        inputs.get("openocd_catalog_sha256") == EXPECTED_OPENOCD_SHA256,
        "baseline OpenOCD binding mismatch",
    )
    require(
        inputs.get("discovery_manifest_sha256") == EXPECTED_DISCOVERY_MANIFEST_SHA256,
        "baseline discovery-manifest binding mismatch",
    )
    require(
        inputs.get("production_manifest_sha256_at_discovery")
        == EXPECTED_PRODUCTION_MANIFEST_SHA256_AT_DISCOVERY,
        "baseline historical Production-manifest binding mismatch",
    )
    require(snapshot.get("exact_icpn_count") == 492, "historical Production count mismatch")
    require(
        snapshot.get("family_exact_icpn_counts")
        == {"STM32F1": 75, "STM32F2": 33, "STM32F4": 384},
        "historical Production family counts mismatch",
    )
    require(snapshot.get("stm32f3_exact_icpn_count") == 0, "historical STM32F3 count mismatch")


def validate(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    baseline_path: Path = DEFAULT_BASELINE,
    catalog_path: Path = DEFAULT_CATALOG,
    discovery_manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    manifest = validate_manifest(
        evidence_dir,
        expected_files=("README.md", "pilot-summary.json", "provenance.json"),
    )
    require(manifest.get("evidence_id") == EXPECTED_EVIDENCE_ID, "evidence ID mismatch")

    baseline = read_json(baseline_path)
    summary = read_json(evidence_dir / "pilot-summary.json")
    provenance = read_json(evidence_dir / "provenance.json")
    core = validate_core_provenance(
        provenance,
        evidence_id=EXPECTED_EVIDENCE_ID,
        expected_repository="physicslu/plasma",
        expected_manufacturer="STMicroelectronics",
    )

    require(sha256(baseline_path) == EXPECTED_BASELINE_SHA256, "baseline byte digest mismatch")
    require(sha256(evidence_dir / "pilot-summary.json") == EXPECTED_SUMMARY_SHA256, "summary byte digest mismatch")
    require(provenance.get("baseline_sha256") == EXPECTED_BASELINE_SHA256, "provenance baseline digest mismatch")
    require(provenance.get("pilot_summary_sha256") == EXPECTED_SUMMARY_SHA256, "provenance summary digest mismatch")

    require(baseline.get("schema_version") == 1, "baseline schema mismatch")
    require(baseline.get("phase") == PHASE, "baseline phase mismatch")
    require(baseline.get("pilot_id") == summary.get("pilot_id"), "baseline/summary pilot mismatch")
    require(baseline.get("executed_git_sha") == EXPECTED_EXECUTED_GIT_SHA, "baseline Git SHA mismatch")
    require(core["executed_git_sha"] == EXPECTED_EXECUTED_GIT_SHA, "provenance Git SHA mismatch")
    require(provenance.get("evidence_profile") == EXPECTED_PROFILE, "provenance evidence profile mismatch")
    require(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "workflow run binding mismatch")
    require(provenance.get("artifact_id") == EXPECTED_ARTIFACT_ID, "artifact binding mismatch")
    require(provenance.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_ZIP_SHA256, "artifact digest mismatch")
    require(provenance.get("playwright_version") == "1.62.0", "Playwright version mismatch")
    require(provenance.get("chromium_version") == "151.0.7922.34", "Chromium version mismatch")
    require(core["headed"] is True, "retained run must be headed Chromium")
    require(core["target_count"] == 6, "retained target count mismatch")
    require(core["acquisition_success"] == 6 and core["acquisition_failure"] == 0, "retained acquisition accounting mismatch")
    require(core["exact_icpn_candidate_count"] == EXPECTED_EXACT_COUNT, "retained candidate count mismatch")
    require(provenance.get("excluded_non_active_part_number_count") == 0, "retained lifecycle exclusion count mismatch")
    require(provenance.get("production_admission_ready") is False, "retained evidence must deny Production readiness")

    _validate_historical_prestate(baseline)
    require(sha256(catalog_path) == EXPECTED_OPENOCD_SHA256, "current OpenOCD catalog drifted from discovery input")
    require(
        sha256(discovery_manifest_path) == EXPECTED_DISCOVERY_MANIFEST_SHA256,
        "current discovery manifest drifted from retained input",
    )

    catalog_rows = read_catalog(catalog_path)
    pilot_id, targets = read_manifest(discovery_manifest_path, catalog_rows)
    require(pilot_id == summary.get("pilot_id"), "manifest/summary pilot mismatch")
    require(summary.get("schema_version") == 1 and summary.get("phase") == PHASE, "summary phase/schema mismatch")
    require(summary.get("family") == "STM32F3", "summary family mismatch")
    require(discovery_is_clean(summary), "retained discovery summary is not clean")
    require(summary.get("active_exact_icpn_candidates") == EXPECTED_EXACT_COUNT, "summary exact ICPN count mismatch")
    require(summary.get("excluded_non_active_part_numbers") == 0, "summary lifecycle exclusions mismatch")
    require(summary.get("manual_intervention_required") == 0, "summary manual intervention mismatch")
    require(
        summary.get("canonical_mapping") == {"unique": 6, "ambiguous": 0, "unmapped": 0},
        "summary mapping accounting mismatch",
    )
    browser = summary.get("browser")
    require(isinstance(browser, dict), "summary browser metadata missing")
    require(browser.get("evidence_profile") == EXPECTED_PROFILE, "summary evidence profile mismatch")
    require(browser.get("headless") is False, "summary must bind headed Chromium")
    require(browser.get("playwright_version") == "1.62.0", "summary Playwright mismatch")
    require(browser.get("browser_version") == "151.0.7922.34", "summary Chromium mismatch")
    claims = summary.get("claims")
    require(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "summary claims must all remain false")

    baseline_targets = baseline.get("targets")
    results = summary.get("results")
    require(isinstance(baseline_targets, list) and len(baseline_targets) == 6, "baseline target list mismatch")
    require(isinstance(results, list) and len(results) == 6, "summary result list mismatch")
    expected_target_pairs = [(target.subfamily, target.base_device) for target in targets]
    require(
        [(item.get("subfamily"), item.get("base_device")) for item in baseline_targets]
        == expected_target_pairs,
        "baseline target order drifted",
    )
    require(
        [(item.get("subfamily"), item.get("base_device")) for item in results]
        == expected_target_pairs,
        "summary target order drifted",
    )

    observed_icpns: list[str] = []
    for target, baseline_target, result in zip(targets, baseline_targets, results):
        require(result.get("acquisition_status") == "success", f"{target.base_device}: retained acquisition is not successful")
        require(result.get("source_url") == target.source_url, f"{target.base_device}: summary source URL mismatch")
        evidence = result.get("evidence")
        mappings = result.get("candidate_mappings")
        canonical = result.get("canonical_mapping")
        require(isinstance(evidence, dict), f"{target.base_device}: retained evidence missing")
        require(isinstance(mappings, list), f"{target.base_device}: retained mappings missing")
        require(isinstance(canonical, dict), f"{target.base_device}: canonical mapping missing")
        require(evidence.get("base_device") == target.base_device, f"{target.base_device}: evidence Base Device mismatch")
        require(evidence.get("source_url") == target.source_url, f"{target.base_device}: evidence source URL mismatch")
        require(evidence.get("final_url") == target.source_url, f"{target.base_device}: evidence final URL mismatch")
        require(evidence.get("evidence_surface") == EVIDENCE_SURFACE, f"{target.base_device}: evidence surface mismatch")
        require(evidence.get("parser_profile") == EXPECTED_PROFILE, f"{target.base_device}: parser profile mismatch")
        require(evidence.get("acquisition_transport") == "chromium_rendered_dom", f"{target.base_device}: transport mismatch")
        require(evidence.get("http_etag") is None and evidence.get("http_last_modified") is None, f"{target.base_device}: browser evidence claims raw HTTP metadata")

        exact = evidence.get("exact_icpns")
        excluded = evidence.get("excluded_non_active_part_numbers")
        records = evidence.get("part_number_records")
        require(isinstance(exact, list) and exact, f"{target.base_device}: exact ICPNs missing")
        require(isinstance(excluded, list) and not excluded, f"{target.base_device}: unexpected lifecycle exclusion")
        require(isinstance(records, list) and len(records) == len(exact), f"{target.base_device}: record count mismatch")
        require([record.get("icpn") for record in records] == exact, f"{target.base_device}: record/identity order mismatch")
        require(all(record.get("active") is True for record in records), f"{target.base_device}: non-active record leaked into Active set")
        require(all(isinstance(record.get("marketing_status"), str) and record["marketing_status"].startswith("Active") for record in records), f"{target.base_device}: lifecycle status mismatch")

        for field in ("retrieved_at_utc", "rendered_dom_sha256", "evidence_section_sha256"):
            require(evidence.get(field) == baseline_target.get(field), f"{target.base_device}: {field} drifted from baseline")
        require(exact == baseline_target.get("active_exact_icpns"), f"{target.base_device}: exact ICPN set drifted from baseline")
        require(excluded == baseline_target.get("excluded_non_active_part_numbers"), f"{target.base_device}: exclusion set drifted from baseline")

        require(len(mappings) == len(exact), f"{target.base_device}: mapping count mismatch")
        for icpn, retained_mapping in zip(exact, mappings):
            require(retained_mapping.get("icpn") == icpn, f"{target.base_device}: mapping identity order mismatch")
            replay = resolve_mapping(icpn, catalog_rows)
            retained_without_identity = {key: value for key, value in retained_mapping.items() if key != "icpn"}
            require(replay == retained_without_identity, f"{icpn}: OpenOCD mapping replay drifted")
            require(replay.get("status") == "unique", f"{icpn}: mapping is no longer unique")
            require(replay.get("target_configs") == ["tcl/target/stm32f3x.cfg"], f"{icpn}: target config drifted")
        require(canonical.get("status") == "unique", f"{target.base_device}: canonical mapping no longer unique")
        require(canonical.get("candidate_count") == len(exact), f"{target.base_device}: canonical candidate count mismatch")
        require(canonical.get("target_configs") == ["tcl/target/stm32f3x.cfg"], f"{target.base_device}: canonical target config mismatch")
        observed_icpns.extend(exact)

    require(len(observed_icpns) == EXPECTED_EXACT_COUNT, "aggregate exact ICPN count mismatch")
    require(len(set(observed_icpns)) == EXPECTED_EXACT_COUNT, "duplicate exact ICPN across retained targets")
    require(baseline.get("result") == {
        "attempted": 6,
        "acquisition_success": 6,
        "acquisition_failure": 0,
        "active_exact_icpn_candidates": 10,
        "excluded_non_active_part_numbers": 0,
        "canonical_mapping": {"unique": 6, "ambiguous": 0, "unmapped": 0},
        "manual_intervention_required": 0,
    }, "baseline result accounting mismatch")
    baseline_claims = baseline.get("claims")
    require(isinstance(baseline_claims, dict) and baseline_claims and set(baseline_claims.values()) == {False}, "baseline claims must all remain false")

    return {
        "status": "valid",
        "phase": PHASE,
        "evidence_id": EXPECTED_EVIDENCE_ID,
        "target_count": 6,
        "active_exact_icpn_candidates": EXPECTED_EXACT_COUNT,
        "mapping_unique": 6,
        "manual_intervention_required": 0,
        "canonical_dataset_admission": False,
        "production_admission_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate(evidence_dir=args.evidence_dir, baseline_path=args.baseline)
    except (EvidenceFrameworkError, STM32F3RetainedEvidenceError, AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
