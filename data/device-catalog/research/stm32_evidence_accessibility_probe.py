#!/usr/bin/env python3
"""Bounded official-ST evidence accessibility probe for STM32U0/C0/L1.

This is a research-selection gate, not a device admission gate.  The candidate
series come from the frozen post-G4 cross-family prioritization shortlist.  One
representative Base Device is selected deterministically from each guarded
OpenOCD ordering-pattern subfamily.  Official ST product-page evidence then
measures commercial identity/lifecycle accessibility on an equal basis.

OpenOCD/CMSIS data is used only to bound the research surface.  It is never
commercial identity or lifecycle authority, and this probe never claims
programming/runtime support or selects a next family by itself.
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

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_PRIORITIZATION = HERE / "stm32-cross-family-prioritization-baseline.json"
DEFAULT_MANIFEST = HERE / "stm32-evidence-accessibility-probe-manifest.json"
DEFAULT_OUTPUT = Path("/tmp/stm32-evidence-accessibility-probe-summary.json")
PARSER_PROFILE = "stm32_cross_family_accessibility_probe_v1"
PROBE_ID = "stm32-cross-family-official-st-evidence-accessibility-probe-v1"
EXPECTED_SHORTLIST = ("STM32U0", "STM32C0", "STM32L1")
EXPECTED_SURFACES = {
    "STM32U0": {
        "rows": 48,
        "ordering": 42,
        "cmsis": 6,
        "target_config": "tcl/target/stm32u0x.cfg",
        "subfamilies": {"STM32U031": 16, "STM32U073": 24, "STM32U083": 8},
    },
    "STM32C0": {
        "rows": 95,
        "ordering": 73,
        "cmsis": 22,
        "target_config": "tcl/target/stm32c0x.cfg",
        "subfamilies": {
            "STM32C011": 9,
            "STM32C031": 12,
            "STM32C051": 12,
            "STM32C071": 30,
            "STM32C091": 16,
            "STM32C092": 16,
        },
    },
    "STM32L1": {
        "rows": 132,
        "ordering": 87,
        "cmsis": 45,
        "target_config": "tcl/target/stm32l1.cfg",
        "subfamilies": {"STM32L100": 7, "STM32L151": 55, "STM32L152": 53, "STM32L162": 17},
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


def _frozen_shortlist(path: Path = DEFAULT_PRIORITIZATION) -> tuple[str, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("policy_id") != "stm32-cross-family-prioritization-v1":
        raise AcquisitionError("unexpected cross-family prioritization policy")
    if payload.get("selected_next_research_family") is not None:
        raise AcquisitionError("accessibility probe requires an unselected research shortlist")
    shortlist = payload.get("research_shortlist")
    if not isinstance(shortlist, list):
        raise AcquisitionError("cross-family prioritization shortlist must be a list")
    observed = tuple(item.get("plasma_series") for item in shortlist if isinstance(item, dict))
    if observed != EXPECTED_SHORTLIST:
        raise AcquisitionError(f"cross-family shortlist drifted: {observed}")
    return observed


def _guarded_series_rows(series: str, catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if series not in EXPECTED_SURFACES:
        raise AcquisitionError(f"unsupported accessibility-probe series: {series}")
    expected = EXPECTED_SURFACES[series]
    rows = [
        row for row in catalog_rows
        if row.get("vendor") == "STMicroelectronics" and row.get("plasma_series") == series
    ]
    if len(rows) != expected["rows"]:
        raise AcquisitionError(f"{series}: source row count drifted")
    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    expected_kinds = Counter({"ordering_pattern": expected["ordering"], "cmsis_device_name": expected["cmsis"]})
    if kinds != expected_kinds:
        raise AcquisitionError(f"{series}: identifier-kind surface drifted: {dict(kinds)}")
    subfamilies = dict(sorted(Counter(row.get("subfamily", "") for row in rows).items()))
    if subfamilies != expected["subfamilies"]:
        raise AcquisitionError(f"{series}: subfamily surface drifted")
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
    prioritization_path: Path = DEFAULT_PRIORITIZATION,
) -> list[tuple[str, str, str]]:
    shortlist = _frozen_shortlist(prioritization_path)
    targets: list[tuple[str, str, str]] = []
    for series in shortlist:
        rows = _guarded_series_rows(series, catalog_rows)
        by_subfamily: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            if row.get("identifier_kind") == "ordering_pattern":
                by_subfamily[row["subfamily"]].add(base_from_ordering_pattern(row))
        expected_subfamilies = tuple(EXPECTED_SURFACES[series]["subfamilies"])
        if tuple(sorted(by_subfamily)) != tuple(sorted(expected_subfamilies)):
            raise AcquisitionError(f"{series}: ordering-pattern subfamily coverage drifted")
        for subfamily in expected_subfamilies:
            bases = sorted(by_subfamily[subfamily])
            if not bases:
                raise AcquisitionError(f"{subfamily}: no ordering-pattern Base Device")
            targets.append((series, subfamily, bases[0]))
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise AcquisitionError("accessibility-probe target count drifted")
    return targets


def read_manifest(
    path: Path,
    catalog_rows: list[dict[str, str]],
    prioritization_path: Path = DEFAULT_PRIORITIZATION,
) -> tuple[str, list[ProbeTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("probe_id") != PROBE_ID:
        raise AcquisitionError("unsupported STM32 evidence accessibility probe manifest")
    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("accessibility probe manifest requires pilot_id")
    if not isinstance(raw_targets, list) or len(raw_targets) != EXPECTED_TARGET_COUNT:
        raise AcquisitionError(f"accessibility probe requires exactly {EXPECTED_TARGET_COUNT} targets")
    targets: list[ProbeTarget] = []
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise AcquisitionError(f"probe target {index} must be an object")
        series = raw.get("series")
        subfamily = raw.get("subfamily")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if series not in EXPECTED_SHORTLIST:
            raise AcquisitionError(f"invalid probe series: {series!r}")
        if not isinstance(subfamily, str) or subfamily not in EXPECTED_SURFACES[series]["subfamilies"]:
            raise AcquisitionError(f"invalid probe subfamily: {subfamily!r}")
        if not isinstance(base, str) or not base.startswith(subfamily):
            raise AcquisitionError(f"invalid probe Base Device: {base!r}")
        if not isinstance(source, str):
            raise AcquisitionError(f"{base}: source_url is required")
        validate_source_url(source)
        if source != source_url_for_base(base):
            raise AcquisitionError(f"{base}: source URL slug mismatch")
        if not isinstance(reason, str) or not reason.strip():
            raise AcquisitionError(f"{base}: selection_reason is required")
        targets.append(ProbeTarget(series, subfamily, base, source, reason.strip()))
    observed = [(target.series, target.subfamily, target.base_device) for target in targets]
    expected = deterministic_targets(catalog_rows, prioritization_path)
    if observed != expected:
        raise AcquisitionError(f"accessibility-probe target selection drifted: expected={expected} observed={observed}")
    return pilot_id, targets


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


def run_probe(
    *,
    pilot_id: str,
    targets: list[ProbeTarget],
    fetcher: Fetcher,
    evidence_builder: EvidenceBuilder = build_probe_evidence_record,
    timeout_seconds: float = 90.0,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    series_metrics: dict[str, Counter[str]] = {series: Counter() for series in EXPECTED_SHORTLIST}
    manual_failures = 0

    for target in targets:
        metric = series_metrics[target.series]
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
        metric = series_metrics[series]
        attempted = metric["attempted"]
        dispositioned = (
            metric["active_candidates"]
            + metric["lifecycle_excluded"]
            + metric["source_unavailable_404"]
        )
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
    bounded_clean = (
        len(targets) == EXPECTED_TARGET_COUNT
        and dispositioned_total == EXPECTED_TARGET_COUNT
        and manual_failures == 0
    )
    return {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "pilot_id": pilot_id,
        "scope": "bounded read-only official-ST commercial identity/lifecycle evidence accessibility comparison",
        "candidate_series": list(EXPECTED_SHORTLIST),
        "attempted_targets": len(targets),
        "dispositioned_targets": dispositioned_total,
        "manual_review_targets": manual_failures,
        "bounded_probe_clean": bounded_clean,
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


def probe_is_clean(summary: dict[str, object]) -> bool:
    claims = summary.get("claims")
    return (
        summary.get("attempted_targets") == EXPECTED_TARGET_COUNT
        and summary.get("dispositioned_targets") == EXPECTED_TARGET_COUNT
        and summary.get("manual_review_targets") == 0
        and summary.get("bounded_probe_clean") is True
        and summary.get("selected_next_research_family") is None
        and isinstance(claims, dict)
        and claims
        and set(claims.values()) == {False}
    )


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
