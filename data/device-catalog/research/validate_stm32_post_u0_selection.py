#!/usr/bin/env python3
"""Hard-lock the STM32 C0.0 post-U0 next-family evidence-selection transaction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from freeze_stm32_post_u0_selection import build_frozen_selection, render
from st_product_page_acquisition import AcquisitionError
from stm32_post_u0_selection import (
    DEFAULT_EVIDENCE,
    DEFAULT_ORDERING_REVIEW,
    DEFAULT_QR_DIAGNOSTIC,
    DEFAULT_QR_DIAGNOSTIC as QR_SUMMARY,
    validate_authoritative_summary,
    validate_qr_only_method_diagnostic,
)

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32-post-u0-next-family-selection.json"
AUTHORITATIVE_PROVENANCE = DEFAULT_EVIDENCE.parent / "provenance.json"
AUTHORITATIVE_TARGETS = DEFAULT_EVIDENCE.parent / "targets.json"
QR_PROVENANCE = DEFAULT_QR_DIAGNOSTIC.parent / "provenance.json"
PRODUCTION_MANIFEST = HERE / "stm32c0-phase-c0.3-production-manifest-prestate.json"
OPENOCD_CATALOG = HERE / "openocd-parts-canonical.csv"

EXPECTED = {
    "selection": "f2bc4d955952cc8c25362ca5568e944470f7a1b43bf41dee2fcca9516e9c8773",
    "authoritative_summary": "1bfa9da6e6b3d020c3f643eb5d6c72ee7ee5c8aa995c66de21fa7576b79a9228",
    "authoritative_provenance": "5f9efa9f2b0b435242e608ebe6458e7c4f92efd8d93d1a69102e68bd979a09ae",
    "authoritative_targets": "c2b30151a5e52975562f03478c7665e16b17ac0751c06275cfd5db717d504671",
    "ordering_review": "9f4bde47508100025d3d6e92813f244431a18d95cf3fc73a45de93849dddd38d",
    "qr_summary": "0634a3044738a19fad163e6ff013c9dab60731f4ee5678612fc3ce9b8a8918b4",
    "qr_provenance": "c57b05e2760e8f8a22409fd70a5447c91e16df64dbba9e0888ee038fa518c0d9",
    "openocd_catalog": "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3",
    "production_manifest": "903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0",
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


def main() -> int:
    paths = {
        "selection": SELECTION,
        "authoritative_summary": DEFAULT_EVIDENCE,
        "authoritative_provenance": AUTHORITATIVE_PROVENANCE,
        "authoritative_targets": AUTHORITATIVE_TARGETS,
        "ordering_review": DEFAULT_ORDERING_REVIEW,
        "qr_summary": QR_SUMMARY,
        "qr_provenance": QR_PROVENANCE,
        "openocd_catalog": OPENOCD_CATALOG,
        "production_manifest": PRODUCTION_MANIFEST,
    }
    for key, path in paths.items():
        req(sha256(path) == EXPECTED[key], f"{key} SHA-256 drifted")

    selection = readj(SELECTION)
    authoritative = readj(DEFAULT_EVIDENCE)
    qr = readj(QR_SUMMARY)
    validate_authoritative_summary(authoritative)
    validate_qr_only_method_diagnostic(qr)

    expected_bytes = render(build_frozen_selection())
    req(SELECTION.read_bytes() == expected_bytes, "frozen selection is not deterministic replay output")
    req(selection.get("selected_next_research_family") == "STM32C0", "selected family drifted")
    req(selection.get("scope") == "next_family_research_only", "selection scope drifted")
    req(selection.get("ordering_review_candidates") == ["STM32C0", "STM32L0"], "ordering candidate set drifted")
    req(selection.get("ordering_evidence_result") == "equivalent_required_ordering_evidence_quality", "ordering evidence comparison drifted")
    req(selection.get("candidate_evidence", {}).get("STM32L1", {}).get("disposition") == "deprioritized_for_next_family_research_due_to_lifecycle", "STM32L1 lifecycle disposition drifted")
    req(selection.get("candidate_evidence", {}).get("STM32L1", {}).get("rejected_for_future_support") is False, "STM32L1 must not be rejected")
    boundaries = selection.get("authority_boundaries")
    req(isinstance(boundaries, dict) and boundaries and set(boundaries.values()) == {False}, "selection authority boundary escaped fail-closed state")

    print("STM32 C0.0 post-U0 next-family evidence selection: PASS")
    print(json.dumps({
        "selected_next_research_family": "STM32C0",
        "selection_sha256": EXPECTED["selection"],
        "authoritative_workflow_run_id": 34560484391,
        "qr_method_diagnostic_run_id": 34561677731,
        "production_exact_icpns": 703,
        "production_base_devices": 243,
        "production_stm32_families": 9,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
