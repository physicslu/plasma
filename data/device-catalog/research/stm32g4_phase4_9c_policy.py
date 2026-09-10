#!/usr/bin/env python3
"""Phase 4.9C deterministic STM32G4 metadata-policy planner.

Retained Phase 4.9B evidence owns commercial identity/lifecycle. Official ST
ordering-information tables own metadata semantics. OpenOCD routing and CMSIS
aliases are explicitly outside this phase. No Production write is allowed.

Phase 4.9B is intentionally commercially incomplete: three deterministic Base
Devices have canonical official-ST product-page HTTP 404 dispositions. Phase
4.9C accepts that exact bounded state and projects only the 25 retained Active
exact identities from the other eight Base Devices.
"""
from __future__ import annotations

import argparse
import json
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
from stm32g4_metadata_policy import (
    DEFAULT_ORDERING_AUTHORITY,
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    EXPECTED_PROPOSAL_EXCLUSIONS,
    METADATA_FIELDS,
    SOURCE_UNAVAILABLE_BASES,
    SUPPORTED_BASE_DEVICES,
    build_candidate_inputs,
    build_metadata_row,
    load_ordering_authority,
)
from validate_stm32g4_phase4_9b_retained_evidence import (
    BASELINE as DISCOVERY_BASELINE,
    EVIDENCE as EVIDENCE_DIR,
    main as validate_retained,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.9C"
DISCOVERY_PHASE = "4.9B"
ADMISSION_PHASE = "4.9D"
ADAPTER_ID = "stm32g4-phase4.9c-metadata"
DEFAULT_POLICY_BASELINE = HERE / "stm32g4-phase4.9c-policy-baseline.json"
DEFAULT_PRODUCTION_MANIFEST = HERE / "stm32g4-phase4.9c-production-manifest-prestate.json"
EXPECTED_PRODUCTION_EXACT_COUNT = 610
EXPECTED_PRODUCTION_BASE_DEVICE_COUNT = 209
EXPECTED_PRODUCTION_FAMILY_COUNTS = {
    "STM32F0": 42,
    "STM32F1": 75,
    "STM32F2": 33,
    "STM32F3": 10,
    "STM32F4": 384,
    "STM32F7": 19,
    "STM32G0": 47,
}
EXPECTED_METADATA_DISTRIBUTION = {
    "flash_size": {"128 KiB": 10, "256 KiB": 5, "32 KiB": 2, "512 KiB": 8},
    "option_suffix": {"": 20, "TR": 5},
    "package": {"LQFP": 14, "UFQFPN": 10, "WLCSP": 1},
    "pin_count": {"48": 24, "49": 1},
    "temperature_grade": {"-40 to 125 C": 6, "-40 to 85 C": 19},
}


class STM32G4PolicyError(AdmissionError):
    pass


def _json_write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def metadata_contract() -> dict[str, Any]:
    return {
        "bounded_active_candidate_count": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "bounded_active_base_devices": sorted(SUPPORTED_BASE_DEVICES),
        "source_unavailable_base_devices": sorted(SOURCE_UNAVAILABLE_BASES),
        "proposal_exact_identity_exclusions": sorted(EXPECTED_PROPOSAL_EXCLUSIONS),
        "openocd_routing_gates_metadata": False,
        "cmsis_alias_gates_metadata": False,
        "package_specific_pin_count_required": True,
        "wlcsp49_exception": "STM32G441CBY6TR decodes C/Y as WLCSP49; C must not be normalized globally to 48 pins",
        "capability_mapping_deferred_to": ADMISSION_PHASE,
        "production_write_authorized": False,
    }


def production_snapshot(manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise STM32G4PolicyError("Production manifest sources must be a list")
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise STM32G4PolicyError("Production manifest source must be an object")
        family = source.get("family")
        relative = source.get("path")
        declared = source.get("row_count")
        if not isinstance(family, str) or not isinstance(relative, str) or not isinstance(declared, int):
            raise STM32G4PolicyError("Production manifest source is incomplete")
        if family == FAMILY:
            raise STM32G4PolicyError("Phase 4.9C requires STM32G4 absent from Production prestate")
        source_path = (manifest_path.parent / relative).resolve()
        _, rows = read_csv(source_path)
        if len(rows) != declared or any(row.get("family") != family for row in rows):
            raise STM32G4PolicyError(f"{family}: Production source drifted")
        family_counts[family] = len(rows)
        base_devices.update((family, row.get("base_device", "")) for row in rows)
    if family_counts != EXPECTED_PRODUCTION_FAMILY_COUNTS:
        raise STM32G4PolicyError(f"Phase 4.9C Production family counts drifted: {family_counts}")
    exact_count = sum(family_counts.values())
    if exact_count != EXPECTED_PRODUCTION_EXACT_COUNT:
        raise STM32G4PolicyError("Phase 4.9C Production exact ICPN count drifted")
    if len(base_devices) != EXPECTED_PRODUCTION_BASE_DEVICE_COUNT:
        raise STM32G4PolicyError(f"Phase 4.9C Production Base Device count drifted: {len(base_devices)}")
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(base_devices),
        "family_exact_icpn_counts": family_counts,
        "stm32g4_exact_icpn_count": 0,
    }


def _metadata_distribution(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    fields = ("flash_size", "package", "pin_count", "temperature_grade", "option_suffix")
    return {field: dict(sorted(Counter(row[field] for row in rows).items())) for field in fields}


def _policy_evidence() -> dict[str, Any]:
    authority_payload = read_json(DEFAULT_ORDERING_AUTHORITY)
    records = load_ordering_authority(DEFAULT_ORDERING_AUTHORITY)
    return {
        "ordering_authority_manifest": DEFAULT_ORDERING_AUTHORITY.name,
        "ordering_authority_manifest_sha256": file_sha256(DEFAULT_ORDERING_AUTHORITY),
        "authority_version": authority_payload.get("authority_version"),
        "ordering_documents": [
            {
                "series": series,
                "datasheet_url": record["datasheet_url"],
                "document_id": record["document_id"],
                "revision": record["revision"],
                "ordering_table": record["ordering_table"],
                "pdf_page": record["pdf_page"],
                "review": record["review"],
                "retained_semantics": record["retained_semantics"],
            }
            for series, record in sorted(records.items())
        ],
        "semantic_decisions": {
            "identity_lifecycle_authority": "retained Phase 4.9B official ST dual-surface evidence",
            "metadata_authority": "official ST datasheet ordering-information tables",
            "c_t_pin_package": "48 physical pins",
            "c_u_pin_package": "48 physical pins",
            "c_y_pin_package": "49 physical balls only where explicitly bound by the retained-series authority",
            "flash_6": "32 KiB",
            "flash_B": "128 KiB",
            "flash_C": "256 KiB",
            "flash_E": "512 KiB",
            "temperature_6": "-40 to 85 C",
            "temperature_3": "-40 to 125 C",
            "option_blank": "standard/programmed-part option as represented by exact ICPN",
            "option_TR": "tape and reel",
            "openocd_role": "not a metadata authority; routing/capability deferred to Phase 4.9D",
            "cmsis_role": "alias/name surface only; not commercial identity or metadata authority",
            "http_404_role": "current canonical source unavailable only; not historical nonexistence",
        },
    }


def build_policy_plan(*, production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    if validate_retained() != 0:
        raise STM32G4PolicyError("Phase 4.9B retained evidence validator failed")
    provenance = read_json(EVIDENCE_DIR / "provenance.json")
    discovery_baseline = read_json(DISCOVERY_BASELINE)
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise STM32G4PolicyError("retained evidence requires evidence_id")
    if provenance.get("bounded_discovery_clean") is not True:
        raise STM32G4PolicyError("Phase 4.9B bounded discovery is not clean")
    if provenance.get("commercial_identity_clean") is not False:
        raise STM32G4PolicyError("Phase 4.9B commercial-incomplete boundary drifted")
    if provenance.get("source_unavailable_exclusion_count") != len(SOURCE_UNAVAILABLE_BASES):
        raise STM32G4PolicyError("Phase 4.9B source-unavailable count drifted")
    if provenance.get("production_admission_ready") is not False:
        raise STM32G4PolicyError("Phase 4.9B cannot already be Production-ready")

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
    distribution = _metadata_distribution(metadata_rows)

    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "discovery_phase": DISCOVERY_PHASE,
        "admission_phase": ADMISSION_PHASE,
        "evidence_id": evidence_id,
        "candidate_count": len(candidates),
        "decision_counts": {
            "metadata_ready": counts["metadata_ready"],
            "manual_review_required": counts["manual_review_required"],
            "reject": counts["reject"],
        },
        "issues": sorted({issue for item in candidates for issue in item["issues"]}),
        "candidates": candidates,
        "metadata_distribution": distribution,
        "inputs": {
            "retained_evidence_directory": EVIDENCE_DIR.name,
            "retained_discovery_baseline": DISCOVERY_BASELINE.name,
            "retained_discovery_baseline_sha256": file_sha256(DISCOVERY_BASELINE),
            "retained_evidence_manifest_sha256": file_sha256(EVIDENCE_DIR / "manifest.json"),
            "ordering_authority_manifest": DEFAULT_ORDERING_AUTHORITY.name,
            "ordering_authority_manifest_sha256": file_sha256(DEFAULT_ORDERING_AUTHORITY),
            "production_manifest": production_manifest_path.name,
            "production_manifest_sha256": file_sha256(production_manifest_path),
            "openocd_catalog_bound": False,
            "cmsis_alias_surface_bound": False,
        },
        "production_snapshot": production_snapshot(production_manifest_path),
        "metadata_contract": metadata_contract(),
        "policy_evidence": _policy_evidence(),
        "canonical_dataset_admission": "deferred",
        "production_write_applied": False,
        "exact_icpn_admission_deferred": True,
        "openocd_routing_gate_applied": False,
        "cmsis_alias_gate_applied": False,
        "capability_mapping_deferred": True,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_support_claimed": False,
        "full_stm32g4_surface_covered": False,
        "fail_closed": True,
    }


def policy_plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        plan.get("phase") == PHASE
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("candidate_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("decision_counts") == {
            "metadata_ready": 25,
            "manual_review_required": 0,
            "reject": 0,
        }
        and plan.get("issues") == []
        and {item.get("base_device") for item in plan.get("candidates", [])} == set(SUPPORTED_BASE_DEVICES)
        and plan.get("metadata_distribution") == EXPECTED_METADATA_DISTRIBUTION
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count") == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts") == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32g4_exact_icpn_count") == 0
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_write_applied") is False
        and plan.get("exact_icpn_admission_deferred") is True
        and plan.get("openocd_routing_gate_applied") is False
        and plan.get("cmsis_alias_gate_applied") is False
        and plan.get("capability_mapping_deferred") is True
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("runtime_support_claimed") is False
        and plan.get("full_stm32g4_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def policy_summary(plan: dict[str, Any]) -> dict[str, Any]:
    rows = [item["metadata"] for item in plan["candidates"]]
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "evidence_id": plan["evidence_id"],
        "retained_evidence_directory": plan["inputs"]["retained_evidence_directory"],
        "retained_discovery_baseline_sha256": plan["inputs"]["retained_discovery_baseline_sha256"],
        "retained_evidence_manifest_sha256": plan["inputs"]["retained_evidence_manifest_sha256"],
        "ordering_authority_manifest": plan["inputs"]["ordering_authority_manifest"],
        "ordering_authority_manifest_sha256": plan["inputs"]["ordering_authority_manifest_sha256"],
        "candidate_count": plan["candidate_count"],
        "base_devices": sorted({item["base_device"] for item in plan["candidates"]}),
        "source_unavailable_base_devices": sorted(SOURCE_UNAVAILABLE_BASES),
        "proposal_exact_identity_exclusions": sorted(EXPECTED_PROPOSAL_EXCLUSIONS),
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
        "cmsis_alias_gate_applied": False,
        "capability_mapping_deferred": True,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_support_claimed": False,
        "full_stm32g4_surface_covered": False,
        "fail_closed": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_POLICY_BASELINE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    plan = build_policy_plan()
    if not policy_plan_is_clean(plan):
        raise STM32G4PolicyError("Phase 4.9C metadata policy plan is not clean")
    summary = policy_summary(plan)
    if args.write_baseline:
        _json_write(args.baseline, summary)
    elif summary != read_json(args.baseline):
        raise STM32G4PolicyError("Phase 4.9C policy baseline drifted")
    if args.output:
        _json_write(args.output, summary)
    print(json.dumps({
        "candidate_count": summary["candidate_count"],
        "decision_counts": summary["decision_counts"],
        "metadata_distribution": summary["metadata_distribution"],
        "production_snapshot": summary["production_snapshot"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
