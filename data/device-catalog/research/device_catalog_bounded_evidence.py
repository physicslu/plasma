"""Reusable retained-evidence checks for bounded device-catalog discovery.

The generic evidence framework validates package integrity/provenance. This module
adds reusable bounded-discovery replay checks: baseline/result binding, lifecycle
snapshot consistency, deterministic target order, fail-closed claims, and execution
identity binding. Family adapters remain responsible for mapping semantics.
"""

from __future__ import annotations

import re
from typing import Any, Callable

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BoundedEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BoundedEvidenceError(message)


def target_snapshot(
    result: dict[str, Any],
    *,
    validate_source_url: Callable[[str], None],
) -> dict[str, Any]:
    evidence = result.get("evidence")
    require(isinstance(evidence, dict), "retained result lacks evidence")
    source_url = evidence.get("source_url")
    final_url = evidence.get("final_url")
    require(isinstance(source_url, str), "retained evidence lacks source_url")
    validate_source_url(source_url)
    require(final_url == source_url, "authoritative final URL drifted")

    active = evidence.get("exact_icpns")
    excluded = evidence.get("excluded_non_active_part_numbers")
    records = evidence.get("part_number_records")
    require(
        isinstance(active, list) and all(isinstance(value, str) for value in active),
        "invalid exact ICPN list",
    )
    require(isinstance(excluded, list), "invalid excluded lifecycle list")
    require(isinstance(records, list), "retained evidence lacks lifecycle records")
    require(
        [record.get("icpn") for record in records if record.get("active") is True] == active,
        "Active lifecycle records do not match exact ICPNs",
    )
    require(
        [
            {
                "icpn": record.get("icpn"),
                "marketing_status": record.get("marketing_status"),
            }
            for record in records
            if record.get("active") is not True
        ]
        == excluded,
        "excluded lifecycle records do not match retained evidence",
    )
    for field in ("rendered_dom_sha256", "evidence_section_sha256"):
        value = evidence.get(field)
        require(
            isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
            f"invalid retained {field}",
        )

    return {
        "subfamily": result.get("subfamily"),
        "base_device": result.get("base_device"),
        "source_url": source_url,
        "retrieved_at_utc": evidence.get("retrieved_at_utc"),
        "rendered_dom_sha256": evidence.get("rendered_dom_sha256"),
        "evidence_section_sha256": evidence.get("evidence_section_sha256"),
        "active_exact_icpns": active,
        "excluded_non_active_part_numbers": excluded,
    }


def validate_baseline_result(
    *,
    baseline: dict[str, Any],
    summary: dict[str, Any],
    target_keys: list[tuple[str, str]],
    validate_source_url: Callable[[str], None],
) -> tuple[list[dict[str, Any]], int, int]:
    result_fields = (
        "attempted",
        "acquisition_success",
        "acquisition_failure",
        "active_exact_icpn_candidates",
        "excluded_non_active_part_numbers",
        "canonical_mapping",
        "manual_intervention_required",
    )
    expected_result = baseline.get("result")
    require(isinstance(expected_result, dict), "baseline result is missing")
    observed_result = {field: summary.get(field) for field in result_fields}
    require(observed_result == expected_result, "retained aggregate result drifted")

    results = summary.get("results")
    require(
        isinstance(results, list) and len(results) == len(target_keys),
        "retained target result count mismatch",
    )
    snapshots = [
        target_snapshot(result, validate_source_url=validate_source_url)
        for result in results
    ]
    require(snapshots == baseline.get("targets"), "retained target evidence drifted")
    observed_keys = [
        (str(result.get("subfamily")), str(result.get("base_device")))
        for result in results
    ]
    require(observed_keys == target_keys, "retained result target order drifted")

    candidate_count = expected_result.get("active_exact_icpn_candidates")
    excluded_count = expected_result.get("excluded_non_active_part_numbers")
    require(isinstance(candidate_count, int) and candidate_count >= 0, "invalid baseline candidate count")
    require(isinstance(excluded_count, int) and excluded_count >= 0, "invalid baseline exclusion count")
    return results, candidate_count, excluded_count


def validate_fail_closed_claims(
    *,
    baseline: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    baseline_claims = baseline.get("claims")
    summary_claims = summary.get("claims")
    require(
        isinstance(baseline_claims, dict)
        and baseline_claims
        and set(baseline_claims.values()) == {False},
        "baseline claims must all fail closed",
    )
    require(
        isinstance(summary_claims, dict)
        and summary_claims
        and set(summary_claims.values()) == {False},
        "retained discovery overclaims authority",
    )


def validate_execution_binding(
    *,
    baseline: dict[str, Any],
    provenance: dict[str, Any],
) -> None:
    context = baseline.get("acquisition_context")
    if isinstance(context, dict):
        for field in (
            "execution_mode",
            "workflow_run_id",
            "artifact_id",
            "artifact_zip_sha256",
        ):
            require(
                provenance.get(field) == context.get(field),
                f"retained provenance {field} drifted",
            )
        return

    for field in ("workflow_run_id", "artifact_id", "artifact_zip_sha256"):
        if field in baseline:
            require(
                provenance.get(field) == baseline.get(field),
                f"retained provenance {field} drifted",
            )
