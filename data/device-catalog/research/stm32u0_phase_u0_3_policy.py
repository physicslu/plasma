#!/usr/bin/env python3
"""STM32U0 U0.3 deterministic manufacturer-authoritative metadata policy planner."""
from __future__ import annotations

import argparse
import hashlib
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
from stm32u0_metadata_policy import (
    DEFAULT_ORDERING_AUTHORITY,
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    FAMILY,
    METADATA_FIELDS,
    SUPPORTED_BASE_DEVICES,
    build_candidate_inputs,
    build_metadata_row,
    load_ordering_authority,
)
from validate_stm32u0_phase_u0_2_retained_evidence import (
    BASELINE as DISCOVERY_BASELINE,
    EVIDENCE as EVIDENCE_DIR,
    EXPECTED_EVIDENCE_ID,
    TARGETS as RETAINED_TARGETS,
    main as validate_retained,
)

HERE = Path(__file__).resolve().parent
PHASE = "U0.3"
DISCOVERY_PHASE = "U0.2"
ADMISSION_PHASE = "U0.4"
ADAPTER_ID = "stm32u0-u0.3-metadata"
DEFAULT_POLICY_BASELINE = HERE / "stm32u0-phase-u0.3-policy-baseline.json"
DEFAULT_PRODUCTION_MANIFEST = HERE / "stm32u0-phase-u0.3-production-manifest-prestate.json"
EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB = "34ad9299ff0c063a8c8b5de1c253dfee47b63428"
EXPECTED_PRODUCTION_EXACT_COUNT = 635
EXPECTED_PRODUCTION_BASE_DEVICE_COUNT = 217
EXPECTED_PRODUCTION_FAMILY_COUNTS = {
    "STM32F0": 42,
    "STM32F1": 75,
    "STM32F2": 33,
    "STM32F3": 10,
    "STM32F4": 384,
    "STM32F7": 19,
    "STM32G0": 47,
    "STM32G4": 25,
}
EXPECTED_METADATA_DISTRIBUTION = {
    "flash_size": {"128 KiB": 13, "16 KiB": 4, "256 KiB": 28, "32 KiB": 7, "64 KiB": 16},
    "option_suffix": {"": 52, "TR": 16},
    "package": {"LQFP": 27, "TSSOP": 5, "UFBGA": 10, "UFQFPN": 26},
    "pin_count": {"20": 5, "32": 14, "48": 22, "64": 15, "80": 8, "81": 4},
    "temperature_grade": {"-40 to 125 C": 13, "-40 to 85 C": 55},
}


class STM32U0PolicyError(AdmissionError):
    pass


def _json_write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def _metadata_rows_sha256(rows: list[dict[str, str]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def metadata_contract() -> dict[str, Any]:
    return {
        "bounded_active_candidate_count": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "bounded_active_base_devices": sorted(SUPPORTED_BASE_DEVICES),
        "identity_lifecycle_authority": "retained U0.2 official ST Quality & Reliability exact Part Number + Marketing Status evidence",
        "metadata_authority": "official ST datasheet Ordering Information",
        "openocd_routing_gates_metadata": False,
        "cmsis_alias_gates_metadata": False,
        "scope_expansion_authorized": False,
        "canonical_admission_authorized": False,
        "capability_mapping_deferred_to": ADMISSION_PHASE,
        "production_write_authorized": False,
        "programming_policy_defined": False,
        "flash_geometry_qualified": False,
        "option_security_semantics_qualified": False,
        "physical_hil_qualified": False,
        "runtime_programming_support_claimed": False,
    }


def production_snapshot(manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    if _git_blob_sha(manifest_path) != EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB:
        raise STM32U0PolicyError("U0.3 Production prestate blob drifted")
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise STM32U0PolicyError("Production prestate sources must be a list")
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise STM32U0PolicyError("Production prestate source must be an object")
        family = source.get("family")
        relative = source.get("path")
        declared = source.get("row_count")
        if not isinstance(family, str) or not isinstance(relative, str) or not isinstance(declared, int):
            raise STM32U0PolicyError("Production prestate source is incomplete")
        if family == FAMILY:
            raise STM32U0PolicyError("U0.3 requires STM32U0 absent from Production prestate")
        source_path = (manifest_path.parent / relative).resolve()
        _, rows = read_csv(source_path)
        if len(rows) != declared or any(row.get("family") != family for row in rows):
            raise STM32U0PolicyError(f"{family}: Production source drifted relative to U0.3 prestate")
        family_counts[family] = len(rows)
        base_devices.update((family, row.get("base_device", "")) for row in rows)
    if family_counts != EXPECTED_PRODUCTION_FAMILY_COUNTS:
        raise STM32U0PolicyError(f"U0.3 Production family counts drifted: {family_counts}")
    exact_count = sum(family_counts.values())
    if exact_count != EXPECTED_PRODUCTION_EXACT_COUNT:
        raise STM32U0PolicyError("U0.3 Production exact ICPN count drifted")
    if len(base_devices) != EXPECTED_PRODUCTION_BASE_DEVICE_COUNT:
        raise STM32U0PolicyError(f"U0.3 Production Base Device count drifted: {len(base_devices)}")
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(base_devices),
        "family_exact_icpn_counts": family_counts,
        "stm32u0_exact_icpn_count": 0,
        "source_manifest_git_blob_sha": EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB,
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
                "ordering_section": record["ordering_section"],
                "pdf_page": record["pdf_page"],
                "review": record["review"],
                "current_revision_check": record["current_revision_check"],
                "retained_semantics": record["retained_semantics"],
            }
            for series, record in sorted(records.items())
        ],
        "semantic_decisions": {
            "u031_pin_package": "F/P=20, K/U=32, C/T=48, C/U=48, R/I=64, R/T=64",
            "u073_u083_m_t": "M/T resolves to LQFP80",
            "u073_u083_m_i": "M/I resolves to UFBGA81",
            "temperature_6": "-40 to 85 C",
            "temperature_3": "-40 to 125 C",
            "option_blank": "standard",
            "option_TR": "tape and reel",
            "openocd_role": "routing observation only; not metadata authority",
            "cmsis_role": "alias/name surface only; not commercial identity or metadata authority",
        },
    }


