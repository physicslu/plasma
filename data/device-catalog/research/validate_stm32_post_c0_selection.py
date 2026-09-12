#!/usr/bin/env python3
"""Hard-lock the post-C0 STM32 next-family evidence-selection transaction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from freeze_stm32_post_c0_selection import (
    AUTHORITATIVE_DIR,
    AUTHORITATIVE_PROVENANCE,
    AUTHORITATIVE_TARGETS,
    EXPECTED_RUN_ID,
    PRODUCTION_MANIFEST_PRESTATE,
    build_frozen_selection,
    render,
)
from st_product_page_acquisition import AcquisitionError
from stm32_post_c0_selection import DEFAULT_EVIDENCE, DEFAULT_ORDERING_REVIEW, validate_authoritative_summary

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32-post-c0-next-family-selection.json"
EVIDENCE_DIR = AUTHORITATIVE_DIR / "evidence"

EXPECTED = {
    "selection": "a46cef39516bf94901b979ccfc446b5720b2c6855b46ede1765232f6082df134",
    "authoritative_summary": "45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c",
    "authoritative_provenance": "e55b5a94090b36aa4b30b8539cf29c3513bafb3b79d0360031a3ad413f38e34d",
    "authoritative_targets": "767ad681a7d8e839cbf68b507babb2c417905a2f40a380566e773fa987ab9434",
    "ordering_review": "d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612",
    "production_manifest_prestate": "15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def req(value: bool, message: str) -> None:
    if not value:
        raise AcquisitionError(message)


def readj(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path}: JSON object required")
    return value


def validate_retained_per_target_evidence(summary: dict) -> None:
    results = summary.get("results")
    req(isinstance(results, list) and len(results) == 44, "authoritative result count drifted")
    expected_names: set[str] = set()
    for row in results:
        req(isinstance(row, dict), "authoritative result must be an object")
        req(row.get("acquisition_status") == "success", "retained result is not successful")
        base = row.get("base_device")
        evidence = row.get("evidence")
        req(isinstance(base, str) and isinstance(evidence, dict), "retained result lacks base/evidence")
        path = EVIDENCE_DIR / f"{base}.json"
        expected_names.add(path.name)
        req(path.is_file(), f"missing retained evidence file for {base}")
        req(readj(path) == evidence, f"{base}: per-target retained evidence drifted from authoritative summary")
    observed_names = {path.name for path in EVIDENCE_DIR.glob("*.json")}
    req(observed_names == expected_names, "retained per-target evidence file set drifted")


def main() -> int:
    paths = {
        "selection": SELECTION,
        "authoritative_summary": DEFAULT_EVIDENCE,
        "authoritative_provenance": AUTHORITATIVE_PROVENANCE,
        "authoritative_targets": AUTHORITATIVE_TARGETS,
        "ordering_review": DEFAULT_ORDERING_REVIEW,
        "production_manifest_prestate": PRODUCTION_MANIFEST_PRESTATE,
    }
    for key, path in paths.items():
        req(sha256(path) == EXPECTED[key], f"{key} SHA-256 drifted")

    selection = readj(SELECTION)
    authoritative = readj(DEFAULT_EVIDENCE)
    provenance = readj(AUTHORITATIVE_PROVENANCE)
    validate_authoritative_summary(authoritative)
    validate_retained_per_target_evidence(authoritative)

    expected_bytes = render(build_frozen_selection())
    req(SELECTION.read_bytes() == expected_bytes, "frozen selection is not deterministic replay output")
    req(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "authoritative workflow run drifted")
    req(selection.get("selected_next_research_family") == "STM32L0", "selected family drifted")
    req(selection.get("scope") == "next_family_research_only", "selection scope drifted")
    req(selection.get("ordering_review_candidates") == ["STM32L0", "STM32L4"], "ordering candidate set drifted")
    req(selection.get("ordering_evidence_result") == "equivalent_required_ordering_evidence_quality", "ordering evidence comparison drifted")
    req(
        selection.get("candidate_evidence", {}).get("STM32L1", {}).get("disposition")
        == "deprioritized_for_next_family_research_due_to_lifecycle",
        "STM32L1 lifecycle disposition drifted",
    )
    req(selection.get("candidate_evidence", {}).get("STM32L1", {}).get("rejected_for_future_support") is False, "STM32L1 must not be rejected for future support")
    req(
        selection.get("candidate_evidence", {}).get("STM32L4", {}).get("disposition")
        == "ordering_review_candidate",
        "STM32L4 exact-variant lifecycle handling drifted",
    )
    boundaries = selection.get("authority_boundaries")
    req(isinstance(boundaries, dict) and boundaries and set(boundaries.values()) == {False}, "selection authority boundary escaped fail-closed state")

    print("STM32 post-C0 next-family evidence selection: PASS")
    print(json.dumps({
        "selected_next_research_family": "STM32L0",
        "selection_sha256": EXPECTED["selection"],
        "authoritative_workflow_run_id": EXPECTED_RUN_ID,
        "representative_targets": 44,
        "production_exact_icpns": 912,
        "production_base_devices": 293,
        "production_stm32_families": 10,
        "production_write_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
