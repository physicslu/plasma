#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import tempfile
from pathlib import Path

from device_catalog_admission_framework import read_csv
from stm32f2_bounded_discovery import (
    DEFAULT_CANONICAL,
    DEFAULT_CATALOG,
    DEFAULT_REGISTRY,
    HERE,
    build_next_batch_plan,
    load_spec,
    read_catalog,
    read_manifest,
    read_production_bases,
)
from stm32f2_bounded_evidence import validate as validate_retained_evidence

PHASES = ("4.3E", "4.3H")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})$")


def _write_historical_canonical(path: Path, *, phase: str) -> None:
    spec = load_spec(phase)
    fields, rows = read_csv(DEFAULT_CANONICAL)
    historical = [
        row for row in rows if row.get("base_device") in spec.expected_production_bases
    ]
    observed_bases = {row.get("base_device") for row in historical}
    assert observed_bases == set(spec.expected_production_bases)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(historical)


def _write_registry_without_phase(path: Path, *, phase: str) -> dict[str, object]:
    payload = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    batches = dict(payload["batches"])
    historical_entry = dict(batches.pop(phase))
    payload["batches"] = batches
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return historical_entry


def _target_projection(payload: list[dict[str, object]]) -> list[tuple[object, object, object]]:
    return [
        (
            item.get("subfamily"),
            item.get("base_device"),
            item.get("source_url"),
        )
        for item in payload
    ]


def _replay_phase(phase: str, temporary_root: Path) -> dict[str, object]:
    spec = load_spec(phase)
    historical_manifest = json.loads(spec.manifest_path.read_text(encoding="utf-8"))
    date_match = DATE_RE.search(str(historical_manifest["pilot_id"]))
    assert date_match is not None
    acquisition_date = date_match.group(1)

    canonical_path = temporary_root / f"{phase}-canonical.csv"
    registry_path = temporary_root / f"{phase}-registry.json"
    _write_historical_canonical(canonical_path, phase=phase)
    historical_entry = _write_registry_without_phase(registry_path, phase=phase)

    catalog_rows = read_catalog(DEFAULT_CATALOG)
    production_bases = read_production_bases(canonical_path, spec=spec)
    pilot_id, targets = read_manifest(
        spec.manifest_path,
        catalog_rows,
        production_bases,
        spec=spec,
    )
    assert pilot_id == historical_manifest["pilot_id"]
    manifest_projection = _target_projection(historical_manifest["targets"])
    observed_projection = [
        (target.subfamily, target.base_device, target.source_url) for target in targets
    ]
    assert observed_projection == manifest_projection

    plan = build_next_batch_plan(
        phase=phase,
        acquisition_date=acquisition_date,
        scope=spec.scope,
        registry_path=registry_path,
        catalog_path=DEFAULT_CATALOG,
        canonical_path=canonical_path,
    )
    planned_entry = plan["registry_entry"]
    assert planned_entry == historical_entry
    assert plan["manifest"]["phase"] == phase
    assert plan["manifest"]["pilot_id"] == historical_manifest["pilot_id"]
    assert _target_projection(plan["manifest"]["targets"]) == manifest_projection

    retained = validate_retained_evidence(phase=phase)
    retained_summary = json.loads(
        (spec.evidence_dir / "pilot-summary.json").read_text(encoding="utf-8")
    )
    assert retained["status"] == "valid"
    assert retained["targets"] == len(manifest_projection)
    assert (
        retained["active_exact_icpn_candidates"]
        == retained_summary["active_exact_icpn_candidates"]
    )
    assert retained["production_admission_ready"] is False

    return {
        "phase": phase,
        "production_base_devices": len(spec.expected_production_bases),
        "targets": [base for _, base, _ in manifest_projection],
        "active_exact_icpn_candidates": retained["active_exact_icpn_candidates"],
        "planner_matches_historical_registry": True,
        "planner_matches_historical_targets": True,
        "retained_evidence_replay": "valid",
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        reports = [_replay_phase(phase, root) for phase in PHASES]

    print(
        json.dumps(
            {
                "status": "valid",
                "family": "STM32F2",
                "validation": "bounded_historical_golden_replay",
                "phases": reports,
                "canonical_dataset_admission": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
