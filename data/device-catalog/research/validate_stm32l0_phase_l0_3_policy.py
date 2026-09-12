#!/usr/bin/env python3
"""Hard-lock and deterministically replay STM32L0 L0.3 metadata policy."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stm32l0_metadata_policy import DEFAULT_ORDERING_AUTHORITY, EXPECTED_EVIDENCE_ID, load_ordering_authority
from stm32l0_phase_l0_3_policy import build_plan, plan_is_clean
from validate_stm32l0_phase_l0_2_retained_evidence import EVIDENCE as L0_2_EVIDENCE, main as validate_retained

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l0-phase-l0.3-policy-baseline.json"
EXPECTED_BASELINE_BLOB = "2cd2e001bc34c1f1335ae78e352e496e59d1e698"
EXPECTED_AUTHORITY_BLOB = "f1ad2e10396405ed3d156597598f73075cf81b67"
EXPECTED_L0_2_SUMMARY_SHA256 = "c664e6458d00f169b2653021284acb56664b607c245e97f51bf13f4a232d51de"
EXPECTED_ACTIVE_SET_SHA256 = "8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b"
EXPECTED_METADATA_ROWS_SHA256 = "6aefd256256febb6d5f48ec58e44b5fec64489593df333c68723581eb7786a95"
EMPTY_SET_SHA256 = "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"


class ValidationError(RuntimeError):
    pass


def req(state: bool, message: str) -> None:
    if not state:
        raise ValidationError(message)


def git_blob(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body, usedforsecurity=False).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"{path.name}: expected JSON object")
    return value


def document_bindings(authorities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for series in sorted(authorities):
        record = authorities[series]
        candidates = [record, *record.get("additional_documents", [])]
        for document in candidates:
            item = {
                "series": series,
                "document_id": document["document_id"],
                "revision": document["revision"],
                "ordering_section": document["ordering_section"],
                "pdf_page": document["pdf_page"],
                "datasheet_url": document["datasheet_url"],
            }
            if isinstance(document.get("covered_base_devices"), list):
                item["covered_base_devices"] = document["covered_base_devices"]
            docs.append(item)
    return docs


def main() -> int:
    req(git_blob(BASELINE) == EXPECTED_BASELINE_BLOB, "L0.3 baseline byte drift")
    baseline = read_json(BASELINE)
    req(baseline.get("schema_version") == 1, "L0.3 baseline schema drift")
    req(baseline.get("phase") == "L0.3" and baseline.get("family") == "STM32L0", "L0.3 baseline identity drift")
    req(baseline.get("adapter_id") == "stm32l0-l0.3-metadata", "L0.3 adapter identity drift")
    req(baseline.get("fail_closed") is True, "L0.3 baseline is not fail-closed")

    req(validate_retained() == 0, "L0.2 retained evidence validation failed")
    l0_2_summary = L0_2_EVIDENCE / "live-summary.json"
    req(sha256(l0_2_summary) == EXPECTED_L0_2_SUMMARY_SHA256, "L0.2 retained summary digest drift")
    inputs = baseline.get("inputs")
    req(isinstance(inputs, dict), "L0.3 baseline inputs missing")
    req(inputs.get("retained_l0_2_evidence_id") == EXPECTED_EVIDENCE_ID, "L0.2 evidence identity drift")
    req(inputs.get("retained_l0_2_active_exact_icpn_set_sha256") == EXPECTED_ACTIVE_SET_SHA256, "L0.2 Active exact set binding drift")
    req(inputs.get("retained_l0_2_summary_sha256") == EXPECTED_L0_2_SUMMARY_SHA256, "L0.2 summary binding drift")

    req(git_blob(DEFAULT_ORDERING_AUTHORITY) == EXPECTED_AUTHORITY_BLOB, "L0.3 Ordering Information authority byte drift")
    req(inputs.get("ordering_authority_git_blob_sha") == EXPECTED_AUTHORITY_BLOB, "L0.3 baseline authority binding drift")
    authorities = load_ordering_authority()
    expected_documents = baseline.get("policy_evidence", {}).get("ordering_documents")
    req(isinstance(expected_documents, list) and len(expected_documents) == 19, "L0.3 baseline must bind 19 official datasheets")
    req(document_bindings(authorities) == expected_documents, "L0.3 official datasheet bindings drifted")
    req(baseline.get("policy_evidence", {}).get("ordering_series_count") == 16, "L0.3 series count drift")
    req(baseline.get("policy_evidence", {}).get("official_datasheet_binding_count") == 19, "L0.3 datasheet count drift")

    plan = build_plan()
    req(plan_is_clean(plan), "L0.3 deterministic planner is not clean")
    req(plan.get("candidate_count") == baseline.get("candidate_count") == 360, "L0.3 candidate count drift")
    req(plan.get("base_device_count") == baseline.get("base_device_count") == 99, "L0.3 Base Device count drift")
    req(plan.get("decision_counts") == baseline.get("decision_counts") == {"metadata_ready": 360, "manual_review_required": 0, "reject": 0}, "L0.3 disposition drift")
    req(plan.get("issues") == [] and plan.get("manual_review_base_devices") == [], "L0.3 unresolved metadata issue appeared")
    req(plan.get("metadata_ready_set_sha256") == baseline.get("metadata_ready_exact_icpn_set_sha256") == EXPECTED_ACTIVE_SET_SHA256, "L0.3 metadata-ready exact set drift")
    req(plan.get("manual_review_set_sha256") == baseline.get("manual_review_set_sha256") == EMPTY_SET_SHA256, "L0.3 manual-review set drift")
    req(plan.get("reject_set_sha256") == baseline.get("reject_set_sha256") == EMPTY_SET_SHA256, "L0.3 reject set drift")
    req(plan.get("metadata_rows_sha256") == baseline.get("metadata_rows_sha256") == EXPECTED_METADATA_ROWS_SHA256, "L0.3 metadata rows drift")
    req(baseline.get("metadata_row_count") == 360, "L0.3 baseline metadata row count drift")
    req(plan.get("metadata_distribution") == baseline.get("metadata_distribution"), "L0.3 metadata distribution drift")

    production = plan.get("production_snapshot")
    frozen_production = baseline.get("production_snapshot")
    req(isinstance(production, dict) and isinstance(frozen_production, dict), "L0.3 Production snapshot missing")
    req(production.get("exact_icpn_count") == frozen_production.get("exact_icpn_count") == 912, "Production exact ICPN count drift")
    req(production.get("base_device_count") == frozen_production.get("base_device_count") == 293, "Production Base Device count drift")
    req(len(production.get("family_exact_icpn_counts", {})) == frozen_production.get("stm32_family_count") == 10, "Production family count drift")
    req(production.get("stm32l0_exact_icpn_count") == frozen_production.get("stm32l0_exact_icpn_count") == 0, "Production unexpectedly contains STM32L0")
    req(production.get("manifest_git_blob_sha") == inputs.get("production_manifest_git_blob_sha") == frozen_production.get("source_manifest_git_blob_sha") == "8abfcc870e51ac4232cdf8d807828cfe4ff5662d", "Production manifest binding drift")

    contract = baseline.get("metadata_contract")
    req(plan.get("metadata_contract") == contract, "L0.3 metadata contract drift")
    req(isinstance(contract, dict) and contract.get("admission_deferred_to") == "L0.4", "L0.3 admission boundary drift")
    false_controls = (
        "canonical_admission_authorized",
        "production_write_authorized",
        "programming_policy_defined",
        "flash_geometry_qualified",
        "option_security_semantics_qualified",
        "physical_hil_qualified",
        "runtime_programming_support_claimed",
        "openocd_routing_gates_metadata",
        "cmsis_alias_gates_metadata",
        "scope_expansion_authorized",
    )
    req(all(contract.get(key) is False for key in false_controls), "L0.3 fail-closed authority boundary escaped")
    req(baseline.get("canonical_dataset_admission") == "deferred", "L0.3 canonical admission was not deferred")
    req(baseline.get("production_write_applied") is False, "L0.3 Production write was applied")
    req(baseline.get("programming_algorithm_equivalence_claimed") is False, "L0.3 programming equivalence claim escaped")
    req(baseline.get("physical_hil_qualified") is False, "L0.3 physical HIL claim escaped")
    req(baseline.get("runtime_support_claimed") is False, "L0.3 runtime support claim escaped")

    print("STM32L0 L0.3 metadata baseline: VALID")
    print("Base Devices: 99")
    print("Metadata-ready exact ICPNs: 360")
    print("Manual review: 0")
    print("Reject: 0")
    print("Production exact ICPNs: 912")
    print("STM32L0 Production: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
