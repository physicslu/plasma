#!/usr/bin/env python3
"""Phase 4.4C deterministic STM32F3 metadata policy planner.

The planner consumes retained Phase 4.4B manufacturer evidence and the current
OpenOCD mapping catalog, derives canonical rows under an explicit STM32F3
ordering-code contract, and stops before canonical/Production admission.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    build_admission_plan,
    file_sha256,
    plan_is_clean,
    read_csv,
    read_json,
)
from stm32f3_admission_policy import (
    CANONICAL_FIELDS,
    FAMILY,
    FLASH_BY_CODE,
    OPTION_SUFFIXES,
    PACKAGE_BY_CODE,
    PINS_BY_COMBINATION,
    SUPPORTED_BASE_DEVICES,
    TARGET_CONFIG,
    TEMPERATURE_BY_CODE,
    build_candidate_inputs,
    build_canonical_row,
)
from stm32f3_foundation import DEFAULT_CATALOG
from validate_stm32f3_phase4_4b_retained_evidence import (
    DEFAULT_BASELINE as DISCOVERY_BASELINE,
    DEFAULT_EVIDENCE_DIR,
    validate as validate_retained_evidence,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.4C"
DISCOVERY_PHASE = "4.4B"
ADMISSION_PHASE = "4.4D"
ADAPTER_ID = "stm32f3-phase4.4c"
DEFAULT_POLICY_BASELINE = HERE / "stm32f3-phase4.4c-policy-baseline.json"
DEFAULT_PRODUCTION_MANIFEST = HERE / "stm32f3-phase4.4d-production-manifest-prestate.json"
DEFAULT_PRODUCTION_MANIFEST_BINDING_NAME = "icpn-v1-manifest.json"
EXPECTED_CANDIDATE_COUNT = 10
EXPECTED_PRODUCTION_EXACT_COUNT = 492
EXPECTED_PRODUCTION_BASE_DEVICE_COUNT = 169
EXPECTED_PRODUCTION_FAMILY_COUNTS = {
    "STM32F1": 75,
    "STM32F2": 33,
    "STM32F4": 384,
}

POLICY_EVIDENCE = {
    "stm32f301_ordering_information": "https://www.st.com/resource/en/datasheet/stm32f301c6.pdf",
    "stm32f302_ordering_information": "https://www.st.com/resource/en/datasheet/stm32f302c6.pdf",
    "stm32f303_ordering_information": "https://www.st.com/resource/en/datasheet/stm32f303r8.pdf",
    "stm32f334_ordering_information": "https://www.st.com/resource/en/datasheet/stm32f334c4.pdf",
    "stm32f373_ordering_information": "https://www.st.com/resource/en/datasheet/stm32f373c8.pdf",
    "stm32f318_ordering_information": "https://www.st.com/resource/en/datasheet/stm32f318c8.pdf",
    "semantic_decisions": {
        "pin_count": "actual package pin or ball count",
        "C/T": "48",
        "C/Y": "49",
        "T_package": "LQFP",
        "Y_package": "WLCSP",
        "4_flash": "16 KiB",
        "6_flash": "32 KiB",
        "8_flash": "64 KiB",
        "metadata_authority": "official ST datasheet ordering-information tables",
        "lifecycle_authority": "retained Phase 4.4B dual-surface official ST evidence",
    },
}


class STM32F3PolicyError(AdmissionError):
    pass


def metadata_contract() -> dict[str, Any]:
    return {
        "flash_by_code": dict(FLASH_BY_CODE),
        "temperature_by_code": dict(TEMPERATURE_BY_CODE),
        "package_by_code": dict(PACKAGE_BY_CODE),
        "pins_by_combination": {
            f"{pin}/{package}": pins
            for (pin, package), pins in sorted(PINS_BY_COMBINATION.items())
        },
        "allowed_option_suffixes": sorted(OPTION_SUFFIXES),
        "openocd_target_config": TARGET_CONFIG,
    }


def production_snapshot(manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise STM32F3PolicyError("Production manifest sources must be a list")

    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise STM32F3PolicyError("Production manifest source must be an object")
        family = source.get("family")
        relative = source.get("path")
        declared = source.get("row_count")
        if not isinstance(family, str) or not isinstance(relative, str) or not isinstance(declared, int):
            raise STM32F3PolicyError("Production manifest source is incomplete")
        if family == FAMILY:
            raise STM32F3PolicyError("Phase 4.4C requires STM32F3 to be absent from Production")
        _, rows = read_csv((manifest_path.parent / relative).resolve())
        if len(rows) != declared or any(row.get("family") != family for row in rows):
            raise STM32F3PolicyError(f"{family}: Production source drifted")
        family_counts[family] = len(rows)
        base_devices.update((family, row.get("base_device", "")) for row in rows)

    if family_counts != EXPECTED_PRODUCTION_FAMILY_COUNTS:
        raise STM32F3PolicyError(
            f"Phase 4.4C Production family counts drifted: {family_counts}"
        )
    exact_count = sum(family_counts.values())
    if exact_count != EXPECTED_PRODUCTION_EXACT_COUNT:
        raise STM32F3PolicyError("Phase 4.4C Production exact ICPN count drifted")
    if len(base_devices) != EXPECTED_PRODUCTION_BASE_DEVICE_COUNT:
        raise STM32F3PolicyError(
            f"Phase 4.4C Production Base Device count drifted: {len(base_devices)}"
        )
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(base_devices),
        "family_exact_icpn_counts": family_counts,
        "stm32f3_exact_icpn_count": 0,
    }


def build_policy_plan(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
    production_manifest_binding_name: str | None = DEFAULT_PRODUCTION_MANIFEST_BINDING_NAME,
) -> dict[str, Any]:
    retained = validate_retained_evidence()
    if (
        retained.get("status") != "valid"
        or retained.get("active_exact_icpn_candidates") != EXPECTED_CANDIDATE_COUNT
        or retained.get("production_admission_ready") is not False
    ):
        raise STM32F3PolicyError("Phase 4.4B retained evidence is not policy-eligible")

    provenance = read_json(DEFAULT_EVIDENCE_DIR / "provenance.json")
    summary = read_json(DEFAULT_EVIDENCE_DIR / "pilot-summary.json")
    if provenance.get("scale_ready") is not True:
        raise STM32F3PolicyError("Phase 4.4B retained evidence is not scale-ready")
    if provenance.get("canonical_dataset_admission") is not False:
        raise STM32F3PolicyError("retained evidence unexpectedly authorizes admission")
    if provenance.get("production_admission_ready") is not False:
        raise STM32F3PolicyError("retained evidence unexpectedly claims Production readiness")
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise STM32F3PolicyError("retained evidence requires evidence_id")

    fields, catalog_rows = read_csv(catalog_path)
    del fields
    candidate_inputs = build_candidate_inputs(
        summary=summary,
        evidence_id=evidence_id,
        catalog_rows=catalog_rows,
        expected_candidate_count=EXPECTED_CANDIDATE_COUNT,
    )
    plan = build_admission_plan(
        candidate_inputs=candidate_inputs,
        canonical_fields=list(CANONICAL_FIELDS),
        canonical_rows=[],
        source_provenance={
            "evidence_id": evidence_id,
            "repository": provenance.get("source_repository"),
            "executed_git_sha": provenance.get("executed_git_sha"),
            "workflow_run_id": provenance.get("workflow_run_id"),
            "artifact_id": provenance.get("artifact_id"),
            "artifact_zip_sha256": provenance.get("artifact_zip_sha256"),
            "evidence_manifest_sha256": file_sha256(DEFAULT_EVIDENCE_DIR / "manifest.json"),
        },
        input_bindings={
            "family_adapter": ADAPTER_ID,
            "retained_evidence_directory": DEFAULT_EVIDENCE_DIR.name,
            "retained_evidence_baseline": DISCOVERY_BASELINE.name,
            "retained_evidence_baseline_sha256": file_sha256(DISCOVERY_BASELINE),
            "mapping_catalog": catalog_path.name,
            "mapping_catalog_sha256": file_sha256(catalog_path),
            "canonical_dataset": "stm32f3-commercial-icpn.csv",
            "canonical_dataset_absent_before_policy": True,
            "production_manifest": (
                production_manifest_binding_name or production_manifest_path.name
            ),
            "production_manifest_sha256": file_sha256(production_manifest_path),
        },
        row_builder=build_canonical_row,
    )
    plan.update(
        {
            "phase": PHASE,
            "family": FAMILY,
            "adapter_id": ADAPTER_ID,
            "discovery_phase": DISCOVERY_PHASE,
            "admission_phase": ADMISSION_PHASE,
            "canonical_dataset_admission": "deferred",
            "policy_ready_count": plan["decision_counts"]["admit"],
            "production_snapshot": production_snapshot(production_manifest_path),
            "production_write_applied": False,
            "exact_icpn_admission_deferred": True,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_support_claimed": False,
            "full_stm32f3_surface_covered": False,
            "fail_closed": True,
        }
    )
    return plan


def policy_plan_is_clean(plan: dict[str, Any]) -> bool:
    expected_decisions = {
        "admit": EXPECTED_CANDIDATE_COUNT,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    candidates = plan.get("candidates")
    return (
        plan_is_clean(plan)
        and plan.get("phase") == PHASE
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("discovery_phase") == DISCOVERY_PHASE
        and plan.get("admission_phase") == ADMISSION_PHASE
        and plan.get("candidate_count") == EXPECTED_CANDIDATE_COUNT
        and plan.get("policy_ready_count") == EXPECTED_CANDIDATE_COUNT
        and plan.get("decision_counts") == expected_decisions
        and isinstance(candidates, list)
        and {item.get("base_device") for item in candidates} == set(SUPPORTED_BASE_DEVICES)
        and plan.get("canonical_rows_before") == 0
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_snapshot", {}).get("exact_icpn_count")
        == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count")
        == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts")
        == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32f3_exact_icpn_count") == 0
        and plan.get("production_write_applied") is False
        and plan.get("exact_icpn_admission_deferred") is True
        and plan.get("runtime_support_claimed") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("full_stm32f3_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def policy_summary(plan: dict[str, Any]) -> dict[str, Any]:
    candidates = plan["candidates"]
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "evidence_id": plan["evidence_id"],
        "retained_evidence_directory": plan["inputs"]["retained_evidence_directory"],
        "candidate_count": plan["candidate_count"],
        "base_devices": sorted({item["base_device"] for item in candidates}),
        "policy_ready_exact_icpns": sorted(item["icpn"] for item in candidates),
        "decision_counts": plan["decision_counts"],
        "conflicts": plan["conflicts"],
        "metadata_contract": metadata_contract(),
        "policy_evidence": POLICY_EVIDENCE,
        "production_snapshot": plan["production_snapshot"],
        "production_write_applied": False,
        "exact_icpn_admission_deferred": True,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_support_claimed": False,
        "full_stm32f3_surface_covered": False,
        "fail_closed": True,
    }


def validate_policy(
    baseline_path: Path = DEFAULT_POLICY_BASELINE,
    *,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
    production_manifest_binding_name: str | None = DEFAULT_PRODUCTION_MANIFEST_BINDING_NAME,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = build_policy_plan(
        production_manifest_path=production_manifest_path,
        production_manifest_binding_name=production_manifest_binding_name,
    )
    if not policy_plan_is_clean(plan):
        raise STM32F3PolicyError("Phase 4.4C policy plan is not clean")
    summary = policy_summary(plan)
    if summary != read_json(baseline_path):
        raise STM32F3PolicyError("Phase 4.4C policy baseline drifted")
    return plan, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_POLICY_BASELINE)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--skip-baseline-check",
        action="store_true",
        help="Generate the deterministic summary before the immutable policy baseline exists.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_policy_plan()
        if not policy_plan_is_clean(plan):
            raise STM32F3PolicyError("Phase 4.4C policy plan is not clean")
        summary = policy_summary(plan)
        if not args.skip_baseline_check and summary != read_json(args.baseline):
            raise STM32F3PolicyError("Phase 4.4C policy baseline drifted")
    except (AdmissionError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
