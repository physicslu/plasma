#!/usr/bin/env python3
"""Phase 4.6C deterministic STM32F7 metadata-policy planner.

Commercial identity/lifecycle authority is retained Phase 4.6B official-ST evidence.
Canonical metadata comes from explicit official ST ordering-information contracts or
the narrow STM32F750N8 exact-product override. OpenOCD is not a metadata authority
and capability routing is deferred to the later admission phase.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    CandidateManualReview,
    CandidateReject,
    file_sha256,
    read_csv,
    read_json,
)
from stm32f7_metadata_policy import (
    DATASHEET_AUTHORITIES,
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    F750_EXACT_PRODUCT_AUTHORITY,
    METADATA_FIELDS,
    SUPPORTED_BASE_DEVICES,
    build_candidate_inputs,
    build_metadata_row,
)
from validate_stm32f7_phase4_6b_retained_evidence import (
    DEFAULT_BASELINE as DISCOVERY_BASELINE,
    DEFAULT_EVIDENCE_DIR,
    validate as validate_retained_evidence,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.6C"
DISCOVERY_PHASE = "4.6B"
ADMISSION_PHASE = "4.6D"
ADAPTER_ID = "stm32f7-phase4.6c-metadata"
DEFAULT_POLICY_BASELINE = HERE / "stm32f7-phase4.6c-policy-baseline.json"
DEFAULT_PRODUCTION_MANIFEST = HERE / "stm32f7-phase4.6c-production-manifest-prestate.json"
CURRENT_PRODUCTION_MANIFEST = HERE.parent / "production/icpn-v1-manifest.json"
EXPECTED_PRODUCTION_EXACT_COUNT = 544
EXPECTED_PRODUCTION_BASE_DEVICE_COUNT = 188
EXPECTED_PRODUCTION_FAMILY_COUNTS = {
    "STM32F0": 42,
    "STM32F1": 75,
    "STM32F2": 33,
    "STM32F3": 10,
    "STM32F4": 384,
}

POLICY_EVIDENCE = {
    "ordering_information": dict(sorted(DATASHEET_AUTHORITIES.items())),
    "stm32f750n8_exact_product_override": F750_EXACT_PRODUCT_AUTHORITY,
    "semantic_decisions": {
        "C_flash": "256 KiB",
        "E_flash": "512 KiB",
        "8_flash": "64 KiB",
        "I_flash": "2048 KiB",
        "T_package": "LQFP",
        "K_package": "UFBGA",
        "H_package": "TFBGA",
        "Y_package": "WLCSP",
        "I_pin_code": "176",
        "N_pin_code": "216",
        "A_pin_code": "180",
        "temperature_6": "-40 to 85 C",
        "temperature_7": "-40 to 105 C",
        "option_blank": "standard packing",
        "option_TR": "tape and reel",
        "identity_lifecycle_authority": "retained Phase 4.6B official ST dual-surface evidence",
        "metadata_authority": "official ST ordering information; F750N8 uses exact-product override",
        "openocd_role": "not a metadata authority; capability routing deferred to Phase 4.6D",
        "f750_boundary": "only retained Active STM32F750N8H6 is accepted; no generalized F750 decode",
    },
}


class STM32F7PolicyError(AdmissionError):
    pass


def _json_write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def metadata_contract() -> dict[str, Any]:
    return {
        "bounded_active_candidate_count": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "bounded_active_base_devices": sorted(SUPPORTED_BASE_DEVICES),
        "openocd_routing_gates_metadata": False,
        "capability_mapping_deferred_to": ADMISSION_PHASE,
        "f750_generalized_decode_allowed": False,
    }


def production_snapshot(manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise STM32F7PolicyError("Production manifest sources must be a list")

    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise STM32F7PolicyError("Production manifest source must be an object")
        family = source.get("family")
        relative = source.get("path")
        declared = source.get("row_count")
        if not isinstance(family, str) or not isinstance(relative, str) or not isinstance(declared, int):
            raise STM32F7PolicyError("Production manifest source is incomplete")
        if family == "STM32F7":
            raise STM32F7PolicyError("Phase 4.6C requires STM32F7 to be absent from Production prestate")
        source_path = (manifest_path.parent / relative).resolve()
        _, rows = read_csv(source_path)
        if len(rows) != declared or any(row.get("family") != family for row in rows):
            raise STM32F7PolicyError(f"{family}: Production source drifted")
        family_counts[family] = len(rows)
        base_devices.update((family, row.get("base_device", "")) for row in rows)

    if family_counts != EXPECTED_PRODUCTION_FAMILY_COUNTS:
        raise STM32F7PolicyError(f"Phase 4.6C Production family counts drifted: {family_counts}")
    exact_count = sum(family_counts.values())
    if exact_count != EXPECTED_PRODUCTION_EXACT_COUNT:
        raise STM32F7PolicyError("Phase 4.6C Production exact ICPN count drifted")
    if len(base_devices) != EXPECTED_PRODUCTION_BASE_DEVICE_COUNT:
        raise STM32F7PolicyError(
            f"Phase 4.6C Production Base Device count drifted: {len(base_devices)}"
        )
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(base_devices),
        "family_exact_icpn_counts": family_counts,
        "stm32f7_exact_icpn_count": 0,
    }


def _metadata_distribution(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    fields = ("flash_size", "package", "pin_count", "temperature_grade", "option_suffix")
    return {
        field: dict(sorted(Counter(row[field] for row in rows).items()))
        for field in fields
    }


def build_policy_plan(*, production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    retained = validate_retained_evidence()
    if (
        retained.get("status") != "valid"
        or retained.get("bounded_discovery_clean") is not True
        or retained.get("commercial_identity_clean") is not False
        or retained.get("active_exact_icpn_candidates") != EXPECTED_ACTIVE_CANDIDATE_COUNT
        or retained.get("production_admission_ready") is not False
    ):
        raise STM32F7PolicyError("Phase 4.6B retained evidence is not Phase 4.6C policy eligible")

    provenance = read_json(DEFAULT_EVIDENCE_DIR / "provenance.json")
    discovery_baseline = read_json(DISCOVERY_BASELINE)
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise STM32F7PolicyError("retained evidence requires evidence_id")
    if provenance.get("canonical_dataset_admission") is not False:
        raise STM32F7PolicyError("retained evidence unexpectedly authorizes admission")

    candidate_inputs = build_candidate_inputs(
        discovery_baseline=discovery_baseline,
        evidence_id=evidence_id,
    )
    candidates: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seen: set[str] = set()
    for candidate in candidate_inputs:
        icpn = candidate.get("icpn")
        decision = "metadata_ready"
        issues: list[str] = []
        row: dict[str, str] | None = None
        if not isinstance(icpn, str) or not icpn or icpn in seen:
            decision = "reject"
            issues.append("duplicate or invalid retained candidate")
        else:
            seen.add(icpn)
            try:
                row = build_metadata_row(candidate, list(METADATA_FIELDS))
            except CandidateManualReview as exc:
                decision = "manual_review_required"
                issues.append(str(exc))
            except CandidateReject as exc:
                decision = "reject"
                issues.append(str(exc))
        counts[decision] += 1
        candidates.append({
            "manufacturer": candidate.get("manufacturer"),
            "base_device": candidate.get("base_device"),
            "icpn": icpn,
            "decision": decision,
            "issues": issues,
            "metadata": row,
        })

    candidates.sort(key=lambda item: (str(item["base_device"]), str(item["icpn"])))
    metadata_rows = [item["metadata"] for item in candidates if item["metadata"] is not None]
    decision_counts = {
        "metadata_ready": counts["metadata_ready"],
        "manual_review_required": counts["manual_review_required"],
        "reject": counts["reject"],
    }
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": "STM32F7",
        "adapter_id": ADAPTER_ID,
        "discovery_phase": DISCOVERY_PHASE,
        "admission_phase": ADMISSION_PHASE,
        "evidence_id": evidence_id,
        "candidate_count": len(candidates),
        "decision_counts": decision_counts,
        "issues": sorted({issue for item in candidates for issue in item["issues"]}),
        "candidates": candidates,
        "metadata_distribution": _metadata_distribution(metadata_rows),
        "inputs": {
            "retained_evidence_directory": DEFAULT_EVIDENCE_DIR.name,
            "retained_discovery_baseline": DISCOVERY_BASELINE.name,
            "retained_discovery_baseline_sha256": file_sha256(DISCOVERY_BASELINE),
            "retained_evidence_manifest_sha256": file_sha256(DEFAULT_EVIDENCE_DIR / "manifest.json"),
            "production_manifest": production_manifest_path.name,
            "production_manifest_sha256": file_sha256(production_manifest_path),
            "openocd_catalog_bound": False,
        },
        "production_snapshot": production_snapshot(production_manifest_path),
        "metadata_contract": metadata_contract(),
        "policy_evidence": POLICY_EVIDENCE,
        "canonical_dataset_admission": "deferred",
        "production_write_applied": False,
        "exact_icpn_admission_deferred": True,
        "openocd_routing_gate_applied": False,
        "capability_mapping_deferred": True,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_support_claimed": False,
        "full_stm32f7_surface_covered": False,
        "fail_closed": True,
    }


def policy_plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        plan.get("phase") == PHASE
        and plan.get("family") == "STM32F7"
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("candidate_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("decision_counts") == {
            "metadata_ready": EXPECTED_ACTIVE_CANDIDATE_COUNT,
            "manual_review_required": 0,
            "reject": 0,
        }
        and plan.get("issues") == []
        and {item.get("base_device") for item in plan.get("candidates", [])} == set(SUPPORTED_BASE_DEVICES)
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count") == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts") == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32f7_exact_icpn_count") == 0
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_write_applied") is False
        and plan.get("exact_icpn_admission_deferred") is True
        and plan.get("openocd_routing_gate_applied") is False
        and plan.get("capability_mapping_deferred") is True
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("runtime_support_claimed") is False
        and plan.get("full_stm32f7_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def policy_summary(plan: dict[str, Any]) -> dict[str, Any]:
    rows = [item["metadata"] for item in plan["candidates"]]
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": "STM32F7",
        "adapter_id": ADAPTER_ID,
        "evidence_id": plan["evidence_id"],
        "retained_evidence_directory": plan["inputs"]["retained_evidence_directory"],
        "retained_discovery_baseline_sha256": plan["inputs"]["retained_discovery_baseline_sha256"],
        "retained_evidence_manifest_sha256": plan["inputs"]["retained_evidence_manifest_sha256"],
        "candidate_count": plan["candidate_count"],
        "base_devices": sorted({item["base_device"] for item in plan["candidates"]}),
        "policy_ready_exact_icpns": sorted(item["icpn"] for item in plan["candidates"]),
        "decision_counts": plan["decision_counts"],
        "metadata_contract": plan["metadata_contract"],
        "metadata_distribution": plan["metadata_distribution"],
        "metadata_rows": rows,
        "policy_evidence": plan["policy_evidence"],
        "production_snapshot": plan["production_snapshot"],
        "production_manifest_sha256": plan["inputs"]["production_manifest_sha256"],
        "production_write_applied": False,
        "exact_icpn_admission_deferred": True,
        "openocd_routing_gate_applied": False,
        "capability_mapping_deferred": True,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_support_claimed": False,
        "full_stm32f7_surface_covered": False,
        "fail_closed": True,
    }


def validate_policy(
    baseline_path: Path = DEFAULT_POLICY_BASELINE,
    *,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = build_policy_plan(production_manifest_path=production_manifest_path)
    if not policy_plan_is_clean(plan):
        raise STM32F7PolicyError("Phase 4.6C metadata policy plan is not clean")
    summary = policy_summary(plan)
    if summary != read_json(baseline_path):
        raise STM32F7PolicyError("Phase 4.6C policy baseline drifted")
    return plan, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_POLICY_BASELINE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--freeze-production", action="store_true")
    parser.add_argument("--skip-baseline-check", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.freeze_production:
            if DEFAULT_PRODUCTION_MANIFEST.exists():
                raise STM32F7PolicyError("Phase 4.6C Production prestate already exists")
            shutil.copyfile(CURRENT_PRODUCTION_MANIFEST, DEFAULT_PRODUCTION_MANIFEST)
        plan = build_policy_plan()
        if not policy_plan_is_clean(plan):
            raise STM32F7PolicyError("Phase 4.6C metadata policy plan is not clean")
        summary = policy_summary(plan)
        if not args.skip_baseline_check and summary != read_json(args.baseline):
            raise STM32F7PolicyError("Phase 4.6C policy baseline drifted")
        if args.output:
            _json_write(args.output, summary)
        print(json.dumps({
            "status": "clean",
            "phase": PHASE,
            "candidate_count": plan["candidate_count"],
            "decision_counts": plan["decision_counts"],
            "production_snapshot": plan["production_snapshot"],
        }, indent=2, sort_keys=True))
        return 0
    except (STM32F7PolicyError, AdmissionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
