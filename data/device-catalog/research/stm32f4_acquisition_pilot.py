#!/usr/bin/env python3
"""Bounded STM32F4 source-acquisition pilot with ordering-pattern mapping."""

from __future__ import annotations

import argparse
import csv
import json
import re
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
    validate_source_url,
)
from stm32f4_admission_policy import TARGET_CONFIG, resolve_ordering_pattern_mapping

PILOT_SCHEMA_VERSION = 1
MAX_PILOT_TARGETS = 6
ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "stm32f4-phase3.1-pilot-manifest.json"
DEFAULT_CATALOG = ROOT / "openocd-parts-canonical.csv"
BASE_RE = re.compile(r"^STM32F4[0-9A-Z]+$")


@dataclass(frozen=True)
class PilotTarget:
    base_device: str
    source_url: str
    selection_reason: str


FetchResult = tuple[bytes, str, str | None, str | None]
Fetcher = Callable[[str, float], FetchResult]
EvidenceBuilder = Callable[..., dict[str, object]]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_manifest(path: Path) -> tuple[str, list[PilotTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != PILOT_SCHEMA_VERSION:
        raise AcquisitionError("unsupported STM32F4 pilot manifest schema_version")
    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("STM32F4 pilot manifest requires pilot_id")
    if not isinstance(raw_targets, list) or not raw_targets or len(raw_targets) > MAX_PILOT_TARGETS:
        raise AcquisitionError("STM32F4 pilot manifest target set is not bounded")

    targets: list[PilotTarget] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise AcquisitionError(f"STM32F4 pilot target {index} must be an object")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if not isinstance(base, str) or BASE_RE.fullmatch(base) is None:
            raise AcquisitionError(f"invalid STM32F4 base device: {base!r}")
        if base in seen:
            raise AcquisitionError(f"duplicate STM32F4 base device: {base}")
        if not isinstance(source, str):
            raise AcquisitionError(f"{base}: source_url is required")
        validate_source_url(source)
        if not source.endswith(f"/{base.lower()}.html"):
            raise AcquisitionError(f"{base}: source URL slug mismatch")
        if not isinstance(reason, str) or not reason.strip():
            raise AcquisitionError(f"{base}: selection_reason is required")
        seen.add(base)
        targets.append(PilotTarget(base, source, reason.strip()))
    return pilot_id, targets


def read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _target_mapping(
    exact_icpns: list[str],
    catalog_rows: list[dict[str, str]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    mappings: list[dict[str, object]] = []
    for icpn in exact_icpns:
        mapping = resolve_ordering_pattern_mapping(icpn, catalog_rows)
        mappings.append({"icpn": icpn, **mapping})

    if mappings and all(item.get("status") == "unique" for item in mappings):
        configs = sorted({config for item in mappings for config in item.get("target_configs", [])})
        status = "unique" if configs == [TARGET_CONFIG] else "ambiguous"
    elif any(item.get("status") == "ambiguous" for item in mappings):
        status = "ambiguous"
        configs = sorted({config for item in mappings for config in item.get("target_configs", [])})
    else:
        status = "unmapped"
        configs = sorted({config for item in mappings for config in item.get("target_configs", [])})
    return {
        "status": status,
        "candidate_count": len(exact_icpns),
        "target_configs": configs,
    }, mappings


def run_pilot(
    *,
    pilot_id: str,
    targets: list[PilotTarget],
    catalog_rows: list[dict[str, str]],
    fetcher: Fetcher = fetch_html,
    evidence_builder: EvidenceBuilder = build_evidence_record,
    timeout_seconds: float = 30.0,
    retrieved_at_factory: Callable[[], str] = utc_now,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    mapping_counts: Counter[str] = Counter()
    acquisition_success = 0
    exact_icpn_candidates = 0
    openocd_targets_mapped = 0
    manual_intervention_required = 0

    for target in targets:
        result: dict[str, object] = {
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
                retrieved_at_utc=retrieved_at_factory(),
                http_etag=etag,
                http_last_modified=last_modified,
            )
            raw_icpns = evidence.get("exact_icpns")
            if not isinstance(raw_icpns, list) or not all(isinstance(value, str) for value in raw_icpns):
                raise AcquisitionError(f"{target.base_device}: evidence exact_icpns must be a string list")
            target_mapping, candidate_mappings = _target_mapping(raw_icpns, catalog_rows)
            result["acquisition_status"] = "success"
            result["evidence"] = evidence
            result["canonical_mapping"] = target_mapping
            result["candidate_mappings"] = candidate_mappings
            acquisition_success += 1
            exact_icpn_candidates += len(raw_icpns)
            mapping_counts[str(target_mapping["status"])] += 1
            if target_mapping["status"] == "unique":
                openocd_targets_mapped += 1
            else:
                manual_intervention_required += 1
        except (AcquisitionError, OSError) as exc:
            result["acquisition_status"] = "failure"
            result["error"] = str(exc)
            result["canonical_mapping"] = {
                "status": "unmapped",
                "candidate_count": 0,
                "target_configs": [],
            }
            result["candidate_mappings"] = []
            mapping_counts["unmapped"] += 1
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
        "openocd_cfg_mapping": {"mapped": openocd_targets_mapped, "total": attempted},
        "manual_intervention_required": manual_intervention_required,
        "results": results,
    }


def pilot_is_clean(summary: dict[str, object]) -> bool:
    attempted = summary.get("attempted")
    return (
        isinstance(attempted, int)
        and attempted > 0
        and summary.get("acquisition_success") == attempted
        and summary.get("acquisition_failure") == 0
        and summary.get("canonical_mapping") == {"unique": attempted, "ambiguous": 0, "unmapped": 0}
        and summary.get("openocd_cfg_mapping") == {"mapped": attempted, "total": attempted}
        and summary.get("manual_intervention_required") == 0
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        pilot_id, targets = read_manifest(args.manifest)
        summary = run_pilot(
            pilot_id=pilot_id,
            targets=targets,
            catalog_rows=read_catalog(args.catalog),
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
