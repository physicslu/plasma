#!/usr/bin/env python3
"""Bounded, fail-closed official-ST discovery for STM32F0 Phase 4.5B.

Commercial identity/lifecycle authority comes from retained ST evidence.
OpenOCD routing is recorded as an orthogonal observation and never gates the
existence/selectability of a legitimate commercial ICPN.
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
from stm32f0_dual_surface_evidence import build_dual_surface_browser_evidence_record
from stm32f0_foundation import (
    DEFAULT_CATALOG,
    EXPECTED_SUBFAMILIES,
    FAMILY,
    deterministic_initial_targets,
    read_catalog,
    resolve_ordering_pattern_mapping,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.5B"
DEFAULT_MANIFEST = HERE / "stm32f0-phase4.5b-discovery-manifest.json"
DEFAULT_OUTPUT = Path("/tmp/stm32f0-phase4.5b-live-summary.json")
MAX_TARGETS = len(EXPECTED_SUBFAMILIES)
MIN_DELAY_SECONDS = 1.0


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


def read_manifest(
    path: Path,
    catalog_rows: list[dict[str, str]],
) -> tuple[str, list[DiscoveryTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("phase") != PHASE:
        raise AcquisitionError("unsupported STM32F0 Phase 4.5B discovery manifest")
    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("Phase 4.5B discovery manifest requires pilot_id")
    if not isinstance(raw_targets, list) or len(raw_targets) != MAX_TARGETS:
        raise AcquisitionError(
            f"Phase 4.5B discovery requires exactly {MAX_TARGETS} targets"
        )

    targets: list[DiscoveryTarget] = []
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise AcquisitionError(f"Phase 4.5B target {index} must be an object")
        subfamily = raw.get("subfamily")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if not isinstance(subfamily, str) or subfamily not in EXPECTED_SUBFAMILIES:
            raise AcquisitionError(f"invalid STM32F0 subfamily: {subfamily!r}")
        if not isinstance(base, str):
            raise AcquisitionError(f"invalid STM32F0 Base Device: {base!r}")
        if not isinstance(source, str):
            raise AcquisitionError(f"{base}: source_url is required")
        validate_source_url(source)
        if source != source_url_for_base(base):
            raise AcquisitionError(f"{base}: source URL slug mismatch")
        if not isinstance(reason, str) or not reason.strip():
            raise AcquisitionError(f"{base}: selection_reason is required")
        targets.append(
            DiscoveryTarget(
                subfamily=subfamily,
                base_device=base,
                source_url=source,
                selection_reason=reason.strip(),
            )
        )

    observed = [(target.subfamily, target.base_device) for target in targets]
    expected = deterministic_initial_targets(catalog_rows)
    if observed != expected:
        raise AcquisitionError(
            f"Phase 4.5B target selection drifted: expected={expected} observed={observed}"
        )
    return pilot_id, targets


def commercial_core(icpn: str) -> str:
    for suffix in ("TR", "TT"):
        if icpn.endswith(suffix):
            return icpn[: -len(suffix)]
    return icpn


def resolve_mapping(
    icpn: str,
    catalog_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Resolve orthogonal OpenOCD routing; never decide commercial identity."""

    return resolve_ordering_pattern_mapping(commercial_core(icpn), catalog_rows)


