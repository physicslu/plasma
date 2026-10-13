#!/usr/bin/env python3
"""Recompute source-bound Microchip DFP *query* execution gap, not SKU coverage.

The query denominator is frozen DFP support search seeds after conservative
accessory/syntax review. The vendor Active commercial ICPN universe is unknown.
This script makes NO live HTTP calls and NEVER writes Production catalogs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import microchip_mcp_batch_plan_v1 as planner
import microchip_mcp_batch_v1 as batch
import microchip_mcp_evidence_ledger_v1 as ledger
from microchip_dfp_index_inventory_v1 import archived_inventory


def require(condition, message):
    if not condition:
        raise ValueError(message)


def build(plan, inventory, pinned_digest, pilot_root, pilot_queries):
    require(isinstance(plan, dict), 'plan must be an object')
    expected = planner.plan_inventory(inventory, pinned_digest,
                                      batch_size=plan.get('batch_size'))
    require(plan == expected, 'plan is not the exact original DFP-derived plan')
    require(isinstance(pilot_queries, list) and
            1 <= len(pilot_queries) <= 27 and
            len(pilot_queries) == len(set(pilot_queries)) and
            all(isinstance(q, str) for q in pilot_queries),
            'invalid bounded pilot query list')
    planned_by_lane = {name: lane for lane in planner.LANES
                       for item in expected['batches'] if item['lane'] == lane
                       for name in item['queries']}
    planned = set(planned_by_lane)
    require(len(planned) == expected['supported_text_search_seeds'] and
            set(pilot_queries) <= planned, 'pilot contains nonplanned query names')
    pilot_root = Path(pilot_root).resolve()
    require('production' not in {part.lower() for part in pilot_root.parts} and
            pilot_root.is_dir(), 'missing or forbidden pilot evidence directory')
    result = ledger.build(pilot_root, pilot_queries)
    reports = result.get('queries')
    require(isinstance(reports, list) and len(reports) == len(pilot_queries) and
            {entry.get('query') for entry in reports} == set(pilot_queries) and
            result.get('selected_queries') == len(pilot_queries) and
            result.get('production_write_authorized') is False and
            result.get('global_active_denominator') is None and
            result.get('manufacturer_population_complete') is False,
            'mismatched or unsafe pilot ledger')
    fully = {entry['query'] for entry in reports
             if entry.get('state') == 'fully_replayed_bounded_query'}
    unresolved = set(pilot_queries) - fully
    require(result.get('fully_replayed_queries') == len(fully),
            'fully replayed pilot total mismatch')
    raw_rows = result.get('ordering_candidates')
    require(isinstance(raw_rows, list) and
            result.get('unique_exact_ordering_candidates') == len(raw_rows),
            'research candidate count mismatch')
    require(all(isinstance(row, dict) and row.get('icpn') and row.get('sources')
                for row in raw_rows), 'missing original source-linked candidate')
    unattempted = sorted(planned - set(pilot_queries))
    manual = expected['needs_manual_query_mapping']
    statuses = Counter(entry['reason'] for entry in manual)
    lanes = {}
    for lane in planner.LANES:
        names = {q for q, sector in planned_by_lane.items() if sector == lane}
        lanes[lane] = {
            'planned_queries': len(names),
            'fully_replayed_queries': len(names & fully),
            'unverified_queries': len(names & unresolved),
            'not_yet_attempted_queries': len(names - set(pilot_queries)),
        }
    require(len(fully) + len(unresolved) + len(unattempted) == len(planned),
            'query ledger must partition entire frozen plan')
    return {
        'schema_version': 1,
        'type': 'microchip-dfp-source-pinned-research-query-gap',
        'manufacturer': 'Microchip',
        'original_dfp_index_sha256': pinned_digest,
        'dfp_device_support_names': expected['dfp_device_support_names'],
        'mapped_discovery_lane_names': expected['mapped_discovery_lane_names'],
        'excluded_or_unclassified_support_names':
            expected['excluded_or_unclassified_support_names'],
        'manual_review_query_names': len(manual),
        'manual_review_reasons': dict(sorted(statuses.items())),
        'planned_text_search_queries': len(planned),
        'fully_replayed_queries': len(fully),
        'unverified_attempted_queries': len(unresolved),
        'not_yet_attempted_queries': len(unattempted),
        'reconciled_query_percent': round(100 * len(fully) / len(planned), 4)
                                    if planned else None,
        'unique_exact_prefix_research_candidates': len(raw_rows),
        'reconciled_query_names': sorted(fully),
        'unverified_attempted_query_names': sorted(unresolved),
        'not_yet_attempted_query_names': unattempted,
        'per_discovery_lane': lanes,
        'query_progress_is_not_exact_sku_coverage': True,
        'manufacturer_population_complete': False,
        'global_active_denominator': None,
        'production_write_authorized': False,
        'live_queries_performed': 0,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True,
                    help='source archived DFP index.html plus manifest.json')
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--pilot-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    registry = json.loads(planner.REGISTRY.read_text(encoding='utf-8'))
    pinned = registry['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    report = build(plan, archived_inventory(args.evidence_root), pinned,
                   args.pilot_root, batch.load_seeds())
    target = args.output.resolve()
    require('production' not in {piece.lower() for piece in target.parts},
            'Production report output forbidden')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n',
                      encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('reconciled_query_names',
                                     'unverified_attempted_query_names',
                                     'not_yet_attempted_query_names')}, indent=2))


if __name__ == '__main__':
    main()
