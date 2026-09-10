#!/usr/bin/env python3
"""Bounded, fail-closed official-ST discovery for STM32G4 Phase 4.9B.

Commercial identity/lifecycle authority comes only from official ST evidence.
OpenOCD routing is orthogonal and never gates commercial identity. CMSIS aliases
from Phase 4.9A are routing/name metadata only and never participate in exact
ICPN selection.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from st_browser_acquisition import BROWSER_TRANSPORT
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32g4_dual_surface_evidence import build_dual_surface_browser_evidence_record
from stm32g4_foundation import (
    DEFAULT_CATALOG,
    EXPECTED_SUBFAMILIES,
    FAMILY,
    deterministic_initial_targets,
    read_catalog,
    resolve_ordering_pattern_mapping,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.9B"
DEFAULT_MANIFEST = HERE / "stm32g4-phase4.9b-discovery-manifest.json"
DEFAULT_OUTPUT = Path("/tmp/stm32g4-phase4.9b-live-summary.json")
MAX_TARGETS = len(EXPECTED_SUBFAMILIES)
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


class RateLimitedFetcher:
    def __init__(self, *, delay_seconds: float, fetcher: Fetcher) -> None:
        if delay_seconds < MIN_DELAY_SECONDS:
            raise AcquisitionError(
                f"live discovery delay must be at least {MIN_DELAY_SECONDS:.1f} seconds"
            )
        self.delay_seconds = delay_seconds
        self.fetcher = fetcher
        self._first = True

    def __call__(self, source_url: str, timeout_seconds: float) -> FetchResult:
        if self._first:
            self._first = False
        else:
            time.sleep(self.delay_seconds)
        return self.fetcher(source_url, timeout_seconds)


def source_url_for_base(base_device: str) -> str:
    return (
        "https://www.st.com/en/microcontrollers-microprocessors/"
        f"{base_device.lower()}.html"
    )


def read_manifest(path: Path, catalog_rows: list[dict[str, str]]) -> tuple[str, list[DiscoveryTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("phase") != PHASE:
        raise AcquisitionError("unsupported STM32G4 Phase 4.9B discovery manifest")
    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("Phase 4.9B discovery manifest requires pilot_id")
    if not isinstance(raw_targets, list) or len(raw_targets) != MAX_TARGETS:
        raise AcquisitionError(f"Phase 4.9B discovery requires exactly {MAX_TARGETS} targets")

    targets: list[DiscoveryTarget] = []
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise AcquisitionError(f"Phase 4.9B target {index} must be an object")
        subfamily = raw.get("subfamily")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if not isinstance(subfamily, str) or subfamily not in EXPECTED_SUBFAMILIES:
            raise AcquisitionError(f"invalid STM32G4 subfamily: {subfamily!r}")
        if not isinstance(base, str):
            raise AcquisitionError(f"invalid STM32G4 Base Device: {base!r}")
        if not isinstance(source, str):
            raise AcquisitionError(f"{base}: source_url is required")
        validate_source_url(source)
        if source != source_url_for_base(base):
            raise AcquisitionError(f"{base}: source URL slug mismatch")
        if not isinstance(reason, str) or not reason.strip():
            raise AcquisitionError(f"{base}: selection_reason is required")
        targets.append(DiscoveryTarget(subfamily, base, source, reason.strip()))

    observed = [(target.subfamily, target.base_device) for target in targets]
    expected = deterministic_initial_targets(catalog_rows)
    if observed != expected:
        raise AcquisitionError(
            f"Phase 4.9B target selection drifted: expected={expected} observed={observed}"
        )
    return pilot_id, targets


def commercial_core(icpn: str) -> str:
    for suffix in ("TR", "TT"):
        if icpn.endswith(suffix):
            return icpn[: -len(suffix)]
    return icpn


def resolve_mapping(icpn: str, catalog_rows: list[dict[str, str]]) -> dict[str, Any]:
    return resolve_ordering_pattern_mapping(commercial_core(icpn), catalog_rows)


def _overall_routing_status(mappings: list[dict[str, Any]]) -> str:
    if not mappings:
        return "not_applicable"
    statuses = Counter(str(item.get("status")) for item in mappings)
    if statuses == Counter({"unique": len(mappings)}):
        return "unique"
    if statuses["ambiguous"]:
        return "ambiguous"
    return "unmapped"


def _excluded_icpns(excluded: list[object], base_device: str) -> list[str]:
    identities: list[str] = []
    for item in excluded:
        if not isinstance(item, dict):
            raise AcquisitionError(f"{base_device}: lifecycle exclusion must be an object")
        icpn = item.get("icpn")
        status = item.get("marketing_status")
        if not isinstance(icpn, str) or not icpn.startswith(base_device):
            raise AcquisitionError(f"{base_device}: invalid lifecycle-excluded ICPN")
        if not isinstance(status, str) or not status.strip():
            raise AcquisitionError(f"{base_device}: lifecycle exclusion lacks Marketing Status")
        identities.append(icpn)
    return identities


def run_discovery(
    *,
    pilot_id: str,
    targets: list[DiscoveryTarget],
    catalog_rows: list[dict[str, str]],
    fetcher: Fetcher,
    evidence_builder: EvidenceBuilder = build_dual_surface_browser_evidence_record,
    timeout_seconds: float = 90.0,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    routing_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    active_candidates = excluded_candidates = acquisition_success = acquisition_failure = 0
    verified_identity_targets = 0

    for target in targets:
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
            raw_icpns = evidence.get("exact_icpns")
            excluded = evidence.get("excluded_non_active_part_numbers")
            if not isinstance(raw_icpns, list) or not all(isinstance(v, str) for v in raw_icpns):
                raise AcquisitionError(f"{target.base_device}: exact_icpns must be a string list")
            if not isinstance(excluded, list):
                raise AcquisitionError(f"{target.base_device}: excluded lifecycle rows must be a list")
            excluded_ids = _excluded_icpns(excluded, target.base_device)
            if any(not value.startswith(target.base_device) for value in raw_icpns):
                raise AcquisitionError(f"{target.base_device}: evidence contains a foreign exact ICPN")
            if not raw_icpns and not excluded_ids:
                raise AcquisitionError(
                    f"{target.base_device}: manufacturer page produced no exact identity disposition"
                )

            mappings = [{"icpn": value, **resolve_mapping(value, catalog_rows)} for value in raw_icpns]
            overall = _overall_routing_status(mappings)
            if raw_icpns:
                disposition = "active_candidates"
                identity_status = "verified_active"
                routing_counts[overall] += 1
            else:
                disposition = "lifecycle_excluded"
                identity_status = "verified_non_active_only"
                routing_counts["not_applicable"] += 1
            result.update(
                acquisition_status="success",
                disposition=disposition,
                commercial_identity_status=identity_status,
                evidence=evidence,
                routing_observations=mappings,
                openocd_routing={
                    "status": overall,
                    "candidate_count": len(mappings),
                    "target_configs": sorted({c for item in mappings for c in item.get("target_configs", [])}),
                    "gates_commercial_identity": False,
                },
            )
            acquisition_success += 1
            verified_identity_targets += 1
            active_candidates += len(raw_icpns)
            excluded_candidates += len(excluded_ids)
            disposition_counts[disposition] += 1
        except (AcquisitionError, OSError) as exc:
            if isinstance(exc, AcquisitionError) and str(exc) == CANONICAL_PAGE_404:
                result.update(
                    acquisition_status="source_unavailable",
                    disposition="source_unavailable_excluded",
                    commercial_identity_status="unverified",
                    source_unavailable_status="http_404",
                    manual_intervention_required=False,
                    error_type=type(exc).__name__, error=str(exc),
                )
                disposition_counts["source_unavailable_excluded"] += 1
                routing_counts["not_applicable"] += 1
            else:
                result.update(
                    acquisition_status="failure", disposition="manual_review",
                    commercial_identity_status="unverified", manual_intervention_required=True,
                    error_type=type(exc).__name__, error=str(exc),
                )
                acquisition_failure += 1
                disposition_counts["manual_review"] += 1
        results.append(result)

    source_unavailable = disposition_counts["source_unavailable_excluded"]
    manual_review = disposition_counts["manual_review"]
    dispositioned = disposition_counts["active_candidates"] + disposition_counts["lifecycle_excluded"] + source_unavailable
    commercial_identity_clean = (
        len(targets) == MAX_TARGETS and verified_identity_targets == MAX_TARGETS
        and source_unavailable == 0 and manual_review == 0
    )
    bounded_discovery_clean = (
        len(targets) == MAX_TARGETS and dispositioned == MAX_TARGETS
        and manual_review == 0 and acquisition_failure == 0 and active_candidates > 0
    )
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "pilot_id": pilot_id,
        "scope": "bounded read-only official-ST STM32G4 commercial identity/lifecycle discovery",
        "attempted": len(targets),
        "acquisition_success": acquisition_success,
        "acquisition_failure": acquisition_failure,
        "active_candidate_targets": disposition_counts["active_candidates"],
        "lifecycle_excluded_targets": disposition_counts["lifecycle_excluded"],
        "source_unavailable_exclusions": source_unavailable,
        "dispositioned_targets": dispositioned,
        "commercial_identity_verified_targets": verified_identity_targets,
        "commercial_identity_unresolved_targets": source_unavailable,
        "active_exact_icpn_candidates": active_candidates,
        "excluded_non_active_part_numbers": excluded_candidates,
        "commercial_identity_clean": commercial_identity_clean,
        "bounded_discovery_clean": bounded_discovery_clean,
        "identity_manual_intervention_required": manual_review,
        "openocd_routing": {
            "unique": routing_counts["unique"], "ambiguous": routing_counts["ambiguous"],
            "unmapped": routing_counts["unmapped"], "not_applicable": routing_counts["not_applicable"],
            "gates_commercial_identity": False,
        },
        "routing_followup_required": routing_counts["ambiguous"] + routing_counts["unmapped"],
        "acquisition_transport": BROWSER_TRANSPORT,
        "results": results,
        "claims": {
            "cmsis_alias_is_commercial_identity": False,
            "canonical_dataset_admission": False,
            "production_admission_ready": False,
            "production_write_authorized": False,
            "programming_policy_defined": False,
            "runtime_support_claimed": False,
        },
    }


def discovery_is_clean(summary: dict[str, object]) -> bool:
    claims = summary.get("claims")
    routing = summary.get("openocd_routing")
    return (
        summary.get("attempted") == MAX_TARGETS
        and summary.get("dispositioned_targets") == MAX_TARGETS
        and summary.get("acquisition_failure") == 0
        and summary.get("bounded_discovery_clean") is True
        and summary.get("identity_manual_intervention_required") == 0
        and isinstance(summary.get("active_exact_icpn_candidates"), int)
        and int(summary["active_exact_icpn_candidates"]) > 0
        and isinstance(routing, dict) and routing.get("gates_commercial_identity") is False
        and isinstance(claims, dict) and claims and set(claims.values()) == {False}
    )


def write_evidence_files(summary: dict[str, object], evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results = summary.get("results")
    if not isinstance(results, list):
        raise AcquisitionError("summary results must be a list")
    for result in results:
        if not isinstance(result, dict) or result.get("acquisition_status") != "success":
            continue
        base = result.get("base_device")
        evidence = result.get("evidence")
        if not isinstance(base, str) or not isinstance(evidence, dict):
            raise AcquisitionError("successful result lacks base/evidence")
        (evidence_dir / f"{base}.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
