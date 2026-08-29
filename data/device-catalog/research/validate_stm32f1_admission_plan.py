#!/usr/bin/env python3
"""Validate the checked-in Phase 2.7 plan and its canonical result offline."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from stm32f1_canonical_admission import (
    AdmissionError,
    build_admission_plan,
    canonical_csv_sha256,
    file_sha256,
    plan_is_clean,
    read_csv,
    read_json,
)
from validate_stm32f1_retained_evidence import validate_retained_evidence

HERE = Path(__file__).resolve().parent
DEFAULT_EVIDENCE = HERE / "evidence" / "stm32f1-phase2.6-browser-2026-08-29"


def validate_admission_plan(
    *,
    plan_path: Path,
    evidence_dir: Path,
    canonical_path: Path,
    catalog_path: Path,
    baseline_path: Path,
) -> dict[str, Any]:
    retained = validate_retained_evidence(evidence_dir, baseline_path=baseline_path)
    plan = read_json(plan_path)
    if plan.get("schema_version") != 1 or not plan_is_clean(plan):
        raise AdmissionError("checked-in admission plan is not clean")
    if plan.get("evidence_id") != retained.get("evidence_id"):
        raise AdmissionError("admission plan evidence_id mismatch")
    inputs = plan.get("inputs")
    if not isinstance(inputs, dict):
        raise AdmissionError("admission plan inputs must be an object")
    expected_hashes = {
        "mapping_catalog_sha256": file_sha256(catalog_path),
        "baseline_sha256": file_sha256(baseline_path),
    }
    for key, expected in expected_hashes.items():
        if inputs.get(key) != expected:
            raise AdmissionError(f"admission plan {key} mismatch")
    if plan.get("source_provenance", {}).get("evidence_manifest_sha256") != file_sha256(evidence_dir / "manifest.json"):
        raise AdmissionError("admission plan evidence manifest digest mismatch")

    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 26:
        raise AdmissionError("admission plan must contain 26 candidates")
    if candidates != sorted(candidates, key=lambda item: (item["manufacturer"], item["base_device"], item["icpn"])):
        raise AdmissionError("admission plan candidate ordering is not deterministic")
    if len({item.get("icpn") for item in candidates}) != 26:
        raise AdmissionError("admission plan contains duplicate ICPNs")
    if any(item.get("decision") not in {"admit", "already_present"} for item in candidates):
        raise AdmissionError("admission plan contains a blocked decision")

    fields, rows = read_csv(canonical_path)
    current_hash = canonical_csv_sha256(fields, rows)
    if current_hash == inputs.get("canonical_input_sha256"):
        fresh = build_admission_plan(
            evidence_dir=evidence_dir,
            canonical_path=canonical_path,
            catalog_path=catalog_path,
            baseline_path=baseline_path,
        )
        if fresh != plan:
            raise AdmissionError("checked-in admission plan is not reproducible")
        state = "planned"
        rows_after = len(rows) + plan["decision_counts"]["admit"]
        idempotent = False
    else:
        by_icpn: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_icpn.setdefault(row.get("icpn", ""), []).append(row)
        for item in candidates:
            proposed = item.get("proposed_canonical_row")
            if not isinstance(proposed, dict) or by_icpn.get(item["icpn"]) != [proposed]:
                raise AdmissionError(f"canonical result does not match plan: {item.get('icpn')}")
        expected_rows = plan.get("canonical_rows_before", -1) + plan["decision_counts"]["admit"]
        if len(rows) != expected_rows:
            raise AdmissionError("canonical row count does not match admission plan")
        rerun = build_admission_plan(
            evidence_dir=evidence_dir,
            canonical_path=canonical_path,
            catalog_path=catalog_path,
            baseline_path=baseline_path,
        )
        counts = rerun.get("decision_counts", {})
        if counts != {"admit": 0, "already_present": 26, "manual_review_required": 0, "reject": 0}:
            raise AdmissionError("post-write planner is not idempotent")
        state = "admitted"
        rows_after = len(rows)
        idempotent = True

    return {
        "evidence_id": plan["evidence_id"],
        "state": state,
        "candidate_count": 26,
        "decision_counts": plan["decision_counts"],
        "conflicts": plan["conflicts"],
        "canonical_rows_before": plan["canonical_rows_before"],
        "canonical_rows_after": rows_after,
        "post_write_idempotent": idempotent,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "stm32f1-phase2.7-admission-plan.json")
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--canonical", type=Path, default=HERE / "stm32f1-commercial-icpn.csv")
    parser.add_argument("--catalog", type=Path, default=HERE / "openocd-parts-canonical.csv")
    parser.add_argument("--baseline", type=Path, default=HERE / "stm32f1-acquisition-pilot-baseline.json")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate_admission_plan(
            plan_path=args.plan,
            evidence_dir=args.evidence_dir,
            canonical_path=args.canonical,
            catalog_path=args.catalog,
            baseline_path=args.baseline,
        )
    except (AdmissionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    print("STM32F1 Phase 2.7 admission plan/result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
