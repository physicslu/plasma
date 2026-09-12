#!/usr/bin/env python3
"""STM32C0 C0.4 deterministic read-only capability/admission planner.

Consumes the closed C0.3 metadata policy, replays the current bounded OpenOCD
ordering-pattern catalog for all 220 retained Active exact ICPNs, and plans
canonical admission only for identities with one unique route to
`tcl/target/stm32c0x.cfg`.

The expected 11 capability-unresolved identities remain manufacturer-verified
and metadata-ready; they are excluded from canonical admission rather than
reclassified as identity rejects. This phase never writes canonical or
Production state and does not claim Flash algorithm equivalence,
option/security semantics, HIL, physical target qualification, or runtime
programming support.
"""
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
    build_admission_plan as build_framework_plan,
    file_sha256,
    plan_is_clean as framework_plan_is_clean,
    read_csv,
    read_json,
)
from stm32c0_admission_policy import CANONICAL_FIELDS, FAMILY, TARGET_CONFIG, build_canonical_row
from stm32c0_metadata_policy import EXPECTED_ACTIVE_CANDIDATE_COUNT, EXPECTED_EVIDENCE_ID, build_candidate_inputs
from stm32c0_phase_c0_1_foundation import DEFAULT_CATALOG, read_catalog
from stm32c0_phase_c0_2_discovery import resolve_mapping
from stm32c0_phase_c0_3_policy import (
    ADAPTER_ID as METADATA_ADAPTER_ID,
    DEFAULT_POLICY_BASELINE,
    DEFAULT_PRODUCTION_MANIFEST,
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    EXPECTED_PRODUCTION_FAMILY_COUNTS,
    EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB,
    EXPECTED_PRODUCTION_MANIFEST_SHA256,
    build_policy_plan,
    policy_plan_is_clean,
    policy_summary,
)
from validate_stm32c0_phase_c0_2_retained_evidence import EVIDENCE as EVIDENCE_DIR

HERE = Path(__file__).resolve().parent
PHASE = "C0.4"
POLICY_PHASE = "C0.3"
DISCOVERY_PHASE = "C0.2"
PUBLICATION_PHASE = "C0.5"
ADAPTER_ID = "stm32c0-c0.4-admission"
DEFAULT_CANONICAL = HERE / "stm32c0-commercial-icpn.csv"
DEFAULT_FROZEN_PLAN = HERE / "stm32c0-phase-c0.4-admission-plan.json"

EXPECTED_ADMITTABLE_COUNT = 209
EXPECTED_CAPABILITY_UNRESOLVED = frozenset({
    "STM32C051K8U3",
    "STM32C051K8U3TR",
    "STM32C051K8U6",
    "STM32C051K8U6TR",
    "STM32C051K8U7",
    "STM32C051K8U7TR",
    "STM32C071FBY6TR",
    "STM32C071R8I6N",
    "STM32C071RBI6N",
    "STM32C091RBI6",
    "STM32C092RBI6",
})
EXPECTED_CAPABILITY_UNRESOLVED_SHA256 = "32698be0aee4f95360a1b27ddfecd1034d7627e0b223dd8873153b5d96ec5601"
EXPECTED_METADATA_BASELINE_GIT_BLOB = "4272a441f072433b0dfe726f1d97459bbad957f3"
EXPECTED_MAPPING_CATALOG_GIT_BLOB = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_METADATA_ROWS_SHA256 = "94ebe11fda28cb6d7b68c13c7edb4bf8341887f6146d52f72461bc6ef35bee19"
EXPECTED_POLICY_READY_EXACT_SET_SHA256 = "b116f624e971a3be5c947e107589bdb4d1bf5f5b0585ecae71e743cfb7a2649a"
EXPECTED_CANONICAL_EMPTY_SHA256 = "a57ec095b1af22963ef5415d7f3cbc1cd4a920dc6e06a9817dca4d029b714971"


class STM32C0AdmissionError(AdmissionError):
    pass


