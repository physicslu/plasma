#!/usr/bin/env python3
"""Fail-closed STM32L1 L1.2 manufacturer-authoritative commercial discovery.

L1.2 expands the frozen L1.1 ordering-pattern research surface into the
complete bounded deterministic Base Device research set, then observes exact
commercial ICPN identity and lifecycle only from official ST dual-surface
evidence.

STM32L1 has a manufacturer-defined generation split. For STM32L100/L151/L152
x6/x8/xB Base Devices, both the legacy canonical product page and the
Generation-A companion page are required evidence surfaces. Other bounded Base
Devices use the canonical current product page. Exact lifecycle dispositions
from multiple surfaces are aggregated fail-closed: an exact ICPN may never be
Active on one surface and non-Active on another.

Quality & Reliability is exact Part Number identity authority. Sample & Buy is
Marketing Status authority. Exact sets must join on every acquired page before
that page contributes evidence. OpenOCD only bounds research and supplies
routing diagnostics.

Nothing here authorizes canonical admission, Production writes, programming
policy, Flash/security qualification, HIL, electrical/socket qualification, or
runtime programming support.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from st_browser_acquisition import BROWSER_TRANSPORT
from st_dual_surface_evidence import build_dual_surface_browser_evidence_record as _build_evidence
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32_post_u0_evidence_probe import base_from_ordering_pattern
from stm32l1_phase_l1_1_foundation import (
    DEFAULT_BASELINE as L1_1_BASELINE,
    DEFAULT_CATALOG,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGETS,
    TARGET_CONFIG,
    commercial_ordering_rows,
    read_catalog,
)

HERE = Path(__file__).resolve().parent
PHASE = "L1.2"
FAMILY = "STM32L1"
PARSER_PROFILE = "stm32l1_l1_2_generation_aware_dual_surface_v1"
DISCOVERY_ID = "stm32l1-l1.2-official-st-commercial-discovery-v1"
EXPECTED_L1_1_BASELINE_GIT_BLOB = "8da20cfc02c8106d5163338e85fb6425bc9ccdc9"
EXPECTED_GATE1_PRODUCTION_GIT_BLOB = "1aa2311a25a69742c428147a402816ed5071e04e"
EXPECTED_L1_1_REPRESENTATIVES = {base for _subfamily, base in EXPECTED_TARGETS}
AUTHORITY_SURFACE = "quality_and_reliability_identity_plus_sample_and_buy_lifecycle"
COMMERCIAL_IDENTITY_AUTHORITY = (
    "official_st_quality_and_reliability_exact_identity_plus_"
    "sample_and_buy_marketing_status_exact_set_join"
)
GENERATION_A_SUBFAMILIES = frozenset({"STM32L100", "STM32L151", "STM32L152"})
GENERATION_A_DENSITIES = frozenset({"6", "8", "B"})
MIGRATION_AUTHORITY = "TN1176"
DEFAULT_PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
DEFAULT_OUTPUT = Path("/tmp/stm32l1-l1.2-live-summary.json")
MAX_BASE_DEVICES = 87
MAX_SURFACES = 174
MIN_DELAY_SECONDS = 1.0
CANONICAL_PAGE_404 = "browser navigation returned HTTP 404"


@dataclass(frozen=True)
class DiscoverySurface:
    role: str
    source_url: str
    required: bool = True


@dataclass(frozen=True)
class DiscoveryTarget:
    subfamily: str
    base_device: str
    surfaces: tuple[DiscoverySurface, ...]
    selection_reason: str


FetchResult = tuple[bytes, str, str | None, str | None]
Fetcher = Callable[[str, float], FetchResult]
EvidenceBuilder = Callable[..., dict[str, object]]


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()


def _all_false(value: object, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise AcquisitionError(f"{label}: missing fail-closed claims")
    escaped = {key: item for key, item in value.items() if item is not False}
    if escaped:
        raise AcquisitionError(f"{label}: escaped fail-closed claims: {escaped}")


def validate_l1_1_boundary(path: Path = L1_1_BASELINE) -> dict[str, Any]:
    if git_blob_sha(path) != EXPECTED_L1_1_BASELINE_GIT_BLOB:
        raise AcquisitionError("L1.1 foundation baseline Git blob drifted")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("phase") != "L1.1" or payload.get("family") != FAMILY:
        raise AcquisitionError("unexpected L1.1 foundation baseline identity")
    if payload.get("source_row_count") != 132 or payload.get("target_config") != TARGET_CONFIG:
        raise AcquisitionError("L1.1 bounded research surface drifted")
    if payload.get("identifier_kind_counts") != {"cmsis_device_name": 45, "ordering_pattern": 87}:
        raise AcquisitionError("L1.1 identifier-kind boundary drifted")
    if payload.get("subfamilies") != list(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("L1.1 subfamily boundary drifted")
    _all_false(payload.get("claims"), "L1.1 claims")
    reps = payload.get("initial_targets")
    observed = {item.get("base_device") for item in reps or [] if isinstance(item, dict)}
    if observed != EXPECTED_L1_1_REPRESENTATIVES:
        raise AcquisitionError("L1.1 representative continuity boundary drifted")
    evidence = payload.get("evidence_foundation")
    if not isinstance(evidence, dict) or evidence.get("generation_migration_authority") != MIGRATION_AUTHORITY:
        raise AcquisitionError("L1.1 generation-migration authority drifted")
    return payload


def validate_gate1_production_boundary(path: Path = DEFAULT_PRODUCTION_MANIFEST) -> dict[str, Any]:
    if git_blob_sha(path) != EXPECTED_GATE1_PRODUCTION_GIT_BLOB:
        raise AcquisitionError("L1.2 Gate 1 Production manifest Git blob drifted")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "production":
        raise AcquisitionError("L1.2 Gate 1 Production manifest is invalid")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise AcquisitionError("L1.2 Gate 1 Production sources missing")
    counts = {
        item.get("family"): item.get("row_count")
        for item in sources if isinstance(item, dict)
    }
    if len(counts) != 12 or sum(value for value in counts.values() if isinstance(value, int)) != 1718:
        raise AcquisitionError("L1.2 Gate 1 Production aggregate drifted")
    if FAMILY in counts or counts.get("STM32L4") != 446:
        raise AcquisitionError("L1.2 Gate 1 Production family boundary drifted")
    return payload


def canonical_url(base_device: str) -> str:
    return f"https://www.st.com/en/microcontrollers-microprocessors/{base_device.lower()}.html"


def generation_a_url(base_device: str) -> str:
    return f"https://www.st.com/en/microcontrollers-microprocessors/{base_device.lower()}-a.html"


def requires_generation_a_companion(subfamily: str, base_device: str) -> bool:
    return subfamily in GENERATION_A_SUBFAMILIES and base_device[-1:] in GENERATION_A_DENSITIES


def surfaces_for_base(subfamily: str, base_device: str) -> tuple[DiscoverySurface, ...]:
    surfaces = [DiscoverySurface(role="canonical_or_legacy", source_url=canonical_url(base_device))]
    if requires_generation_a_companion(subfamily, base_device):
        surfaces.append(DiscoverySurface(role="generation_a_companion", source_url=generation_a_url(base_device)))
    return tuple(surfaces)


def deterministic_targets(catalog_rows: list[dict[str, str]]) -> list[DiscoveryTarget]:
    validate_l1_1_boundary()
    validate_gate1_production_boundary()
    rows = commercial_ordering_rows(catalog_rows)
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_subfamily[row["subfamily"]].add(base_from_ordering_pattern(row))

    targets: list[DiscoveryTarget] = []
    for subfamily in EXPECTED_SUBFAMILIES:
        bases = sorted(by_subfamily[subfamily])
        if not bases:
            raise AcquisitionError(f"{subfamily}: no ordering-pattern Base Devices")
        for base in bases:
            targets.append(DiscoveryTarget(
                subfamily=subfamily,
                base_device=base,
                surfaces=surfaces_for_base(subfamily, base),
                selection_reason=(
                    "deterministic unique Base Device collapsed from frozen L1.1 "
                    "ordering-pattern surface with TN1176 generation-aware page policy"
                ),
            ))

    bases = [target.base_device for target in targets]
    surface_count = sum(len(target.surfaces) for target in targets)
    if not bases or len(bases) > MAX_BASE_DEVICES or len(set(bases)) != len(bases):
        raise AcquisitionError(f"L1.2 invalid deterministic Base Device set: {len(bases)}")
    if surface_count > MAX_SURFACES:
        raise AcquisitionError(f"L1.2 evidence surface count escaped bound: {surface_count}")
    if not EXPECTED_L1_1_REPRESENTATIVES.issubset(set(bases)):
        raise AcquisitionError("L1.2 deterministic set lost a frozen L1.1 representative")
    return targets


def validate_targets(targets: list[DiscoveryTarget]) -> None:
    if not targets or len(targets) > MAX_BASE_DEVICES:
        raise AcquisitionError("L1.2 target count escaped frozen ordering-pattern bound")
    seen: set[str] = set()
    covered: set[str] = set()
    surface_urls: set[str] = set()
    for target in targets:
        if target.subfamily not in EXPECTED_SUBFAMILIES:
            raise AcquisitionError(f"unsupported L1 subfamily: {target.subfamily}")
        if target.base_device in seen or not target.base_device.startswith(target.subfamily):
            raise AcquisitionError(f"invalid/duplicate L1 Base Device: {target.base_device}")
        seen.add(target.base_device)
        covered.add(target.subfamily)
        expected_surfaces = surfaces_for_base(target.subfamily, target.base_device)
        if target.surfaces != expected_surfaces:
            raise AcquisitionError(f"{target.base_device}: generation-aware evidence surface drifted")
        for surface in target.surfaces:
            validate_source_url(surface.source_url)
            if not surface.required:
                raise AcquisitionError(f"{target.base_device}: L1.2 currently permits required surfaces only")
            if surface.source_url in surface_urls:
                raise AcquisitionError(f"duplicate L1.2 evidence URL: {surface.source_url}")
            surface_urls.add(surface.source_url)
    if covered != set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("L1.2 target manifest lost a frozen subfamily")
    if not EXPECTED_L1_1_REPRESENTATIVES.issubset(seen):
        raise AcquisitionError("L1.2 target manifest lost L1.1 representatives")


def target_manifest(targets: list[DiscoveryTarget]) -> dict[str, object]:
    validate_targets(targets)
    counts = Counter(target.subfamily for target in targets)
    generation_pairs = sum(1 for target in targets if len(target.surfaces) == 2)
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "discovery_id": DISCOVERY_ID,
        "scope": "bounded read-only official-ST STM32L1 complete commercial discovery",
        "l1_1_foundation_git_blob": EXPECTED_L1_1_BASELINE_GIT_BLOB,
        "production_manifest_git_blob_at_gate1": EXPECTED_GATE1_PRODUCTION_GIT_BLOB,
        "generation_migration_authority": MIGRATION_AUTHORITY,
        "generation_a_rule": "L100/L151/L152 x6/x8/xB require canonical legacy plus -a companion",
        "base_device_count": len(targets),
        "base_device_counts_by_subfamily": dict(sorted(counts.items())),
        "generation_pair_target_count": generation_pairs,
        "evidence_surface_count": sum(len(target.surfaces) for target in targets),
        "targets": [
            {
                "subfamily": target.subfamily,
                "base_device": target.base_device,
                "selection_reason": target.selection_reason,
                "surfaces": [
                    {"role": surface.role, "source_url": surface.source_url, "required": surface.required}
                    for surface in target.surfaces
                ],
            }
            for target in targets
        ],
        "claims": {
            "canonical_admission_authorized": False,
            "complete_family_inventory_claimed_before_live_evidence": False,
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


class RateLimitedFetcher:
    def __init__(self, *, delay_seconds: float, fetcher: Fetcher) -> None:
        if delay_seconds < MIN_DELAY_SECONDS:
            raise AcquisitionError(f"live discovery delay must be at least {MIN_DELAY_SECONDS:.1f}s")
        self.delay_seconds = delay_seconds
        self.fetcher = fetcher
        self._first = True

    def __call__(self, source_url: str, timeout_seconds: float) -> FetchResult:
        if self._first:
            self._first = False
        else:
            time.sleep(self.delay_seconds)
        return self.fetcher(source_url, timeout_seconds)


def build_discovery_evidence_record(**kwargs: Any) -> dict[str, object]:
    evidence = _build_evidence(parser_profile=PARSER_PROFILE, **kwargs)
    if evidence.get("evidence_surface") != AUTHORITY_SURFACE:
        raise AcquisitionError("STM32L1 L1.2 evidence authority surface drifted")
    return evidence


def _excluded_ids(excluded: object, base_device: str) -> list[str]:
    if not isinstance(excluded, list):
        raise AcquisitionError(f"{base_device}: lifecycle exclusions must be a list")
    values: list[str] = []
    for item in excluded:
        if not isinstance(item, dict):
            raise AcquisitionError(f"{base_device}: lifecycle exclusion must be an object")
        icpn = item.get("icpn")
        status = item.get("marketing_status")
        if not isinstance(icpn, str) or not icpn.startswith(base_device):
            raise AcquisitionError(f"{base_device}: invalid lifecycle-excluded ICPN")
        if not isinstance(status, str) or not status.strip():
            raise AcquisitionError(f"{base_device}: lifecycle exclusion lacks Marketing Status")
        values.append(icpn)
    return values


def commercial_core(icpn: str) -> str:
    for suffix in ("TR", "TT"):
        if icpn.endswith(suffix):
            return icpn[:-len(suffix)]
    return icpn


def resolve_mapping(icpn: str, catalog_rows: list[dict[str, str]]) -> dict[str, object]:
    core = commercial_core(icpn)
    candidates: list[dict[str, str]] = []
    for row in commercial_ordering_rows(catalog_rows):
        pattern = row["part_number"]
        if core.startswith(pattern[:-1]):
            candidates.append(row)
    if len(candidates) == 1:
        row = candidates[0]
        return {"status": "unique", "ordering_pattern": row["part_number"], "target_config": row["target_config"]}
    if len(candidates) > 1:
        return {"status": "ambiguous", "ordering_patterns": sorted(row["part_number"] for row in candidates)}
    return {"status": "unmapped"}


def _routing_status(mappings: list[dict[str, object]]) -> str:
    if not mappings:
        return "not_applicable"
    statuses = Counter(str(item.get("status")) for item in mappings)
    if statuses == Counter({"unique": len(mappings)}):
        return "unique"
    if statuses["ambiguous"]:
        return "ambiguous"
    return "unmapped"


def _aggregate_surface_evidence(
    *,
    target: DiscoveryTarget,
    acquired: list[dict[str, object]],
) -> dict[str, object]:
    active: set[str] = set()
    excluded: dict[str, dict[str, object]] = {}
    lifecycle_class: dict[str, str] = {}
    records: dict[str, dict[str, object]] = {}

    for item in acquired:
        evidence = item.get("evidence")
        if not isinstance(evidence, dict):
            raise AcquisitionError(f"{target.base_device}: missing surface evidence")
        page_active = evidence.get("exact_icpns")
        if not isinstance(page_active, list) or not all(isinstance(value, str) for value in page_active):
            raise AcquisitionError(f"{target.base_device}: exact_icpns must be a string list")
        page_excluded = _excluded_ids(evidence.get("excluded_non_active_part_numbers"), target.base_device)
        if not page_active and not page_excluded:
            raise AcquisitionError(f"{target.base_device}: evidence surface has no exact identity disposition")
        page_records = evidence.get("part_number_records")
        if not isinstance(page_records, list):
            raise AcquisitionError(f"{target.base_device}: exact part-number records missing")

        excluded_objects = {
            row.get("icpn"): row
            for row in evidence.get("excluded_non_active_part_numbers", [])
            if isinstance(row, dict) and isinstance(row.get("icpn"), str)
        }
        record_objects = {
            row.get("icpn"): row
            for row in page_records if isinstance(row, dict) and isinstance(row.get("icpn"), str)
        }
        if set(record_objects) != set(page_active) | set(page_excluded):
            raise AcquisitionError(f"{target.base_device}: surface exact-set join drifted")

        for icpn in page_active:
            if not icpn.startswith(target.base_device):
                raise AcquisitionError(f"{target.base_device}: foreign Active exact ICPN {icpn}")
            prior = lifecycle_class.setdefault(icpn, "active")
            if prior != "active":
                raise AcquisitionError(f"{icpn}: lifecycle conflict across STM32L1 product surfaces")
            active.add(icpn)
            records.setdefault(icpn, record_objects[icpn])
        for icpn in page_excluded:
            prior = lifecycle_class.setdefault(icpn, "non_active")
            if prior != "non_active":
                raise AcquisitionError(f"{icpn}: lifecycle conflict across STM32L1 product surfaces")
            excluded.setdefault(icpn, excluded_objects[icpn])
            records.setdefault(icpn, record_objects[icpn])

    if active & set(excluded):
        raise AcquisitionError(f"{target.base_device}: Active/non-Active exact sets overlap")
    return {
        "evidence_surface": "generation_aware_aggregate_of_official_st_dual_surface_pages",
        "exact_icpns": sorted(active),
        "excluded_non_active_part_numbers": [excluded[key] for key in sorted(excluded)],
        "part_number_records": [records[key] for key in sorted(records)],
        "surface_count": len(acquired),
        "surface_roles": [str(item.get("role")) for item in acquired],
        "generation_migration_authority": MIGRATION_AUTHORITY,
    }


def run_discovery(
    *,
    targets: list[DiscoveryTarget],
    catalog_rows: list[dict[str, str]],
    fetcher: Fetcher,
    evidence_builder: EvidenceBuilder = build_discovery_evidence_record,
    timeout_seconds: float = 90.0,
) -> dict[str, object]:
    validate_targets(targets)
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
                    retrieved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    http_etag=etag,
                    http_last_modified=last_modified,
                )
                acquired.append({
                    "role": surface.role,
                    "source_url": surface.source_url,
                    "final_url": final_url,
                    "evidence": evidence,
                })
                metrics["surface_success"] += 1
            except (AcquisitionError, OSError) as exc:
                if isinstance(exc, AcquisitionError) and str(exc) == CANONICAL_PAGE_404:
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
            aggregate = _aggregate_surface_evidence(target=target, acquired=acquired)
            active = aggregate["exact_icpns"]
            excluded_rows = aggregate["excluded_non_active_part_numbers"]
            assert isinstance(active, list) and isinstance(excluded_rows, list)
            for icpn in active:
                owner = exact_owner.setdefault(str(icpn), target.base_device)
                if owner != target.base_device:
                    raise AcquisitionError(f"{icpn}: duplicate exact identity across Base Devices")
            mappings = [{"icpn": str(value), **resolve_mapping(str(value), catalog_rows)} for value in active]
            route_status = _routing_status(mappings)
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

    dispositioned = metrics["active_candidates"] + metrics["lifecycle_excluded"] + metrics["source_unavailable_404"]
    representative_results = {
        str(result["base_device"]): result
        for result in results if result.get("base_device") in EXPECTED_L1_1_REPRESENTATIVES
    }
    representative_continuity = (
        set(representative_results) == EXPECTED_L1_1_REPRESENTATIVES
        and all(result.get("commercial_identity_status") == "verified_active" for result in representative_results.values())
    )
    expected_surfaces = sum(len(target.surfaces) for target in targets)
    clean = (
        metrics["attempted"] == len(targets)
        and metrics["surface_attempted"] == expected_surfaces
        and metrics["surface_success"] == expected_surfaces
        and metrics["verified_identity_targets"] == len(targets)
        and dispositioned == len(targets)
        and metrics["manual_review"] == 0
        and metrics["acquisition_failure"] == 0
        and metrics["source_unavailable_404"] == 0
        and representative_continuity
    )
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "discovery_id": DISCOVERY_ID,
        "scope": "bounded read-only official-ST STM32L1 complete commercial discovery",
        "acquisition_transport": BROWSER_TRANSPORT,
        "commercial_identity_authority": COMMERCIAL_IDENTITY_AUTHORITY,
        "generation_migration_authority": MIGRATION_AUTHORITY,
        "base_device_count": len(targets),
        "generation_pair_target_count": sum(1 for target in targets if len(target.surfaces) == 2),
        "evidence_surface_count": expected_surfaces,
        "attempted": metrics["attempted"],
        "surface_attempted": metrics["surface_attempted"],
        "surface_success": metrics["surface_success"],
        "surface_source_unavailable_404": metrics["surface_source_unavailable_404"],
        "surface_failure": metrics["surface_failure"],
        "dispositioned_targets": dispositioned,
        "commercial_identity_verified_targets": metrics["verified_identity_targets"],
        "active_candidate_targets": metrics["active_candidates"],
        "lifecycle_excluded_targets": metrics["lifecycle_excluded"],
        "source_unavailable_exclusions": metrics["source_unavailable_404"],
        "identity_manual_intervention_required": metrics["manual_review"],
        "acquisition_failure": metrics["acquisition_failure"],
        "active_exact_icpn_candidates": len(exact_owner),
        "excluded_non_active_part_numbers": metrics["excluded_non_active_part_numbers"],
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
        "results": results,
        "claims": {
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
        },
    }


def discovery_is_clean(summary: dict[str, object]) -> bool:
    claims = summary.get("claims")
    return (
        summary.get("bounded_discovery_clean") is True
        and summary.get("commercial_identity_clean") is True
        and summary.get("representative_continuity_clean") is True
        and summary.get("attempted") == summary.get("base_device_count")
        and summary.get("surface_attempted") == summary.get("evidence_surface_count")
        and summary.get("surface_success") == summary.get("evidence_surface_count")
        and summary.get("commercial_identity_verified_targets") == summary.get("base_device_count")
        and summary.get("identity_manual_intervention_required") == 0
        and summary.get("acquisition_failure") == 0
        and summary.get("source_unavailable_exclusions") == 0
        and isinstance(claims, dict) and bool(claims)
        and all(value is False for value in claims.values())
    )


def write_evidence_files(summary: dict[str, object], evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for result in summary.get("results", []):
        if not isinstance(result, dict) or result.get("acquisition_status") != "success":
            continue
        base = result.get("base_device")
        if isinstance(base, str):
            (evidence_dir / f"{base.lower()}.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets-output", type=Path)
    args = parser.parse_args()
    rows = read_catalog(DEFAULT_CATALOG)
    targets = deterministic_targets(rows)
    payload = target_manifest(targets)
    if args.targets_output is not None:
        args.targets_output.parent.mkdir(parents=True, exist_ok=True)
        args.targets_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
