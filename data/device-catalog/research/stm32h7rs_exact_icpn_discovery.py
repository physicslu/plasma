#!/usr/bin/env python3
"""Bounded official-ST exact ICPN discovery for the selected STM32H7RS partition.

This transaction enumerates exact Active orderable part numbers from official ST
Quality & Reliability product-page surfaces for every deterministic Base Device
derived from the frozen H7RS ordering-pattern rows. It does not admit devices,
write Production, claim programming equivalence, runtime support, physical
validation, or require HIL for Catalog admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

from st_browser_acquisition import BROWSER_TRANSPORT, STBrowserAcquirer, build_browser_evidence_record
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32_post_u0_evidence_probe import ProbeTarget, RateLimitedFetcher, base_from_ordering_pattern, source_url_for_base
from stm32h7rs_evidence_accessibility_probe import (
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    SOURCE_PATH,
    SELECTION_PATH,
    guarded_partition_rows,
)

HERE = Path(__file__).resolve().parent
ACCESSIBILITY = HERE / "evidence/stm32h7rs-accessibility-live-2026-09-16/probe-summary.json"
DISCOVERY_ID = "stm32h7rs-bounded-exact-icpn-discovery-v1"
MIN_DELAY_SECONDS = 1.0
EXPECTED_BASE_DEVICE_COUNT = 20


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcquisitionError(f"{path.name}: expected JSON object")
    return value


def guard_accessibility() -> dict[str, object]:
    payload = load_json(ACCESSIBILITY)
    if payload.get("probe_id") != "stm32h7rs-bounded-official-st-evidence-accessibility-v1":
        raise AcquisitionError("unexpected H7RS accessibility probe id")
    if payload.get("official_st_evidence_accessible_for_all_subfamilies") is not True:
        raise AcquisitionError("H7RS official-ST accessibility gate is not complete")
    if payload.get("next_gate") != "stm32h7rs-bounded-exact-icpn-discovery-gate":
        raise AcquisitionError("H7RS accessibility next gate drifted")
    claims = payload.get("claims")
    if not isinstance(claims, dict) or any(value is not False for value in claims.values()):
        raise AcquisitionError("H7RS accessibility claims escaped fail-closed state")
    return payload


def deterministic_targets() -> list[ProbeTarget]:
    guard_accessibility()
    rows = guarded_partition_rows()
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("identifier_kind") != "ordering_pattern":
            continue
        base = base_from_ordering_pattern(row)
        by_subfamily[row["subfamily"]].add(base)

    targets: list[ProbeTarget] = []
    for subfamily in EXPECTED_SUBFAMILIES:
        for base in sorted(by_subfamily[subfamily]):
            url = source_url_for_base(base)
            validate_source_url(url)
            targets.append(ProbeTarget(
                series="STM32H7RS",
                subfamily=subfamily,
                base_device=base,
                source_url=url,
                selection_reason="unique Base Device derived from frozen STM32H7RS ordering-pattern rows",
            ))
    if len(targets) != EXPECTED_BASE_DEVICE_COUNT:
        raise AcquisitionError(f"STM32H7RS Base Device count drifted: {len(targets)}")
    if {target.subfamily for target in targets} != set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32H7RS target subfamily coverage drifted")
    return targets


def target_manifest(targets: list[ProbeTarget]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "scope": "bounded exact ICPN discovery from official ST Q&R surfaces",
        "target_config": EXPECTED_TARGET_CONFIG,
        "partition_source_sha256": sha256(SOURCE_PATH),
        "selection_sha256": sha256(SELECTION_PATH),
        "accessibility_summary_sha256": sha256(ACCESSIBILITY),
        "base_device_count": len(targets),
        "targets": [
            {
                "series": t.series,
                "subfamily": t.subfamily,
                "base_device": t.base_device,
                "source_url": t.source_url,
                "selection_reason": t.selection_reason,
            }
            for t in targets
        ],
    }


def run_live(targets: list[ProbeTarget], *, headless: bool, delay_seconds: float, timeout_seconds: float) -> tuple[dict[str, object], str | None]:
    if delay_seconds < MIN_DELAY_SECONDS:
        raise AcquisitionError(f"live discovery delay must be at least {MIN_DELAY_SECONDS:.1f}s")

    results: list[dict[str, object]] = []
    browser_version: str | None = None
    exact_set: set[str] = set()
    excluded_set: set[str] = set()

    with STBrowserAcquirer(headless=headless) as browser:
        browser_version = browser.browser_version
        fetcher = RateLimitedFetcher(delay_seconds=delay_seconds, fetcher=browser.fetch)
        for target in targets:
            result: dict[str, object] = {
                "series": target.series,
                "subfamily": target.subfamily,
                "base_device": target.base_device,
                "source_url": target.source_url,
            }
            try:
                body, final_url, etag, last_modified = fetcher(target.source_url, timeout_seconds)
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
                if not isinstance(active, list) or not all(isinstance(v, str) for v in active):
                    raise AcquisitionError(f"{target.base_device}: exact_icpns must be a string list")
                if not isinstance(excluded, list):
                    raise AcquisitionError(f"{target.base_device}: excluded list missing")
                if any(not value.startswith(target.base_device) for value in active):
                    raise AcquisitionError(f"{target.base_device}: foreign exact ICPN")
                local_excluded: list[str] = []
                for item in excluded:
                    if not isinstance(item, dict):
                        raise AcquisitionError(f"{target.base_device}: invalid lifecycle exclusion")
                    icpn = item.get("icpn")
                    status = item.get("marketing_status")
                    if not isinstance(icpn, str) or not icpn.startswith(target.base_device):
                        raise AcquisitionError(f"{target.base_device}: foreign excluded ICPN")
                    if not isinstance(status, str) or not status.strip():
                        raise AcquisitionError(f"{target.base_device}: lifecycle exclusion lacks status")
                    local_excluded.append(icpn)
                if not active and not local_excluded:
                    raise AcquisitionError(f"{target.base_device}: no exact identity disposition")
                exact_set.update(active)
                excluded_set.update(local_excluded)
                result.update(
                    acquisition_status="success",
                    active_exact_icpns=active,
                    excluded_non_active_icpns=local_excluded,
                    manual_intervention_required=False,
                    evidence=evidence,
                )
            except (AcquisitionError, OSError) as exc:
                result.update(
                    acquisition_status="failure",
                    active_exact_icpns=[],
                    excluded_non_active_icpns=[],
                    manual_intervention_required=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            results.append(result)

    success = [r for r in results if r.get("acquisition_status") == "success"]
    manual = [r for r in results if r.get("manual_intervention_required") is True]
    complete = len(success) == len(targets) and not manual and bool(exact_set)
    exact_list = sorted(exact_set)
    exact_digest = hashlib.sha256(("\n".join(exact_list) + "\n").encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "scope": "STM32H7RS bounded official-ST exact ICPN discovery",
        "selected_partition": "STM32H7RS",
        "target_config": EXPECTED_TARGET_CONFIG,
        "base_device_count": len(targets),
        "attempted_targets": len(results),
        "successful_targets": len(success),
        "manual_review_targets": len(manual),
        "active_exact_icpn_count": len(exact_list),
        "active_exact_icpns": exact_list,
        "active_exact_icpn_set_sha256": exact_digest,
        "excluded_non_active_part_number_count": len(excluded_set),
        "excluded_non_active_part_numbers": sorted(excluded_set),
        "bounded_exact_discovery_complete": complete,
        "status": "discovered" if complete else "blocked_manual_review",
        "next_gate": "stm32h7rs-bounded-exact-icpn-admission-readiness-gate" if complete else None,
        "claims": {
            "production_write_authorized": False,
            "icpn_admission_authorized": False,
            "exact_icpn_discovery_completed": complete,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "physical_validation_claimed": False,
            "hil_required_for_catalog_admission": False,
        },
        "results": results,
    }, browser_version


def write_outputs(output_dir: Path, manifest: dict[str, object], summary: dict[str, object], browser_version: str | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "targets.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "discovery-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "exact-icpns.json").write_text(json.dumps({
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "exact_icpn_count": summary["active_exact_icpn_count"],
        "exact_icpn_set_sha256": summary["active_exact_icpn_set_sha256"],
        "exact_icpns": summary["active_exact_icpns"],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in summary.get("results", []):
        if isinstance(item, dict) and isinstance(item.get("evidence"), dict):
            base = str(item["base_device"]).lower()
            (output_dir / f"{base}.json").write_text(json.dumps(item["evidence"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    provenance = {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "acquisition_transport": BROWSER_TRANSPORT,
        "browser_version": browser_version,
        "partition_source_sha256": sha256(SOURCE_PATH),
        "selection_sha256": sha256(SELECTION_PATH),
        "accessibility_summary_sha256": sha256(ACCESSIBILITY),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()

    targets = deterministic_targets()
    manifest = target_manifest(targets)
    summary, browser_version = run_live(
        targets,
        headless=args.headless,
        delay_seconds=args.delay_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    write_outputs(args.output_dir, manifest, summary, browser_version)
    if summary.get("bounded_exact_discovery_complete") is not True:
        raise SystemExit("STM32H7RS exact ICPN discovery requires manual review")


if __name__ == "__main__":
    main()
