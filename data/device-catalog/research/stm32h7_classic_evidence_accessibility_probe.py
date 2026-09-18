#!/usr/bin/env python3
"""Bounded official-ST evidence accessibility probe for STM32H7-classic.

This transaction proves only that one deterministic representative Base Device
per frozen STM32H7-classic subfamily has accessible official ST commercial
identity and lifecycle evidence. It does not perform full exact-ICPN discovery,
admit devices, write Production, define programming equivalence, or authorize
runtime/debug/security/physical/HIL execution behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from st_browser_acquisition import BROWSER_TRANSPORT, STBrowserAcquirer, build_browser_evidence_record
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32_post_u0_evidence_probe import (
    ProbeTarget,
    RateLimitedFetcher,
    base_from_ordering_pattern,
    source_url_for_base,
)

HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE / "stm32h7-partition-source.json"
SELECTION_PATH = HERE / "stm32h7-classic-scope-selection.json"
PROBE_ID = "stm32h7-classic-bounded-official-st-evidence-accessibility-v1"
EXPECTED_TARGET_CONFIG = "tcl/target/stm32h7x.cfg"
EXPECTED_FAMILY = "STM32H7 Series"
EXPECTED_SUBFAMILIES = (
    "STM32H723", "STM32H725", "STM32H730", "STM32H733",
    "STM32H735", "STM32H742", "STM32H743", "STM32H745",
    "STM32H747", "STM32H750", "STM32H753", "STM32H755",
    "STM32H757", "STM32H7A3", "STM32H7B0", "STM32H7B3",
)
EXPECTED_ROWS = 166
EXPECTED_ORDERING_ROWS = 138
EXPECTED_CMSIS_ROWS = 28
EXPECTED_SOURCE_ROWS = 200
EXPECTED_SOURCE_DUPLICATE_RESOLUTIONS = 34
MIN_DELAY_SECONDS = 1.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcquisitionError(f"{path.name}: expected JSON object")
    return value


def guarded_partition_rows() -> list[dict[str, str]]:
    selection = load_json(SELECTION_PATH)
    if selection.get("selection_id") != "stm32h7-classic-scope-selection-v1":
        raise AcquisitionError("unexpected STM32H7-classic scope selection id")
    if selection.get("selected_partition") != "STM32H7-classic":
        raise AcquisitionError("STM32H7-classic is no longer the selected bounded partition")
    if selection.get("selected_target_config") != EXPECTED_TARGET_CONFIG:
        raise AcquisitionError("STM32H7-classic selected target config drifted")
    if selection.get("selected_row_count") != EXPECTED_ROWS:
        raise AcquisitionError("STM32H7-classic selected row count drifted")
    if selection.get("selected_subfamily_count") != len(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32H7-classic selected subfamily count drifted")
    if selection.get("next_gate") != "stm32h7-classic-bounded-official-manufacturer-evidence-accessibility-gate":
        raise AcquisitionError("STM32H7-classic evidence-accessibility gate drifted")

    source = load_json(SOURCE_PATH)
    if source.get("source_id") != "stm32h7-partition-source-v1":
        raise AcquisitionError("unexpected STM32H7 partition source id")
    rows = source.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_SOURCE_ROWS:
        raise AcquisitionError("frozen STM32H7 source must contain exactly 200 rows")
    resolutions = source.get("duplicate_resolutions")
    if not isinstance(resolutions, list) or len(resolutions) != EXPECTED_SOURCE_DUPLICATE_RESOLUTIONS:
        raise AcquisitionError("frozen STM32H7 duplicate-resolution surface drifted")

    bounded: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise AcquisitionError("frozen STM32H7 source row is not an object")
        if row.get("family") == EXPECTED_FAMILY and row.get("target_config") == EXPECTED_TARGET_CONFIG:
            bounded.append({str(k): str(v) for k, v in row.items()})
    if len(bounded) != EXPECTED_ROWS:
        raise AcquisitionError(f"STM32H7-classic bounded row count drifted: {len(bounded)}")

    kinds = Counter(row.get("identifier_kind", "") for row in bounded)
    if kinds != Counter({"ordering_pattern": EXPECTED_ORDERING_ROWS, "cmsis_device_name": EXPECTED_CMSIS_ROWS}):
        raise AcquisitionError(f"STM32H7-classic identifier-kind surface drifted: {dict(kinds)}")
    subfamilies = tuple(sorted({row.get("subfamily", "") for row in bounded}))
    if subfamilies != EXPECTED_SUBFAMILIES:
        raise AcquisitionError(f"STM32H7-classic subfamily surface drifted: {subfamilies}")
    if any(row.get("plasma_series") != "STM32H7" for row in bounded):
        raise AcquisitionError("STM32H7-classic row escaped STM32H7 plasma-series boundary")
    return bounded


def deterministic_targets() -> list[ProbeTarget]:
    rows = guarded_partition_rows()
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("identifier_kind") == "ordering_pattern":
            by_subfamily[row["subfamily"]].add(base_from_ordering_pattern(row))

    targets: list[ProbeTarget] = []
    for subfamily in EXPECTED_SUBFAMILIES:
        bases = sorted(by_subfamily[subfamily])
        if not bases:
            raise AcquisitionError(f"{subfamily}: no ordering-pattern Base Device")
        base = bases[0]
        url = source_url_for_base(base)
        validate_source_url(url)
        if not base.startswith(subfamily):
            raise AcquisitionError(f"{base}: escaped {subfamily} boundary")
        targets.append(
            ProbeTarget(
                series="STM32H7-classic",
                subfamily=subfamily,
                base_device=base,
                source_url=url,
                selection_reason="deterministic lexical-min Base Device in frozen STM32H7-classic ordering-pattern subfamily",
            )
        )
    if len(targets) != len(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32H7-classic representative target count drifted")
    return targets


def target_manifest(targets: list[ProbeTarget]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "scope": "bounded representative official-ST evidence accessibility only",
        "selection_source": str(SELECTION_PATH.relative_to(HERE.parent.parent.parent)),
        "partition_source": str(SOURCE_PATH.relative_to(HERE.parent.parent.parent)),
        "selection_sha256": sha256(SELECTION_PATH),
        "partition_source_sha256": sha256(SOURCE_PATH),
        "target_count": len(targets),
        "targets": [
            {
                "series": target.series,
                "subfamily": target.subfamily,
                "base_device": target.base_device,
                "source_url": target.source_url,
                "selection_reason": target.selection_reason,
            }
            for target in targets
        ],
    }


def run_live(targets: list[ProbeTarget], *, headless: bool, delay_seconds: float, timeout_seconds: float) -> tuple[dict[str, object], str | None]:
    if delay_seconds < MIN_DELAY_SECONDS:
        raise AcquisitionError(f"live probe delay must be at least {MIN_DELAY_SECONDS:.1f}s")
    results: list[dict[str, object]] = []
    browser_version: str | None = None
    with STBrowserAcquirer(headless=headless) as browser:
        browser_version = browser.browser_version
        fetcher = RateLimitedFetcher(delay_seconds=delay_seconds, fetcher=browser.fetch)
        for target in targets:
            result: dict[str, object] = {
                "series": target.series,
                "subfamily": target.subfamily,
                "base_device": target.base_device,
                "source_url": target.source_url,
                "selection_reason": target.selection_reason,
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
                    raise AcquisitionError(f"{target.base_device}: foreign exact ICPN in evidence")
                excluded_ids = []
                for item in excluded:
                    if not isinstance(item, dict):
                        raise AcquisitionError(f"{target.base_device}: invalid lifecycle exclusion")
                    icpn = item.get("icpn")
                    status = item.get("marketing_status")
                    if not isinstance(icpn, str) or not icpn.startswith(target.base_device):
                        raise AcquisitionError(f"{target.base_device}: foreign excluded ICPN")
                    if not isinstance(status, str) or not status.strip():
                        raise AcquisitionError(f"{target.base_device}: excluded ICPN lacks Marketing Status")
                    excluded_ids.append(icpn)
                if not active and not excluded_ids:
                    raise AcquisitionError(f"{target.base_device}: no commercial identity disposition")
                result.update(
                    acquisition_status="success",
                    commercial_identity_status="verified_active" if active else "verified_non_active_only",
                    active_exact_icpn_count=len(active),
                    excluded_non_active_count=len(excluded_ids),
                    manual_intervention_required=False,
                    evidence=evidence,
                )
            except (AcquisitionError, OSError) as exc:
                result.update(
                    acquisition_status="failure",
                    commercial_identity_status="unverified",
                    active_exact_icpn_count=0,
                    excluded_non_active_count=0,
                    manual_intervention_required=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            results.append(result)

    success = [item for item in results if item.get("acquisition_status") == "success"]
    manual = [item for item in results if item.get("manual_intervention_required") is True]
    active_total = sum(int(item.get("active_exact_icpn_count", 0)) for item in results)
    excluded_total = sum(int(item.get("excluded_non_active_count", 0)) for item in results)
    complete = len(success) == len(EXPECTED_SUBFAMILIES) and not manual
    summary = {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "scope": "STM32H7-classic bounded representative official-ST commercial identity/lifecycle evidence accessibility",
        "selected_partition": "STM32H7-classic",
        "target_config": EXPECTED_TARGET_CONFIG,
        "attempted_targets": len(results),
        "successful_targets": len(success),
        "manual_review_targets": len(manual),
        "active_exact_icpns_observed_on_representative_pages": active_total,
        "excluded_non_active_part_numbers_observed": excluded_total,
        "bounded_probe_complete": complete,
        "official_st_evidence_accessible_for_all_subfamilies": complete,
        "status": "accessible" if complete else "blocked_manual_review",
        "next_gate": "stm32h7-classic-bounded-exact-icpn-discovery-gate" if complete else None,
        "claims": {
            "production_write_authorized": False,
            "icpn_admission_authorized": False,
            "full_exact_icpn_discovery_completed": False,
            "representative_probe_is_full_family_enumeration": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "security_mutation_authorized": False,
            "debug_attach_supported": False,
            "physical_validation_claimed": False,
            "hil_required_for_catalog_admission": False,
        },
        "results": results,
    }
    return summary, browser_version


def write_outputs(output_dir: Path, manifest: dict[str, object], summary: dict[str, object], browser_version: str | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "targets.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "probe-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in summary.get("results", []):
        if isinstance(item, dict) and isinstance(item.get("evidence"), dict):
            base = str(item["base_device"]).lower()
            (output_dir / f"{base}.json").write_text(
                json.dumps(item["evidence"], indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    provenance = {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "acquisition_transport": BROWSER_TRANSPORT,
        "browser_version": browser_version,
        "partition_source_sha256": sha256(SOURCE_PATH),
        "selection_sha256": sha256(SELECTION_PATH),
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
    if summary.get("bounded_probe_complete") is not True:
        raise SystemExit("STM32H7-classic evidence accessibility probe requires manual review")


if __name__ == "__main__":
    main()