def build_policy_plan(*, production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    if validate_retained() != 0:
        raise STM32U0PolicyError("U0.2 retained evidence validator failed")
    provenance = read_json(EVIDENCE_DIR / "provenance.json")
    discovery_baseline = read_json(DISCOVERY_BASELINE)
    if provenance.get("evidence_id") != EXPECTED_EVIDENCE_ID:
        raise STM32U0PolicyError("U0.2 retained evidence identity drifted")
    if (
        provenance.get("bounded_discovery_clean") is not True
        or provenance.get("commercial_identity_clean") is not True
        or provenance.get("exact_icpn_candidate_count") != EXPECTED_ACTIVE_CANDIDATE_COUNT
        or provenance.get("target_count") != 26
        or provenance.get("source_unavailable_exclusion_count") != 0
        or provenance.get("production_admission_ready") is not False
    ):
        raise STM32U0PolicyError("U0.2 clean commercial boundary drifted")
    if discovery_baseline.get("claims", {}).get("production_write_authorized") is not False:
        raise STM32U0PolicyError("U0.2 cannot authorize Production")

    candidate_inputs = build_candidate_inputs(evidence_id=EXPECTED_EVIDENCE_ID)
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
        "evidence_id": EXPECTED_EVIDENCE_ID,
        "candidate_count": len(candidates),
        "decision_counts": {"metadata_ready": counts["metadata_ready"], "manual_review_required": counts["manual_review_required"], "reject": counts["reject"]},
        "issues": sorted({issue for item in candidates for issue in item["issues"]}),
        "candidates": candidates,
        "metadata_distribution": distribution,
        "inputs": {
            "retained_discovery_baseline": DISCOVERY_BASELINE.name,
            "retained_discovery_baseline_sha256": file_sha256(DISCOVERY_BASELINE),
            "retained_targets": str(RETAINED_TARGETS.relative_to(HERE)),
            "retained_targets_sha256": file_sha256(RETAINED_TARGETS),
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
        "flash_geometry_qualified": False,
        "option_security_semantics_qualified": False,
        "physical_hil_qualified": False,
        "runtime_support_claimed": False,
        "full_stm32u0_surface_covered": False,
        "fail_closed": True,
    }


def policy_plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        plan.get("phase") == PHASE
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("candidate_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("decision_counts") == {"metadata_ready": 68, "manual_review_required": 0, "reject": 0}
        and plan.get("issues") == []
        and {item.get("base_device") for item in plan.get("candidates", [])} == set(SUPPORTED_BASE_DEVICES)
        and plan.get("metadata_distribution") == EXPECTED_METADATA_DISTRIBUTION
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count") == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts") == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32u0_exact_icpn_count") == 0
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_write_applied") is False
        and plan.get("exact_icpn_admission_deferred") is True
        and plan.get("openocd_routing_gate_applied") is False
        and plan.get("cmsis_alias_gate_applied") is False
        and plan.get("capability_mapping_deferred") is True
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("flash_geometry_qualified") is False
        and plan.get("option_security_semantics_qualified") is False
        and plan.get("physical_hil_qualified") is False
        and plan.get("runtime_support_claimed") is False
        and plan.get("full_stm32u0_surface_covered") is False
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
        "candidate_count": plan["candidate_count"],
        "base_devices": sorted({item["base_device"] for item in plan["candidates"]}),
        "policy_ready_exact_icpns": sorted(item["icpn"] for item in plan["candidates"]),
        "decision_counts": plan["decision_counts"],
        "metadata_contract": plan["metadata_contract"],
        "metadata_distribution": plan["metadata_distribution"],
        "metadata_row_count": len(rows),
        "metadata_rows_sha256": _metadata_rows_sha256(rows),
        "policy_evidence": plan["policy_evidence"],
        "inputs": plan["inputs"],
        "production_snapshot": plan["production_snapshot"],
        "production_write_applied": False,
        "exact_icpn_admission_deferred": True,
        "openocd_routing_gate_applied": False,
        "cmsis_alias_gate_applied": False,
        "capability_mapping_deferred": True,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_qualified": False,
        "option_security_semantics_qualified": False,
        "physical_hil_qualified": False,
        "runtime_support_claimed": False,
        "full_stm32u0_surface_covered": False,
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
        raise STM32U0PolicyError("U0.3 metadata policy plan is not clean")
    summary = policy_summary(plan)
    if args.write_baseline:
        _json_write(args.baseline, summary)
    elif summary != read_json(args.baseline):
        raise STM32U0PolicyError("U0.3 policy baseline drifted")
    if args.output:
        _json_write(args.output, summary)
    print(json.dumps({"candidate_count": summary["candidate_count"], "decision_counts": summary["decision_counts"], "metadata_rows_sha256": summary["metadata_rows_sha256"], "metadata_distribution": summary["metadata_distribution"], "production_snapshot": summary["production_snapshot"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