def _git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def _string_set_sha256(values: set[str] | frozenset[str] | list[str]) -> str:
    payload = "\n".join(sorted(values)).encode("utf-8") + b"\n"
    return hashlib.sha256(payload).hexdigest()


def _canonical_prestate(canonical_path: Path | None) -> tuple[list[str], list[dict[str, str]], bool]:
    if canonical_path is None or not canonical_path.exists():
        return list(CANONICAL_FIELDS), [], True
    fields, rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise STM32C0AdmissionError("STM32C0 canonical CSV schema mismatch")
    if any(row.get("family") not in ("", FAMILY) for row in rows):
        raise STM32C0AdmissionError("STM32C0 canonical CSV contains a foreign family")
    identities = [row.get("icpn", "") for row in rows]
    if len(identities) != len(set(identities)):
        raise STM32C0AdmissionError("STM32C0 canonical CSV contains duplicate ICPNs")
    if rows:
        raise STM32C0AdmissionError(
            f"C0.4 requires zero-row STM32C0 canonical prestate, got {len(rows)}"
        )
    return fields, rows, False


def _is_unique_mapping(mapping: dict[str, Any]) -> bool:
    ordering_pattern = mapping.get("ordering_pattern")
    return (
        mapping.get("status") == "unique"
        and mapping.get("target_config") == TARGET_CONFIG
        and isinstance(ordering_pattern, str)
        and ordering_pattern.endswith("x")
        and bool(ordering_pattern[:-1])
    )


