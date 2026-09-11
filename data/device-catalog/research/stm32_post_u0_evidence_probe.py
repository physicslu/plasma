#!/usr/bin/env python3
"""Post-U0 bounded official-ST evidence probe for STM32C0/L1/L0.

This transaction is a research-selection gate only. Current Production and the
current cross-family prioritization bound the three candidate series. One
representative Base Device is selected deterministically per ordering-pattern
subfamily, then official ST product-page evidence is used to disposition
commercial identity/lifecycle accessibility.

OpenOCD/CMSIS data only bounds research. It is never commercial identity or
lifecycle authority. This module does not admit devices, define programming
policy, or claim runtime/HIL support.
"""
from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from st_browser_acquisition import BROWSER_TRANSPORT
from st_dual_surface_evidence import build_dual_surface_browser_evidence_record as _build_evidence
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32_cross_family_prioritization import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST as DEFAULT_PRODUCTION_MANIFEST,
    build_prioritization,
)

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path("/tmp/stm32-post-u0-evidence-summary.json")
PARSER_PROFILE = "stm32_post_u0_accessibility_probe_v1"
PROBE_ID = "stm32-post-u0-official-st-evidence-accessibility-probe-v1"
EXPECTED_SHORTLIST = ("STM32C0", "STM32L1", "STM32L0")
EXPECTED_PRODUCTION = {
    "exact_icpn_count": 703,
    "base_device_count": 243,
    "family_count": 9,
    "stm32u0_exact_icpn_count": 68,
}
EXPECTED_SURFACES = {
    "STM32C0": {
        "rows": 95,
        "ordering": 73,
        "cmsis": 22,
        "target_config": "tcl/target/stm32c0x.cfg",
        "subfamilies": (
            "STM32C011", "STM32C031", "STM32C051",
            "STM32C071", "STM32C091", "STM32C092",
        ),
    },
    "STM32L1": {
        "rows": 132,
        "ordering": 87,
        "cmsis": 45,
        "target_config": "tcl/target/stm32l1.cfg",
        "subfamilies": ("STM32L100", "STM32L151", "STM32L152", "STM32L162"),
    },
    "STM32L0": {
        "rows": 166,
        "ordering": 164,
        "cmsis": 2,
        "target_config": "tcl/target/stm32l0.cfg",
        "subfamilies": (
            "STM32L010", "STM32L011", "STM32L021", "STM32L031",
            "STM32L041", "STM32L051", "STM32L052", "STM32L053",
            "STM32L062", "STM32L063", "STM32L071", "STM32L072",
            "STM32L073", "STM32L081", "STM32L082", "STM32L083",
        ),
    },
}
EXPECTED_TARGET_COUNT = sum(len(v["subfamilies"]) for v in EXPECTED_SURFACES.values())
MIN_DELAY_SECONDS = 1.0
CANONICAL_PAGE_404 = "browser navigation returned HTTP 404"
ORDERING_PATTERN_RE = re.compile(r"^(STM32[A-Z0-9]+)([A-Z])x$")


@dataclass(frozen=True)
class ProbeTarget:
    series: str
    subfamily: str
    base_device: str
    source_url: str
    selection_reason: str


FetchResult = tuple[bytes, str, str | None, str | None]
Fetcher = Callable[[str, float], FetchResult]
EvidenceBuilder = Callable[..., dict[str, object]]


def read_catalog(path: Path = DEFAULT_CATALOG) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def source_url_for_base(base_device: str) -> str:
    return (
        "https://www.st.com/en/microcontrollers-microprocessors/"
        f"{base_device.lower()}.html"
    )


