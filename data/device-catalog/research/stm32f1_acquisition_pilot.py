#!/usr/bin/env python3
"""Controlled batch runner for STM32F1 commercial ICPN source acquisition.

This research tool batches the Phase 2.4 fail-closed ST product-page probe over a
small manifest. It emits candidate evidence and KPI summary only; it never writes
or promotes rows into the canonical commercial ICPN dataset.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from st_product_page_acquisition import (
    AcquisitionError,
    build_evidence_record,
    fetch_html,
    validate_base_device,
    validate_source_url,
)

PILOT_SCHEMA_VERSION = 1
MAX_PILOT_TARGETS = 10
ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "stm32f1-acquisition-pilot-manifest.json"
DEFAULT_CATALOG = ROOT / "openocd-parts-canonical.csv"


@dataclass(frozen=True)
class PilotTarget:
    base_device: str
    source_url: str
    selection_reason: str


FetchResult = tuple[bytes, str, str | None, str | None]
Fetcher = Callable[[str, float], FetchResult]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_manifest(path: Path) -> tuple[str, list[PilotTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != PILOT_SCHEMA_VERSION:
        raise AcquisitionError("unsupported pilot manifest schema_version")
    pilot_id = payload.get("pilot_id")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("pilot manifest requires non-empty pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise AcquisitionError("pilot manifest requires non-empty targets")
    if len(raw_targets) > MAX_PILOT_TARGETS:
        raise AcquisitionError(
            f"pilot manifest exceeds bounded target limit of {MAX_PILOT_TARGETS}"
        )

    targets: list[PilotTarget] = []
    seen_bases: set[str] = set()
    seen_urls: set[str] = set()
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise AcquisitionError(f"pilot target {index} must be an object")
        base_device = raw.get("base_device")
        source_url = raw.get("source_url")
        selection_reason = raw.get("selection_reason")
        if not isinstance(base_device, str) or not isinstance(source_url, str):
            raise AcquisitionError(f"pilot target {index} requires base_device and source_url")
        if not isinstance(selection_reason, str) or not selection_reason.strip():
            raise AcquisitionError(f"pilot target {index} requires selection_reason")
        validate_base_device(base_device)
        validate_source_url(source_url)
        expected_slug = f"/{base_device.lower()}.html"
        if not source_url.endswith(expected_slug):
            raise AcquisitionError(
                f"pilot target {base_device}: source URL slug must end with {expected_slug}"
            )
        if base_device in seen_bases:
            raise AcquisitionError(f"duplicate pilot base_device: {base_device}")
        if source_url in seen_urls:
            raise AcquisitionError(f"duplicate pilot source_url: {source_url}")
        seen_bases.add(base_device)
        seen_urls.add(source_url)
        targets.append(PilotTarget(base_device, source_url, selection_reason.strip()))
    return pilot_id, targets


def read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def catalog_mapping(base_device: str, catalog_rows: list[dict[str, str]]) -> dict[str, object]:
    matches = [row for row in catalog_rows if row.get("part_number") == base_device]
    if not matches:
        return {"status": "unmapped", "match_count": 0, "target_configs": []}
    target_configs = sorted(
        {row.get("target_config", "") for row in matches if row.get("target_config", "")}
    )
    if len(matches) == 1:
        return {
            "status": "unique",
            "match_count": 1,
            "identifier_kind": matches[0].get("identifier_kind", ""),
            "target_configs": target_configs,
        }
    return {
        "status": "ambiguous",
        "match_count": len(matches),
        "identifier_kinds": sorted({row.get("identifier_kind", "") for row in matches}),
        "target_configs": target_configs,
    }


def run_pilot(
    *,
    pilot_id: str,
    targets: list[PilotTarget],
    catalog_rows: list[dict[str, str]],
    fetcher: Fetcher = fetch_html,
    timeout_seconds: float = 30.0,
    retrieved_at_factory: Callable[[], str] = utc_now,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    mapping_counts: Counter[str] = Counter()
    acquisition_success = 0
    exact_icpn_candidates = 0
    openocd_cfg_mapping = 0
    manual_intervention_required = 0

    for target in targets:
        mapping = catalog_mapping(target.base_device, catalog_rows)
        mapping_counts[str(mapping["status"])] += 1
        if mapping["status"] == "unique" and mapping["target_configs"]:
            openocd_cfg_mapping += 1

        result: dict[str, object] = {
            "base_device": target.base_device,
            "source_url": target.source_url,
            "selection_reason": target.selection_reason,
            "canonical_mapping": mapping,
        }
        try:
            body, final_url, etag, last_modified = fetcher(target.source_url, timeout_seconds)
            evidence = build_evidence_record(
                body=body,
                source_url=target.source_url,
                final_url=final_url,
                base_device=target.base_device,
                retrieved_at_utc=retrieved_at_factory(),
                http_etag=etag,
                http_last_modified=last_modified,
            )
            result["acquisition_status"] = "success"
            result["evidence"] = evidence
            acquisition_success += 1
            exact_icpn_candidates += len(evidence["exact_icpns"])
        except (AcquisitionError, OSError) as exc:
            result["acquisition_status"] = "failure"
            result["error"] = str(exc)

        mapping_ready = mapping["status"] == "unique" and bool(mapping["target_configs"])
        if result["acquisition_status"] != "success" or not mapping_ready:
            manual_intervention_required += 1
        results.append(result)

    attempted = len(targets)
    return {
        "schema_version": PILOT_SCHEMA_VERSION,
        "pilot_id": pilot_id,
        "attempted": attempted,
        "acquisition_success": acquisition_success,
        "acquisition_failure": attempted - acquisition_success,
        "exact_icpn_candidates": exact_icpn_candidates,
        "canonical_mapping": {
            "unique": mapping_counts["unique"],
            "ambiguous": mapping_counts["ambiguous"],
            "unmapped": mapping_counts["unmapped"],
        },
        "openocd_cfg_mapping": {"mapped": openocd_cfg_mapping, "total": attempted},
        "manual_intervention_required": manual_intervention_required,
        "results": results,
    }


def pilot_is_clean(summary: dict[str, object]) -> bool:
    return summary.get("manual_intervention_required") == 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, help="Write summary JSON; stdout if omitted")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        pilot_id, targets = read_manifest(args.manifest)
        catalog_rows = read_catalog(args.catalog)
        summary = run_pilot(
            pilot_id=pilot_id,
            targets=targets,
            catalog_rows=catalog_rows,
            timeout_seconds=args.timeout,
        )
        payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if pilot_is_clean(summary) else 1
    except (AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
