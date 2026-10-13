#!/usr/bin/env python3
"""Offline, source-pinned Microchip DFP name batching. NEVER admits Production ICPNs.

This creates an execution *plan*, not a network capture or manufacturer SKU census.
The input must be reconstructed from archived original DFP index bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from microchip_dfp_index_inventory_v1 import LANES, archived_inventory
from microchip_mcp_probe_v1 import BASE_QUERY

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / 'microchip-bulk-source-registry-v1.json'
EXCLUDED = ('excluded_mpu_candidate', 'unclassified_or_non_mcu_pack')
BATCH_SIZES = (3, 10)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def plan_inventory(inventory, pinned_digest, batch_size=10):
    require(type(batch_size) is int and batch_size in BATCH_SIZES,
            'batch size must be explicitly bounded to 3 or 10')
    require(isinstance(inventory, dict) and inventory.get('manufacturer') == 'Microchip',
            'unexpected manufacturer inventory')
    require(inventory.get('source_url') == 'https://packs.download.microchip.com/',
            'unexpected source URL')
    digest = inventory.get('source_bytes_sha256')
    require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) and
            digest == pinned_digest, 'inventory source digest not pinned')
    require(inventory.get('population_boundary_validated') is False and
            inventory.get('production_write_authorized') is False and
            inventory.get('global_active_denominator') is None and
            inventory.get('device_support_list_is_complete_commercial_sku_inventory') is False,
            'unsafe manufacturer scope claim')

    packs = inventory.get('device_packs')
    require(isinstance(packs, list) and
            len(packs) == inventory.get('manufacturer_device_pack_count'),
            'manufacturer pack count mismatch')
    lanes = {lane: [] for lane in (*LANES, *EXCLUDED)}
    seen_names, seen_packs = set(), set()
    for pack in packs:
        require(isinstance(pack, dict) and pack.get('publisher') == 'Microchip',
                'non-Microchip pack')
        name, lane, names = (pack.get('pack_name'), pack.get('discovery_lane'),
                             pack.get('device_names'))
        require(isinstance(name, str) and name and name not in seen_packs,
                'invalid or duplicate pack name')
        seen_packs.add(name)
        require(lane in lanes and isinstance(names, list) and
                len(names) == pack.get('supported_name_count'), 'invalid pack support list')
        for device in names:
            require(isinstance(device, str) and device and
                    device == device.strip() and device not in seen_names,
                    'invalid or repeated device support name')
            seen_names.add(device)
            lanes[lane].append((device, name))
    require(len(seen_names) == inventory.get('observed_manufacturer_device_support_names'),
            'inventory support-name total mismatch')
    observed_lanes = inventory.get('lanes')
    require(isinstance(observed_lanes, dict) and set(observed_lanes) == set(lanes),
            'missing or unexpected discovery lane')
    for lane, entries in lanes.items():
        declared = observed_lanes[lane]
        require(isinstance(declared, dict) and
                declared.get('candidate_device_name_count') == len(entries) and
                declared.get('pack_count') ==
                sum(pack['discovery_lane'] == lane for pack in packs),
                'declared lane total differs from source packs')

    batches, manual = [], []
    per_lane = {}
    for lane in LANES:
        entries = sorted(lanes[lane])
        safe = sorted(device for device, _ in entries if BASE_QUERY.fullmatch(device))
        unsupported = [(device, pack) for device, pack in entries
                       if not BASE_QUERY.fullmatch(device)]
        manual.extend({'lane': lane, 'device_name': device, 'pack_name': pack,
                       'reason': 'unsupported_exact_query_syntax'}
                      for device, pack in unsupported)
        per_lane[lane] = {'dfp_device_names': len(entries),
                          'safe_text_search_seeds': len(safe),
                          'requires_manual_query_mapping': len(unsupported)}
        for start in range(0, len(safe), batch_size):
            query_names = safe[start:start + batch_size]
            serial = json.dumps(query_names, separators=(',', ':'), ensure_ascii=True)
            batches.append({'batch_id': f'{lane}-{start // batch_size + 1:04d}',
                            'lane': lane, 'queries': query_names,
                            'query_list_sha256': hashlib.sha256(serial.encode()).hexdigest(),
                            'state': 'plan_only_no_vendor_queries_executed'})

    excluded_count = sum(len(lanes[lane]) for lane in EXCLUDED)
    return {
        'schema_version': 1,
        'manufacturer': 'Microchip',
        'input_type': 'source_pinned_archived_dfp_support_names',
        'original_dfp_index_sha256': digest,
        'dfp_device_support_names': len(seen_names),
        'mapped_discovery_lane_names': sum(len(lanes[lane]) for lane in LANES),
        'excluded_or_unclassified_support_names': excluded_count,
        'supported_text_search_seeds': sum(x['safe_text_search_seeds']
                                           for x in per_lane.values()),
        'needs_manual_query_mapping': manual,
        'batch_size': batch_size, 'batch_count': len(batches),
        'lanes': per_lane, 'batches': batches,
        'source_names_are_orderable_icpns': False,
        'no_live_capture_performed': True,
        'manufacturer_population_complete': False,
        'population_boundary_validated': False,
        'global_active_denominator': None,
        'production_write_authorized': False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True,
                    help='directory containing original index.html and manifest.json')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--batch-size', type=int, choices=BATCH_SIZES, default=10)
    args = ap.parse_args()
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    pinned = registry['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    plan = plan_inventory(archived_inventory(args.evidence_root), pinned, args.batch_size)
    output = args.output.resolve()
    require('production' not in (segment.lower() for segment in output.parts),
            'Production output path forbidden')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in plan.items()
                      if key not in ('batches', 'needs_manual_query_mapping')}, indent=2))


if __name__ == '__main__':
    main()