def current_prioritization(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
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
        raise AcquisitionError("post-U0 Production exact ICPN count drifted")
    if production.get("base_device_count") != EXPECTED_PRODUCTION["base_device_count"]:
        raise AcquisitionError("post-U0 Production Base Device count drifted")
    series = production.get("production_series")
    if not isinstance(series, list) or len(series) != EXPECTED_PRODUCTION["family_count"]:
        raise AcquisitionError("post-U0 Production family count drifted")
    family_counts = production.get("family_exact_icpn_counts")
    if not isinstance(family_counts, dict) or family_counts.get("STM32U0") != EXPECTED_PRODUCTION["stm32u0_exact_icpn_count"]:
        raise AcquisitionError("post-U0 STM32U0 Production state drifted")
    shortlist = report.get("research_shortlist")
    observed = tuple(
        item.get("plasma_series") for item in shortlist or [] if isinstance(item, dict)
    )
    if observed != EXPECTED_SHORTLIST:
        raise AcquisitionError(f"post-U0 research shortlist drifted: {observed}")
    if report.get("selected_next_research_family") is not None:
        raise AcquisitionError("current prioritization unexpectedly selected a family")
    return report


def _guarded_series_rows(series: str, catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if series not in EXPECTED_SURFACES:
        raise AcquisitionError(f"unsupported post-U0 probe series: {series}")
    expected = EXPECTED_SURFACES[series]
    rows = [
        row for row in catalog_rows
        if row.get("vendor") == "STMicroelectronics" and row.get("plasma_series") == series
    ]
    if len(rows) != expected["rows"]:
        raise AcquisitionError(f"{series}: source row count drifted: {len(rows)}")
    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    expected_kinds = Counter({"ordering_pattern": expected["ordering"], "cmsis_device_name": expected["cmsis"]})
    if kinds != expected_kinds:
        raise AcquisitionError(f"{series}: identifier-kind surface drifted: {dict(kinds)}")
    subfamilies = tuple(sorted({row.get("subfamily", "") for row in rows if row.get("subfamily")}))
    if subfamilies != tuple(sorted(expected["subfamilies"])):
        raise AcquisitionError(f"{series}: subfamily surface drifted: {subfamilies}")
    for row in rows:
        if row.get("target_config") != expected["target_config"]:
            raise AcquisitionError(f"{series}: target-config surface drifted")
        if row.get("openocd_distribution") != "upstream-openocd":
            raise AcquisitionError(f"{series}: unexpected OpenOCD distribution")
        if row.get("mapping_status") != "mapping_candidate":
            raise AcquisitionError(f"{series}: unexpected mapping status")
        if row.get("validation_status") != "not_verified":
            raise AcquisitionError(f"{series}: unexpected validation status")
    return rows


def base_from_ordering_pattern(row: dict[str, str]) -> str:
    if row.get("identifier_kind") != "ordering_pattern":
        raise AcquisitionError("commercial research selection requires ordering_pattern rows")
    part = row.get("part_number", "")
    match = ORDERING_PATTERN_RE.fullmatch(part)
    if match is None:
        raise AcquisitionError(f"unsupported ordering pattern: {part!r}")
    base = match.group(1)
    subfamily = row.get("subfamily", "")
    if not base.startswith(subfamily) or len(base) != len(subfamily) + 2:
        raise AcquisitionError(f"{part}: invalid concrete Base Device {base!r}")
    return base


def deterministic_targets(
    catalog_rows: list[dict[str, str]],
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
) -> list[ProbeTarget]:
    current_prioritization(catalog_path=catalog_path, manifest_path=manifest_path)
    targets: list[ProbeTarget] = []
    for series in EXPECTED_SHORTLIST:
        rows = _guarded_series_rows(series, catalog_rows)
        by_subfamily: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            if row.get("identifier_kind") == "ordering_pattern":
                by_subfamily[row["subfamily"]].add(base_from_ordering_pattern(row))
        for subfamily in EXPECTED_SURFACES[series]["subfamilies"]:
            bases = sorted(by_subfamily[subfamily])
            if not bases:
                raise AcquisitionError(f"{subfamily}: no ordering-pattern Base Device")
            base = bases[0]
            targets.append(
                ProbeTarget(
                    series=series,
                    subfamily=subfamily,
                    base_device=base,
                    source_url=source_url_for_base(base),
                    selection_reason="deterministic lexical-min Base Device in guarded ordering-pattern subfamily",
                )
            )
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise AcquisitionError(f"post-U0 probe target count drifted: {len(targets)}")
    return targets


def validate_targets(targets: list[ProbeTarget]) -> None:
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise AcquisitionError(f"probe requires exactly {EXPECTED_TARGET_COUNT} targets")
    seen: set[tuple[str, str]] = set()
    for target in targets:
        key = (target.series, target.subfamily)
        if key in seen:
            raise AcquisitionError(f"duplicate probe subfamily target: {key}")
        seen.add(key)
        validate_source_url(target.source_url)
        if target.source_url != source_url_for_base(target.base_device):
            raise AcquisitionError(f"{target.base_device}: source URL slug mismatch")
        if not target.base_device.startswith(target.subfamily):
            raise AcquisitionError(f"{target.base_device}: escaped subfamily boundary")


class RateLimitedFetcher:
    def __init__(self, *, delay_seconds: float, fetcher: Fetcher) -> None:
        if delay_seconds < MIN_DELAY_SECONDS:
            raise AcquisitionError(f"live probe delay must be at least {MIN_DELAY_SECONDS:.1f} seconds")
        self.delay_seconds = delay_seconds
        self.fetcher = fetcher
        self._first = True

    def __call__(self, source_url: str, timeout_seconds: float) -> FetchResult:
        if self._first:
            self._first = False
        else:
            time.sleep(self.delay_seconds)
        return self.fetcher(source_url, timeout_seconds)


def build_probe_evidence_record(**kwargs: Any) -> dict[str, object]:
    return _build_evidence(parser_profile=PARSER_PROFILE, **kwargs)


def _excluded_ids(excluded: object, base_device: str) -> list[str]:
    if not isinstance(excluded, list):
        raise AcquisitionError(f"{base_device}: excluded lifecycle rows must be a list")
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


def run_probe(
    *,
    targets: list[ProbeTarget],
    fetcher: Fetcher,
    evidence_builder: EvidenceBuilder = build_probe_evidence_record,
    timeout_seconds: float = 90.0,
) -> dict[str, object]:
    validate_targets(targets)
    results: list[dict[str, object]] = []
    metrics: dict[str, Counter[str]] = {series: Counter() for series in EXPECTED_SHORTLIST}
    manual_failures = 0

    for target in targets:
        metric = metrics[target.series]
        metric["attempted"] += 1
        result: dict[str, object] = {
            "series": target.series,
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
            excluded = evidence.get("excluded_non_active_part_numbers")
            if not isinstance(active, list) or not all(isinstance(value, str) for value in active):
                raise AcquisitionError(f"{target.base_device}: exact_icpns must be a string list")
            if any(not value.startswith(target.base_device) for value in active):
                raise AcquisitionError(f"{target.base_device}: evidence contains foreign exact ICPN")
            excluded_ids = _excluded_ids(excluded, target.base_device)
            if not active and not excluded_ids:
                raise AcquisitionError(f"{target.base_device}: no exact identity disposition")
            disposition = "active_candidates" if active else "lifecycle_excluded"
            metric["verified_identity_targets"] += 1
            metric[disposition] += 1
            metric["active_exact_icpns"] += len(active)
            metric["excluded_non_active_part_numbers"] += len(excluded_ids)
            result.update(
                acquisition_status="success",
                disposition=disposition,
                commercial_identity_status="verified_active" if active else "verified_non_active_only",
                evidence=evidence,
                manual_intervention_required=False,
            )
        except (AcquisitionError, OSError) as exc:
            if isinstance(exc, AcquisitionError) and str(exc) == CANONICAL_PAGE_404:
                metric["source_unavailable_404"] += 1
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
                metric["manual_review"] += 1
                manual_failures += 1
                result.update(
                    acquisition_status="failure",
                    disposition="manual_review",
                    commercial_identity_status="unverified",
                    manual_intervention_required=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        results.append(result)

    by_series: dict[str, dict[str, object]] = {}
    for series in EXPECTED_SHORTLIST:
        metric = metrics[series]
        attempted = metric["attempted"]
        dispositioned = metric["active_candidates"] + metric["lifecycle_excluded"] + metric["source_unavailable_404"]
        by_series[series] = {
            "attempted_targets": attempted,
            "verified_identity_targets": metric["verified_identity_targets"],
            "active_candidate_targets": metric["active_candidates"],
            "lifecycle_excluded_targets": metric["lifecycle_excluded"],
            "source_unavailable_404": metric["source_unavailable_404"],
            "manual_review": metric["manual_review"],
            "active_exact_icpns": metric["active_exact_icpns"],
            "excluded_non_active_part_numbers": metric["excluded_non_active_part_numbers"],
            "dispositioned_targets": dispositioned,
            "verified_identity_fraction": round(metric["verified_identity_targets"] / attempted, 6) if attempted else 0.0,
            "disposition_fraction": round(dispositioned / attempted, 6) if attempted else 0.0,
            "commercial_identity_access_clean": bool(
                attempted > 0
                and metric["verified_identity_targets"] == attempted
                and metric["source_unavailable_404"] == 0
                and metric["manual_review"] == 0
            ),
        }

    dispositioned_total = sum(int(v["dispositioned_targets"]) for v in by_series.values())
    return {
        "schema_version": 1,
        "phase": "C0.0",
        "probe_id": PROBE_ID,
        "scope": "post-U0 bounded read-only official-ST commercial identity/lifecycle evidence accessibility comparison",
        "candidate_series": list(EXPECTED_SHORTLIST),
        "attempted_targets": len(targets),
        "dispositioned_targets": dispositioned_total,
        "manual_review_targets": manual_failures,
        "bounded_probe_complete": dispositioned_total == EXPECTED_TARGET_COUNT and manual_failures == 0,
        "by_series": by_series,
        "results": results,
        "acquisition_transport": BROWSER_TRANSPORT,
        "selected_next_research_family": None,
        "claims": {
            "commercial_identity_asserted_for_unverified_targets": False,
            "openocd_is_commercial_identity_authority": False,
            "cmsis_alias_is_commercial_identity": False,
            "manufacturer_evidence_probe_is_admission": False,
            "selected_next_research_family": False,
            "production_write_authorized": False,
            "programming_policy_defined": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_support_claimed": False,
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
        base = result.get("base_device")
        evidence = result.get("evidence")
        if not isinstance(base, str) or not isinstance(evidence, dict):
            raise AcquisitionError("successful probe result lacks base/evidence")
        (evidence_dir / f"{base}.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def target_manifest(targets: list[ProbeTarget]) -> dict[str, object]:
    validate_targets(targets)
    return {
        "schema_version": 1,
        "phase": "C0.0",
        "probe_id": PROBE_ID,
        "selection_rule": "one lexical-min Base Device per guarded ordering-pattern subfamily",
        "target_count": len(targets),
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
        "claims": {
            "commercial_identity_claimed_from_openocd": False,
            "production_write_authorized": False,
            "selected_next_research_family": False,
        },
    }
