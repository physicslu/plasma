#!/usr/bin/env python3
"""Bounded sharded official-ST exact ICPN discovery for STM32H7-classic.

Sharding changes execution only. Target selection, commercial identity authority,
lifecycle policy, and Catalog governance remain unchanged. Only the complete
aggregate may claim exact ICPN discovery completion.
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

from st_browser_acquisition import BROWSER_TRANSPORT, STBrowserAcquirer, build_browser_evidence_record
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32_post_u0_evidence_probe import ProbeTarget, RateLimitedFetcher, base_from_ordering_pattern, source_url_for_base
from stm32h7_classic_evidence_accessibility_probe import (
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    SOURCE_PATH,
    SELECTION_PATH,
    guarded_partition_rows,
)

HERE = Path(__file__).resolve().parent
ACCESSIBILITY = HERE / "evidence/stm32h7-classic-accessibility-live-2026-09-18/probe-summary.json"
DISCOVERY_ID = "stm32h7-classic-bounded-exact-icpn-discovery-v1"
EXPECTED_BASE_DEVICE_COUNT = 102
EXPECTED_ORDERING_ROWS = 138
MIN_DELAY_SECONDS = 1.0
MAX_SHARDS = 8
DEFAULT_SHARD_COUNT = 6


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcquisitionError(f"{path.name}: expected JSON object")
    return value


def guard_accessibility() -> dict[str, Any]:
    payload = load_json(ACCESSIBILITY)
    if payload.get("probe_id") != "stm32h7-classic-bounded-official-st-evidence-accessibility-v1":
        raise AcquisitionError("unexpected STM32H7-classic accessibility probe id")
    if payload.get("selected_partition") != "STM32H7-classic":
        raise AcquisitionError("STM32H7-classic accessibility partition drifted")
    if payload.get("attempted_targets") != 16 or payload.get("successful_targets") != 16:
        raise AcquisitionError("STM32H7-classic accessibility coverage drifted")
    if payload.get("manual_review_targets") != 0:
        raise AcquisitionError("STM32H7-classic accessibility retains manual review")
    if payload.get("official_st_evidence_accessible_for_all_subfamilies") is not True:
        raise AcquisitionError("STM32H7-classic official-ST accessibility gate is not complete")
    if payload.get("next_gate") != "stm32h7-classic-bounded-exact-icpn-discovery-gate":
        raise AcquisitionError("STM32H7-classic accessibility next gate drifted")
    claims = payload.get("claims")
    if not isinstance(claims, dict) or any(value is not False for value in claims.values()):
        raise AcquisitionError("STM32H7-classic accessibility claims escaped fail-closed state")
    return payload


def deterministic_targets() -> list[ProbeTarget]:
    guard_accessibility()
    rows = guarded_partition_rows()
    ordering_rows = [row for row in rows if row.get("identifier_kind") == "ordering_pattern"]
    if len(ordering_rows) != EXPECTED_ORDERING_ROWS:
        raise AcquisitionError(f"STM32H7-classic ordering-pattern row count drifted: {len(ordering_rows)}")

    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in ordering_rows:
        base = base_from_ordering_pattern(row)
        by_subfamily[row["subfamily"]].add(base)

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
                    series="STM32H7-classic",
                    subfamily=subfamily,
                    base_device=base,
                    source_url=url,
                    selection_reason="unique Base Device derived from frozen STM32H7-classic ordering-pattern rows",
                )
            )

    if len(targets) != EXPECTED_BASE_DEVICE_COUNT:
        raise AcquisitionError(f"STM32H7-classic Base Device count drifted: {len(targets)}")
    if len({target.base_device for target in targets}) != EXPECTED_BASE_DEVICE_COUNT:
        raise AcquisitionError("STM32H7-classic deterministic targets are not unique")
    if {target.subfamily for target in targets} != set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32H7-classic target subfamily coverage drifted")
    return targets


def target_manifest(targets: list[ProbeTarget]) -> dict[str, Any]:
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
                "series": target.series,
                "subfamily": target.subfamily,
                "base_device": target.base_device,
                "source_url": target.source_url,
                "selection_reason": target.selection_reason,
            }
            for target in targets
        ],
    }


def select_shard(full_targets: list[ProbeTarget], *, shard_index: int, shard_count: int) -> list[ProbeTarget]:
    if shard_count < 1 or shard_count > MAX_SHARDS:
        raise AcquisitionError(f"invalid STM32H7-classic shard_count: {shard_count}")
    if shard_index < 0 or shard_index >= shard_count:
        raise AcquisitionError(f"invalid STM32H7-classic shard_index: {shard_index}")
    selected = [target for index, target in enumerate(full_targets) if index % shard_count == shard_index]
    if not selected:
        raise AcquisitionError(f"STM32H7-classic shard {shard_index}/{shard_count} is empty")
    return selected


def _false_claims(*, discovery_complete: bool) -> dict[str, bool]:
    return {
        "production_write_authorized": False,
        "icpn_admission_authorized": False,
        "exact_icpn_discovery_completed": discovery_complete,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_programming_support_claimed": False,
        "security_mutation_authorized": False,
        "debug_attach_supported": False,
        "physical_validation_claimed": False,
        "hil_required_for_catalog_admission": False,
    }


def run_live_slice(
    *,
    full_targets: list[ProbeTarget],
    targets: list[ProbeTarget],
    shard_index: int,
    shard_count: int,
    headless: bool,
    delay_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    expected = select_shard(full_targets, shard_index=shard_index, shard_count=shard_count)
    if targets != expected:
        raise AcquisitionError("STM32H7-classic shard membership drifted")
    if delay_seconds < MIN_DELAY_SECONDS:
        raise AcquisitionError(f"live discovery delay must be at least {MIN_DELAY_SECONDS:.1f}s")

    results: list[dict[str, Any]] = []
    exact_set: set[str] = set()
    excluded_set: set[str] = set()
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
                if not isinstance(active, list) or not all(isinstance(value, str) for value in active):
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
                if set(active) & set(local_excluded):
                    raise AcquisitionError(f"{target.base_device}: Active/excluded identity overlap")

                exact_set.update(active)
                excluded_set.update(local_excluded)
                result.update(
                    acquisition_status="success",
                    commercial_identity_status="verified_active" if active else "verified_non_active_only",
                    active_exact_icpns=active,
                    excluded_non_active_icpns=local_excluded,
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

    success = [item for item in results if item.get("acquisition_status") == "success"]
    manual = [item for item in results if item.get("manual_intervention_required") is True]
    clean = len(success) == len(targets) and not manual

    return {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "scope": "STM32H7-classic bounded official-ST exact ICPN discovery shard",
        "selected_partition": "STM32H7-classic",
        "target_config": EXPECTED_TARGET_CONFIG,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "full_base_device_count": len(full_targets),
        "base_device_count": len(targets),
        "attempted_targets": len(results),
        "successful_targets": len(success),
        "manual_review_targets": len(manual),
        "active_exact_icpn_count": len(exact_set),
        "active_exact_icpns": sorted(exact_set),
        "excluded_non_active_part_number_count": len(excluded_set),
        "excluded_non_active_part_numbers": sorted(excluded_set),
        "slice_clean": clean,
        "bounded_exact_discovery_complete": False,
        "browser_version": browser_version,
        "claims": _false_claims(discovery_complete=False),
        "results": results,
    }


def slice_is_clean(summary: dict[str, Any]) -> bool:
    claims = summary.get("claims")
    return (
        summary.get("slice_clean") is True
        and summary.get("bounded_exact_discovery_complete") is False
        and summary.get("attempted_targets") == summary.get("base_device_count")
        and summary.get("successful_targets") == summary.get("base_device_count")
        and summary.get("manual_review_targets") == 0
        and isinstance(claims, dict)
        and claims.get("exact_icpn_discovery_completed") is False
        and all(value is False for key, value in claims.items() if key != "exact_icpn_discovery_completed")
    )


def aggregate_summaries(*, full_targets: list[ProbeTarget], summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if not summaries:
        raise AcquisitionError("STM32H7-classic sharded aggregation requires summaries")

    shard_counts = {item.get("shard_count") for item in summaries}
    if len(shard_counts) != 1:
        raise AcquisitionError("STM32H7-classic shard_count mismatch")
    shard_count = next(iter(shard_counts))
    if not isinstance(shard_count, int) or shard_count < 1 or shard_count > MAX_SHARDS:
        raise AcquisitionError("STM32H7-classic aggregate has invalid shard_count")
    indices = [item.get("shard_index") for item in summaries]
    if sorted(indices) != list(range(shard_count)) or len(summaries) != shard_count:
        raise AcquisitionError("STM32H7-classic aggregate shard index set is incomplete or duplicated")

    expected_by_base = {target.base_device: target for target in full_targets}
    results_by_base: dict[str, dict[str, Any]] = {}
    browser_shards: list[dict[str, Any]] = []

    for summary in summaries:
        if summary.get("discovery_id") != DISCOVERY_ID:
            raise AcquisitionError("STM32H7-classic shard discovery id mismatch")
        if summary.get("selected_partition") != "STM32H7-classic":
            raise AcquisitionError("STM32H7-classic shard partition mismatch")
        if summary.get("target_config") != EXPECTED_TARGET_CONFIG:
            raise AcquisitionError("STM32H7-classic shard target config mismatch")
        if summary.get("full_base_device_count") != len(full_targets):
            raise AcquisitionError("STM32H7-classic shard full target boundary drifted")
        if not slice_is_clean(summary):
            raise AcquisitionError(f"STM32H7-classic shard {summary.get('shard_index')} is not clean")

        browser_shards.append(
            {
                "shard_index": summary.get("shard_index"),
                "browser_version": summary.get("browser_version"),
                "base_device_count": summary.get("base_device_count"),
            }
        )
        results = summary.get("results")
        if not isinstance(results, list):
            raise AcquisitionError("STM32H7-classic shard results missing")
        for result in results:
            if not isinstance(result, dict):
                raise AcquisitionError("STM32H7-classic shard result must be an object")
            base = result.get("base_device")
            if not isinstance(base, str) or base not in expected_by_base:
                raise AcquisitionError("STM32H7-classic shard contains unexpected Base Device")
            if base in results_by_base:
                raise AcquisitionError(f"{base}: duplicate Base Device across shards")
            results_by_base[base] = result

    expected_bases = [target.base_device for target in full_targets]
    if set(results_by_base) != set(expected_bases):
        missing = sorted(set(expected_bases) - set(results_by_base))
        extra = sorted(set(results_by_base) - set(expected_bases))
        raise AcquisitionError(f"STM32H7-classic aggregate coverage mismatch: missing={missing}, extra={extra}")

    results = [results_by_base[base] for base in expected_bases]
    exact_owner: dict[str, str] = {}
    excluded_owner: dict[str, str] = {}
    for result in results:
        base = str(result["base_device"])
        if result.get("acquisition_status") != "success" or result.get("manual_intervention_required") is not False:
            raise AcquisitionError(f"{base}: aggregate contains non-success result")
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise AcquisitionError(f"{base}: aggregate evidence missing")
        active = evidence.get("exact_icpns")
        excluded = evidence.get("excluded_non_active_part_numbers")
        if not isinstance(active, list) or not isinstance(excluded, list):
            raise AcquisitionError(f"{base}: aggregate exact disposition missing")
        if not active and not excluded:
            raise AcquisitionError(f"{base}: aggregate lacks exact identity disposition")

        for icpn in active:
            if not isinstance(icpn, str):
                raise AcquisitionError(f"{base}: Active ICPN is not a string")
            owner = exact_owner.setdefault(icpn, base)
            if owner != base:
                raise AcquisitionError(f"{icpn}: duplicate Active identity across Base Devices")
        for row in excluded:
            if not isinstance(row, dict) or not isinstance(row.get("icpn"), str):
                raise AcquisitionError(f"{base}: malformed lifecycle exclusion")
            icpn = str(row["icpn"])
            owner = excluded_owner.setdefault(icpn, base)
            if owner != base:
                raise AcquisitionError(f"{icpn}: duplicate excluded identity across Base Devices")

    overlap = set(exact_owner) & set(excluded_owner)
    if overlap:
        raise AcquisitionError(f"Active/excluded exact identity overlap: {sorted(overlap)}")

    exact_list = sorted(exact_owner)
    excluded_list = sorted(excluded_owner)
    if not exact_list:
        raise AcquisitionError("STM32H7-classic aggregate discovered no Active exact ICPNs")
    exact_digest = hashlib.sha256(("\n".join(exact_list) + "\n").encode("utf-8")).hexdigest()

    return {
        "schema_version": 1,
        "discovery_id": DISCOVERY_ID,
        "scope": "STM32H7-classic bounded official-ST exact ICPN discovery",
        "selected_partition": "STM32H7-classic",
        "target_config": EXPECTED_TARGET_CONFIG,
        "base_device_count": len(full_targets),
        "attempted_targets": len(results),
        "successful_targets": len(results),
        "manual_review_targets": 0,
        "active_exact_icpn_count": len(exact_list),
        "active_exact_icpns": exact_list,
        "active_exact_icpn_set_sha256": exact_digest,
        "excluded_non_active_part_number_count": len(excluded_list),
        "excluded_non_active_part_numbers": excluded_list,
        "bounded_exact_discovery_complete": True,
        "status": "discovered",
        "next_gate": "stm32h7-classic-bounded-exact-icpn-admission-readiness-gate",
        "parallel_shards": {
            "count": shard_count,
            "indices": list(range(shard_count)),
            "base_device_partition": "deterministic target index modulo shard_count",
            "base_device_is_atomic": True,
        },
        "browser_shards": sorted(browser_shards, key=lambda item: int(item["shard_index"])),
        "claims": _false_claims(discovery_complete=True),
        "results": results,
    }


def write_shard_outputs(output_dir: Path, summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shard-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_aggregate_outputs(output_dir: Path, manifest: dict[str, Any], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "targets.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "discovery-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "exact-icpns.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "discovery_id": DISCOVERY_ID,
                "exact_icpn_count": summary["active_exact_icpn_count"],
                "exact_icpn_set_sha256": summary["active_exact_icpn_set_sha256"],
                "exact_icpns": summary["active_exact_icpns"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
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
        "workflow_role": "authoritative_sharded_exact_icpn_discovery",
        "source_repository": os.environ.get("GITHUB_REPOSITORY"),
        "executed_git_sha": os.environ.get("GITHUB_SHA"),
        "workflow_run_id": int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None,
        "workflow_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]) if os.environ.get("GITHUB_RUN_ATTEMPT") else None,
        "acquisition_transport": BROWSER_TRANSPORT,
        "browser_shards": summary.get("browser_shards"),
        "shard_count": (summary.get("parallel_shards") or {}).get("count"),
        "partition_source_sha256": sha256(SOURCE_PATH),
        "selection_sha256": sha256(SELECTION_PATH),
        "accessibility_summary_sha256": sha256(ACCESSIBILITY),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_shard_summaries(root: Path) -> list[dict[str, Any]]:
    paths = sorted(root.rglob("shard-summary.json"))
    if not paths:
        raise AcquisitionError(f"no shard summaries found below {root}")
    return [load_json(path) for path in paths]


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--shard-index", type=int)
    mode.add_argument("--aggregate-root", type=Path)
    parser.add_argument("--shard-count", type=int, default=DEFAULT_SHARD_COUNT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()

    full_targets = deterministic_targets()
    manifest = target_manifest(full_targets)

    if args.shard_index is not None:
        targets = select_shard(full_targets, shard_index=args.shard_index, shard_count=args.shard_count)
        summary = run_live_slice(
            full_targets=full_targets,
            targets=targets,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            headless=args.headless,
            delay_seconds=args.delay_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        write_shard_outputs(args.output_dir, summary)
        if not slice_is_clean(summary):
            raise SystemExit(f"STM32H7-classic discovery shard {args.shard_index} requires manual review")
        return

    summaries = load_shard_summaries(args.aggregate_root)
    aggregate = aggregate_summaries(full_targets=full_targets, summaries=summaries)
    write_aggregate_outputs(args.output_dir, manifest, aggregate)


if __name__ == "__main__":
    main()