def _overall_routing_status(mappings: list[dict[str, Any]]) -> str:
    statuses = Counter(str(item.get("status")) for item in mappings)
    if statuses == Counter({"unique": len(mappings)}):
        return "unique"
    if statuses["ambiguous"]:
        return "ambiguous"
    return "unmapped"


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
    active_candidates = 0
    excluded_candidates = 0
    acquisition_success = 0

    for target in targets:
        result: dict[str, object] = {
            "subfamily": target.subfamily,
            "base_device": target.base_device,
            "source_url": target.source_url,
            "selection_reason": target.selection_reason,
        }
        try:
            body, final_url, etag, last_modified = fetcher(
                target.source_url, timeout_seconds
            )
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
            if not isinstance(raw_icpns, list) or not all(
                isinstance(value, str) for value in raw_icpns
            ):
                raise AcquisitionError(
                    f"{target.base_device}: exact_icpns must be a string list"
                )
            if not isinstance(excluded, list):
                raise AcquisitionError(
                    f"{target.base_device}: excluded lifecycle rows must be a list"
                )
            if not raw_icpns:
                raise AcquisitionError(
                    f"{target.base_device}: official ST page has no Active exact ICPN"
                )
            if any(not value.startswith(target.base_device) for value in raw_icpns):
                raise AcquisitionError(
                    f"{target.base_device}: evidence contains a foreign exact ICPN"
                )

            mappings = [
                {"icpn": value, **resolve_mapping(value, catalog_rows)}
                for value in raw_icpns
            ]
            overall = _overall_routing_status(mappings)
            result.update(
                acquisition_status="success",
                commercial_identity_status="verified_active",
                evidence=evidence,
                routing_observations=mappings,
                openocd_routing={
                    "status": overall,
                    "candidate_count": len(mappings),
                    "target_configs": sorted(
                        {
                            config
                            for item in mappings
                            for config in item.get("target_configs", [])
                        }
                    ),
                    "gates_commercial_identity": False,
                },
            )
            acquisition_success += 1
            active_candidates += len(raw_icpns)
            excluded_candidates += len(excluded)
            routing_counts[overall] += 1
        except (AcquisitionError, OSError) as exc:
            result.update(
                acquisition_status="failure",
                commercial_identity_status="unverified",
                error_type=type(exc).__name__,
                error=str(exc),
            )
        results.append(result)

    acquisition_failure = len(targets) - acquisition_success
    commercial_identity_clean = (
        len(targets) == MAX_TARGETS
        and acquisition_success == MAX_TARGETS
        and acquisition_failure == 0
        and active_candidates > 0
    )
    summary: dict[str, object] = {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "pilot_id": pilot_id,
        "scope": "bounded read-only official-ST STM32F0 commercial identity discovery",
        "attempted": len(targets),
        "acquisition_success": acquisition_success,
        "acquisition_failure": acquisition_failure,
        "active_exact_icpn_candidates": active_candidates,
        "excluded_non_active_part_numbers": excluded_candidates,
        "commercial_identity_clean": commercial_identity_clean,
        "identity_manual_intervention_required": acquisition_failure,
        "openocd_routing": {
            "unique": routing_counts["unique"],
            "ambiguous": routing_counts["ambiguous"],
            "unmapped": routing_counts["unmapped"],
            "gates_commercial_identity": False,
        },
        "routing_followup_required": routing_counts["ambiguous"] + routing_counts["unmapped"],
        "acquisition_transport": BROWSER_TRANSPORT,
        "results": results,
        "claims": {
            "canonical_dataset_admission": False,
            "production_admission_ready": False,
            "production_write_authorized": False,
            "programming_policy_defined": False,
            "runtime_support_claimed": False,
        },
    }
    return summary


def discovery_is_clean(summary: dict[str, object]) -> bool:
    """Commercial-identity clean gate; routing state is intentionally orthogonal."""

    claims = summary.get("claims")
    routing = summary.get("openocd_routing")
    return (
        summary.get("attempted") == MAX_TARGETS
        and summary.get("acquisition_success") == MAX_TARGETS
        and summary.get("acquisition_failure") == 0
        and summary.get("commercial_identity_clean") is True
        and summary.get("identity_manual_intervention_required") == 0
        and isinstance(summary.get("active_exact_icpn_candidates"), int)
        and int(summary["active_exact_icpn_candidates"]) > 0
        and isinstance(routing, dict)
        and routing.get("gates_commercial_identity") is False
        and isinstance(claims, dict)
        and claims
        and set(claims.values()) == {False}
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
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
