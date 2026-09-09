#!/usr/bin/env python3
"""Phase 4.8C deterministic STM32G0 metadata-policy planner.

Retained Phase 4.8B evidence owns commercial identity/lifecycle. Official ST
ordering-information datasheets own metadata semantics. OpenOCD routing and
CMSIS aliases are explicitly outside this phase. No Production write is allowed.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError, CandidateManualReview, CandidateReject, file_sha256, read_csv, read_json,
)
from stm32g0_metadata_policy import (
    DATASHEET_AUTHORITIES, EXPECTED_ACTIVE_CANDIDATE_COUNT, METADATA_FIELDS,
    SUPPORTED_BASE_DEVICES, build_candidate_inputs, build_metadata_row,
)
from validate_stm32g0_phase4_8b_retained_evidence import BASELINE as DISCOVERY_BASELINE, EVIDENCE as EVIDENCE_DIR, main as validate_retained

HERE = Path(__file__).resolve().parent
PHASE = "4.8C"
DISCOVERY_PHASE = "4.8B"
ADMISSION_PHASE = "4.8D"
ADAPTER_ID = "stm32g0-phase4.8c-metadata"
DEFAULT_POLICY_BASELINE = HERE / "stm32g0-phase4.8c-policy-baseline.json"
DEFAULT_PRODUCTION_MANIFEST = HERE / "stm32g0-phase4.8c-production-manifest-prestate.json"
EXPECTED_PRODUCTION_EXACT_COUNT = 563
EXPECTED_PRODUCTION_BASE_DEVICE_COUNT = 197
EXPECTED_PRODUCTION_FAMILY_COUNTS = {
    "STM32F0": 42, "STM32F1": 75, "STM32F2": 33,
    "STM32F3": 10, "STM32F4": 384, "STM32F7": 19,
}

POLICY_EVIDENCE = {
    "ordering_information": dict(sorted(DATASHEET_AUTHORITIES.items())),
    "semantic_decisions": {
        "pin_C": "48",
        "flash_4": "16 KiB", "flash_6": "32 KiB", "flash_8": "64 KiB",
        "flash_B": "128 KiB", "flash_C": "256 KiB", "flash_E": "512 KiB",
        "package_T": "LQFP", "package_U": "UFQFPN",
        "temperature_6": "-40 to 85 C",
        "temperature_7": "-40 to 105 C",
        "temperature_3": "-40 to 125 C",
        "option_blank": "standard product version / tray-or-unspecified packing as represented by exact ICPN",
        "option_TR": "tape and reel packing",
        "option_N": "ST N product version; preserve exact identity and physical pinout variant",
        "option_NTR": "ST N product version with tape and reel packing; supported by ordering grammar but absent from retained 49-candidate set",
        "identity_lifecycle_authority": "retained Phase 4.8B official ST dual-surface evidence",
        "metadata_authority": "official ST ordering information",
        "openocd_role": "not a metadata authority; routing/capability gate deferred to Phase 4.8D",
        "cmsis_role": "alias surface only; never commercial identity or metadata authority",
        "n_version_boundary": "N must never be normalized away; retained STM32G0B1CBT6N and STM32G0B1CBU6N remain distinct exact ICPNs",
    },
}


class STM32G0PolicyError(AdmissionError):
    pass


def _json_write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def metadata_contract() -> dict[str, Any]:
    return {
        "bounded_active_candidate_count": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "bounded_active_base_devices": sorted(SUPPORTED_BASE_DEVICES),
        "openocd_routing_gates_metadata": False,
        "cmsis_alias_gates_metadata": False,
        "capability_mapping_deferred_to": ADMISSION_PHASE,
        "n_product_version_preserved": True,
        "production_write_authorized": False,
    }


def production_snapshot(manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise STM32G0PolicyError("Production manifest sources must be a list")
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise STM32G0PolicyError("Production manifest source must be an object")
        family, relative, declared = source.get("family"), source.get("path"), source.get("row_count")
        if not isinstance(family, str) or not isinstance(relative, str) or not isinstance(declared, int):
            raise STM32G0PolicyError("Production manifest source is incomplete")
        if family == "STM32G0":
            raise STM32G0PolicyError("Phase 4.8C requires STM32G0 absent from Production prestate")
        source_path = (manifest_path.parent / relative).resolve()
        _, rows = read_csv(source_path)
        if len(rows) != declared or any(row.get("family") != family for row in rows):
            raise STM32G0PolicyError(f"{family}: Production source drifted")
        family_counts[family] = len(rows)
        base_devices.update((family, row.get("base_device", "")) for row in rows)
    if family_counts != EXPECTED_PRODUCTION_FAMILY_COUNTS:
        raise STM32G0PolicyError(f"Phase 4.8C Production family counts drifted: {family_counts}")
    exact_count = sum(family_counts.values())
    if exact_count != EXPECTED_PRODUCTION_EXACT_COUNT:
        raise STM32G0PolicyError("Phase 4.8C Production exact ICPN count drifted")
    if len(base_devices) != EXPECTED_PRODUCTION_BASE_DEVICE_COUNT:
        raise STM32G0PolicyError(f"Phase 4.8C Production Base Device count drifted: {len(base_devices)}")
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(base_devices),
        "family_exact_icpn_counts": family_counts,
        "stm32g0_exact_icpn_count": 0,
    }


def _metadata_distribution(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    fields = ("flash_size", "package", "pin_count", "temperature_grade", "option_suffix")
    return {field: dict(sorted(Counter(row[field] for row in rows).items())) for field in fields}


def build_policy_plan(*, production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    if validate_retained() != 0:
        raise STM32G0PolicyError("Phase 4.8B retained evidence validator failed")
    provenance = read_json(EVIDENCE_DIR / "provenance.json")
    discovery_baseline = read_json(DISCOVERY_BASELINE)
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise STM32G0PolicyError("retained evidence requires evidence_id")
    if provenance.get("commercial_identity_clean") is not True or provenance.get("production_admission_ready") is not False:
        raise STM32G0PolicyError("Phase 4.8B retained evidence is not Phase 4.8C policy eligible")

    candidate_inputs = build_candidate_inputs(discovery_baseline=discovery_baseline, evidence_id=evidence_id)
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
                decision = "manual_review_required"; issues.append(str(exc))
            except CandidateReject as exc:
                decision = "reject"; issues.append(str(exc))
        counts[decision] += 1
        candidates.append({
            "manufacturer": candidate.get("manufacturer"), "base_device": candidate.get("base_device"),
            "icpn": icpn, "decision": decision, "issues": issues, "metadata": row,
        })
    candidates.sort(key=lambda item: (str(item["base_device"]), str(item["icpn"])))
    metadata_rows = [item["metadata"] for item in candidates if item["metadata"] is not None]
    return {
        "schema_version": 1, "phase": PHASE, "family": "STM32G0", "adapter_id": ADAPTER_ID,
        "discovery_phase": DISCOVERY_PHASE, "admission_phase": ADMISSION_PHASE,
        "evidence_id": evidence_id, "candidate_count": len(candidates),
        "decision_counts": {
            "metadata_ready": counts["metadata_ready"],
            "manual_review_required": counts["manual_review_required"],
            "reject": counts["reject"],
        },
        "issues": sorted({issue for item in candidates for issue in item["issues"]}),
        "candidates": candidates,
        "metadata_distribution": _metadata_distribution(metadata_rows),
        "inputs": {
            "retained_evidence_directory": EVIDENCE_DIR.name,
            "retained_discovery_baseline": DISCOVERY_BASELINE.name,
            "retained_discovery_baseline_sha256": file_sha256(DISCOVERY_BASELINE),
            "retained_evidence_manifest_sha256": file_sha256(EVIDENCE_DIR / "manifest.json"),
            "production_manifest": production_manifest_path.name,
            "production_manifest_sha256": file_sha256(production_manifest_path),
            "openocd_catalog_bound": False,
            "cmsis_alias_surface_bound": False,
        },
        "production_snapshot": production_snapshot(production_manifest_path),
        "metadata_contract": metadata_contract(), "policy_evidence": POLICY_EVIDENCE,
        "canonical_dataset_admission": "deferred", "production_write_applied": False,
        "exact_icpn_admission_deferred": True, "openocd_routing_gate_applied": False,
        "cmsis_alias_gate_applied": False, "capability_mapping_deferred": True,
        "programming_algorithm_equivalence_claimed": False, "runtime_support_claimed": False,
        "full_stm32g0_surface_covered": False, "fail_closed": True,
    }


def policy_plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        plan.get("phase") == PHASE and plan.get("family") == "STM32G0"
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("candidate_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("decision_counts") == {"metadata_ready": 49, "manual_review_required": 0, "reject": 0}
        and plan.get("issues") == []
        and {item.get("base_device") for item in plan.get("candidates", [])} == set(SUPPORTED_BASE_DEVICES)
        and plan.get("metadata_distribution", {}).get("option_suffix") == {"": 27, "N": 2, "TR": 20}
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count") == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts") == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32g0_exact_icpn_count") == 0
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_write_applied") is False and plan.get("exact_icpn_admission_deferred") is True
        and plan.get("openocd_routing_gate_applied") is False and plan.get("cmsis_alias_gate_applied") is False
        and plan.get("capability_mapping_deferred") is True
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("runtime_support_claimed") is False and plan.get("full_stm32g0_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def policy_summary(plan: dict[str, Any]) -> dict[str, Any]:
    rows = [item["metadata"] for item in plan["candidates"]]
    return {
        "schema_version": 1, "phase": PHASE, "family": "STM32G0", "adapter_id": ADAPTER_ID,
        "evidence_id": plan["evidence_id"],
        "retained_evidence_directory": plan["inputs"]["retained_evidence_directory"],
        "retained_discovery_baseline_sha256": plan["inputs"]["retained_discovery_baseline_sha256"],
        "retained_evidence_manifest_sha256": plan["inputs"]["retained_evidence_manifest_sha256"],
        "candidate_count": plan["candidate_count"],
        "base_devices": sorted({item["base_device"] for item in plan["candidates"]}),
        "policy_ready_exact_icpns": sorted(item["icpn"] for item in plan["candidates"]),
        "decision_counts": plan["decision_counts"], "metadata_contract": plan["metadata_contract"],
        "metadata_distribution": plan["metadata_distribution"], "metadata_rows": rows,
        "policy_evidence": plan["policy_evidence"], "production_snapshot": plan["production_snapshot"],
        "production_manifest_sha256": plan["inputs"]["production_manifest_sha256"],
        "production_write_applied": False, "exact_icpn_admission_deferred": True,
        "openocd_routing_gate_applied": False, "cmsis_alias_gate_applied": False,
        "capability_mapping_deferred": True, "programming_algorithm_equivalence_claimed": False,
        "runtime_support_claimed": False, "full_stm32g0_surface_covered": False, "fail_closed": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_POLICY_BASELINE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    plan = build_policy_plan()
    if not policy_plan_is_clean(plan):
        raise STM32G0PolicyError("Phase 4.8C metadata policy plan is not clean")
    summary = policy_summary(plan)
    if args.write_baseline:
        _json_write(args.baseline, summary)
    elif summary != read_json(args.baseline):
        raise STM32G0PolicyError("Phase 4.8C policy baseline drifted")
    if args.output:
        _json_write(args.output, summary)
    print(json.dumps({
        "candidate_count": summary["candidate_count"], "decision_counts": summary["decision_counts"],
        "metadata_distribution": summary["metadata_distribution"],
        "production_snapshot": summary["production_snapshot"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
