#!/usr/bin/env python3
"""Fail-closed STM32C0 C0.2 manufacturer-authoritative commercial discovery.

C0.2 expands the frozen C0.1 ordering-pattern surface into the complete deterministic
Base Device set, then observes exact commercial ICPNs plus lifecycle only from official
ST product pages. STM32C0 uses the already-qualified dual-surface authority:
Quality & Reliability supplies exact identity, Sample & Buy supplies Marketing Status,
and the exact Part Number sets must join exactly before any lifecycle disposition is
accepted. OpenOCD routing is diagnostic only and never gates commercial identity.

No canonical admission, Production write, programming, HIL, or runtime authority is
created by this module.
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
from stm32c0_phase_c0_1_foundation import (
    DEFAULT_BASELINE as C0_1_BASELINE,
    DEFAULT_CATALOG,
    EXPECTED_SUBFAMILIES,
    TARGET_CONFIG,
    base_from_row,
    commercial_ordering_rows,
    read_catalog,
)

HERE = Path(__file__).resolve().parent
PHASE = "C0.2"
FAMILY = "STM32C0"
PARSER_PROFILE = "stm32c0_c0_2_dual_surface_v1"
DISCOVERY_ID = "stm32c0-c0.2-official-st-commercial-discovery-v1"
EXPECTED_C0_1_BASELINE_SHA256 = "c89e8c528f80f9b199a2b153d3d40aa4af090e50c492a7c88bfa7876ce406515"
EXPECTED_C0_1_REPRESENTATIVES = {
    "STM32C011F4", "STM32C031C4", "STM32C051C6",
    "STM32C071C8", "STM32C091CB", "STM32C092CB",
}
AUTHORITY_SURFACE = "quality_and_reliability_identity_plus_sample_and_buy_lifecycle"
COMMERCIAL_IDENTITY_AUTHORITY = (
    "official_st_quality_and_reliability_exact_identity_plus_"
    "sample_and_buy_marketing_status_exact_set_join"
)
DEFAULT_OUTPUT = Path("/tmp/stm32c0-c0.2-live-summary.json")
MAX_TARGETS = 73
MIN_DELAY_SECONDS = 1.0
CANONICAL_PAGE_404 = "browser navigation returned HTTP 404"


@dataclass(frozen=True)
class DiscoveryTarget:
    subfamily: str
    base_device: str
    source_url: str
    selection_reason: str


FetchResult = tuple[bytes, str, str | None, str | None]
Fetcher = Callable[[str, float], FetchResult]
EvidenceBuilder = Callable[..., dict[str, object]]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _all_false(value: object, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise AcquisitionError(f"{label}: missing fail-closed claims")
    escaped = {key: item for key, item in value.items() if item is not False}
    if escaped:
        raise AcquisitionError(f"{label}: escaped fail-closed claims: {escaped}")


def validate_c0_1_boundary(path: Path = C0_1_BASELINE) -> dict[str, Any]:
    if sha256(path) != EXPECTED_C0_1_BASELINE_SHA256:
        raise AcquisitionError("C0.1 foundation baseline SHA-256 drifted")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("phase") != "C0.1" or payload.get("family") != FAMILY:
        raise AcquisitionError("unexpected C0.1 foundation baseline identity")
    if payload.get("source_row_count") != 95 or payload.get("target_config") != TARGET_CONFIG:
        raise AcquisitionError("C0.1 bounded research surface drifted")
    kinds = payload.get("identifier_kind_counts")
    if kinds != {"cmsis_device_name": 22, "ordering_pattern": 73}:
        raise AcquisitionError("C0.1 identifier-kind boundary drifted")
    _all_false(payload.get("claims"), "C0.1 claims")
    reps = payload.get("initial_targets")
    observed = {
        item.get("base_device") for item in reps or [] if isinstance(item, dict)
    }
    if observed != EXPECTED_C0_1_REPRESENTATIVES:
        raise AcquisitionError("C0.1 representative continuity boundary drifted")
    return payload


def source_url_for_base(base_device: str) -> str:
    return f"https://www.st.com/en/microcontrollers-microprocessors/{base_device.lower()}.html"


def deterministic_targets(catalog_rows: list[dict[str, str]]) -> list[DiscoveryTarget]:
    validate_c0_1_boundary()
    rows = commercial_ordering_rows(catalog_rows)
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_subfamily[row["subfamily"]].add(base_from_row(row))

    targets: list[DiscoveryTarget] = []
    for subfamily in EXPECTED_SUBFAMILIES:
        bases = sorted(by_subfamily[subfamily])
        if not bases:
            raise AcquisitionError(f"{subfamily}: no ordering-pattern Base Devices")
        for base in bases:
            targets.append(
                DiscoveryTarget(
                    subfamily=subfamily,
                    base_device=base,
                    source_url=source_url_for_base(base),
                    selection_reason=(
                        "deterministic unique Base Device collapsed from frozen C0.1 "
                        "ordering-pattern surface"
                    ),
                )
            )

    bases = [target.base_device for target in targets]
    if not bases or len(bases) > MAX_TARGETS or len(set(bases)) != len(bases):
        raise AcquisitionError(f"C0.2 invalid deterministic Base Device set: {len(bases)}")
    if not EXPECTED_C0_1_REPRESENTATIVES.issubset(set(bases)):
        raise AcquisitionError("C0.2 deterministic set lost a frozen C0.1 representative")
    return targets


def target_manifest(targets: list[DiscoveryTarget]) -> dict[str, object]:
    validate_targets(targets)
    counts = Counter(target.subfamily for target in targets)
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "discovery_id": DISCOVERY_ID,
        "scope": "bounded read-only official-ST STM32C0 complete commercial discovery",
        "c0_1_foundation_sha256": EXPECTED_C0_1_BASELINE_SHA256,
        "base_device_count": len(targets),
        "base_device_counts_by_subfamily": dict(sorted(counts.items())),
        "targets": [
            {
                "subfamily": target.subfamily,
                "base_device": target.base_device,
                "source_url": target.source_url,
                "selection_reason": target.selection_reason,
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


def validate_targets(targets: list[DiscoveryTarget]) -> None:
    if not targets or len(targets) > MAX_TARGETS:
        raise AcquisitionError("C0.2 target count escaped frozen ordering-pattern bound")
    seen: set[str] = set()
    for target in targets:
        if target.subfamily not in EXPECTED_SUBFAMILIES:
            raise AcquisitionError(f"unsupported C0 subfamily: {target.subfamily}")
        if target.base_device in seen or not target.base_device.startswith(target.subfamily):
            raise AcquisitionError(f"invalid/duplicate C0 Base Device: {target.base_device}")
        seen.add(target.base_device)
        validate_source_url(target.source_url)
        if target.source_url != source_url_for_base(target.base_device):
            raise AcquisitionError(f"{target.base_device}: source URL slug mismatch")
    if not EXPECTED_C0_1_REPRESENTATIVES.issubset(seen):
        raise AcquisitionError("C0.2 target manifest lost C0.1 representatives")


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
        raise AcquisitionError("STM32C0 C0.2 evidence authority surface drifted")
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
        return {
            "status": "unique",
            "ordering_pattern": row["part_number"],
            "target_config": row["target_config"],
        }
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "ordering_patterns": sorted(row["part_number"] for row in candidates),
        }
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

    for target in targets:
        metrics["attempted"] += 1
        result: dict[str, object] = {
            "subfamily": target.subfamily,
            "base_device": target.base_device,
            "source_url": target.source_url,
            "selection_reason": target.selection_reason,
        }
        try:
            body, final_url, etag, last_modified = fetcher(target.source_url, timeout_seconds)
            evidence = evidence_builder(
                body=body,
                source_url=target.source_url,
                final_url=final_url,
                base_device=target.base_device,
                retrieved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                http_etag=etag,
                http_last_modified=last_modified,
            )
            active = evidence.get("exact_icpns")
            if not isinstance(active, list) or not all(isinstance(value, str) for value in active):
                raise AcquisitionError(f"{target.base_device}: exact_icpns must be a string list")
            if any(not value.startswith(target.base_device) for value in active):
                raise AcquisitionError(f"{target.base_device}: foreign exact ICPN in evidence")
            excluded_ids = _excluded_ids(evidence.get("excluded_non_active_part_numbers"), target.base_device)
            if not active and not excluded_ids:
                raise AcquisitionError(f"{target.base_device}: no exact identity disposition")
            mappings = [{"icpn": value, **resolve_mapping(value, catalog_rows)} for value in active]
            route_status = _routing_status(mappings)
            disposition = "active_candidates" if active else "lifecycle_excluded"
            result.update(
                acquisition_status="success",
                disposition=disposition,
                commercial_identity_status="verified_active" if active else "verified_non_active_only",
                evidence=evidence,
                routing_observations=mappings,
                openocd_routing={"status": route_status, "gates_commercial_identity": False},
                manual_intervention_required=False,
            )
            metrics["verified_identity_targets"] += 1
            metrics[disposition] += 1
            metrics["active_exact_icpns"] += len(active)
            metrics["excluded_non_active_part_numbers"] += len(excluded_ids)
            routing[route_status if active else "not_applicable"] += 1
        except (AcquisitionError, OSError) as exc:
            if isinstance(exc, AcquisitionError) and str(exc) == CANONICAL_PAGE_404:
                metrics["source_unavailable_404"] += 1
                routing["not_applicable"] += 1
                result.update(
                    acquisition_status="source_unavailable",
                    disposition="source_unavailable_excluded",
                    commercial_identity_status="unverified",
                    source_unavailable_status="http_404",
                    manual_intervention_required=False,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            else:
                metrics["manual_review"] += 1
                metrics["acquisition_failure"] += 1
                result.update(
                    acquisition_status="failure",
                    disposition="manual_review",
                    commercial_identity_status="unverified",
                    manual_intervention_required=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        results.append(result)

    dispositioned = (
        metrics["active_candidates"]
        + metrics["lifecycle_excluded"]
        + metrics["source_unavailable_404"]
    )
    exact_set: set[str] = set()
    for result in results:
        evidence = result.get("evidence")
        if isinstance(evidence, dict):
            for icpn in evidence.get("exact_icpns", []):
                if isinstance(icpn, str):
                    exact_set.add(icpn)

    representative_results = {
        result["base_device"]: result
        for result in results
        if result.get("base_device") in EXPECTED_C0_1_REPRESENTATIVES
    }
    representative_continuity = (
        set(representative_results) == EXPECTED_C0_1_REPRESENTATIVES
        and all(result.get("commercial_identity_status") == "verified_active" for result in representative_results.values())
    )

    clean = (
        metrics["attempted"] == len(targets)
        and metrics["verified_identity_targets"] == len(targets)
        and dispositioned == len(targets)
        and metrics["manual_review"] == 0
        and metrics["acquisition_failure"] == 0
        and metrics["source_unavailable_404"] == 0
        and bool(exact_set)
        and representative_continuity
    )
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "discovery_id": DISCOVERY_ID,
        "scope": "bounded read-only official-ST STM32C0 commercial identity/lifecycle discovery",
        "c0_1_foundation_sha256": EXPECTED_C0_1_BASELINE_SHA256,
        "commercial_identity_authority": COMMERCIAL_IDENTITY_AUTHORITY,
        "evidence_surface": AUTHORITY_SURFACE,
        "attempted": metrics["attempted"],
        "base_device_count": len(targets),
        "commercial_identity_verified_targets": metrics["verified_identity_targets"],
        "active_candidate_targets": metrics["active_candidates"],
        "lifecycle_excluded_targets": metrics["lifecycle_excluded"],
        "source_unavailable_exclusions": metrics["source_unavailable_404"],
        "identity_manual_intervention_required": metrics["manual_review"],
        "acquisition_failure": metrics["acquisition_failure"],
        "dispositioned_targets": dispositioned,
        "active_exact_icpn_candidates": len(exact_set),
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
        "acquisition_transport": BROWSER_TRANSPORT,
        "results": results,
        "claims": {
            "canonical_admission_authorized": False,
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
        and summary.get("commercial_identity_verified_targets") == summary.get("base_device_count")
        and summary.get("identity_manual_intervention_required") == 0
        and isinstance(summary.get("active_exact_icpn_candidates"), int)
        and int(summary["active_exact_icpn_candidates"]) > 0
        and isinstance(claims, dict)
        and claims
        and all(value is False for value in claims.values())
    )


def write_evidence_files(summary: dict[str, object], evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for result in summary.get("results", []):
        if not isinstance(result, dict) or result.get("acquisition_status") != "success":
            continue
        base = result.get("base_device")
        evidence = result.get("evidence")
        if not isinstance(base, str) or not isinstance(evidence, dict):
            raise AcquisitionError("successful C0.2 result lacks Base Device/evidence")
        (evidence_dir / f"{base}.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def write_target_manifest(path: Path, targets: list[DiscoveryTarget]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(target_manifest(targets), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets-output", type=Path)
    args = parser.parse_args()
    rows = read_catalog(DEFAULT_CATALOG)
    targets = deterministic_targets(rows)
    payload = target_manifest(targets)
    if args.targets_output is not None:
        write_target_manifest(args.targets_output, targets)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
