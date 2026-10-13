#!/usr/bin/env python3
"""Read-only, bounded Microchip MCP batch research; never produces Production ICPNs.

Each query is an independently replayable text-search observation. Even a fully
successful batch is NOT a complete or authoritative MCU/SKU population.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import microchip_mcp_probe_v1 as probe

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


def execute(output, parts, offline=False):
    """Return a bounded research summary, preserving failures separately."""
    output = Path(output)
    if not offline:
        output.mkdir(parents=True, exist_ok=False)
    else:
        require(output.is_dir(), 'missing archived batch folder')
    reports = []
    for part in parts:
        folder = output / part
        if offline and not (folder / 'manifest.json').exists():
            reports.append({'base_device_query': part, 'state': 'not_archived'})
            continue
        try:
            result = probe.replay(folder, part) if offline else probe.run(folder, part)
            require(result.get('query') == part and
                    result.get('population_boundary_validated') is False and
                    result.get('global_active_denominator') is None and
                    result.get('production_write_authorized') is False,
                    'unsafe result scope')
        except Exception as error:
            reports.append({'base_device_query': part, 'state': 'failed_or_unverified',
                            'error_type': type(error).__name__,
                            'error': str(error)[:240]})
        else:
            reports.append({'base_device_query': part, 'state': 'bounded_search_reconciled',
                            'observed_unique_ordering_candidates':
                            result['unique_ordering_count']})
    report = {
        'schema_version': 1,
        'manufacturer': 'Microchip',
        'scope': 'candidate PIC10/PIC12 DFP base-device text-search queries',
        'mode': 'offline_replay' if offline else 'live_read_only',
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
    parser.add_argument('--max-queries', type=int, default=MAX_SEEDS,
                        help='bounded prefix length for staged research, default all 27')
    args = parser.parse_args()
    require(1 <= args.max_queries <= MAX_SEEDS, 'query count out of range')
    result = execute(args.output_dir, load_seeds()[:args.max_queries],
                     offline=args.replay)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result['all_queries_reconciled']:
        sys.exit(1)


if __name__ == '__main__':
    main()
