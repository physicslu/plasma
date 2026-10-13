#!/usr/bin/env python3
"""Build a read-only exact-prefix Microchip research ledger from archived MCP bytes.

This is not a Production catalog or evidence of exhaustive manufacturer coverage.
Every emitted SKU is backed by a successfully replayed complete bounded query,
and its original raw response SHA-256 is retained.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import microchip_mcp_probe_v1 as probe
import microchip_mcp_paged_probe_v2 as paged
from microchip_mcp_batch_v1 import load_seeds


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def build(root: Path, parts: list[str]) -> dict:
    root = Path(root)
    require(root.is_dir(), 'missing raw evidence root')
    require(isinstance(parts, list) and 1 <= len(parts) <= 27 and
            len(set(parts)) == len(parts), 'invalid candidate query set')
    observations: dict[str, dict] = {}
    query_reports: list[dict] = []
    for part in parts:
        require(isinstance(part, str) and probe.BASE_QUERY.fullmatch(part),
                'invalid device query')
        folder = root / part
        try:
            manifest = json.loads((folder / 'manifest.json').read_text())
            version = manifest.get('schema_version', 1)
            require(type(version) is int and version in (1, 2),
                    'unknown archived capture schema')
            check = (probe if version == 1 else paged).replay(folder, part)
            primary_limit = 2 if version == 1 else paged.PRIMARY_LIMIT
            local_observations = []
            for event in manifest['responses']:
                req = event['request']
                if req.get('method') != 'tools/call':
                    continue
                args = req['params']['arguments']
                if args['limit'] != primary_limit:
                    continue
                raw = (folder / event['file']).read_bytes()
                data = probe.product_data(probe.decode(raw, req['id']))
                validator = probe.validate_page if version == 1 else paged.validate_page
                _, rows = validator(data, args['offset'], args['limit'], query=part)
                for row in rows:
                    part_number = row['partNumber']
                    if not probe.exact_ordering_prefix(part_number, part):
                        continue
                    local_observations.append({
                        'icpn': part_number,
                        'query': part,
                        'basePartNumber': row['basePartNumber'],
                        'rawLifecycleStatus': row['lifecycleStatus'],
                        'productUrl': row.get('productUrl'),
                        'evidence_file': f"{part}/{event['file']}",
                        'response_sha256': event['sha256'],
                        'retrieved_at_utc': event.get('retrieved_at_utc'),
                    })
            require(len(local_observations) == check['exact_prefix_ordering_count'],
                    'target evidence row count mismatch')
            require({r['icpn'] for r in local_observations} ==
                    set(check['exact_query_ordering_parts']),
                    'exact orderables mismatch replay summary')
            require(len(local_observations) > 0, 'no exact orderable evidence')
            # Check every cross-query conflict before mutating the ledger:
            # a rejected query must never leak partially accepted SKU rows.
            for row in local_observations:
                previous = observations.get(row['icpn'])
                if previous is not None:
                    require(previous['rawLifecycleStatus'] == row['rawLifecycleStatus'],
                            'cross-query raw lifecycle conflict')
            for row in local_observations:
                key = row['icpn']
                previous = observations.get(key)
                if previous is not None:
                    previous['sources'].append(row)
                else:
                    observations[key] = {
                        'icpn': key,
                        'rawLifecycleStatus': row['rawLifecycleStatus'],
                        'sources': [row],
                    }
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            query_reports.append({'query': part, 'state': 'unverified',
                                  'error_type': type(exc).__name__,
                                  'error': str(exc)[:240]})
        else:
            query_reports.append({'query': part, 'state': 'fully_replayed_bounded_query',
                                  'raw_result_count': check['unique_ordering_count'],
                                  'exact_ordering_count': len(local_observations),
                                  'fuzzy_foreign_count': check['fuzzy_foreign_ordering_count'],
                                  'vendor_base_alias_count': check['vendor_base_part_alias_count']})

    ordered = [observations[k] for k in sorted(observations)]
    reconciled_count = sum(r['state'] == 'fully_replayed_bounded_query'
                           for r in query_reports)
    return {
        'schema_version': 1,
        'type': 'microchip-mcp-bounded-search-research-ledger',
        'source_endpoint': probe.ENDPOINT,
        'source_scope': '27 PIC10/PIC12 DFP discovery candidates only',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'selected_queries': len(parts),
        'fully_replayed_queries': reconciled_count,
        'all_queries_reconciled': reconciled_count == len(parts),
        'unique_exact_ordering_candidates': len(ordered),
        'raw_lifecycle_values': sorted({r['rawLifecycleStatus'] for r in ordered}),
        'manufacturer_population_complete': False,
        'global_active_denominator': None,
        'production_write_authorized': False,
        'programming_support_claimed': False,
        'queries': query_reports,
        'ordering_candidates': ordered,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--max-queries', type=int, default=27)
    args = ap.parse_args()
    require(1 <= args.max_queries <= 27, 'query count out of range')
    report = build(args.evidence_root, load_seeds()[:args.max_queries])
    # Explicitly separate research artifacts from Production catalog paths.
    output = args.output.resolve()
    require('production' not in output.parts, 'Production output forbidden')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ('ordering_candidates', 'queries')}, indent=2))
    if not report['all_queries_reconciled']:
        sys.exit(1)


if __name__ == '__main__':
    main()
