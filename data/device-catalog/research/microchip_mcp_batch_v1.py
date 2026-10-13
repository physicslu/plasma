#!/usr/bin/env python3
"""Read-only, bounded Microchip MCP batch research; never produces Production ICPNs.

Each query is an independently replayable text-search observation. Even a fully
successful batch is NOT a complete or authoritative MCU/SKU population.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import microchip_mcp_probe_v1 as probe
import microchip_mcp_paged_probe_v2 as paged

HERE = Path(__file__).resolve().parent
SEEDS = HERE / 'microchip-pic10-pic12-mcp-batch-seeds-v1.json'
MAX_SEEDS = 27


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load_seeds(path=SEEDS):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    require(isinstance(data, dict) and data.get('schema_version') == 1,
            'unsupported seed schema')
    require(data.get('manufacturer') == 'Microchip' and
            data.get('source_pack') == 'PIC10-12Fxxx_DFP', 'wrong seed source')
    require(data.get('population_boundary_validated') is False and
            data.get('production_write_authorized') is False and
            data.get('global_active_denominator') is None, 'unsafe scope claim')
    require(data.get('evidence_status') ==
            'observed_support_list_not_archived_pack_bytes', 'unreviewed seed evidence')
    parts = data.get('device_names')
    require(isinstance(parts, list) and len(parts) == MAX_SEEDS and
            data.get('observed_device_count') == len(parts), 'unexpected seed count')
    require(len(set(parts)) == len(parts), 'duplicate seed query')
    for part in parts:
        require(isinstance(part, str) and part.startswith(('PIC10', 'PIC12')) and
                bool(probe.BASE_QUERY.fullmatch(part)), 'invalid candidate query')
    return parts


def execute(output, parts, offline=False, workers=1, capture_format='v1',
            source_attestation=None):
    """Run independent read-only queries with bounded optional concurrency."""
    require(type(workers) is int and 1 <= workers <= 2, 'worker count out of range')
    require(capture_format in ('v1', 'paged_v2'), 'unsupported live capture format')
    require(isinstance(parts, list) and 1 <= len(parts) <= MAX_SEEDS and
            len(set(parts)) == len(parts) and
            all(isinstance(part, str) and probe.BASE_QUERY.fullmatch(part)
                for part in parts), 'invalid selected query set')
    output = Path(output)
    require(source_attestation is None or
            (not offline and isinstance(source_attestation, dict) and
             source_attestation.get('production_write_authorized') is False and
             source_attestation.get('global_active_denominator') is None and
             source_attestation.get('ordered_queries') == parts),
            'unsafe or mismatched pre-capture attestation')
    if not offline:
        output.mkdir(parents=True, exist_ok=False)
        if source_attestation is not None:
            # Source evidence must exist BEFORE the first vendor call; hard
            # timeout kills an entire worker process without running finally.
            with (output / 'batch-source.json').open('x', encoding='utf-8') as f:
                f.write(json.dumps(source_attestation, indent=2, sort_keys=True)+'\n')
                f.flush()
                os.fsync(f.fileno())
    else:
        require(output.is_dir(), 'missing archived batch folder')

    def capture(part):
        folder = output / part
        if offline and not (folder / 'manifest.json').exists():
            return {'base_device_query': part, 'state': 'not_archived'}
        try:
            if offline:
                manifest = json.loads((folder / 'manifest.json').read_text())
                version = manifest.get('schema_version', 1)
                require(type(version) is int and version in (1, 2),
                        'unknown archived capture schema')
                result = (probe if version == 1 else paged).replay(folder, part)
            else:
                result = (probe if capture_format == 'v1' else paged).run(folder, part)
            require(result.get('query') == part and
                    result.get('population_boundary_validated') is False and
                    result.get('global_active_denominator') is None and
                    result.get('production_write_authorized') is False,
                    'unsafe result scope')
        except Exception as error:
            return {'base_device_query': part, 'state': 'failed_or_unverified',
                    'error_type': type(error).__name__, 'error': str(error)[:240]}
        target_count = result['exact_prefix_ordering_count']
        if target_count == 0:
            return {'base_device_query': part,
                    'state': 'no_exact_ordering_prefix_found',
                    'raw_fuzzy_results': result['unique_ordering_count']}
        return {'base_device_query': part, 'state': 'bounded_search_reconciled',
                'observed_unique_ordering_candidates': target_count,
                'raw_fuzzy_results': result['unique_ordering_count'],
                'foreign_result_count': result['fuzzy_foreign_ordering_count'],
                'vendor_base_alias_count': result['vendor_base_part_alias_count']}

    if workers == 1:
        reports = [capture(part) for part in parts]
    else:
        # Each call owns its MCP session and output directory; map preserves
        # seed order. More than two concurrent sessions is deliberately barred.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            reports = list(pool.map(capture, parts))
    report = {
        'schema_version': 1,
        'manufacturer': 'Microchip',
        'scope': 'candidate PIC10/PIC12 DFP base-device text-search queries',
        'mode': 'offline_replay' if offline else 'live_read_only',
        'capture_format': 'archive_auto_detect' if offline else capture_format,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'selected_device_names': len(parts),
        'bounded_reconciled_queries': sum(
            r['state'] == 'bounded_search_reconciled' for r in reports),
        'all_queries_reconciled': all(
            r['state'] == 'bounded_search_reconciled' for r in reports),
        'search_results_are_exhaustive_sku_population': False,
        'population_boundary_validated': False,
        'global_active_denominator': None,
        'production_write_authorized': False,
        'results': reports,
    }
    (output / 'batch-summary.json').write_text(
        json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--replay', action='store_true',
                        help='verify archived per-query bytes without network')
    parser.add_argument('--capture-format', choices=('v1', 'paged_v2'),
                        default='v1', help='v2 verifies full 20- and 60-row walks')
    parser.add_argument('--workers', type=int, default=1,
                        help='independent concurrent MCP sessions, 1 or 2')
    parser.add_argument('--max-queries', type=int, default=MAX_SEEDS,
                        help='bounded prefix length for staged research, default all 27')
    args = parser.parse_args()
    require(1 <= args.max_queries <= MAX_SEEDS, 'query count out of range')
    result = execute(args.output_dir, load_seeds()[:args.max_queries],
                     offline=args.replay, workers=args.workers,
                     capture_format=args.capture_format)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result['all_queries_reconciled']:
        sys.exit(1)


if __name__ == '__main__':
    main()