def build_admission_plan(
    *,
    canonical_path: Path | None = DEFAULT_CANONICAL,
    mapping_catalog_path: Path = DEFAULT_CATALOG,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
) -> dict[str, Any]:
    metadata_plan = build_policy_plan()
    if not policy_plan_is_clean(metadata_plan):
        raise STM32C0AdmissionError("C0.3 metadata policy is not clean")
    frozen_metadata = read_json(DEFAULT_POLICY_BASELINE)
    if policy_summary(metadata_plan) != frozen_metadata:
        raise STM32C0AdmissionError("C0.3 metadata policy baseline drifted")
    if _git_blob_sha(DEFAULT_POLICY_BASELINE) != EXPECTED_METADATA_BASELINE_GIT_BLOB:
        raise STM32C0AdmissionError("C0.3 metadata policy baseline bytes drifted")
    if frozen_metadata.get("metadata_rows_sha256") != EXPECTED_METADATA_ROWS_SHA256:
        raise STM32C0AdmissionError("C0.3 canonical metadata row digest drifted")
    if frozen_metadata.get("policy_ready_exact_icpn_set_sha256") != EXPECTED_POLICY_READY_EXACT_SET_SHA256:
        raise STM32C0AdmissionError("C0.3 policy-ready exact-identity set drifted")

    provenance = read_json(EVIDENCE_DIR / "provenance.json")
    if (
        provenance.get("family") != FAMILY
        or provenance.get("phase") != DISCOVERY_PHASE
        or provenance.get("bounded_discovery_clean") is not True
        or provenance.get("active_exact_icpn_candidates") != EXPECTED_ACTIVE_CANDIDATE_COUNT
    ):
        raise STM32C0AdmissionError("C0.2 retained commercial discovery is not clean")

    historical_catalog_blob = provenance.get("openocd_catalog_git_blob")
    current_catalog_blob = _git_blob_sha(mapping_catalog_path)
    if historical_catalog_blob != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
        raise STM32C0AdmissionError("C0.2 historical OpenOCD catalog binding drifted")
    if current_catalog_blob != EXPECTED_MAPPING_CATALOG_GIT_BLOB:
        raise STM32C0AdmissionError(
            "current OpenOCD catalog bytes changed after C0.4 planning boundary"
        )

    if _git_blob_sha(production_manifest_path) != EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB:
        raise STM32C0AdmissionError("C0.3 Production prestate blob drifted")
    if file_sha256(production_manifest_path) != EXPECTED_PRODUCTION_MANIFEST_SHA256:
        raise STM32C0AdmissionError("C0.3 Production prestate SHA-256 drifted")

    catalog_rows = read_catalog(mapping_catalog_path)
    all_identity_candidates = build_candidate_inputs()
    admissible: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    routing = Counter()
    for source_candidate in all_identity_candidates:
        candidate = dict(source_candidate)
        icpn = candidate.get("icpn")
        if not isinstance(icpn, str):
            raise STM32C0AdmissionError("candidate lacks exact ICPN")
        mapping = resolve_mapping(icpn, catalog_rows)
        status = str(mapping.get("status"))
        routing[status] += 1
        candidate["base_mapping"] = mapping
        if _is_unique_mapping(mapping):
            admissible.append(candidate)
        else:
            unresolved.append({
                "manufacturer": candidate["manufacturer"],
                "base_device": candidate["base_device"],
                "icpn": icpn,
                "identity_status": "manufacturer_verified_active",
                "metadata_status": "metadata_ready",
                "capability_status": "openocd_ordering_pattern_unresolved",
                "mapping": mapping,
                "policy_action": "exclude_from_canonical_admission_until_positive_route_evidence",
            })

    unresolved_icpns = {item["icpn"] for item in unresolved}
    if unresolved_icpns != set(EXPECTED_CAPABILITY_UNRESOLVED):
        raise STM32C0AdmissionError(
            f"C0.4 capability-unresolved set drifted: {sorted(unresolved_icpns)}"
        )
    if _string_set_sha256(unresolved_icpns) != EXPECTED_CAPABILITY_UNRESOLVED_SHA256:
        raise STM32C0AdmissionError("C0.4 capability-unresolved exact-set digest drifted")
    if len(admissible) != EXPECTED_ADMITTABLE_COUNT:
        raise STM32C0AdmissionError(
            f"C0.4 expected {EXPECTED_ADMITTABLE_COUNT} uniquely routable candidates, got {len(admissible)}"
        )
    if routing != Counter({"unique": EXPECTED_ADMITTABLE_COUNT, "unmapped": len(EXPECTED_CAPABILITY_UNRESOLVED)}):
        raise STM32C0AdmissionError(f"C0.4 current mapping replay drifted: {dict(routing)}")

    fields, canonical_rows, absent = _canonical_prestate(canonical_path)
    plan = build_framework_plan(
        candidate_inputs=admissible,
        canonical_fields=fields,
        canonical_rows=canonical_rows,
        source_provenance={**provenance, "evidence_id": EXPECTED_EVIDENCE_ID},
        input_bindings={
            "family_adapter": ADAPTER_ID,
            "metadata_adapter": METADATA_ADAPTER_ID,
            "policy_phase": POLICY_PHASE,
            "policy_baseline": DEFAULT_POLICY_BASELINE.name,
            "policy_baseline_git_blob_sha": EXPECTED_METADATA_BASELINE_GIT_BLOB,
            "metadata_rows_sha256": EXPECTED_METADATA_ROWS_SHA256,
            "policy_ready_exact_icpn_set_sha256": EXPECTED_POLICY_READY_EXACT_SET_SHA256,
            "retained_evidence_directory": EVIDENCE_DIR.name,
            "mapping_catalog": mapping_catalog_path.name,
            "mapping_catalog_git_blob_sha": current_catalog_blob,
            "historical_c0_2_mapping_catalog_git_blob_sha": historical_catalog_blob,
            "canonical_dataset": DEFAULT_CANONICAL.name,
            "canonical_dataset_absent_before_admission": absent,
            "production_manifest": str(production_manifest_path.relative_to(HERE.parent)),
            "production_manifest_git_blob_sha": EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB,
            "production_manifest_sha256": EXPECTED_PRODUCTION_MANIFEST_SHA256,
        },
        row_builder=build_canonical_row,
    )
    plan.update({
        "phase": PHASE,
        "policy_phase": POLICY_PHASE,
        "discovery_phase": DISCOVERY_PHASE,
        "publication_phase": PUBLICATION_PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "metadata_adapter_id": METADATA_ADAPTER_ID,
        "manufacturer_verified_identity_count": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "metadata_ready_count": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "bounded_commercial_surface_complete": True,
        "capability_admittable_count": EXPECTED_ADMITTABLE_COUNT,
        "capability_unresolved_count": len(unresolved),
        "capability_unresolved": sorted(unresolved, key=lambda item: item["icpn"]),
        "capability_unresolved_exact_icpns": sorted(unresolved_icpns),
        "capability_unresolved_exact_set_sha256": EXPECTED_CAPABILITY_UNRESOLVED_SHA256,
        "capability_unresolved_is_identity_rejection": False,
        "current_mapping_replay": {
            "unique": routing["unique"],
            "ambiguous": routing["ambiguous"],
            "unmapped": routing["unmapped"],
        },
        "production_snapshot": metadata_plan["production_snapshot"],
        "metadata_policy_clean": True,
        "capability_mapping_gate_applied": True,
        "required_target_config": TARGET_CONFIG,
        "canonical_write_applied": False,
        "production_write_applied": False,
        "programming_algorithm_equivalence_claimed": False,
        "flash_geometry_equivalence_claimed": False,
        "option_security_semantics_claimed": False,
        "physical_target_qualification_claimed": False,
        "hil_qualification_claimed": False,
        "runtime_programming_support_claimed": False,
        "full_stm32c0_surface_covered": False,
        "fail_closed": True,
    })
    return plan


