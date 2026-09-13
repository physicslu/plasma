#!/usr/bin/env python3
"""Aggregate deterministic STM32L1 L1.2 live-discovery shard artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import stm32l1_phase_l1_2_discovery as core
from stm32l1_phase_l1_2_sharded import aggregate_summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets-output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    paths = sorted(args.input_root.glob("**/summary.json"))
    if not paths:
        raise SystemExit("no STM32L1 L1.2 shard summaries found")
    summaries = [json.loads(path.read_text(encoding="utf-8")) for path in paths]

    rows = core.read_catalog(core.DEFAULT_CATALOG)
    full_targets = core.deterministic_targets(rows)
    summary = aggregate_summaries(full_targets=full_targets, summaries=summaries)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.targets_output.parent.mkdir(parents=True, exist_ok=True)
    args.targets_output.write_text(
        json.dumps(core.target_manifest(full_targets), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    core.write_evidence_files(summary, args.evidence_dir)
    print(
        json.dumps(
            {
                "base_device_count": summary["base_device_count"],
                "evidence_surface_count": summary["evidence_surface_count"],
                "active_candidate_targets": summary["active_candidate_targets"],
                "lifecycle_excluded_targets": summary["lifecycle_excluded_targets"],
                "active_exact_icpn_candidates": summary["active_exact_icpn_candidates"],
                "excluded_non_active_part_numbers": summary["excluded_non_active_part_numbers"],
                "routing_followup_required": summary["routing_followup_required"],
                "bounded_discovery_clean": summary["bounded_discovery_clean"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if core.discovery_is_clean(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
