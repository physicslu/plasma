#!/usr/bin/env python3
"""Optional live, source-checked Microchip cross-lane MCP v2 canary.

The exact 10-name list is pinned to original DFP index bytes. Validation
happens before creating output or contacting the manufacturer. Offline replay
accepts only a matching source-bound attestation and original archived bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import microchip_mcp_batch_v1 as batch
import microchip_mcp_probe_v1 as probe
from microchip_dfp_index_inventory_v1 import archived_inventory
from microchip_mcp_batch_plan_v1 import ACCESSORY_REVIEW_PACKS, REGISTRY

HERE = Path(__file__).resolve().parent
CANARY = HERE / 'microchip-mcp-crosslane-canary-v1.json'
SELECT_COUNTS = (3, 10)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def select(inventory, frozen, expected_digest, max_queries=3):
    require(type(max_queries) is int and max_queries in SELECT_COUNTS,
            'canary selection must be exactly 3 or 10 queries')
    require(isinstance(frozen, dict) and frozen.get('schema_version') == 1 and
            frozen.get('manufacturer') == 'Microchip' and
            frozen.get('source_index_sha256') == expected_digest and
            inventory.get('source_bytes_sha256') == expected_digest,
            'canary source digest or manufacturer mismatch')
    require(frozen.get('source_type') ==
            'original_microchip_dfp_index_supported_device_names' and
            frozen.get('canary_type') == 'cross_lanes_bounded_mcp_text_search' and
            frozen.get('approved_max_query_counts') == [3, 10] and
            frozen.get('query_count') == 10 and
            frozen.get('query_names_are_commercial_ordering_skus') is False and
            frozen.get('manufacturer_population_complete') is False and
            frozen.get('population_boundary_validated') is False and
            frozen.get('global_active_denominator') is None and
            frozen.get('production_write_authorized') is False and
            frozen.get('live_capture_performed') is False,
            'unsafe canary source or population claim')
    entries = frozen.get('ordered_queries')
    require(isinstance(entries, list) and len(entries) == 10,
            'canary must contain exactly 10 reviewed DFP names')
    packs = {pack['pack_name']: pack for pack in inventory['device_packs']}
    names = set()
    for entry in entries:
        require(isinstance(entry, dict) and
                set(entry) == {'device_name', 'pack_name', 'lane'},
                'invalid canary record')
        name, pack_name, lane = (entry['device_name'], entry['pack_name'],
                                  entry['lane'])
        require(isinstance(name, str) and bool(probe.BASE_QUERY.fullmatch(name))
                and name not in names, 'invalid/duplicate canary query name')
        names.add(name)
        pack = packs.get(pack_name)
        require(pack_name not in ACCESSORY_REVIEW_PACKS and
                isinstance(pack, dict) and pack['publisher'] == 'Microchip' and
                pack['discovery_lane'] == lane and
                lane in ('8bit', '16bit', '32bit-pic-sam', 'wireless') and
                name in pack['device_names'], 'unmatched or excluded DFP source identity')
    return [entry['device_name'] for entry in entries[:max_queries]]


def attestation(inventory, frozen, selected):
    raw = json.dumps(frozen, sort_keys=True, separators=(',', ':'))
    names = json.dumps(selected, sort_keys=True, separators=(',', ':'))
    return {'schema_version': 1, 'manufacturer': 'Microchip',
            'dfp_index_sha256': inventory['source_bytes_sha256'],
            'source_manifest_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'selected_query_list_sha256': hashlib.sha256(names.encode()).hexdigest(),
            'ordered_queries': list(selected), 'capture_format': 'paged_v2',
            'manufacturer_population_complete': False,
            'population_boundary_validated': False,
            'global_active_denominator': None, 'production_write_authorized': False}


def execute(inventory, frozen, expected_digest, target_root,
            max_queries=3, capture=False):
    selected = select(inventory, frozen, expected_digest, max_queries)
    target_root = Path(target_root).resolve()
    require('production' not in {p.lower() for p in target_root.parts},
            'Production output path forbidden')
    target = target_root / f'crosslane-{max_queries}'
    record = attestation(inventory, frozen, selected)
    attestation_path = target / 'crosslane-source.json'
    if capture:
        require(not target.exists(), 'existing output must never be overwritten')
        target_root.mkdir(parents=True, exist_ok=True)
    else:
        require(target.is_dir() and not target.is_symlink(),
                'missing archived crosslane evidence')
        existing = json.loads(attestation_path.read_text(encoding='utf-8'))
        require(existing == record, 'source-bound crosslane attestation mismatch')
    result = batch.execute(target, selected, offline=not capture,
                           workers=1, capture_format='paged_v2')
    if capture:
        attestation_path.write_text(json.dumps(record, sort_keys=True, indent=2)+'\n',
                                    encoding='utf-8')
    require(result['selected_device_names'] == len(selected) and
            result['population_boundary_validated'] is False and
            result['production_write_authorized'] is False and
            result['global_active_denominator'] is None,
            'unsafe batch result')
    return {'schema_version': 1, 'manufacturer': 'Microchip',
            'selected_queries': selected,
            'all_queries_reconciled': result['all_queries_reconciled'],
            'mode': 'explicit_live_capture' if capture else 'offline_replay',
            'original_dfp_index_sha256': expected_digest,
            'manufacturer_population_complete': False,
            'global_active_denominator': None,
            'production_write_authorized': False,
            'batch_summary': result}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root', type=Path, required=True)
    ap.add_argument('--target-root', type=Path, required=True)
    ap.add_argument('--max-queries', type=int, choices=SELECT_COUNTS, default=3)
    ap.add_argument('--capture', action='store_true', help='explicit live MCP canary')
    args = ap.parse_args()
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    digest = registry['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    inventory = archived_inventory(args.evidence_root)
    frozen = json.loads(CANARY.read_text(encoding='utf-8'))
    outcome = execute(inventory, frozen, digest, args.target_root,
                      args.max_queries, args.capture)
    print(json.dumps(outcome, indent=2, sort_keys=True))
    if not outcome['all_queries_reconciled']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
