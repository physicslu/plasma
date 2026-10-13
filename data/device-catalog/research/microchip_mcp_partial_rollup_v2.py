#!/usr/bin/env python3
"""Source-bound Microchip partial-batch research rollup, with per-query quarantine.

A single failed query does not discard independently verified queries within
the same source-attested batch. This is NOT SKU population completeness or
authorization for Production admission. No vendor network operations occur.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import microchip_mcp_batch_plan_v1 as planner
import microchip_mcp_evidence_ledger_v1 as ledger
import microchip_mcp_plan_capture_v1 as capture
from microchip_dfp_index_inventory_v1 import archived_inventory


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def build(plan, inventory, digest, batch_root):
    require(isinstance(plan, dict), 'expected source-pinned plan object')
    source = planner.plan_inventory(inventory, digest, batch_size=plan.get('batch_size'))
    require(plan == source, 'untrusted or changed DFP batch plan')
    root = Path(batch_root).resolve()
    require('production' not in {p.lower() for p in root.parts} and root.is_dir(),
            'missing or forbidden batch root')
    expected_ids = {b['batch_id'] for b in source['batches']}
    unexpected = sorted(x.name for x in root.iterdir()
                        if x.is_symlink() or x.is_dir() and x.name not in expected_ids)
    reports, rows, conflicts, reconciled = [], {}, {}, set()
    zero_prefix = set()
    for item in source['batches']:
        batch_id = item['batch_id']
        folder = root / batch_id
        if not folder.exists() and not folder.is_symlink():
            reports.append({'batch_id': batch_id, 'state': 'not_archived',
                            'planned_queries': len(item['queries'])})
            continue
        record = {'batch_id': batch_id, 'planned_queries': len(item['queries']),
                  'fully_replayed_queries': 0, 'unverified_queries': [],
                  'not_archived_queries': [],
                  'replayed_zero_exact_prefix_queries': []}
        try:
            require(folder.is_dir() and not folder.is_symlink(),
                    'unsafe batch evidence path')
            allowed = {*item['queries'], 'batch-source.json', 'batch-summary.json'}
            require(all((p.name in allowed) and not p.is_symlink()
                        for p in folder.iterdir()), 'unplanned batch evidence entries')
            proof = folder / 'batch-source.json'
            require(proof.is_file() and not proof.is_symlink(), 'missing batch attestation')
            require(json.loads(proof.read_text(encoding='utf-8')) ==
                    capture.attestation(source, item), 'mismatched source-bound attestation')
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            record.update(state='entire_batch_quarantined',
                          error_type=type(error).__name__,
                          error=str(error)[:200])
            reports.append(record)
            continue
        for query in item['queries']:
            qdir = folder / query
            if not qdir.exists() and not qdir.is_symlink():
                record['not_archived_queries'].append(query)
                continue
            try:
                require(qdir.is_dir() and not qdir.is_symlink() and
                        all(not p.is_symlink() for p in qdir.iterdir()),
                        'unsafe query or response symlink')
                evidence = ledger.build(folder, [query])
                require(evidence.get('fully_replayed_queries') == 1 and
                        evidence.get('all_queries_reconciled') is True and
                        evidence.get('selected_queries') == 1 and
                        evidence.get('production_write_authorized') is False and
                        evidence.get('global_active_denominator') is None and
                        evidence.get('manufacturer_population_complete') is False,
                        'query evidence did not fully replay')
                candidates = evidence.get('ordering_candidates')
                require(isinstance(candidates, list) and
                        len(candidates) == evidence.get('unique_exact_ordering_candidates'),
                        'inconsistent source-linked identity result')
                if not candidates:
                    require(evidence.get('replayed_zero_exact_prefix_queries') == 1 and
                            evidence['queries'][0]['state'] ==
                            'fully_replayed_zero_exact_prefix',
                            'zero candidate count lacks complete replay proof')
                    record['replayed_zero_exact_prefix_queries'].append(query)
                    zero_prefix.add(query)
                    reconciled.add(query)
                    record['fully_replayed_queries'] += 1
                    continue
                require(evidence.get('positive_exact_prefix_queries') == 1,
                        'positive candidate count lacks replay proof')
                local = {}
                for row in candidates:
                    icpn, lifecycle = row.get('icpn'), row.get('rawLifecycleStatus')
                    require(isinstance(icpn, str) and icpn and icpn not in local and
                            isinstance(lifecycle, str) and lifecycle,
                            'invalid ordering identity or lifecycle')
                    sources = row.get('sources')
                    require(isinstance(sources, list) and sources, 'missing source links')
                    links = []
                    for evidence_link in sources:
                        path = evidence_link.get('evidence_file')
                        digest_link = evidence_link.get('response_sha256')
                        require(evidence_link.get('query') == query and
                                isinstance(path, str) and
                                re.fullmatch(re.escape(query)+r'/response-[0-9]{2,3}\.txt',
                                             path) and
                                isinstance(digest_link, str) and
                                re.fullmatch('[0-9a-f]{64}', digest_link),
                                'unsafe or unverified response link')
                        links.append(dict(evidence_link,
                                          evidence_file=batch_id+'/'+path))
                    local[icpn] = {'icpn': icpn, 'rawLifecycleStatus': lifecycle,
                                   'sources': links}
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                record['unverified_queries'].append({
                    'query': query, 'error_type': type(error).__name__,
                    'reason': str(error)[:180]})
                continue

            record['fully_replayed_queries'] += 1
            reconciled.add(query)
            for icpn, row in local.items():
                if icpn in conflicts:
                    conflicts[icpn]['observations'].append(row)
                elif icpn not in rows:
                    rows[icpn] = row
                elif rows[icpn]['rawLifecycleStatus'] == row['rawLifecycleStatus']:
                    rows[icpn]['sources'].extend(row['sources'])
                else:
                    conflicts[icpn] = {'icpn': icpn, 'observations': [rows.pop(icpn), row]}
        record['state'] = ('fully_replayed' if
                           record['fully_replayed_queries'] == len(item['queries'])
                           else 'partial_independent_queries_only')
        reports.append(record)

    planned_queries = source['supported_text_search_seeds']
    require(len(reconciled) <= planned_queries, 'invalid research query denominator')
    candidate_rows = [rows[k] for k in sorted(rows)]
    conflict_rows = [conflicts[k] for k in sorted(conflicts)]
    return {'schema_version': 2, 'type': 'microchip-partial-research-evidence-rollup',
            'manufacturer': 'Microchip', 'original_dfp_index_sha256': digest,
            'planned_batches': len(source['batches']),
            'planned_query_names': planned_queries,
            'independently_replayed_queries': len(reconciled),
            'independently_replayed_positive_queries': len(reconciled-zero_prefix),
            'replayed_zero_exact_prefix_queries': len(zero_prefix),
            'replayed_zero_exact_prefix_query_names': sorted(zero_prefix),
            'unreplayed_or_unattempted_queries': planned_queries-len(reconciled),
            'query_progress_percent': round(100*len(reconciled)/planned_queries,4)
                                      if planned_queries else None,
            'validated_exact_prefix_candidates': len(candidate_rows),
            'raw_lifecycle_conflicts': len(conflict_rows),
            'unexpected_batch_directories_or_symlinks': unexpected,
            'all_queries_replayed_with_no_conflicts':
                len(reconciled) == planned_queries and not conflicts and not unexpected,
            'batch_reports': reports, 'ordering_candidates': candidate_rows,
            'conflicting_ordering_identities': conflict_rows,
            'discovery_names_are_orderable_sku_population': False,
            'manufacturer_population_complete': False,
            'global_active_denominator': None,
            'production_write_authorized': False, 'live_queries_performed': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--batch-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    registry = json.loads(planner.REGISTRY.read_text(encoding='utf-8'))
    digest = registry['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    report = build(json.loads(args.plan.read_text(encoding='utf-8')),
                   archived_inventory(args.evidence_root), digest, args.batch_root)
    destination = args.output.resolve()
    require('production' not in {part.lower() for part in destination.parts},
            'Production output path forbidden')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n',
                           encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in
                      ('batch_reports','ordering_candidates','conflicting_ordering_identities')},
                     indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
