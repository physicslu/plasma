#!/usr/bin/env python3
"""Validate retained STM32F4 Phase 4.1 R/T policy evidence offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    validate_core_provenance,
    validate_manifest,
)

HERE = Path(__file__).resolve().parent
DEFAULT_EVIDENCE_DIR = HERE / "evidence" / "stm32f4-phase4.1-rt-policy-2026-09-01"
EXPECTED_FILES = {"README.md", "evaluation.json", "provenance.json", "sources.json"}
EXPECTED_BASE_DEVICES = {
    "STM32F401RB",
    "STM32F401RC",
    "STM32F401RD",
    "STM32F401RE",
    "STM32F405RG",
    "STM32F411RC",
    "STM32F411RE",
    "STM32F413RG",
    "STM32F415RG",
    "STM32F446RC",
    "STM32F446RE",
}
EXPECTED_SOURCE_IDS = {
    "DS9716",
    "DS10086",
    "DS8626",
    "DS8597",
    "DS10314",
    "DS11581",
    "DS10693",
}


class PolicyEvidenceError(EvidenceFrameworkError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyEvidenceError(message)


def _validate_source_url(value: object) -> None:
    _require(isinstance(value, str), "policy source URL must be a string")
    parsed = urlparse(value)
    _require(parsed.scheme == "https", "policy source URL must use HTTPS")
    _require(parsed.hostname == "www.st.com", "policy source URL must be official ST")
    _require(
        parsed.path.startswith("/resource/en/datasheet/") and parsed.path.endswith(".pdf"),
        "policy source URL must identify an ST datasheet PDF",
    )


def validate_policy_evidence(evidence_dir: Path = DEFAULT_EVIDENCE_DIR) -> dict[str, Any]:
    manifest = validate_manifest(evidence_dir, expected_files=EXPECTED_FILES)
    evidence_id = manifest["evidence_id"]
    provenance = read_json(evidence_dir / "provenance.json")
    core = validate_core_provenance(
        provenance,
        evidence_id=evidence_id,
        expected_repository="physicslu/plasma",
        expected_manufacturer="STMicroelectronics",
    )
    _require(core["acquisition_transport"] == "official_st_datasheet_pdf_text", "unexpected transport")
    _require(core["headed"] is False, "datasheet text observation must be headless")
    _require(core["target_count"] == 7, "policy evidence must bind seven datasheets")
    _require(core["acquisition_success"] == 7, "all policy sources must succeed")
    _require(core["acquisition_failure"] == 0, "policy evidence cannot retain source failures")
    _require(core["exact_icpn_candidate_count"] == 0, "policy evidence cannot claim ICPN candidates")
    _require(provenance.get("source_bytes_retained") is False, "source-byte retention claim mismatch")
    _require(provenance.get("source_byte_hashes_claimed") is False, "source-byte hash claim mismatch")

    sources = read_json(evidence_dir / "sources.json")
    _require(sources.get("schema_version") == 1, "sources schema_version mismatch")
    _require(sources.get("evidence_id") == evidence_id, "sources evidence_id mismatch")
    _require(sources.get("manufacturer") == "STMicroelectronics", "sources manufacturer mismatch")
    _require(sources.get("family") == "STM32F4", "sources family mismatch")
    _require(
        sources.get("policy_claim")
        == {
            "package": "LQFP",
            "package_code": "T",
            "pin_code": "R",
            "pin_count": "64",
        },
        "R/T policy claim mismatch",
    )
    observations = sources.get("sources")
    _require(isinstance(observations, list) and len(observations) == 7, "expected seven source observations")
    source_ids: set[str] = set()
    covered_bases: set[str] = set()
    for observation in observations:
        _require(isinstance(observation, dict), "source observation must be an object")
        source_id = observation.get("document_id")
        _require(isinstance(source_id, str), "source observation requires document_id")
        _require(source_id not in source_ids, f"duplicate source document: {source_id}")
        source_ids.add(source_id)
        _validate_source_url(observation.get("source_url"))
        _require(isinstance(observation.get("revision"), int), f"{source_id}: revision must be an integer")
        _require(isinstance(observation.get("page_locator"), str), f"{source_id}: page locator missing")
        _require(
            observation.get("assertions") == {"R": "64 pins", "T": "LQFP"},
            f"{source_id}: policy assertions mismatch",
        )
        bases = observation.get("affected_base_devices")
        _require(isinstance(bases, list) and bases, f"{source_id}: affected bases missing")
        _require(all(isinstance(base, str) for base in bases), f"{source_id}: invalid affected base")
        covered_bases.update(bases)
    _require(source_ids == EXPECTED_SOURCE_IDS, "policy evidence document set mismatch")
    _require(covered_bases == EXPECTED_BASE_DEVICES, "policy evidence base-device coverage mismatch")

    evaluation = read_json(evidence_dir / "evaluation.json")
    _require(evaluation.get("schema_version") == 1, "evaluation schema_version mismatch")
    _require(evaluation.get("evidence_id") == evidence_id, "evaluation evidence_id mismatch")
    _require(evaluation.get("decision") == "policy_mapping_supported", "policy decision mismatch")
    _require(evaluation.get("canonical_dataset_admission") is False, "evaluation cannot claim admission")
    _require(evaluation.get("algorithm_equivalence_claimed") is False, "evaluation cannot claim equivalence")
    _require(evaluation.get("exact_icpn_lifecycle_claimed") is False, "evaluation cannot claim lifecycle")
    _require(evaluation.get("production_exact_icpns_before") == 158, "production F4 baseline mismatch")
    _require(evaluation.get("production_exact_icpns_after") == 158, "policy PR must not change F4 rows")
    _require(evaluation.get("production_st_exact_icpns") == 233, "production ST baseline mismatch")
    _require(evaluation.get("gap_base_devices") == 93, "gap baseline mismatch")
    _require(evaluation.get("policy_ready_before") == 0, "policy-ready baseline mismatch")
    _require(evaluation.get("policy_ready_after") == 11, "policy-ready delta mismatch")
    _require(evaluation.get("policy_blocked_before") == 93, "policy-blocked baseline mismatch")
    _require(evaluation.get("policy_blocked_after") == 82, "policy-blocked delta mismatch")
    _require(set(evaluation.get("newly_policy_ready", [])) == EXPECTED_BASE_DEVICES, "ready set mismatch")

    return {
        "schema_version": 1,
        "evidence_id": evidence_id,
        "source_documents": len(source_ids),
        "covered_base_devices": len(covered_bases),
        "policy_ready_before": 0,
        "policy_ready_after": 11,
        "policy_blocked_after": 82,
        "canonical_dataset_admission": False,
        "algorithm_equivalence_claimed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    args = parser.parse_args(argv)
    print(json.dumps(validate_policy_evidence(args.evidence_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
