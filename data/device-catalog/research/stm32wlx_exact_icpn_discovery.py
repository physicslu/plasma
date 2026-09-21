#!/usr/bin/env python3
"""Bounded official-ST exact ICPN discovery for STM32WLX.

This research-only transaction enumerates exact commercial identities from all
17 deterministic Base Devices represented by the frozen STM32WLX
ordering-pattern surface. The known STM32WL5MOC non-prefix anomaly remains
explicitly tied to its frozen STM32WL55 cohort and is discovered through its
own official ST product page; no alias normalization is claimed.

Catalog admission/publication, runtime programming, wireless radio/security
operations, target execution, physical validation, and HIL remain explicitly
outside this gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from st_browser_acquisition import (
    BROWSER_TRANSPORT,
    STBrowserAcquirer,
    build_browser_evidence_record,
)
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32_post_u0_evidence_probe import ProbeTarget, RateLimitedFetcher, source_url_for_base
from stm32wlx_evidence_accessibility_probe import (
    EXPECTED_NON_PREFIX_BASE,
    EXPECTED_NON_PREFIX_PATTERN,
    EXPECTED_SERIES,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    SELECTION_PATH,
    SOURCE_PATH,
    guarded_series_rows,
    ordering_base,
)

HERE = Path(__file__).resolve().parent
ACCESSIBILITY = HERE / "evidence/stm32wlx-accessibility-live-2026-09-21/probe-summary.json"

DISCOVERY_ID = "stm32wlx-bounded-exact-icpn-discovery-v1"
EXPECTED_ORDERING_ROWS = 17
EXPECTED_BASE_DEVICE_COUNT = 17
EXPECTED_BASES = (
    "STM32WL54CC",
    "STM32WL54JC",
    "STM32WL55CC",
    "STM32WL55JC",
    "STM32WL5MOC",
    "STM32WLE4C8",
    "STM32WLE4CB",
    "STM32WLE4CC",
    "STM32WLE4J8",
    "STM32WLE4JB",
    "STM32WLE4JC",
    "STM32WLE5C8",
    "STM32WLE5CB",
    "STM32WLE5CC",
    "STM32WLE5J8",
    "STM32WLE5JB",
    "STM32WLE5JC",
)
MIN_DELAY_SECONDS = 1.0
NEXT_GATE = "stm32wlx-bounded-exact-icpn-admission-readiness-gate"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcquisitionError(f"{path.name}: expected JSON object")
    return value


def guard_accessibility() -> dict[str, Any]:
    payload = load_json(ACCESSIBILITY)
    if payload.get("probe_id") != "stm32wlx-bounded-official-st-evidence-accessibility-v1":
        raise AcquisitionError("unexpected STM32WLX accessibility probe id")
    if payload.get("selected_wireless_frontier") != EXPECTED_SERIES:
        raise AcquisitionError("STM32WLX accessibility frontier drifted")
    if payload.get("target_config") != EXPECTED_TARGET_CONFIG:
        raise AcquisitionError("STM32WLX accessibility target config drifted")
    if payload.get("attempted_targets") != len(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32WLX accessibility attempted-target count drifted")
    if payload.get("successful_targets") != len(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32WLX accessibility success coverage drifted")
    if payload.get("manual_review_targets") != 0:
        raise AcquisitionError("STM32WLX accessibility retains manual review")
    if payload.get("official_st_evidence_accessible_for_all_subfamilies") is not True:
        raise AcquisitionError("STM32WLX official-ST accessibility gate is incomplete")
    if payload.get("next_gate") != "stm32wlx-bounded-exact-icpn-discovery-gate":
        raise AcquisitionError("STM32WLX accessibility next gate drifted")
    claims = payload.get("claims")
    if not isinstance(claims, dict) or any(value is not False for value in claims.values()):
        raise AcquisitionError("STM32WLX accessibility claims escaped fail-closed state")
    return payload


def deterministic_targets() -> list[ProbeTarget]:
    guard_accessibility()
    rows = guarded_series_rows()
    ordering_rows = [row for row in rows if row.get("identifier_kind") == "ordering_pattern"]
    if len(ordering_rows) != EXPECTED_ORDERING_ROWS:
        raise AcquisitionError(
            f"STM32WLX ordering-pattern row count drifted: {len(ordering_rows)}"
        )

    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in ordering_rows:
        by_subfamily[row["subfamily"]].add(ordering_base(row))

    targets: list[ProbeTarget] = []
    for subfamily in EXPECTED_SUBFAMILIES:
        bases = sorted(by_subfamily[subfamily])
        if not bases:
            raise AcquisitionError(f"{subfamily}: no ordering-pattern Base Device")
        for base in bases:
            url = source_url_for_base(base)
            validate_source_url(url)
            targets.append(
                ProbeTarget(
                    series=EXPECTED_SERIES,
                    subfamily=subfamily,
                    base_device=base,
                    source_url=url,
                    selection_reason=(
                        "unique Base Device derived from frozen STM32WLX ordering-pattern row; "
                        "frozen cohort label retained even when Base Device is non-prefix"
                    ),
                )
            )

    observed = tuple(target.base_device for target in targets)
    if observed != EXPECTED_BASES:
        raise AcquisitionError(f"STM32WLX deterministic Base Devices drifted: {observed}")
    if len({target.base_device for target in targets}) != EXPECTED_BASE_DEVICE_COUNT:
        raise AcquisitionError("STM32WLX deterministic targets are not unique")
    if {target.subfamily for target in targets} != set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32WLX target subfamily coverage drifted")

    anomalies = [
        (target.subfamily, target.base_device)
        for target in targets
        if not target.base_device.startswith(target.subfamily)
    ]
    if anomalies != [("STM32WL55", EXPECTED_NON_PREFIX_BASE)]:
        raise AcquisitionError(f"STM32WLX exact-discovery anomaly boundary drifted: {anomalies}")
    return targets


def target_manifest(targets: list[ProbeTarget]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "scope": "bounded exact ICPN discovery from official ST Q&R surfaces",
        "selected_wireless_frontier": EXPECTED_SERIES,
        "target_config": EXPECTED_TARGET_CONFIG,
        "candidate_source_sha256": sha256(SOURCE_PATH),
        "selection_sha256": sha256(SELECTION_PATH),
        "accessibility_summary_sha256": sha256(ACCESSIBILITY),
        "base_device_count": len(targets),
        "known_non_prefix_ordering_targets": [
            {
                "frozen_subfamily": "STM32WL55",
                "part_number_pattern": EXPECTED_NON_PREFIX_PATTERN,
                "base_device": EXPECTED_NON_PREFIX_BASE,
                "alias_normalized": False,
                "included_in_exact_discovery": True,
            }
        ],
        "targets": [
            {
                "series": target.series,
                "subfamily": target.subfamily,
                "base_device": target.base_device,
                "source_url": target.source_url,
                "selection_reason": target.selection_reason,
                "prefix_consistent_with_frozen_subfamily": target.base_device.startswith(
                    target.subfamily
                ),
            }
            for target in targets
        ],
    }


def claims(*, discovery_complete: bool) -> dict[str, bool]:
    return {
        "production_write_authorized": False,
        "icpn_admission_authorized": False,
        "exact_icpn_discovery_completed": discovery_complete,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_programming_support_claimed": False,
        "wireless_radio_operation_authorized": False,
        "wireless_security_operation_authorized": False,
        "security_mutation_authorized": False,
        "debug_attach_supported": False,
        "target_execution_authorized": False,
        "physical_validation_claimed": False,
        "hil_required_for_catalog_admission": False,
        "remaining_wireless_families_rejected": False,
        "stm32wlx_admission_ready": False,
        "wl5m_alias_normalized": False,
    }


def run_live(
    targets: list[ProbeTarget],
    *,
    headless: bool,
    delay_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    if targets != deterministic_targets():
        raise AcquisitionError("STM32WLX discovery target set drifted")
    if delay_seconds < MIN_DELAY_SECONDS:
        raise AcquisitionError(
            f"live discovery delay must be at least {MIN_DELAY_SECONDS:.1f}s"
        )

    results: list[dict[str, Any]] = []
    exact_owner: dict[str, str] = {}
    excluded_owner: dict[str, str] = {}
    browser_version: str | None = None

    with STBrowserAcquirer(headless=headless) as browser:
        browser_version = browser.browser_version
        fetcher = RateLimitedFetcher(delay_seconds=delay_seconds, fetcher=browser.fetch)

        for target in targets:
            result: dict[str, Any] = {
                "series": target.series,
                "subfamily": target.subfamily,
                "base_device": target.base_device,
                "source_url": target.source_url,
                "prefix_consistent_with_frozen_subfamily": target.base_device.startswith(
                    target.subfamily
                ),
            }
            try:
                body, final_url, etag, last_modified = fetcher(
                    target.source_url, timeout_seconds
                )
                evidence = build_browser_evidence_record(
                    body=body,
                    source_url=target.source_url,
                    final_url=final_url,
                    base_device=target.base_device,
                    retrieved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    http_etag=etag,
                    http_last_modified=last_modified,
                )
                active = evidence.get("exact_icpns")
                excluded = evidence.get("excluded_non_active_part_numbers")
                if not isinstance(active, list) or not all(
                    isinstance(value, str) for value in active
                ):
                    raise AcquisitionError(
                        f"{target.base_device}: exact_icpns must be a string list"
                    )
                if not isinstance(excluded, list):
                    raise AcquisitionError(f"{target.base_device}: excluded list missing")
                if any(
                    not value.startswith(target.base_device)
                    for value in active
                ):
                    raise AcquisitionError(
                        f"{target.base_device}: foreign Active exact ICPN"
                    )

                excluded_ids: list[str] = []
                for item in excluded:
                    if not isinstance(item, dict):
                        raise AcquisitionError(
                            f"{target.base_device}: malformed lifecycle exclusion"
                        )
                    icpn = item.get("icpn")
                    status = item.get("marketing_status")
                    if not isinstance(icpn, str) or not icpn.startswith(
                        target.base_device
                    ):
                        raise AcquisitionError(
                            f"{target.base_device}: foreign excluded ICPN"
                        )
                    if not isinstance(status, str) or not status.strip():
                        raise AcquisitionError(
                            f"{target.base_device}: lifecycle exclusion lacks status"
                        )
                    excluded_ids.append(icpn)

                if not active and not excluded_ids:
                    raise AcquisitionError(
                        f"{target.base_device}: no exact identity disposition"
                    )
                if set(active) & set(excluded_ids):
                    raise AcquisitionError(
                        f"{target.base_device}: Active/excluded identity overlap"
                    )

                for icpn in active:
                    previous = exact_owner.setdefault(icpn, target.base_device)
                    if previous != target.base_device:
                        raise AcquisitionError(
                            f"{icpn}: duplicate Active identity across Base Devices"
                        )
                for icpn in excluded_ids:
                    previous = excluded_owner.setdefault(icpn, target.base_device)
                    if previous != target.base_device:
                        raise AcquisitionError(
                            f"{icpn}: duplicate excluded identity across Base Devices"
                        )

                result.update(
                    acquisition_status="success",
                    commercial_identity_status=(
                        "verified_active" if active else "verified_non_active_only"
                    ),
                    active_exact_icpns=active,
                    excluded_non_active_icpns=excluded_ids,
                    manual_intervention_required=False,
                    evidence=evidence,
                )
            except (AcquisitionError, OSError) as exc:
                result.update(
                    acquisition_status="failure",
                    commercial_identity_status="unverified",
                    active_exact_icpns=[],
                    excluded_non_active_icpns=[],
                    manual_intervention_required=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            results.append(result)

    success = [
        item for item in results if item.get("acquisition_status") == "success"
    ]
    manual = [
        item for item in results
        if item.get("manual_intervention_required") is True
    ]
    overlap = set(exact_owner) & set(excluded_owner)
    if overlap:
        raise AcquisitionError(
            f"Active/excluded exact identity overlap: {sorted(overlap)}"
        )

    complete = len(success) == len(targets) and not manual
    exact_list = sorted(exact_owner)
    excluded_list = sorted(excluded_owner)
    if complete and not exact_list:
        raise AcquisitionError(
            "STM32WLX complete discovery yielded no Active exact ICPNs"
        )
    digest = (
        hashlib.sha256(("\n".join(exact_list) + "\n").encode("utf-8")).hexdigest()
        if exact_list
        else None
    )

    return {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "scope": "STM32WLX bounded official-ST exact ICPN discovery",
        "selected_wireless_frontier": EXPECTED_SERIES,
        "target_config": EXPECTED_TARGET_CONFIG,
        "base_device_count": len(targets),
        "attempted_targets": len(results),
        "successful_targets": len(success),
        "manual_review_targets": len(manual),
        "active_exact_icpn_count": len(exact_list),
        "active_exact_icpns": exact_list,
        "active_exact_icpn_set_sha256": digest,
        "excluded_non_active_part_number_count": len(excluded_list),
        "excluded_non_active_part_numbers": excluded_list,
        "bounded_exact_discovery_complete": complete,
        "status": "discovered" if complete else "blocked_manual_review",
        "next_gate": NEXT_GATE if complete else None,
        "browser_version": browser_version,
        "known_non_prefix_base_device": EXPECTED_NON_PREFIX_BASE,
        "claims": claims(discovery_complete=complete),
        "results": results,
    }


def write_outputs(
    output_dir: Path,
    manifest: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "targets.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "discovery-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    exact_snapshot = {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "exact_icpn_count": summary.get("active_exact_icpn_count"),
        "exact_icpn_set_sha256": summary.get("active_exact_icpn_set_sha256"),
        "exact_icpns": summary.get("active_exact_icpns"),
    }
    (output_dir / "exact-icpns.json").write_text(
        json.dumps(exact_snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for item in summary.get("results", []):
        if isinstance(item, dict) and isinstance(item.get("evidence"), dict):
            base = str(item["base_device"]).lower()
            (output_dir / f"{base}.json").write_text(
                json.dumps(item["evidence"], indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    provenance = {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "workflow_role": "authoritative_exact_icpn_discovery",
        "source_repository": os.environ.get("GITHUB_REPOSITORY"),
        "executed_git_sha": os.environ.get("GITHUB_SHA"),
        "workflow_run_id": (
            int(os.environ["GITHUB_RUN_ID"])
            if os.environ.get("GITHUB_RUN_ID")
            else None
        ),
        "workflow_run_attempt": (
            int(os.environ["GITHUB_RUN_ATTEMPT"])
            if os.environ.get("GITHUB_RUN_ATTEMPT")
            else None
        ),
        "acquisition_transport": BROWSER_TRANSPORT,
        "browser_version": summary.get("browser_version"),
        "candidate_source_sha256": sha256(SOURCE_PATH),
        "selection_sha256": sha256(SELECTION_PATH),
        "accessibility_summary_sha256": sha256(ACCESSIBILITY),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()

    targets = deterministic_targets()
    manifest = target_manifest(targets)
    summary = run_live(
        targets,
        headless=args.headless,
        delay_seconds=args.delay_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    write_outputs(args.output_dir, manifest, summary)
    if summary.get("bounded_exact_discovery_complete") is not True:
        raise SystemExit("STM32WLX exact ICPN discovery requires manual review")


if __name__ == "__main__":
    main()
