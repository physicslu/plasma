#!/usr/bin/env python3
"""Build/check the frozen post-U0 STM32 next-family research selection artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError
from stm32_post_u0_selection import (
    DEFAULT_EVIDENCE,
    DEFAULT_ORDERING_REVIEW,
    DEFAULT_QR_DIAGNOSTIC,
    build_selection,
    validate_qr_only_method_diagnostic,
)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
AUTHORITATIVE_DIR = DEFAULT_EVIDENCE.parent
AUTHORITATIVE_PROVENANCE = AUTHORITATIVE_DIR / "provenance.json"
AUTHORITATIVE_TARGETS = AUTHORITATIVE_DIR / "targets.json"
QR_DIAGNOSTIC_DIR = DEFAULT_QR_DIAGNOSTIC.parent
QR_DIAGNOSTIC_PROVENANCE = QR_DIAGNOSTIC_DIR / "provenance.json"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
OPENOCD_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_OUTPUT = HERE / "stm32-post-u0-next-family-selection.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def readj(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AcquisitionError(f"{path}: JSON object required")
    return payload


def require(value: bool, message: str) -> None:
    if not value:
        raise AcquisitionError(message)


def build_frozen_selection() -> dict[str, Any]:
    summary = readj(DEFAULT_EVIDENCE)
    provenance = readj(AUTHORITATIVE_PROVENANCE)
    qr_summary = readj(DEFAULT_QR_DIAGNOSTIC)
    qr_provenance = readj(QR_DIAGNOSTIC_PROVENANCE)
    review = readj(DEFAULT_ORDERING_REVIEW)

    result = build_selection(summary, review)
    validate_qr_only_method_diagnostic(qr_summary)

    require(provenance.get("workflow_run_id") == 34560484391, "authoritative run id drifted")
    require(provenance.get("target_count") == 26, "authoritative target count drifted")
    require(provenance.get("evidence_file_count") == 26, "authoritative evidence file count drifted")
    require(provenance.get("manual_review_targets") == 0, "authoritative evidence requires zero manual review")
    require(provenance.get("probe_summary_sha256") == sha256(DEFAULT_EVIDENCE), "authoritative summary digest drifted")
    require(provenance.get("targets_sha256") == sha256(AUTHORITATIVE_TARGETS), "authoritative target digest drifted")
    require(provenance.get("openocd_catalog_sha256") == sha256(OPENOCD_CATALOG), "OpenOCD catalog binding drifted")
    require(provenance.get("production_manifest_sha256") == sha256(PRODUCTION_MANIFEST), "Production manifest binding drifted")
    require(provenance.get("production_state") == {"base_devices": 243, "exact_icpns": 703, "stm32_families": 9}, "Production prestate drifted")

    require(qr_provenance.get("workflow_run_id") == 34561677731, "Q&R diagnostic run id drifted")
    require(qr_provenance.get("target_count") == 26, "Q&R diagnostic target count drifted")
    require(qr_provenance.get("manual_review_targets") == 6, "Q&R diagnostic C0 method limitation drifted")
    require(qr_provenance.get("probe_summary_sha256") == sha256(DEFAULT_QR_DIAGNOSTIC), "Q&R diagnostic summary digest drifted")
    require(qr_provenance.get("openocd_catalog_sha256") == provenance.get("openocd_catalog_sha256"), "Q&R diagnostic catalog binding drifted")
    require(qr_provenance.get("production_manifest_sha256") == provenance.get("production_manifest_sha256"), "Q&R diagnostic Production binding drifted")

    require(result.get("selected_next_research_family") == "STM32C0", "post-U0 selection did not resolve to STM32C0")
    require(result.get("ordering_review_candidates") == ["STM32C0", "STM32L0"], "ordering-review candidate set drifted")
    require(result.get("candidate_evidence", {}).get("STM32L1", {}).get("disposition") == "deprioritized_for_next_family_research_due_to_lifecycle", "STM32L1 lifecycle disposition drifted")

    result["inputs"] = {
        "authoritative_probe_summary": str(DEFAULT_EVIDENCE.relative_to(REPO_ROOT)),
        "authoritative_probe_summary_sha256": sha256(DEFAULT_EVIDENCE),
        "authoritative_probe_provenance_sha256": sha256(AUTHORITATIVE_PROVENANCE),
        "authoritative_targets_sha256": sha256(AUTHORITATIVE_TARGETS),
        "authoritative_workflow_run_id": provenance["workflow_run_id"],
        "ordering_information_review": str(DEFAULT_ORDERING_REVIEW.relative_to(REPO_ROOT)),
        "ordering_information_review_sha256": sha256(DEFAULT_ORDERING_REVIEW),
        "qr_only_method_diagnostic_summary": str(DEFAULT_QR_DIAGNOSTIC.relative_to(REPO_ROOT)),
        "qr_only_method_diagnostic_summary_sha256": sha256(DEFAULT_QR_DIAGNOSTIC),
        "qr_only_method_diagnostic_provenance_sha256": sha256(QR_DIAGNOSTIC_PROVENANCE),
        "qr_only_method_diagnostic_workflow_run_id": qr_provenance["workflow_run_id"],
        "openocd_catalog_sha256": provenance["openocd_catalog_sha256"],
        "production_manifest_sha256": provenance["production_manifest_sha256"],
    }
    result["method_findings"] = {
        "authoritative_probe": "official ST Q&R exact identity joined to Sample & Buy Marketing Status only when exact Part Number sets match",
        "qr_only_diagnostic": "STM32C0 pages did not co-locate Marketing Status in the Q&R surface; six C0 representatives timed out under the Q&R-only readiness rule",
        "qr_only_c0_timeout_is_family_evidence": False,
        "sample_buy_alone_is_commercial_identity_authority": False,
        "transport_diagnostics_are_selection_evidence": False,
    }
    return result


def render(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render(build_frozen_selection())
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            raise AcquisitionError("frozen post-U0 selection artifact drifted")
        print("STM32 post-U0 frozen selection: PASS")
        print(f"selection_sha256={hashlib.sha256(expected).hexdigest()}")
        return 0
    args.output.write_bytes(expected)
    print(f"wrote {args.output}")
    print(f"selection_sha256={hashlib.sha256(expected).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
