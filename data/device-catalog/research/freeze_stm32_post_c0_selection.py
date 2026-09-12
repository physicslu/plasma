#!/usr/bin/env python3
"""Build/check the frozen post-C0 STM32 next-family research selection artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError
from stm32_post_c0_selection import DEFAULT_EVIDENCE, DEFAULT_ORDERING_REVIEW, build_selection

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
AUTHORITATIVE_DIR = DEFAULT_EVIDENCE.parent
AUTHORITATIVE_PROVENANCE = AUTHORITATIVE_DIR / "provenance.json"
AUTHORITATIVE_TARGETS = AUTHORITATIVE_DIR / "targets.json"
AUTHORITATIVE_EVIDENCE_DIR = AUTHORITATIVE_DIR / "evidence"
PRODUCTION_MANIFEST_PRESTATE = HERE / "stm32-post-c0-production-manifest-prestate.json"
DEFAULT_OUTPUT = HERE / "stm32-post-c0-next-family-selection.json"
EXPECTED_RUN_ID = 34674798156
EXPECTED_OPENOCD_CATALOG_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_PRODUCTION_MANIFEST_SHA256 = "15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420"


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


def _validate_production_prestate() -> None:
    manifest = readj(PRODUCTION_MANIFEST_PRESTATE)
    require(sha256(PRODUCTION_MANIFEST_PRESTATE) == EXPECTED_PRODUCTION_MANIFEST_SHA256, "post-C0 Production prestate digest drifted")
    sources = manifest.get("sources")
    require(isinstance(sources, list) and len(sources) == 10, "post-C0 Production family count drifted")
    require(sum(int(row.get("row_count", 0)) for row in sources) == 912, "post-C0 Production exact ICPN count drifted")
    c0 = [row for row in sources if row.get("family") == "STM32C0"]
    require(len(c0) == 1 and c0[0].get("row_count") == 209, "post-C0 STM32C0 Production state drifted")


def build_frozen_selection() -> dict[str, Any]:
    summary = readj(DEFAULT_EVIDENCE)
    provenance = readj(AUTHORITATIVE_PROVENANCE)
    targets = readj(AUTHORITATIVE_TARGETS)
    review = readj(DEFAULT_ORDERING_REVIEW)
    _validate_production_prestate()

    require(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "authoritative run id drifted")
    require(provenance.get("workflow_run_attempt") == 1, "authoritative run attempt drifted")
    require(provenance.get("source_repository") == "physicslu/plasma", "authoritative source repository drifted")
    require(provenance.get("acquire_step_outcome") == "success", "authoritative acquisition did not succeed")
    require(provenance.get("attempted_targets") == 44, "authoritative target count drifted")
    require(provenance.get("dispositioned_targets") == 44, "authoritative disposition count drifted")
    require(provenance.get("manual_review_targets") == 0, "authoritative evidence requires zero manual review")
    require(provenance.get("bounded_probe_complete") is True, "authoritative probe is incomplete")
    require(provenance.get("production_write_authorized") is False, "authoritative probe escaped Production boundary")
    require(provenance.get("selected_next_research_family") is False, "authoritative probe escaped pre-selection boundary")
    require(provenance.get("openocd_catalog_sha256") == EXPECTED_OPENOCD_CATALOG_SHA256, "OpenOCD catalog acquisition binding drifted")
    require(provenance.get("production_manifest_sha256") == EXPECTED_PRODUCTION_MANIFEST_SHA256, "Production acquisition binding drifted")

    require(targets.get("target_count") == 44, "retained target manifest count drifted")
    require(len(targets.get("targets", [])) == 44, "retained target manifest rows drifted")
    evidence_files = sorted(AUTHORITATIVE_EVIDENCE_DIR.glob("*.json"))
    require(len(evidence_files) == 44, "retained per-target evidence count drifted")

    result = build_selection(summary, review)
    require(result.get("selected_next_research_family") == "STM32L0", "post-C0 selection did not resolve to STM32L0")
    require(result.get("ordering_review_candidates") == ["STM32L0", "STM32L4"], "ordering-review candidate set drifted")
    require(
        result.get("candidate_evidence", {}).get("STM32L1", {}).get("disposition")
        == "deprioritized_for_next_family_research_due_to_lifecycle",
        "STM32L1 lifecycle disposition drifted",
    )
    require(
        result.get("candidate_evidence", {}).get("STM32L4", {}).get("disposition")
        == "ordering_review_candidate",
        "STM32L4 mixed-variant lifecycle semantics drifted",
    )

    result["inputs"] = {
        "authoritative_probe_summary": str(DEFAULT_EVIDENCE.relative_to(REPO_ROOT)),
        "authoritative_probe_summary_sha256": sha256(DEFAULT_EVIDENCE),
        "authoritative_probe_provenance_sha256": sha256(AUTHORITATIVE_PROVENANCE),
        "authoritative_targets_sha256": sha256(AUTHORITATIVE_TARGETS),
        "authoritative_workflow_run_id": provenance["workflow_run_id"],
        "ordering_information_review": str(DEFAULT_ORDERING_REVIEW.relative_to(REPO_ROOT)),
        "ordering_information_review_sha256": sha256(DEFAULT_ORDERING_REVIEW),
        "production_manifest_prestate": str(PRODUCTION_MANIFEST_PRESTATE.relative_to(REPO_ROOT)),
        "production_manifest_prestate_sha256": sha256(PRODUCTION_MANIFEST_PRESTATE),
        "openocd_catalog_sha256_at_acquisition": provenance["openocd_catalog_sha256"],
    }
    result["method_findings"] = {
        "authoritative_probe": "official ST Q&R exact identity joined to Sample & Buy Marketing Status only when exact Part Number sets match",
        "stm32l1_lifecycle": "three of four representative subfamilies expose only NRND exact identities and are deprioritized for this next-family transaction",
        "stm32l4_variant_lifecycle": "all 24 representative subfamilies retain Active exact identities; three extra non-Active STM32L462 variants remain exact-variant dispositions and do not exclude STM32L4",
        "ordering_review": "STM32L0 and STM32L4 have equivalent complete required Ordering Information evidence quality from official ST datasheets",
        "tie_break": "current post-C0 shortlist order selects STM32L0 only after manufacturer lifecycle and Ordering Information gates are equivalent",
        "selection_is_admission": False,
        "selection_is_programming_support": False,
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
            raise AcquisitionError("frozen post-C0 selection artifact drifted")
        print("STM32 post-C0 frozen selection: PASS")
        print(f"selection_sha256={hashlib.sha256(expected).hexdigest()}")
        return 0
    args.output.write_bytes(expected)
    print(f"wrote {args.output}")
    print(f"selection_sha256={hashlib.sha256(expected).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
