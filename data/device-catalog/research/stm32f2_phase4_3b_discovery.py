#!/usr/bin/env python3
"""Run bounded, fail-closed official-ST discovery for STM32F2.

Phase 4.3B deliberately samples one deterministic Base Device from each
OpenOCD-listed STM32F2 subfamily.  It records exact commercial part numbers and
their official ST marketing status, but it does not authorize Production,
runtime, REST, or programming-policy changes.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from st_browser_acquisition import (
    BROWSER_TRANSPORT,
    STBrowserAcquirer,
    build_browser_evidence_record,
)
from st_product_page_acquisition import AcquisitionError, validate_source_url

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_MANIFEST = HERE / "stm32f2-phase4.3b-discovery-manifest.json"
SCHEMA_VERSION = 1
PHASE = "4.3B"
MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32F2"
TARGET_CONFIG = "tcl/target/stm32f2x.cfg"
EXPECTED_SUBFAMILIES = ("STM32F205", "STM32F207", "STM32F215", "STM32F217")
MAX_TARGETS = len(EXPECTED_SUBFAMILIES)
BASE_RE = re.compile(r"^STM32F2[0-9]{2}[A-Z][A-Z0-9]$")
PATTERN_RE = re.compile(r"^(STM32F2[0-9]{2}[A-Z][A-Z0-9])([A-Z])x$")
ICPN_RE = re.compile(r"^STM32F2[0-9A-Z]+$")
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


def read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _f2_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [
        row
        for row in catalog_rows
        if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY
    ]
    if len(rows) != 47:
        raise AcquisitionError(f"Phase 4.3B requires the guarded 47-row STM32F2 surface, got {len(rows)}")
    for row in rows:
        pattern = row.get("part_number", "")
        if PATTERN_RE.fullmatch(pattern) is None:
            raise AcquisitionError(f"unsupported STM32F2 ordering pattern: {pattern!r}")
        if row.get("identifier_kind") != "ordering_pattern":
            raise AcquisitionError(f"{pattern}: identifier kind is not ordering_pattern")
        if row.get("target_config") != TARGET_CONFIG:
            raise AcquisitionError(f"{pattern}: unexpected OpenOCD target config")
        if row.get("openocd_distribution") != "upstream-openocd":
            raise AcquisitionError(f"{pattern}: unexpected OpenOCD distribution")
        if row.get("mapping_status") != "mapping_candidate":
            raise AcquisitionError(f"{pattern}: unexpected mapping status")
        if row.get("validation_status") != "not_verified":
            raise AcquisitionError(f"{pattern}: unexpected validation status")
    return rows


def deterministic_targets(catalog_rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in _f2_rows(catalog_rows):
        match = PATTERN_RE.fullmatch(row["part_number"])
        assert match is not None
        subfamily = row.get("subfamily", "")
        by_subfamily[subfamily].add(match.group(1))
    if tuple(sorted(by_subfamily)) != EXPECTED_SUBFAMILIES:
        raise AcquisitionError(
            "Phase 4.3B STM32F2 subfamily set drifted: " + ", ".join(sorted(by_subfamily))
        )
    return [(subfamily, sorted(by_subfamily[subfamily])[0]) for subfamily in EXPECTED_SUBFAMILIES]


def read_manifest(path: Path, catalog_rows: list[dict[str, str]]) -> tuple[str, list[DiscoveryTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("phase") != PHASE:
        raise AcquisitionError("unsupported STM32F2 Phase 4.3B discovery manifest")
    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("Phase 4.3B discovery manifest requires pilot_id")
    if not isinstance(raw_targets, list) or len(raw_targets) != MAX_TARGETS:
        raise AcquisitionError(f"Phase 4.3B discovery requires exactly {MAX_TARGETS} targets")

    targets: list[DiscoveryTarget] = []
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise AcquisitionError(f"Phase 4.3B target {index} must be an object")
        subfamily = raw.get("subfamily")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if not isinstance(subfamily, str) or subfamily not in EXPECTED_SUBFAMILIES:
            raise AcquisitionError(f"invalid STM32F2 subfamily: {subfamily!r}")
        if not isinstance(base, str) or BASE_RE.fullmatch(base) is None:
            raise AcquisitionError(f"invalid STM32F2 base device: {base!r}")
        if not isinstance(source, str):
            raise AcquisitionError(f"{base}: source_url is required")
        validate_source_url(source)
        if not source.endswith(f"/{base.lower()}.html"):
            raise AcquisitionError(f"{base}: source URL slug mismatch")
        if not isinstance(reason, str) or not reason.strip():
            raise AcquisitionError(f"{base}: selection_reason is required")
        targets.append(DiscoveryTarget(subfamily, base, source, reason.strip()))

    observed = [(target.subfamily, target.base_device) for target in targets]
    expected = deterministic_targets(catalog_rows)
    if observed != expected:
        raise AcquisitionError(f"Phase 4.3B target selection drifted: expected={expected} observed={observed}")
    return pilot_id, targets


def _commercial_core(icpn: str) -> str:
    for suffix in ("TR", "TT"):
        if icpn.endswith(suffix):
            return icpn[: -len(suffix)]
    return icpn


def _pattern_matches(pattern: str, value: str) -> bool:
    expression = "".join("[A-Z0-9]" if char.lower() == "x" else re.escape(char) for char in pattern)
    return re.fullmatch(expression, value) is not None


def resolve_mapping(icpn: str, catalog_rows: list[dict[str, str]]) -> dict[str, Any]:
    if ICPN_RE.fullmatch(icpn) is None:
        return {"status": "unmapped", "match_count": 0, "target_configs": []}
    matches = [
        row
        for row in _f2_rows(catalog_rows)
        if _pattern_matches(row["part_number"], _commercial_core(icpn))
    ]
    configs = sorted({row["target_config"] for row in matches})
    identifiers = sorted({row["part_number"] for row in matches})
    if len(matches) == 1 and configs == [TARGET_CONFIG]:
        return {
            "status": "unique",
            "match_count": 1,
            "identifier_kind": "ordering_pattern",
            "existing_identifier": identifiers[0],
            "target_configs": configs,
        }
    return {
        "status": "ambiguous" if matches else "unmapped",
        "match_count": len(matches),
        "existing_identifiers": identifiers,
        "target_configs": configs,
    }


class RateLimitedFetcher:
    def __init__(self, *, delay_seconds: float, fetcher: Fetcher) -> None:
        if delay_seconds < MIN_DELAY_SECONDS:
            raise AcquisitionError(f"live discovery delay must be at least {MIN_DELAY_SECONDS:.1f} seconds")
        self.delay_seconds = delay_seconds
        self.fetcher = fetcher
        self._first = True

    def __call__(self, source_url: str, timeout_seconds: float) -> FetchResult:
        if self._first:
            self._first = False
        else:
            time.sleep(self.delay_seconds)
        return self.fetcher(source_url, timeout_seconds)


def run_discovery(
    *,
    pilot_id: str,
    targets: list[DiscoveryTarget],
    catalog_rows: list[dict[str, str]],
    fetcher: Fetcher,
    evidence_builder: EvidenceBuilder = build_browser_evidence_record,
    timeout_seconds: float = 75.0,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    mapping_counts: Counter[str] = Counter()
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
            if not isinstance(raw_icpns, list) or not all(isinstance(value, str) for value in raw_icpns):
                raise AcquisitionError(f"{target.base_device}: exact_icpns must be a string list")
            if not isinstance(excluded, list):
                raise AcquisitionError(f"{target.base_device}: excluded lifecycle rows must be a list")
            if not raw_icpns:
                raise AcquisitionError(f"{target.base_device}: official ST page has no Active exact ICPN")
            if any(not value.startswith(target.base_device) for value in raw_icpns):
                raise AcquisitionError(f"{target.base_device}: evidence contains a foreign exact ICPN")
            mappings = [{"icpn": value, **resolve_mapping(value, catalog_rows)} for value in raw_icpns]
            statuses = Counter(str(item["status"]) for item in mappings)
            overall = "unique" if statuses == Counter({"unique": len(mappings)}) else (
                "ambiguous" if statuses["ambiguous"] else "unmapped"
            )
            result.update(
                acquisition_status="success",
                evidence=evidence,
                candidate_mappings=mappings,
                canonical_mapping={
                    "status": overall,
                    "candidate_count": len(mappings),
                    "target_configs": sorted(
                        {config for item in mappings for config in item.get("target_configs", [])}
                    ),
                },
            )
            acquisition_success += 1
            active_candidates += len(raw_icpns)
            excluded_candidates += len(excluded)
            mapping_counts[overall] += 1
        except (AcquisitionError, OSError) as exc:
            result.update(
                acquisition_status="failure",
                error=str(exc),
                candidate_mappings=[],
                canonical_mapping={"status": "unmapped", "candidate_count": 0, "target_configs": []},
            )
            mapping_counts["unmapped"] += 1
        results.append(result)

    attempted = len(targets)
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "pilot_id": pilot_id,
        "scope": "bounded read-only official-ST discovery",
        "claims": {
            "production_write_authorized": False,
            "production_admission_ready": False,
            "programming_policy_defined": False,
            "runtime_support_claimed": False,
        },
        "attempted": attempted,
        "acquisition_success": acquisition_success,
        "acquisition_failure": attempted - acquisition_success,
        "active_exact_icpn_candidates": active_candidates,
        "excluded_non_active_part_numbers": excluded_candidates,
        "canonical_mapping": {
            "unique": mapping_counts["unique"],
            "ambiguous": mapping_counts["ambiguous"],
            "unmapped": mapping_counts["unmapped"],
        },
        "manual_intervention_required": sum(
            mapping_counts[key] for key in ("ambiguous", "unmapped")
        ),
        "results": results,
    }


def discovery_is_clean(summary: dict[str, object]) -> bool:
    return (
        summary.get("attempted") == MAX_TARGETS
        and summary.get("acquisition_success") == MAX_TARGETS
        and summary.get("acquisition_failure") == 0
        and isinstance(summary.get("active_exact_icpn_candidates"), int)
        and int(summary["active_exact_icpn_candidates"]) > 0
        and summary.get("canonical_mapping") == {"unique": MAX_TARGETS, "ambiguous": 0, "unmapped": 0}
        and summary.get("manual_intervention_required") == 0
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        catalog_rows = read_catalog(args.catalog)
        pilot_id, targets = read_manifest(args.manifest, catalog_rows)
        with STBrowserAcquirer(headless=args.headless) as acquirer:
            fetcher = RateLimitedFetcher(delay_seconds=args.delay, fetcher=acquirer.fetch)
            summary = run_discovery(
                pilot_id=pilot_id,
                targets=targets,
                catalog_rows=catalog_rows,
                fetcher=fetcher,
                timeout_seconds=args.timeout,
            )
            browser_version = acquirer.browser_version
        summary["acquisition_transport"] = BROWSER_TRANSPORT
        summary["browser_runtime"] = {
            "engine": "chromium",
            "browser_version": browser_version,
            "playwright_requirement": "1.62.0",
            "headless": args.headless,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if discovery_is_clean(summary) else 1
    except (AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
