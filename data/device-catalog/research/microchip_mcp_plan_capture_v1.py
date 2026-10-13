#!/usr/bin/env python3
"""Single source-pinned Microchip DFP batch executor; research-only and opt-in.

Rebuilds the proposed plan from the archived *original* manufacturer index;
a plan JSON file alone is not trusted. One selected <=10-query batch per run.
Without --capture, only archived evidence replay is permitted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import microchip_mcp_batch_plan_v1 as planner
import microchip_mcp_batch_v1 as batch
from microchip_dfp_index_inventory_v1 import archived_inventory


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def select_batch(plan, inventory, source_digest, batch_id):
    require(isinstance(plan, dict), 'invalid plan JSON')
    require(isinstance(batch_id, str) and batch_id, 'missing batch identity')
    expected = planner.plan_inventory(inventory, source_digest,
                                      batch_size=plan.get('batch_size'))
    require(plan == expected, 'plan differs from source-pinned archived DFP inventory')
    matches = [entry for entry in expected['batches']
               if entry['batch_id'] == batch_id]
    require(len(matches) == 1, 'batch ID absent or ambiguous')
    selected = matches[0]
    require(1 <= len(selected['queries']) <= 10 and
            all(planner.BASE_QUERY.fullmatch(query)
                for query in selected['queries']),
            'invalid bounded executable query batch')
    return selected


def attestation(plan, selected):
    return {'schema_version': 1, 'manufacturer': 'Microchip',
            'batch_id': selected['batch_id'],
            'dfp_index_sha256': plan['original_dfp_index_sha256'],
            'query_list_sha256': selected['query_list_sha256'],
            'ordered_queries': list(selected['queries']),
            'capture_format': 'paged_v2',
            'search_results_are_complete_manufacturer_population': False,
            'population_boundary_validated': False,
            'global_active_denominator': None,
            'production_write_authorized': False}


def execute(plan, inventory, source_digest, batch_id, output_root,
            offline=True, workers=1):
    require(type(workers) is int and 1 <= workers <= 2, 'unsafe worker count')
    selected = select_batch(plan, inventory, source_digest, batch_id)
    root = Path(output_root).resolve()
    require('production' not in {p.lower() for p in root.parts},
            'Production path is forbidden')
    target = root / selected['batch_id']
    provenance = target / 'batch-source.json'
    expected = attestation(plan, selected)
    if offline:
        require(provenance.is_file(), 'missing source-bound batch attestation')
        actual = json.loads(provenance.read_text(encoding='utf-8'))
        require(actual == expected, 'batch provenance mismatch')
    else:
        require(not target.exists(), 'batch folder already exists; refuse overwrite')
        root.mkdir(parents=True, exist_ok=True)

    report = batch.execute(target, selected['queries'], offline=offline,
                           workers=workers, capture_format='paged_v2')
    if not offline:
        provenance.write_text(json.dumps(expected, indent=2, sort_keys=True)+'\n',
                              encoding='utf-8')
    require(report['selected_device_names'] == len(selected['queries']) and
            report['population_boundary_validated'] is False and
            report['global_active_denominator'] is None and
            report['production_write_authorized'] is False,
            'unsafe batch result or mismatched selection')
    return {'batch_id': batch_id, 'dfp_index_sha256': source_digest,
            'query_list_sha256': selected['query_list_sha256'],
            'mode': 'offline_replay' if offline else 'opt_in_live_capture',
            'all_queries_reconciled': report['all_queries_reconciled'],
            'source_is_exhaustive_sku_population': False,
            'population_boundary_validated': False,
            'global_active_denominator': None,
            'production_write_authorized': False,
            'batch_report': report}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True)
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--batch-id', required=True)
    ap.add_argument('--output-root', type=Path, required=True)
    ap.add_argument('--workers', type=int, choices=(1, 2), default=1)
    ap.add_argument('--capture', action='store_true',
                    help='explicit opt-in for bounded live official MCP queries')
    args = ap.parse_args()
    registry = json.loads(planner.REGISTRY.read_text(encoding='utf-8'))
    digest = registry['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    inventory = archived_inventory(args.evidence_root)
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    report = execute(plan, inventory, digest, args.batch_id,
                     args.output_root, offline=not args.capture, workers=args.workers)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report['all_queries_reconciled']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
