#!/usr/bin/env python3
"""Bounded read-only STM32L1 official-ST lifecycle requalification.

This probe exists because the earlier cross-family evidence gate sampled one
lexical-min product page per STM32L1 subfamily. That is insufficient when ST
publishes generation-specific companion pages: a historical page may be NRND
while a generation-A page for the same Base Device exposes Active exact orderable
parts. Lifecycle remains an exact-variant property.

OpenOCD only bounds the STM32L1 research surface. Official ST Quality &
Reliability plus Sample & Buy is the commercial identity/lifecycle authority.
This module does not admit ICPNs, modify Production, select the next family,
define programming policy, or claim runtime/HIL support.
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from st_browser_acquisition import BROWSER_TRANSPORT
from st_dual_surface_evidence import build_dual_surface_browser_evidence_record
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32_cross_family_prioritization import DEFAULT_CATALOG, DEFAULT_MANIFEST, build_prioritization
from stm32_post_u0_evidence_probe import RateLimitedFetcher

HERE = Path(__file__).resolve().parent
FAMILY = "STM32L1"
PROBE_ID = "stm32l1-official-st-lifecycle-requalification-v1"
PARSER_PROFILE = "stm32l1_requalification_dual_surface_v1"
DEFAULT_OUTPUT = Path("/tmp/stm32l1-requalification-summary.json")
EXPECTED_PRODUCTION = {
    "exact_icpn_count": 1718,
    "base_device_count": 530,
    "family_count": 12,
    "stm32l4_exact_icpn_count": 446,
}
EXPECTED_SURFACE = {
    "rows": 132,
    "ordering": 87,
    "cmsis": 45,
    "target_config": "tcl/target/stm32l1.cfg",
    "subfamilies": ("STM32L100", "STM32L151", "STM32L152", "STM32L162"),
}
CANONICAL_PAGE_404 = "browser navigation returned HTTP 404"


@dataclass(frozen=True)
class RequalificationTarget:
    target_id: str
    subfamily: str
    base_device: str
    source_url: str
    role: str


TARGETS = (
    RequalificationTarget(
        "STM32L100C6-legacy", "STM32L100", "STM32L100C6",
        "https://www.st.com/en/microcontrollers-microprocessors/stm32l100c6.html",
        "historical_representative",
    ),
    RequalificationTarget(
        "STM32L100C6-generation-a", "STM32L100", "STM32L100C6",
        "https://www.st.com/en/microcontrollers-microprocessors/stm32l100c6-a.html",
        "generation_companion",
    ),
    RequalificationTarget(
        "STM32L151C6-legacy", "STM32L151", "STM32L151C6",
        "https://www.st.com/en/microcontrollers-microprocessors/stm32l151c6.html",
        "historical_representative",
    ),
    RequalificationTarget(
        "STM32L151C6-generation-a", "STM32L151", "STM32L151C6",
        "https://www.st.com/en/microcontrollers-microprocessors/stm32l151c6-a.html",
        "generation_companion",
    ),
    RequalificationTarget(
        "STM32L152C6-legacy", "STM32L152", "STM32L152C6",
        "https://www.st.com/en/microcontrollers-microprocessors/stm32l152c6.html",
        "historical_representative",
    ),
    RequalificationTarget(
        "STM32L152C6-generation-a", "STM32L152", "STM32L152C6",
        "https://www.st.com/en/microcontrollers-microprocessors/stm32l152c6-a.html",
        "generation_companion",
    ),
    RequalificationTarget(
        "STM32L162QC-current", "STM32L162", "STM32L162QC",
        "https://www.st.com/en/microcontrollers-microprocessors/stm32l162qc.html",
        "historical_representative",
    ),
)

FetchResult = tuple[bytes, str, str | None, str | None]
Fetcher = Callable[[str, float], FetchResult]


def read_catalog(path: Path = DEFAULT_CATALOG) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_current_boundary(
    *, catalog_path: Path = DEFAULT_CATALOG, manifest_path: Path = DEFAULT_MANIFEST
) -> dict[str, Any]:
    report = build_prioritization(catalog_path=catalog_path, manifest_path=manifest_path)
    if report.get("policy_id") != "stm32-cross-family-prioritization-v1":
        raise AcquisitionError("unexpected cross-family prioritization policy")
    claims = report.get("claims")
    if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
        raise AcquisitionError("cross-family prioritization claims escaped fail-closed state")
    production = report.get("production_invariants")
    if not isinstance(production, dict):
        raise AcquisitionError("missing Production invariants")
    if production.get("exact_icpn_count") != EXPECTED_PRODUCTION["exact_icpn_count"]:
        raise AcquisitionError("post-L4 Production exact ICPN count drifted")
    if production.get("base_device_count") != EXPECTED_PRODUCTION["base_device_count"]:
        raise AcquisitionError("post-L4 Production Base Device count drifted")
    if len(production.get("production_series") or []) != EXPECTED_PRODUCTION["family_count"]:
        raise AcquisitionError("post-L4 Production family count drifted")
    family_counts = production.get("family_exact_icpn_counts")
    if not isinstance(family_counts, dict) or family_counts.get("STM32L4") != EXPECTED_PRODUCTION["stm32l4_exact_icpn_count"]:
        raise AcquisitionError("post-L4 STM32L4 Production state drifted")
    if family_counts.get(FAMILY, 0) != 0:
        raise AcquisitionError("STM32L1 must not already be in Production for requalification")
    shortlist = report.get("research_shortlist") or []
    observed = [item.get("plasma_series") for item in shortlist if isinstance(item, dict)]
    if observed != [FAMILY]:
        raise AcquisitionError(f"post-L4 research shortlist drifted: {observed}")
    if report.get("selected_next_research_family") is not None:
        raise AcquisitionError("current prioritization unexpectedly selected a family")
    return report


def validate_openocd_surface(rows: list[dict[str, str]]) -> None:
    family_rows = [
        row for row in rows
        if row.get("vendor") == "STMicroelectronics" and row.get("plasma_series") == FAMILY
    ]
    if len(family_rows) != EXPECTED_SURFACE["rows"]:
        raise AcquisitionError(f"STM32L1 source row count drifted: {len(family_rows)}")
    kinds = Counter(row.get("identifier_kind", "") for row in family_rows)
    if kinds != Counter({"ordering_pattern": EXPECTED_SURFACE["ordering"], "cmsis_device_name": EXPECTED_SURFACE["cmsis"]}):
        raise AcquisitionError(f"STM32L1 identifier-kind surface drifted: {dict(kinds)}")
    subfamilies = tuple(sorted({row.get("subfamily", "") for row in family_rows if row.get("subfamily")}))
    if subfamilies != tuple(sorted(EXPECTED_SURFACE["subfamilies"])):
        raise AcquisitionError(f"STM32L1 subfamily surface drifted: {subfamilies}")
    if any(row.get("target_config") != EXPECTED_SURFACE["target_config"] for row in family_rows):
        raise AcquisitionError("STM32L1 target-config surface drifted")


def deterministic_targets(
    *, catalog_path: Path = DEFAULT_CATALOG, manifest_path: Path = DEFAULT_MANIFEST
) -> list[RequalificationTarget]:
    validate_current_boundary(catalog_path=catalog_path, manifest_path=manifest_path)
    validate_openocd_surface(read_catalog(catalog_path))
    targets = list(TARGETS)
    seen_ids: set[str] = set()
    per_subfamily: dict[str, set[str]] = defaultdict(set)
    for target in targets:
        if target.target_id in seen_ids:
            raise AcquisitionError(f"duplicate target id: {target.target_id}")
        seen_ids.add(target.target_id)
        if target.subfamily not in EXPECTED_SURFACE["subfamilies"]:
            raise AcquisitionError(f"target escaped STM32L1 subfamily boundary: {target.subfamily}")
        if not target.base_device.startswith(target.subfamily):
            raise AcquisitionError(f"target Base Device escaped subfamily: {target.base_device}")
        validate_source_url(target.source_url)
        if target.role not in {"historical_representative", "generation_companion"}:
            raise AcquisitionError(f"unsupported target role: {target.role}")
        per_subfamily[target.subfamily].add(target.role)
    if set(per_subfamily) != set(EXPECTED_SURFACE["subfamilies"]):
        raise AcquisitionError("requalification target set does not cover all STM32L1 subfamilies")
    for subfamily in ("STM32L100", "STM32L151", "STM32L152"):
        if per_subfamily[subfamily] != {"historical_representative", "generation_companion"}:
            raise AcquisitionError(f"{subfamily}: generation-aware target pair missing")
    if per_subfamily["STM32L162"] != {"historical_representative"}:
        raise AcquisitionError("STM32L162 target boundary drifted")
    return targets


def _build_evidence(*, base_device: str, **kwargs: Any) -> dict[str, object]:
    return build_dual_surface_browser_evidence_record(
        base_device=base_device,
        parser_profile=PARSER_PROFILE,
        **kwargs,
    )


def _excluded_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        raise AcquisitionError("excluded_non_active_part_numbers must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("icpn"), str):
            raise AcquisitionError("invalid lifecycle exclusion record")
        result.append(item["icpn"])
    return result


def run_probe(
    *, targets: list[RequalificationTarget], fetcher: Fetcher, timeout_seconds: float = 90.0
) -> dict[str, object]:
    expected = deterministic_targets()
    if targets != expected:
        raise AcquisitionError("live target list differs from deterministic requalification target set")
    results: list[dict[str, object]] = []
    manual_review = 0
    source_unavailable = 0
    for target in targets:
        result: dict[str, object] = {
            "target_id": target.target_id,
            "series": FAMILY,
            "subfamily": target.subfamily,
            "base_device": target.base_device,
            "source_url": target.source_url,
            "role": target.role,
        }
        try:
            body, final_url, etag, last_modified = fetcher(target.source_url, timeout_seconds)
            evidence = _build_evidence(
                body=body,
                source_url=target.source_url,
                final_url=final_url,
                retrieved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                http_etag=etag,
                http_last_modified=last_modified,
                base_device=target.base_device,
            )
            active = evidence.get("exact_icpns")
            if not isinstance(active, list) or not all(isinstance(v, str) for v in active):
                raise AcquisitionError(f"{target.target_id}: exact_icpns must be a string list")
            excluded = _excluded_ids(evidence.get("excluded_non_active_part_numbers"))
            if not active and not excluded:
                raise AcquisitionError(f"{target.target_id}: no exact identity lifecycle disposition")
            result.update(
                acquisition_status="success",
                disposition="active_exact_available" if active else "non_active_exact_only",
                active_exact_icpns=active,
                excluded_non_active_icpns=excluded,
                evidence=evidence,
                manual_intervention_required=False,
            )
        except (AcquisitionError, OSError) as exc:
            if isinstance(exc, AcquisitionError) and str(exc) == CANONICAL_PAGE_404:
                source_unavailable += 1
                result.update(
                    acquisition_status="source_unavailable",
                    disposition="source_unavailable",
                    manual_intervention_required=False,
                    error=str(exc),
                )
            else:
                manual_review += 1
                result.update(
                    acquisition_status="failure",
                    disposition="manual_review",
                    manual_intervention_required=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        results.append(result)

    by_subfamily: dict[str, dict[str, object]] = {}
    false_negative_subfamilies: list[str] = []
    for subfamily in EXPECTED_SURFACE["subfamilies"]:
        subset = [r for r in results if r["subfamily"] == subfamily]
        active = sorted({icpn for r in subset for icpn in r.get("active_exact_icpns", []) if isinstance(icpn, str)})
        excluded = sorted({icpn for r in subset for icpn in r.get("excluded_non_active_icpns", []) if isinstance(icpn, str)})
        legacy = [r for r in subset if r["role"] == "historical_representative"]
        companion = [r for r in subset if r["role"] == "generation_companion"]
        legacy_active = any(r.get("active_exact_icpns") for r in legacy)
        companion_active = any(r.get("active_exact_icpns") for r in companion)
        if companion and not legacy_active and companion_active:
            false_negative_subfamilies.append(subfamily)
        by_subfamily[subfamily] = {
            "target_count": len(subset),
            "active_exact_icpns": active,
            "excluded_non_active_icpns": excluded,
            "active_exact_available": bool(active),
            "historical_representative_active": legacy_active,
            "generation_companion_active": companion_active,
        }

    active_subfamilies = [s for s, v in by_subfamily.items() if v["active_exact_available"]]
    clean = (
        manual_review == 0
        and source_unavailable == 0
        and len(active_subfamilies) == len(EXPECTED_SURFACE["subfamilies"])
    )
    return {
        "schema_version": 1,
        "phase": "post-L4-STM32L1-requalification",
        "probe_id": PROBE_ID,
        "scope": "bounded read-only current official-ST exact-identity/lifecycle requalification for STM32L1",
        "family": FAMILY,
        "target_count": len(targets),
        "subfamily_count": len(EXPECTED_SURFACE["subfamilies"]),
        "active_subfamilies": active_subfamilies,
        "active_subfamily_count": len(active_subfamilies),
        "historical_single_page_false_negative_subfamilies": false_negative_subfamilies,
        "manual_review_targets": manual_review,
        "source_unavailable_targets": source_unavailable,
        "bounded_probe_complete": clean,
        "requalification_status": "eligible_for_next_research_gate" if clean else "not_eligible_fail_closed",
        "by_subfamily": by_subfamily,
        "results": results,
        "acquisition_transport": BROWSER_TRANSPORT,
        "selected_next_research_family": None,
        "claims": {
            "production_write_authorized": False,
            "canonical_admission_authorized": False,
            "exact_icpn_publication_authorized": False,
            "openocd_is_commercial_identity_authority": False,
            "subfamily_lifecycle_inferred_from_one_product_page": False,
            "selected_next_research_family": False,
            "programming_policy_defined": False,
            "programming_algorithm_equivalence_claimed": False,
            "flash_geometry_qualified": False,
            "option_security_qualified": False,
            "hil_qualified": False,
            "runtime_programming_support_claimed": False,
        },
    }


def target_manifest(targets: list[RequalificationTarget]) -> dict[str, object]:
    expected = deterministic_targets()
    if targets != expected:
        raise AcquisitionError("target manifest requires deterministic target set")
    return {
        "schema_version": 1,
        "phase": "post-L4-STM32L1-requalification",
        "probe_id": PROBE_ID,
        "selection_rule": "historical representative plus generation companion where ST splits lifecycle across product pages",
        "target_count": len(targets),
        "targets": [target.__dict__ for target in targets],
        "claims": {
            "production_write_authorized": False,
            "commercial_identity_claimed_from_openocd": False,
            "selected_next_research_family": False,
        },
    }


def write_evidence_files(summary: dict[str, object], evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results = summary.get("results")
    if not isinstance(results, list):
        raise AcquisitionError("probe results must be a list")
    for result in results:
        if not isinstance(result, dict) or result.get("acquisition_status") != "success":
            continue
        target_id = result.get("target_id")
        evidence = result.get("evidence")
        if not isinstance(target_id, str) or not isinstance(evidence, dict):
            raise AcquisitionError("successful result lacks target/evidence")
        (evidence_dir / f"{target_id}.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
