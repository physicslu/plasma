"""Generic deterministic canonical-admission framework for device catalogs.

The framework owns admission mechanics: deterministic ordering, duplicate/conflict
classification, canonical input binding, clean-plan gating, and idempotent writes.
Manufacturer/family policy owns commercial identity parsing, metadata derivation,
source authority, and programming-mapping requirements.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
DECISIONS = {"admit", "already_present", "manual_review_required", "reject"}


class AdmissionError(RuntimeError):
    pass


class CandidateReject(AdmissionError):
    """Policy rejected one candidate as invalid commercial identity/evidence."""


class CandidateManualReview(AdmissionError):
    """Policy cannot safely resolve one candidate without human review."""


CandidateRowBuilder = Callable[[dict[str, Any], list[str]], dict[str, str]]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path}: expected a JSON object")
    return value


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_csv_sha256(fields: list[str], rows: list[dict[str, str]]) -> str:
    payload = json.dumps(
        {"fields": fields, "rows": rows},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_admission_plan(
    *,
    candidate_inputs: list[dict[str, Any]],
    canonical_fields: list[str],
    canonical_rows: list[dict[str, str]],
    source_provenance: dict[str, Any],
    input_bindings: dict[str, Any],
    row_builder: CandidateRowBuilder,
) -> dict[str, Any]:
    """Build a deterministic admission plan without manufacturer-specific rules."""

    canonical_by_icpn: dict[str, list[dict[str, str]]] = {}
    for row in canonical_rows:
        canonical_by_icpn.setdefault(row.get("icpn", ""), []).append(row)

    candidates: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for candidate_input in candidate_inputs:
        manufacturer = candidate_input.get("manufacturer")
        base_device = candidate_input.get("base_device")
        icpn = candidate_input.get("icpn")
        evidence = candidate_input.get("authoritative_evidence")
        mapping = candidate_input.get("base_mapping")
        if not isinstance(manufacturer, str) or not manufacturer:
            raise AdmissionError("candidate manufacturer must be a non-empty string")
        if not isinstance(base_device, str) or not base_device:
            raise AdmissionError("candidate base_device must be a non-empty string")
        if not isinstance(evidence, dict):
            raise AdmissionError(f"{base_device}: authoritative_evidence must be an object")
        if not isinstance(mapping, dict):
            raise AdmissionError(f"{base_device}: base_mapping must be an object")

        issues: list[str] = []
        decision = "admit"
        proposed: dict[str, str] | None = None
        if not isinstance(icpn, str) or not icpn or icpn in seen_candidates:
            decision = "reject"
            issues.append("duplicate or invalid retained candidate")
        else:
            seen_candidates.add(icpn)
            try:
                proposed = row_builder(candidate_input, canonical_fields)
            except CandidateManualReview as exc:
                decision = "manual_review_required"
                issues.append(str(exc))
            except CandidateReject as exc:
                decision = "reject"
                issues.append(str(exc))

        existing = canonical_by_icpn.get(str(icpn), [])
        if len(existing) > 1:
            decision = "manual_review_required"
            issues.append("canonical dataset already contains duplicate ICPN rows")
        elif len(existing) == 1 and proposed is not None:
            if existing[0] == proposed:
                decision = "already_present"
            else:
                decision = "manual_review_required"
                issues.append("existing canonical row conflicts with proposed semantics")

        candidates.append(
            {
                "manufacturer": manufacturer,
                "base_device": base_device,
                "icpn": icpn,
                "authoritative_evidence": evidence,
                "base_mapping": mapping,
                "canonical_duplicate_count": len(existing),
                "canonical_conflict": decision == "manual_review_required" and bool(existing),
                "decision": decision,
                "issues": issues,
                "proposed_canonical_row": proposed,
            }
        )

    candidates.sort(key=lambda item: (item["manufacturer"], item["base_device"], str(item["icpn"])))
    counts = Counter(item["decision"] for item in candidates)
    unknown = set(counts) - DECISIONS
    if unknown:
        raise AdmissionError(f"unsupported decisions: {sorted(unknown)}")
    conflicts = sum(bool(item["canonical_conflict"]) for item in candidates)
    issues = sorted({issue for item in candidates for issue in item["issues"]})
    inputs = dict(input_bindings)
    inputs["canonical_input_sha256"] = canonical_csv_sha256(canonical_fields, canonical_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": source_provenance.get("evidence_id"),
        "source_provenance": {key: value for key, value in source_provenance.items() if key != "evidence_id"},
        "inputs": inputs,
        "candidate_count": len(candidates),
        "decision_counts": {decision: counts.get(decision, 0) for decision in sorted(DECISIONS)},
        "conflicts": conflicts,
        "canonical_rows_before": len(canonical_rows),
        "canonical_dataset_admission": "planned",
        "issues": issues,
        "candidates": candidates,
    }


def plan_is_clean(plan: dict[str, Any]) -> bool:
    """Generic clean gate; intentionally has no batch-size assumption."""

    counts = plan.get("decision_counts")
    candidate_count = plan.get("candidate_count")
    if not isinstance(counts, dict) or set(counts) != DECISIONS:
        return False
    if not isinstance(candidate_count, int) or candidate_count < 0:
        return False
    if any(not isinstance(counts.get(decision), int) or counts[decision] < 0 for decision in DECISIONS):
        return False
    return (
        sum(counts.values()) == candidate_count
        and counts["manual_review_required"] == 0
        and counts["reject"] == 0
        and plan.get("conflicts") == 0
        and plan.get("issues") == []
    )


def write_canonical_dataset(
    *,
    plan: dict[str, Any],
    canonical_path: Path,
) -> dict[str, Any]:
    """Apply a clean plan or return an explicit no-op when already applied."""

    if not plan_is_clean(plan):
        raise AdmissionError("admission writer refuses a non-clean plan")
    inputs = plan.get("inputs")
    candidates = plan.get("candidates")
    if not isinstance(inputs, dict) or not isinstance(candidates, list):
        raise AdmissionError("admission plan structure is invalid")
    expected_input_sha = inputs.get("canonical_input_sha256")
    if not isinstance(expected_input_sha, str) or not expected_input_sha:
        raise AdmissionError("admission plan lacks canonical input binding")

    fields, rows = read_csv(canonical_path)
    current_by_icpn = {row.get("icpn", ""): row for row in rows}
    admit_rows = [item.get("proposed_canonical_row") for item in candidates if item.get("decision") == "admit"]
    if canonical_csv_sha256(fields, rows) != expected_input_sha:
        if all(
            isinstance(row, dict) and current_by_icpn.get(row.get("icpn", "")) == row
            for row in admit_rows
        ):
            return {"status": "no_op", "rows_before": len(rows), "rows_after": len(rows), "added": []}
        raise AdmissionError("canonical dataset changed after admission planning")

    existing = set(current_by_icpn)
    added: list[str] = []
    for row in admit_rows:
        if not isinstance(row, dict) or set(row) != set(fields):
            raise AdmissionError("plan contains an invalid proposed canonical row")
        icpn = row.get("icpn")
        if not isinstance(icpn, str) or not icpn:
            raise AdmissionError("plan contains a proposed row without ICPN")
        if icpn in existing:
            raise AdmissionError(f"writer refuses duplicate ICPN: {icpn}")
        existing.add(icpn)
        rows.append(row)
        added.append(icpn)

    rows.sort(key=lambda row: (row["manufacturer"], row["base_device"], row["icpn"]))
    with canonical_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return {
        "status": "written",
        "rows_before": len(rows) - len(added),
        "rows_after": len(rows),
        "added": sorted(added),
    }
