#!/usr/bin/env python3
"""Deterministic sharding and aggregation for STM32L1 L1.2 live discovery.

This module changes execution only. Commercial identity authority, target
selection, generation-aware surface policy, exact-set join rules, and the
Production read-only boundary remain owned by stm32l1_phase_l1_2_discovery.
A Base Device and all of its required evidence surfaces always stay in one
shard. Only the final aggregate may claim full bounded-discovery cleanliness.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from st_product_page_acquisition import AcquisitionError
import stm32l1_phase_l1_2_discovery as core

MAX_SHARDS = 8


def _all_false(value: object, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise AcquisitionError(f"{label}: missing fail-closed claims")
    escaped = {key: item for key, item in value.items() if item is not False}
    if escaped:
        raise AcquisitionError(f"{label}: escaped fail-closed claims: {escaped}")


def select_shard(
    full_targets: list[core.DiscoveryTarget], *, shard_index: int, shard_count: int
) -> list[core.DiscoveryTarget]:
    core.validate_targets(full_targets)
    if shard_count < 1 or shard_count > MAX_SHARDS:
        raise AcquisitionError(f"invalid L1.2 shard_count: {shard_count}")
    if shard_index < 0 or shard_index >= shard_count:
        raise AcquisitionError(f"invalid L1.2 shard_index: {shard_index}")
    selected = [target for index, target in enumerate(full_targets) if index % shard_count == shard_index]
    if not selected:
        raise AcquisitionError(f"L1.2 shard {shard_index}/{shard_count} is empty")
    return selected


def _validate_slice(
    *,
    full_targets: list[core.DiscoveryTarget],
    targets: list[core.DiscoveryTarget],
    shard_index: int,
    shard_count: int,
) -> None:
    expected = select_shard(full_targets, shard_index=shard_index, shard_count=shard_count)
    if targets != expected:
        raise AcquisitionError(f"L1.2 shard {shard_index}/{shard_count} target membership drifted")


def run_discovery_slice(
    *,
    full_targets: list[core.DiscoveryTarget],
    targets: list[core.DiscoveryTarget],
    shard_index: int,
    shard_count: int,
    catalog_rows: list[dict[str, str]],
    fetcher: core.Fetcher,
    evidence_builder: core.EvidenceBuilder = core.build_discovery_evidence_record,
    timeout_seconds: float = 90.0,
) -> dict[str, object]:
    _validate_slice(
        full_targets=full_targets,
        targets=targets,
        shard_index=shard_index,
        shard_count=shard_count,
    )
    results: list[dict[str, object]] = []
    metrics: Counter[str] = Counter()
    routing: Counter[str] = Counter()
    exact_owner: dict[str, str] = {}

    for target in targets:
        metrics["attempted"] += 1
        result: dict[str, object] = {
            "subfamily": target.subfamily,
            "base_device": target.base_device,
            "selection_reason": target.selection_reason,
            "required_surface_count": len(target.surfaces),
        }
        acquired: list[dict[str, object]] = []
        failed_surface: dict[str, object] | None = None
        for surface in target.surfaces:
            metrics["surface_attempted"] += 1
            try:
                body, final_url, etag, last_modified = fetcher(surface.source_url, timeout_seconds)
                evidence = evidence_builder(
                    body=body,
                    source_url=surface.source_url,
                    final_url=final_url,
                    base_device=target.base_device,
                    retrieved_at_utc=core.time.strftime("%Y-%m-%dT%H:%M:%SZ", core.time.gmtime()),
                    http_etag=etag,
                    http_last_modified=last_modified,
                )
                acquired.append(
                    {
                        "role": surface.role,
                        "source_url": surface.source_url,
                        "final_url": final_url,
                        "evidence": evidence,
                    }
                )
                metrics["surface_success"] += 1
            except (AcquisitionError, OSError) as exc:
                if isinstance(exc, AcquisitionError) and str(exc) == core.CANONICAL_PAGE_404:
                    metrics["surface_source_unavailable_404"] += 1
                    failed_surface = {
                        "role": surface.role,
                        "source_url": surface.source_url,
                        "status": "source_unavailable",
                        "error": str(exc),
                    }
                else:
                    metrics["surface_failure"] += 1
                    failed_surface = {
                        "role": surface.role,
                        "source_url": surface.source_url,
                        "status": "failure",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                break

        if failed_surface is not None:
            is_404 = failed_surface.get("status") == "source_unavailable"
            metrics["source_unavailable_404" if is_404 else "manual_review"] += 1
            if not is_404:
                metrics["acquisition_failure"] += 1
            routing["not_applicable"] += 1
            result.update(
                acquisition_status="source_unavailable" if is_404 else "failure",
                disposition="source_unavailable_excluded" if is_404 else "manual_review",
                commercial_identity_status="unverified",
                surface_results=acquired + [failed_surface],
                manual_intervention_required=not is_404,
            )
            results.append(result)
            continue

        try:
            aggregate = core._aggregate_surface_evidence(target=target, acquired=acquired)
            active = aggregate["exact_icpns"]
            excluded_rows = aggregate["excluded_non_active_part_numbers"]
            assert isinstance(active, list) and isinstance(excluded_rows, list)
            for icpn in active:
                owner = exact_owner.setdefault(str(icpn), target.base_device)
                if owner != target.base_device:
                    raise AcquisitionError(f"{icpn}: duplicate exact identity across Base Devices")
            mappings = [
                {"icpn": str(value), **core.resolve_mapping(str(value), catalog_rows)}
                for value in active
            ]
            route_status = core._routing_status(mappings)
            disposition = "active_candidates" if active else "lifecycle_excluded"
            result.update(
                acquisition_status="success",
                disposition=disposition,
                commercial_identity_status="verified_active" if active else "verified_non_active_only",
                evidence=aggregate,
                surface_results=acquired,
                routing_observations=mappings,
                openocd_routing={"status": route_status, "gates_commercial_identity": False},
                manual_intervention_required=False,
            )
            metrics["verified_identity_targets"] += 1
            metrics[disposition] += 1
            metrics["active_exact_icpns"] += len(active)
            metrics["excluded_non_active_part_numbers"] += len(excluded_rows)
            routing[route_status if active else "not_applicable"] += 1
        except AcquisitionError as exc:
            metrics["manual_review"] += 1
            metrics["acquisition_failure"] += 1
            routing["not_applicable"] += 1
            result.update(
                acquisition_status="failure",
                disposition="manual_review",
                commercial_identity_status="unverified",
                surface_results=acquired,
                manual_intervention_required=True,
                error_type=type(exc).__name__,
                error=str(exc),
            )
        results.append(result)

    expected_surfaces = sum(len(target.surfaces) for target in targets)
    clean = (
        metrics["attempted"] == len(targets)
        and metrics["surface_attempted"] == expected_surfaces
        and metrics["surface_success"] == expected_surfaces
        and metrics["verified_identity_targets"] == len(targets)
        and metrics["active_candidates"] + metrics["lifecycle_excluded"] == len(targets)
        and metrics["manual_review"] == 0
        and metrics["acquisition_failure"] == 0
        and metrics["source_unavailable_404"] == 0
    )
    return {
        "schema_version": 1,
        "phase": core.PHASE,
        "family": core.FAMILY,
        "discovery_id": core.DISCOVERY_ID,
        "scope": "bounded read-only official-ST STM32L1 commercial discovery shard",
        "acquisition_transport": core.BROWSER_TRANSPORT,
        "commercial_identity_authority": core.COMMERCIAL_IDENTITY_AUTHORITY,
        "generation_migration_authority": core.MIGRATION_AUTHORITY,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "full_base_device_count": len(full_targets),
        "full_evidence_surface_count": sum(len(target.surfaces) for target in full_targets),
        "base_device_count": len(targets),
        "evidence_surface_count": expected_surfaces,
        "attempted": metrics["attempted"],
        "surface_attempted": metrics["surface_attempted"],
        "surface_success": metrics["surface_success"],
        "surface_source_unavailable_404": metrics["surface_source_unavailable_404"],
        "surface_failure": metrics["surface_failure"],
        "commercial_identity_verified_targets": metrics["verified_identity_targets"],
        "active_candidate_targets": metrics["active_candidates"],
        "lifecycle_excluded_targets": metrics["lifecycle_excluded"],
        "source_unavailable_exclusions": metrics["source_unavailable_404"],
        "identity_manual_intervention_required": metrics["manual_review"],
        "acquisition_failure": metrics["acquisition_failure"],
        "active_exact_icpn_candidates": len(exact_owner),
        "excluded_non_active_part_numbers": metrics["excluded_non_active_part_numbers"],
        "slice_clean": clean,
        "bounded_discovery_clean": False,
        "results": results,
        "claims": {
            "canonical_admission_authorized": False,
            "complete_family_inventory_claimed": False,
            "flash_geometry_qualified": False,
            "manufacturer_evidence_is_admission": False,
            "option_security_semantics_qualified": False,
            "physical_hil_qualified": False,
            "production_write_authorized": False,
            "programming_algorithm_equivalence": False,
            "programming_policy_defined": False,
            "runtime_programming_support_claimed": False,
        },
    }


def slice_is_clean(summary: dict[str, object]) -> bool:
    claims = summary.get("claims")
    return (
        summary.get("slice_clean") is True
        and summary.get("bounded_discovery_clean") is False
        and summary.get("attempted") == summary.get("base_device_count")
        and summary.get("surface_attempted") == summary.get("evidence_surface_count")
        and summary.get("surface_success") == summary.get("evidence_surface_count")
        and summary.get("commercial_identity_verified_targets") == summary.get("base_device_count")
        and summary.get("identity_manual_intervention_required") == 0
        and summary.get("acquisition_failure") == 0
        and summary.get("source_unavailable_exclusions") == 0
        and isinstance(claims, dict)
        and bool(claims)
        and all(value is False for value in claims.values())
    )


def aggregate_summaries(
    *, full_targets: list[core.DiscoveryTarget], summaries: list[dict[str, object]]
) -> dict[str, object]:
    core.validate_targets(full_targets)
    if not summaries:
        raise AcquisitionError("L1.2 sharded aggregation requires summaries")

    shard_counts = {item.get("shard_count") for item in summaries}
    if len(shard_counts) != 1:
        raise AcquisitionError("L1.2 shard_count mismatch")
    shard_count = next(iter(shard_counts))
    if not isinstance(shard_count, int) or shard_count < 1 or shard_count > MAX_SHARDS:
        raise AcquisitionError("L1.2 aggregate has invalid shard_count")
    indices = [item.get("shard_index") for item in summaries]
    if sorted(indices) != list(range(shard_count)):
        raise AcquisitionError("L1.2 aggregate shard index set is incomplete or duplicated")
    if len(summaries) != shard_count:
        raise AcquisitionError("L1.2 aggregate summary count does not match shard_count")

    expected_by_base = {target.base_device: target for target in full_targets}
    results_by_base: dict[str, dict[str, object]] = {}
    browser_records: list[dict[str, object]] = []
    for summary in summaries:
        if summary.get("phase") != core.PHASE or summary.get("family") != core.FAMILY:
            raise AcquisitionError("L1.2 aggregate shard identity mismatch")
        if summary.get("discovery_id") != core.DISCOVERY_ID:
            raise AcquisitionError("L1.2 aggregate discovery_id mismatch")
        if summary.get("full_base_device_count") != len(full_targets):
            raise AcquisitionError("L1.2 aggregate full Base Device boundary drifted")
        if summary.get("full_evidence_surface_count") != sum(len(t.surfaces) for t in full_targets):
            raise AcquisitionError("L1.2 aggregate full surface boundary drifted")
        if not slice_is_clean(summary):
            raise AcquisitionError(f"L1.2 shard {summary.get('shard_index')} is not clean")
        _all_false(summary.get("claims"), "L1.2 shard claims")
        browser = summary.get("browser")
        if isinstance(browser, dict):
            browser_records.append(browser)
        results = summary.get("results")
        if not isinstance(results, list):
            raise AcquisitionError("L1.2 shard results missing")
        for result in results:
            if not isinstance(result, dict):
                raise AcquisitionError("L1.2 shard result must be an object")
            base = result.get("base_device")
            if not isinstance(base, str) or base not in expected_by_base:
                raise AcquisitionError("L1.2 shard contains an unexpected Base Device")
            if base in results_by_base:
                raise AcquisitionError(f"{base}: duplicate Base Device across shards")
            target = expected_by_base[base]
            if result.get("required_surface_count") != len(target.surfaces):
                raise AcquisitionError(f"{base}: required surface count drifted in shard result")
            results_by_base[base] = result

    expected_bases = [target.base_device for target in full_targets]
    if set(results_by_base) != set(expected_bases):
        missing = sorted(set(expected_bases) - set(results_by_base))
        extra = sorted(set(results_by_base) - set(expected_bases))
        raise AcquisitionError(f"L1.2 aggregate Base Device coverage mismatch: missing={missing}, extra={extra}")

    results = [results_by_base[base] for base in expected_bases]
    routing: Counter[str] = Counter()
    exact_owner: dict[str, str] = {}
    active_targets = 0
    lifecycle_excluded_targets = 0
    excluded_count = 0
    surface_success = 0
    for result in results:
        base = str(result["base_device"])
        if result.get("acquisition_status") != "success":
            raise AcquisitionError(f"{base}: aggregate contains non-success result")
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise AcquisitionError(f"{base}: aggregate evidence missing")
        active = evidence.get("exact_icpns")
        excluded = evidence.get("excluded_non_active_part_numbers")
        if not isinstance(active, list) or not isinstance(excluded, list):
            raise AcquisitionError(f"{base}: aggregate exact disposition missing")
        for icpn in active:
            if not isinstance(icpn, str):
                raise AcquisitionError(f"{base}: aggregate Active ICPN is not a string")
            owner = exact_owner.setdefault(icpn, base)
            if owner != base:
                raise AcquisitionError(f"{icpn}: duplicate exact identity across L1.2 shards")
        excluded_count += len(excluded)
        disposition = result.get("disposition")
        if disposition == "active_candidates":
            active_targets += 1
        elif disposition == "lifecycle_excluded":
            lifecycle_excluded_targets += 1
        else:
            raise AcquisitionError(f"{base}: unexpected aggregate disposition {disposition}")
        route = result.get("openocd_routing")
        status = route.get("status") if isinstance(route, dict) else "not_applicable"
        routing[str(status)] += 1
        surface_results = result.get("surface_results")
        if not isinstance(surface_results, list):
            raise AcquisitionError(f"{base}: aggregate surface results missing")
        if len(surface_results) != int(result["required_surface_count"]):
            raise AcquisitionError(f"{base}: aggregate surface result count drifted")
        if not all(isinstance(item, dict) and isinstance(item.get("evidence"), dict) for item in surface_results):
            raise AcquisitionError(f"{base}: aggregate contains non-success evidence surface")
        surface_success += len(surface_results)

    representative_results = {
        str(result["base_device"]): result
        for result in results
        if result.get("base_device") in core.EXPECTED_L1_1_REPRESENTATIVES
    }
    representative_continuity = (
        set(representative_results) == core.EXPECTED_L1_1_REPRESENTATIVES
        and all(
            result.get("commercial_identity_status") == "verified_active"
            for result in representative_results.values()
        )
    )
    expected_surfaces = sum(len(target.surfaces) for target in full_targets)
    clean = (
        len(results) == len(full_targets)
        and surface_success == expected_surfaces
        and active_targets + lifecycle_excluded_targets == len(full_targets)
        and representative_continuity
    )
    claims = {
        "canonical_admission_authorized": False,
        "complete_family_inventory_claimed_before_clean_live_evidence": False,
        "flash_geometry_qualified": False,
        "manufacturer_evidence_is_admission": False,
        "option_security_semantics_qualified": False,
        "physical_hil_qualified": False,
        "production_write_authorized": False,
        "programming_algorithm_equivalence": False,
        "programming_policy_defined": False,
        "runtime_programming_support_claimed": False,
    }
    summary: dict[str, object] = {
        "schema_version": 1,
        "phase": core.PHASE,
        "family": core.FAMILY,
        "discovery_id": core.DISCOVERY_ID,
        "scope": "bounded read-only official-ST STM32L1 complete commercial discovery",
        "acquisition_transport": core.BROWSER_TRANSPORT,
        "commercial_identity_authority": core.COMMERCIAL_IDENTITY_AUTHORITY,
        "generation_migration_authority": core.MIGRATION_AUTHORITY,
        "base_device_count": len(full_targets),
        "generation_pair_target_count": sum(1 for target in full_targets if len(target.surfaces) == 2),
        "evidence_surface_count": expected_surfaces,
        "attempted": len(results),
        "surface_attempted": surface_success,
        "surface_success": surface_success,
        "surface_source_unavailable_404": 0,
        "surface_failure": 0,
        "dispositioned_targets": len(results),
        "commercial_identity_verified_targets": len(results),
        "active_candidate_targets": active_targets,
        "lifecycle_excluded_targets": lifecycle_excluded_targets,
        "source_unavailable_exclusions": 0,
        "identity_manual_intervention_required": 0,
        "acquisition_failure": 0,
        "active_exact_icpn_candidates": len(exact_owner),
        "excluded_non_active_part_numbers": excluded_count,
        "representative_continuity_clean": representative_continuity,
        "commercial_identity_clean": clean,
        "bounded_discovery_clean": clean,
        "openocd_routing": {
            "unique": routing["unique"],
            "ambiguous": routing["ambiguous"],
            "unmapped": routing["unmapped"],
            "not_applicable": routing["not_applicable"],
            "gates_commercial_identity": False,
        },
        "routing_followup_required": routing["ambiguous"] + routing["unmapped"],
        "parallel_shards": {
            "count": shard_count,
            "indices": list(range(shard_count)),
            "base_device_partition": "deterministic target index modulo shard_count",
            "base_device_surfaces_are_atomic": True,
        },
        "results": results,
        "claims": claims,
    }
    if browser_records:
        summary["browser_shards"] = browser_records
    if not core.discovery_is_clean(summary):
        raise AcquisitionError("L1.2 full sharded aggregate did not satisfy canonical clean predicate")
    return summary
