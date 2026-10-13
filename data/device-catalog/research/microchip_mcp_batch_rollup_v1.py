#!/usr/bin/env python3
"""Offline-only Microchip MCP evidence rollup across source-pinned DFP batches.

Never assumes a DFP support name is an exact orderable SKU, and never treats
a partial query batch as complete evidence. No network or Production writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import microchip_mcp_batch_plan_v1 as planner
import microchip_mcp_plan_capture_v1 as capture
import microchip_mcp_evidence_ledger_v1 as ledger
from microchip_dfp_index_inventory_v1 import archived_inventory


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def build(plan, inventory, pinned_digest, batch_root):
    require(isinstance(plan, dict), 'invalid batch plan')
    expected = planner.plan_inventory(inventory, pinned_digest,
                                      batch_size=plan.get('batch_size'))
    require(plan == expected, 'batch plan diverges from pinned official DFP source')
    root = Path(batch_root).resolve()
    require('production' not in {part.lower() for part in root.parts},
            'Production evidence path is forbidden')
    require(root.is_dir(), 'missing offline batch evidence directory')
    planned_ids = {entry['batch_id'] for entry in expected['batches']}
    unplanned_entries = sorted(entry.name for entry in root.iterdir()
                               if (entry.is_dir() or entry.is_symlink()) and
                               entry.name not in planned_ids)
    reports, candidates, conflicted = [], {}, {}
    complete_batches = 0
    complete_queries = 0

    for batch in expected['batches']:
        batch_id = batch['batch_id']
        location = root / batch_id
        record = {'batch_id': batch_id, 'lane': batch['lane'],
                  'planned_queries': len(batch['queries']),
                  'query_list_sha256': batch['query_list_sha256']}
        if not location.exists() and not location.is_symlink():
            record['state'] = 'not_captured'
            reports.append(record)
            continue
        try:
            require(location.is_dir() and not location.is_symlink(),
                    'unsafe evidence batch directory')
            attestation = json.loads(
                (location / 'batch-source.json').read_text(encoding='utf-8'))
            require(attestation == capture.attestation(expected, batch),
                    'missing or mismatched batch attestation')
            research = ledger.build(location, list(batch['queries']))
            require(research.get('selected_queries') == len(batch['queries']) and
                    research.get('production_write_authorized') is False and
                    research.get('global_active_denominator') is None and
                    research.get('manufacturer_population_complete') is False,
                    'unsafe or mismatched research ledger claims')
            require(research.get('all_queries_reconciled') is True and
                    research.get('fully_replayed_queries') == len(batch['queries']),
                    'partial/unverified query batch; quarantine all batch observations')
            rows = research.get('ordering_candidates')
            require(isinstance(rows, list) and
                    len(rows) == research.get('unique_exact_ordering_candidates'),
                    'ledger candidate row count mismatch')
            local = {}
            for item in rows:
                require(isinstance(item, dict), 'invalid ledger candidate')
                icpn, lifecycle = item.get('icpn'), item.get('rawLifecycleStatus')
                require(isinstance(icpn, str) and icpn and
                        isinstance(lifecycle, str) and lifecycle.strip(),
                        'missing ordering identity or raw lifecycle')
                require(icpn not in local, 'duplicate ledger ordering identity')
                sources = item.get('sources')
                require(isinstance(sources, list) and sources,
                        'ordering identity missing source bytes')
                rel_sources = []
                for source in sources:
                    require(isinstance(source, dict) and
                            source.get('query') in batch['queries'] and
                            isinstance(source.get('response_sha256'), str) and
                            re.fullmatch(r'[0-9a-f]{64}', source['response_sha256']) and
                            isinstance(source.get('evidence_file'), str) and
                            re.fullmatch(r'[A-Za-z0-9]+/response-[0-9]{2,3}\.txt',
                                         source['evidence_file']) and
                            source['evidence_file'].startswith(source['query']+'/'),
                            'unsafe or unproven source link')
                    rel_sources.append(dict(source, evidence_file=
                                            batch_id+'/'+source['evidence_file']))
                local[icpn] = {'icpn': icpn,
                               'rawLifecycleStatus': lifecycle,
                               'sources': rel_sources}
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            record.update(state='unverified_or_partial_archive',
                          error_type=type(error).__name__,
                          error=str(error)[:200])
            reports.append(record)
            continue

        # Only after entire source batch passes replay may its rows reach rollup.
        record.update(state='fully_replayed_research_batch',
                      source_linked_candidates=len(local))
        reports.append(record)
        complete_batches += 1
        complete_queries += len(batch['queries'])
        for icpn, current in local.items():
            if icpn in conflicted:
                conflicted[icpn]['observations'].append(current)
                continue
            previous = candidates.get(icpn)
            if previous is None:
                candidates[icpn] = current
            elif previous['rawLifecycleStatus'] == current['rawLifecycleStatus']:
                previous['sources'].extend(current['sources'])
            else:
                conflicted[icpn] = {'icpn': icpn, 'observations': [previous, current]}
                del candidates[icpn]

    ordered = [candidates[part] for part in sorted(candidates)]
    conflict_rows = [conflicted[part] for part in sorted(conflicted)]
    return {
        'schema_version': 1,
        'type': 'microchip-source-pinned-batch-research-rollup',
        'manufacturer': 'Microchip',
        'original_dfp_index_sha256': pinned_digest,
        'unexpected_archive_directories_or_symlinks': unplanned_entries,
        'planned_batches': len(expected['batches']),
        'fully_replayed_batches': complete_batches,
        'not_captured_batches': sum(r['state'] == 'not_captured' for r in reports),
        'unverified_or_partial_batches': sum(
            r['state'] == 'unverified_or_partial_archive' for r in reports),
        'planned_text_search_queries': expected['supported_text_search_seeds'],
        'fully_replayed_text_search_queries': complete_queries,
        'requires_manual_query_mapping': len(expected['needs_manual_query_mapping']),
        'excluded_or_unclassified_dfp_names':
            expected['excluded_or_unclassified_support_names'],
        'source_linked_unique_exact_prefix_candidates': len(ordered),
        'cross_batch_duplicate_evidence_count': sum(
            max(0, len(row['sources'])-1) for row in ordered),
        'lifecycle_conflict_identity_count': len(conflict_rows),
        'all_planned_batches_fully_replayed':
            complete_batches == len(expected['batches']) and not conflicted and
            not unplanned_entries,
        'batch_reports': reports,
        'ordering_candidates': ordered,
        'conflicting_ordering_identities': conflict_rows,
        'discovery_names_are_complete_orderable_sku_population': False,
        'search_results_are_exhaustive_sku_population': False,
        'manufacturer_population_complete': False,
        'population_boundary_validated': False,
        'global_active_denominator': None,
        'production_write_authorized': False,
        'programming_support_claimed': False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True)
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--batch-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--require-all', action='store_true',
                    help='nonzero exit unless every planned batch replays')
    args = ap.parse_args()
    registry = json.loads(planner.REGISTRY.read_text(encoding='utf-8'))
    digest = registry['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    report = build(plan, archived_inventory(args.evidence_root),
                   digest, args.batch_root)
    target = args.output.resolve()
    require('production' not in {p.lower() for p in target.parts},
            'Production output forbidden')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n',
                      encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in
                      ('ordering_candidates', 'batch_reports',
                       'conflicting_ordering_identities')}, indent=2))
    if args.require_all and not report['all_planned_batches_fully_replayed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