def admission_plan_is_clean(plan: dict[str, Any]) -> bool:
    unresolved = plan.get("capability_unresolved_exact_icpns")
    return (
        framework_plan_is_clean(plan)
        and plan.get("phase") == PHASE
        and plan.get("policy_phase") == POLICY_PHASE
        and plan.get("discovery_phase") == DISCOVERY_PHASE
        and plan.get("publication_phase") == PUBLICATION_PHASE
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == ADAPTER_ID
        and plan.get("metadata_adapter_id") == METADATA_ADAPTER_ID
        and plan.get("manufacturer_verified_identity_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("metadata_ready_count") == EXPECTED_ACTIVE_CANDIDATE_COUNT
        and plan.get("candidate_count") == EXPECTED_ADMITTABLE_COUNT
        and plan.get("capability_admittable_count") == EXPECTED_ADMITTABLE_COUNT
        and plan.get("decision_counts") == {
            "admit": EXPECTED_ADMITTABLE_COUNT,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        }
        and plan.get("canonical_rows_before") == 0
        and plan.get("canonical_dataset_admission") == "planned"
        and plan.get("bounded_commercial_surface_complete") is True
        and plan.get("capability_unresolved_count") == len(EXPECTED_CAPABILITY_UNRESOLVED)
        and set(unresolved or []) == set(EXPECTED_CAPABILITY_UNRESOLVED)
        and plan.get("capability_unresolved_exact_set_sha256") == EXPECTED_CAPABILITY_UNRESOLVED_SHA256
        and plan.get("capability_unresolved_is_identity_rejection") is False
        and plan.get("current_mapping_replay") == {"unique": 209, "ambiguous": 0, "unmapped": 11}
        and plan.get("production_snapshot", {}).get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT_COUNT
        and plan.get("production_snapshot", {}).get("base_device_count") == EXPECTED_PRODUCTION_BASE_DEVICE_COUNT
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts") == EXPECTED_PRODUCTION_FAMILY_COUNTS
        and plan.get("production_snapshot", {}).get("stm32c0_exact_icpn_count") == 0
        and plan.get("metadata_policy_clean") is True
        and plan.get("capability_mapping_gate_applied") is True
        and plan.get("required_target_config") == TARGET_CONFIG
        and plan.get("canonical_write_applied") is False
        and plan.get("production_write_applied") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("flash_geometry_equivalence_claimed") is False
        and plan.get("option_security_semantics_claimed") is False
        and plan.get("physical_target_qualification_claimed") is False
        and plan.get("hil_qualification_claimed") is False
        and plan.get("runtime_programming_support_claimed") is False
        and plan.get("full_stm32c0_surface_covered") is False
        and plan.get("fail_closed") is True
    )


def admission_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "adapter_id": ADAPTER_ID,
        "metadata_adapter_id": METADATA_ADAPTER_ID,
        "evidence_id": plan.get("evidence_id"),
        "manufacturer_verified_identity_count": plan.get("manufacturer_verified_identity_count"),
        "metadata_ready_count": plan.get("metadata_ready_count"),
        "capability_admittable_count": plan.get("capability_admittable_count"),
        "capability_unresolved_count": plan.get("capability_unresolved_count"),
        "capability_unresolved_exact_icpns": plan.get("capability_unresolved_exact_icpns"),
        "capability_unresolved_exact_set_sha256": plan.get("capability_unresolved_exact_set_sha256"),
        "capability_unresolved_is_identity_rejection": plan.get("capability_unresolved_is_identity_rejection"),
        "decision_counts": plan.get("decision_counts"),
        "canonical_rows_before": plan.get("canonical_rows_before"),
        "canonical_dataset_admission": plan.get("canonical_dataset_admission"),
        "canonical_dataset_absent_before_admission": (plan.get("inputs") or {}).get(
            "canonical_dataset_absent_before_admission"
        ),
        "canonical_input_sha256": (plan.get("inputs") or {}).get("canonical_input_sha256"),
        "required_target_config": plan.get("required_target_config"),
        "current_mapping_replay": plan.get("current_mapping_replay"),
        "inputs": {
            "policy_baseline_git_blob_sha": (plan.get("inputs") or {}).get(
                "policy_baseline_git_blob_sha"
            ),
            "metadata_rows_sha256": (plan.get("inputs") or {}).get("metadata_rows_sha256"),
            "policy_ready_exact_icpn_set_sha256": (plan.get("inputs") or {}).get(
                "policy_ready_exact_icpn_set_sha256"
            ),
            "mapping_catalog_git_blob_sha": (plan.get("inputs") or {}).get(
                "mapping_catalog_git_blob_sha"
            ),
            "historical_c0_2_mapping_catalog_git_blob_sha": (plan.get("inputs") or {}).get(
                "historical_c0_2_mapping_catalog_git_blob_sha"
            ),
            "production_manifest_git_blob_sha": (plan.get("inputs") or {}).get(
                "production_manifest_git_blob_sha"
            ),
            "production_manifest_sha256": (plan.get("inputs") or {}).get(
                "production_manifest_sha256"
            ),
        },
        "production_snapshot": plan.get("production_snapshot"),
        "claims": {
            "canonical_write_applied": plan.get("canonical_write_applied"),
            "production_write_applied": plan.get("production_write_applied"),
            "programming_algorithm_equivalence_claimed": plan.get("programming_algorithm_equivalence_claimed"),
            "flash_geometry_equivalence_claimed": plan.get("flash_geometry_equivalence_claimed"),
            "option_security_semantics_claimed": plan.get("option_security_semantics_claimed"),
            "physical_target_qualification_claimed": plan.get("physical_target_qualification_claimed"),
            "hil_qualification_claimed": plan.get("hil_qualification_claimed"),
            "runtime_programming_support_claimed": plan.get("runtime_programming_support_claimed"),
            "full_stm32c0_surface_covered": plan.get("full_stm32c0_surface_covered"),
        },
        "fail_closed": plan.get("fail_closed"),
    }


def validate_frozen_plan(plan: dict[str, Any], path: Path = DEFAULT_FROZEN_PLAN) -> None:
    expected = read_json(path)
    observed = admission_summary(plan)
    if observed != expected:
        raise STM32C0AdmissionError("C0.4 frozen admission-plan summary drifted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    plan = build_admission_plan()
    if not admission_plan_is_clean(plan):
        raise STM32C0AdmissionError("C0.4 admission plan is not clean")
    validate_frozen_plan(plan)
    summary = admission_summary(plan)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            "STM32C0 C0.4 admission plan: PASS "
            f"metadata_ready={summary['metadata_ready_count']} "
            f"admittable={summary['capability_admittable_count']} "
            f"unresolved={summary['capability_unresolved_count']}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdmissionError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
