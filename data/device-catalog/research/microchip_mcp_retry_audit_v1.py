#!/usr/bin/env python3
"""Source-pinned, offline-only Microchip MCP batch recovery diagnostics.

Never overwrites archives or runs a vendor query. A missing query is NOT an
EOL verdict; a corrupt archive is quarantined and cannot become an accepted
SKU. New captures must use a separate fresh evidence directory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import microchip_mcp_batch_plan_v1 as planner
import microchip_mcp_plan_capture_v1 as capture
import microchip_mcp_probe_v1 as old
import microchip_mcp_paged_probe_v2 as paged
from microchip_dfp_index_inventory_v1 import archived_inventory


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(plan, inventory, pinned_digest, batch_id, batch_root):
    selected = capture.select_batch(plan, inventory, pinned_digest, batch_id)
    root = Path(batch_root).resolve()
    require('production' not in {piece.lower() for piece in root.parts},
            'Production evidence path forbidden')
    target = root / selected['batch_id']
    require(target.is_dir() and not target.is_symlink(),
            'missing or unsafe attested batch directory')
    attested = json.loads((target / 'batch-source.json').read_text(encoding='utf-8'))
    require(attested == capture.attestation(plan, selected),
            'missing or mismatched source-bound attestation')

    queries = selected['queries']
    unexpected = sorted(p.name for p in target.iterdir()
                        if p.name not in {*queries, 'batch-source.json', 'batch-summary.json'})
    states = []
    for query in queries:
        folder = target / query
        if not folder.exists() and not folder.is_symlink():
            states.append({'query': query, 'state': 'not_archived',
                           'next_action': 'fresh_capture_only'})
            continue
        try:
            require(folder.is_dir() and not folder.is_symlink(),
                    'unsafe query evidence directory')
            manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
            version = manifest.get('schema_version', 1)
            require(type(version) is int and version in (1, 2),
                    'unrecognized archive schema')
            result = (old if version == 1 else paged).replay(folder, query)
            require(result.get('query') == query and
                    result.get('population_boundary_validated') is False and
                    result.get('global_active_denominator') is None and
                    result.get('production_write_authorized') is False,
                    'unsafe replay result')
            count = result.get('exact_prefix_ordering_count')
            require(type(count) is int and count >= 0, 'invalid exact ordering count')
            if count == 0:
                states.append({'query': query, 'state': 'zero_exact_prefix_candidates',
                               'schema_version': version,
                               'reported_fuzzy_results': result['unique_ordering_count'],
                               'next_action': 'independent_vendor_identity_lifecycle_review'})
            else:
                states.append({'query': query, 'state': 'fully_replayed',
                               'schema_version': version,
                               'exact_prefix_candidates': count,
                               'next_action': 'retain_verified_archive'})
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            states.append({'query': query, 'state': 'unverified_archive',
                           'error_type': type(error).__name__,
                           'error': str(error)[:200],
                           'next_action': 'quarantine_original_then_fresh_capture'})
    counts = {key: sum(r['state'] == key for r in states)
              for key in ('fully_replayed', 'not_archived',
                          'zero_exact_prefix_candidates', 'unverified_archive')}
    return {
        'schema_version': 1, 'type': 'microchip-source-pinned-recovery-audit',
        'manufacturer': 'Microchip', 'batch_id': selected['batch_id'],
        'original_dfp_index_sha256': pinned_digest,
        'query_list_sha256': selected['query_list_sha256'],
        'planned_queries': len(queries),
        'unexpected_archive_entries': unexpected,
        'query_states': states, 'counts': counts,
        'fully_replayed_batch': counts['fully_replayed'] == len(queries) and
                                not unexpected,
        'new_capture_recommended': [r['query'] for r in states
                                    if r['state'] == 'not_archived'],
        'manual_review_required': [r['query'] for r in states
                                   if r['state'] in (
                                       'zero_exact_prefix_candidates',
                                       'unverified_archive')],
        'no_live_calls_performed': True,
        'manufacturer_population_complete': False,
        'population_boundary_validated': False,
        'global_active_denominator': None,
        'production_write_authorized': False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True)
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--batch-root', type=Path, required=True)
    ap.add_argument('--batch-id', required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    registry = json.loads(planner.REGISTRY.read_text(encoding='utf-8'))
    digest = registry['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    result = audit(plan, archived_inventory(args.evidence_root), digest,
                   args.batch_id, args.batch_root)
    dest = args.output.resolve()
    require('production' not in {piece.lower() for piece in dest.parts},
            'Production output forbidden')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n',
                    encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'query_states'},
                     indent=2))


if __name__ == '__main__':
    main()
