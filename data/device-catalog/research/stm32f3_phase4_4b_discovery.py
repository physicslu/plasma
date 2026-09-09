#!/usr/bin/env python3
"""Bounded, fail-closed official-ST discovery for STM32F3 Phase 4.4B.

The adapter consumes the deterministic Phase 4.4A source foundation and a
six-target manifest. It may acquire and retain manufacturer evidence, but it
never writes canonical/Production data and never defines programming policy.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

from st_browser_acquisition import (
    BROWSER_TRANSPORT,
    STBrowserAcquirer,
    build_browser_evidence_record,
)
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f3_foundation import (
    DEFAULT_CATALOG,
    EXPECTED_SUBFAMILIES,
    FAMILY,
    TARGET_CONFIG,
    deterministic_initial_targets,
    read_catalog,
    resolve_ordering_pattern_mapping,
)

HERE = Path(__file__).resolve().parent
PHASE = "4.4B"
DEFAULT_MANIFEST = HERE / "stm32f3-phase4.4b-discovery-manifest.json"
DEFAULT_OUTPUT = Path("/tmp/stm32f3-phase4.4b-live-summary.json")
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
        raise AcquisitionError("unsupported STM32F3 Phase 4.4B discovery manifest")
    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("Phase 4.4B discovery manifest requires pilot_id")
    if not isinstance(raw_targets, list) or len(raw_targets) != MAX_TARGETS:
        raise AcquisitionError(
            f"Phase 4.4B discovery requires exactly {MAX_TARGETS} targets"
        )

    targets: list[DiscoveryTarget] = []
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise AcquisitionError(f"Phase 4.4B target {index} must be an object")
        subfamily = raw.get("subfamily")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if not isinstance(subfamily, str) or subfamily not in EXPECTED_SUBFAMILIES:
            raise AcquisitionError(f"invalid STM32F3 subfamily: {subfamily!r}")
        if not isinstance(base, str):
            raise AcquisitionError(f"invalid STM32F3 Base Device: {base!r}")
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
            f"Phase 4.4B target selection drifted: expected={expected} observed={observed}"
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
    return resolve_ordering_pattern_mapping(commercial_core(icpn), catalog_rows)


def run_discovery(
    *,
    pilot_id: str,
    targets: list[DiscoveryTarget],
    catalog_rows: list[dict[str, str]],
    fetcher: Fetcher,
    evidence_builder: EvidenceBuilder = build_browser_evidence_record,
    timeout_seconds: float = 90.0,
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
            body, final_url, etag, last_modified = fetcher(
                target.source_url, timeout_seconds
            )
            evidence = evidence_builder(
                body=body,
                source_url=target.source_url,
                final_url=final_url,
                base_device=target.base_device,
                retrieved_at_utc=time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
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
            statuses = Counter(str(item["status"]) for item in mappings)
            overall = (
                "unique"
                if statuses == Counter({"unique": len(mappings)})
                else "ambiguous"
                if statuses["ambiguous"]
                else "unmapped"
            )
            result.update(
                acquisition_status="success",
                evidence=evidence,
                candidate_mappings=mappings,
                canonical_mapping={
                    "status": overall,
                    "candidate_count": len(mappings),
                    "target_configs": sorted(
                        {
                            config
                            for item in mappings
                            for config in item.get("target_configs", [])
                        }
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
                error_type=type(exc).__name__,
                error=str(exc),
            )
        results.append(result)

    summary: dict[str, object] = {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "pilot_id": pilot_id,
        "scope": "bounded read-only official-ST STM32F3 discovery",
        "attempted": len(targets),
        "acquisition_success": acquisition_success,
        "acquisition_failure": len(targets) - acquisition_success,
        "active_exact_icpn_candidates": active_candidates,
        "excluded_non_active_part_numbers": excluded_candidates,
        "canonical_mapping": {
            "unique": mapping_counts["unique"],
            "ambiguous": mapping_counts["ambiguous"],
            "unmapped": mapping_counts["unmapped"],
        },
        "manual_intervention_required": (
            mapping_counts["ambiguous"]
            + mapping_counts["unmapped"]
            + len(targets)
            - acquisition_success
        ),
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
    mapping = summary.get("canonical_mapping")
    claims = summary.get("claims")
    return (
        summary.get("attempted") == MAX_TARGETS
        and summary.get("acquisition_success") == MAX_TARGETS
        and summary.get("acquisition_failure") == 0
        and isinstance(summary.get("active_exact_icpn_candidates"), int)
        and int(summary["active_exact_icpn_candidates"]) > 0
        and isinstance(mapping, dict)
        and mapping.get("unique") == MAX_TARGETS
        and mapping.get("ambiguous") == 0
        and mapping.get("unmapped") == 0
        and summary.get("manual_intervention_required") == 0
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


def _playwright_version() -> str:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    catalog_rows = read_catalog(DEFAULT_CATALOG)
    pilot_id, targets = read_manifest(args.manifest, catalog_rows)
    with STBrowserAcquirer(headless=args.headless) as acquirer:
        fetcher = RateLimitedFetcher(
            delay_seconds=args.delay,
            fetcher=acquirer.fetch,
        )
        summary = run_discovery(
            pilot_id=pilot_id,
            targets=targets,
            catalog_rows=catalog_rows,
            fetcher=fetcher,
            timeout_seconds=args.timeout,
        )
        summary["browser"] = {
            "headless": args.headless,
            "browser_version": acquirer.browser_version,
            "playwright_version": _playwright_version(),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.evidence_dir is not None:
        write_evidence_files(summary, args.evidence_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if discovery_is_clean(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
