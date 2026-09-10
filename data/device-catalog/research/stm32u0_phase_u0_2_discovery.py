#!/usr/bin/env python3
"""Bounded fail-closed official-ST discovery for STM32U0 Phase U0.2.

U0.2 expands the frozen U0.1 ordering-pattern surface into the complete deterministic
Base Device set and observes exact commercial ICPNs plus Marketing Status only from
official ST product pages. OpenOCD routing is recorded separately and never gates
commercial identity. No function authorizes canonical admission or Production writes.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT, STBrowserAcquirer
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32u0_dual_surface_evidence import build_dual_surface_browser_evidence_record
from stm32u0_phase_u0_1_foundation import (
    DEFAULT_CATALOG,
    EXPECTED_SUBFAMILIES,
    commercial_ordering_rows,
    base_from_row,
    read_catalog,
    resolve_ordering_pattern_mapping,
)

HERE = Path(__file__).resolve().parent
PHASE = "U0.2"
FAMILY = "STM32U0"
DEFAULT_MANIFEST = HERE / "stm32u0-phase-u0.2-discovery-manifest.json"
EXPECTED_BASE_COUNTS = {"STM32U031": 10, "STM32U073": 12, "STM32U083": 4}
MAX_TARGETS = sum(EXPECTED_BASE_COUNTS.values())
MIN_DELAY_SECONDS = 1.0
CANONICAL_PAGE_404 = "browser navigation returned HTTP 404"


@dataclass(frozen=True)
class DiscoveryTarget:
    subfamily: str
    base_device: str
    source_url: str
    selection_reason: str


def deterministic_targets(catalog_rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    by_subfamily: dict[str, set[str]] = {subfamily: set() for subfamily in EXPECTED_SUBFAMILIES}
    for row in commercial_ordering_rows(catalog_rows):
        subfamily = row["subfamily"]
        by_subfamily[subfamily].add(base_from_row(row))
    counts = {subfamily: len(by_subfamily[subfamily]) for subfamily in EXPECTED_SUBFAMILIES}
    if counts != EXPECTED_BASE_COUNTS:
        raise AcquisitionError(f"{PHASE} deterministic Base Device surface drifted: {counts}")
    result = [
        (subfamily, base)
        for subfamily in EXPECTED_SUBFAMILIES
        for base in sorted(by_subfamily[subfamily])
    ]
    if len(result) != MAX_TARGETS or len({base for _, base in result}) != MAX_TARGETS:
        raise AcquisitionError(f"{PHASE} deterministic Base Device set is not exactly {MAX_TARGETS} unique targets")
    return result


def source_url_for_base(base_device: str) -> str:
    return f"https://www.st.com/en/microcontrollers-microprocessors/{base_device.lower()}.html"


def read_manifest(path: Path, catalog_rows: list[dict[str, str]]) -> tuple[str, list[DiscoveryTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("phase") != PHASE:
        raise AcquisitionError("unsupported STM32U0 U0.2 discovery manifest")
    claims = payload.get("claims")
    if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
        raise AcquisitionError("U0.2 authority boundaries must remain fail-closed")
    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("U0.2 manifest requires pilot_id")
    if not isinstance(raw_targets, list) or len(raw_targets) != MAX_TARGETS:
        raise AcquisitionError(f"U0.2 manifest requires exactly {MAX_TARGETS} targets")

    targets: list[DiscoveryTarget] = []
    for raw in raw_targets:
        if not isinstance(raw, dict):
            raise AcquisitionError("U0.2 target must be an object")
        subfamily = raw.get("subfamily")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if not isinstance(subfamily, str) or subfamily not in EXPECTED_SUBFAMILIES:
            raise AcquisitionError(f"invalid STM32U0 subfamily: {subfamily!r}")
        if not isinstance(base, str) or not base.startswith(subfamily):
            raise AcquisitionError(f"invalid STM32U0 Base Device: {base!r}")
        if not isinstance(source, str):
            raise AcquisitionError(f"{base}: source_url is required")
        validate_source_url(source)
        if source != source_url_for_base(base):
            raise AcquisitionError(f"{base}: source URL slug mismatch")
        if not isinstance(reason, str) or not reason.strip():
            raise AcquisitionError(f"{base}: selection_reason is required")
        targets.append(DiscoveryTarget(subfamily, base, source, reason.strip()))

    observed = [(target.subfamily, target.base_device) for target in targets]
    expected = deterministic_targets(catalog_rows)
    if observed != expected:
        raise AcquisitionError(f"U0.2 target selection drifted: expected={expected} observed={observed}")
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


def run_discovery(
    *, pilot_id: str, targets: list[DiscoveryTarget], catalog_rows: list[dict[str, str]],
    acquirer: STBrowserAcquirer, delay_seconds: float, timeout_seconds: float,
) -> dict[str, object]:
    if delay_seconds < MIN_DELAY_SECONDS:
        raise AcquisitionError(f"live discovery delay must be at least {MIN_DELAY_SECONDS:.1f} seconds")
    results: list[dict[str, object]] = []
    dispositions: Counter[str] = Counter()
    routing: Counter[str] = Counter()
    active_exact = excluded_exact = acquisition_failures = verified_targets = 0
    previous_fetch = False

    for target in targets:
        if previous_fetch:
            time.sleep(delay_seconds)
        previous_fetch = True
        result: dict[str, object] = {
            "subfamily": target.subfamily,
            "base_device": target.base_device,
            "source_url": target.source_url,
            "selection_reason": target.selection_reason,
        }
        try:
            body, final_url, etag, last_modified = acquirer.fetch(target.source_url, timeout_seconds)
            evidence = build_dual_surface_browser_evidence_record(
                body=body, source_url=target.source_url, final_url=final_url,
                base_device=target.base_device,
                retrieved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                http_etag=etag, http_last_modified=last_modified,
            )
            exact = evidence.get("exact_icpns")
            excluded = evidence.get("excluded_non_active_part_numbers")
            if not isinstance(exact, list) or not all(isinstance(value, str) for value in exact):
                raise AcquisitionError(f"{target.base_device}: invalid exact ICPN evidence")
            if not isinstance(excluded, list):
                raise AcquisitionError(f"{target.base_device}: invalid lifecycle exclusions")
            if any(not value.startswith(target.base_device) for value in exact):
                raise AcquisitionError(f"{target.base_device}: foreign exact ICPN in evidence")
            if not exact and not excluded:
                raise AcquisitionError(f"{target.base_device}: no exact identity disposition")
            mappings = [{"icpn": value, **resolve_mapping(value, catalog_rows)} for value in exact]
            route_status = _overall_routing_status(mappings)
            disposition = "active_candidates" if exact else "lifecycle_excluded"
            identity_status = "verified_active" if exact else "verified_non_active_only"
            result.update(
                acquisition_status="success", disposition=disposition,
                commercial_identity_status=identity_status, evidence=evidence,
                routing_observations=mappings,
                openocd_routing={"status": route_status, "gates_commercial_identity": False},
            )
            dispositions[disposition] += 1
            routing[route_status if exact else "not_applicable"] += 1
            verified_targets += 1
            active_exact += len(exact)
            excluded_exact += len(excluded)
        except (AcquisitionError, OSError) as exc:
            if isinstance(exc, AcquisitionError) and str(exc) == CANONICAL_PAGE_404:
                result.update(
                    acquisition_status="source_unavailable", disposition="source_unavailable_excluded",
                    commercial_identity_status="unverified", source_unavailable_status="http_404",
                    manual_intervention_required=False, error_type=type(exc).__name__, error=str(exc),
                )
                dispositions["source_unavailable_excluded"] += 1
                routing["not_applicable"] += 1
            else:
                result.update(
                    acquisition_status="failure", disposition="manual_review",
                    commercial_identity_status="unverified", manual_intervention_required=True,
                    error_type=type(exc).__name__, error=str(exc),
                )
                dispositions["manual_review"] += 1
                acquisition_failures += 1
        results.append(result)

    source_unavailable = dispositions["source_unavailable_excluded"]
    manual_review = dispositions["manual_review"]
    dispositioned = dispositions["active_candidates"] + dispositions["lifecycle_excluded"] + source_unavailable
    return {
        "schema_version": 1, "phase": PHASE, "family": FAMILY, "pilot_id": pilot_id,
        "scope": "bounded read-only official-ST STM32U0 commercial identity/lifecycle discovery",
        "attempted": len(targets), "acquisition_success": verified_targets,
        "acquisition_failure": acquisition_failures,
        "active_candidate_targets": dispositions["active_candidates"],
        "lifecycle_excluded_targets": dispositions["lifecycle_excluded"],
        "source_unavailable_exclusions": source_unavailable,
        "dispositioned_targets": dispositioned,
        "commercial_identity_verified_targets": verified_targets,
        "commercial_identity_unresolved_targets": source_unavailable,
        "active_exact_icpn_candidates": active_exact,
        "excluded_non_active_part_numbers": excluded_exact,
        "commercial_identity_clean": verified_targets == MAX_TARGETS and source_unavailable == 0 and manual_review == 0,
        "bounded_discovery_clean": dispositioned == MAX_TARGETS and manual_review == 0 and acquisition_failures == 0 and active_exact > 0,
        "identity_manual_intervention_required": manual_review,
        "openocd_routing": {"unique": routing["unique"], "ambiguous": routing["ambiguous"], "unmapped": routing["unmapped"], "not_applicable": routing["not_applicable"], "gates_commercial_identity": False},
        "routing_followup_required": routing["ambiguous"] + routing["unmapped"],
        "acquisition_transport": BROWSER_TRANSPORT,
        "results": results,
        "claims": {
            "canonical_admission_authorized": False, "production_write_authorized": False,
            "programming_policy_defined": False, "programming_algorithm_equivalence": False,
            "flash_geometry_qualified": False, "option_security_semantics_qualified": False,
            "physical_hil_qualified": False, "runtime_programming_support_claimed": False,
        },
    }


def discovery_is_clean(summary: dict[str, object]) -> bool:
    claims = summary.get("claims")
    return (
        summary.get("attempted") == MAX_TARGETS
        and summary.get("dispositioned_targets") == MAX_TARGETS
        and summary.get("acquisition_failure") == 0
        and summary.get("bounded_discovery_clean") is True
        and summary.get("identity_manual_intervention_required") == 0
        and isinstance(summary.get("active_exact_icpn_candidates"), int)
        and int(summary["active_exact_icpn_candidates"]) > 0
        and isinstance(claims, dict) and claims and all(value is False for value in claims.values())
    )


def write_evidence_files(summary: dict[str, object], evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for result in summary.get("results", []):
        if not isinstance(result, dict) or result.get("acquisition_status") != "success":
            continue
        base = result.get("base_device")
        evidence = result.get("evidence")
        if not isinstance(base, str) or not isinstance(evidence, dict):
            raise AcquisitionError("successful result lacks Base Device/evidence")
        (evidence_dir / f"{base}.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    catalog_rows = read_catalog(DEFAULT_CATALOG)
    pilot_id, targets = read_manifest(args.manifest, catalog_rows)
    with STBrowserAcquirer(headless=not args.headed) as acquirer:
        summary = run_discovery(
            pilot_id=pilot_id, targets=targets, catalog_rows=catalog_rows,
            acquirer=acquirer, delay_seconds=args.delay, timeout_seconds=args.timeout,
        )
        summary["browser_version"] = acquirer.browser_version
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_evidence_files(summary, args.evidence_dir)
    print(json.dumps({key: summary[key] for key in (
        "attempted", "acquisition_success", "acquisition_failure", "active_candidate_targets",
        "lifecycle_excluded_targets", "source_unavailable_exclusions", "active_exact_icpn_candidates",
        "excluded_non_active_part_numbers", "identity_manual_intervention_required", "bounded_discovery_clean",
    )}, sort_keys=True))
    return 0 if discovery_is_clean(summary) else 2


if __name__ == "__main__":
    raise SystemExit(main())
