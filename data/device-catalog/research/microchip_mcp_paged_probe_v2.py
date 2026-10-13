#!/usr/bin/env python3
"""Source-hashed, bounded double-pagination Microchip MCP research capture v2.

Both page-size 20 and page-size 60 walks MUST cover the same exact ordering
identity set and raw lifecycle values. Search results are not a SKU census.
Old page-size 2/60 v1 evidence remains independently replayable by v1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import microchip_mcp_probe_v1 as v1

PRIMARY_LIMIT = 20
COMPARISON_LIMIT = 60
MAX_TOTAL = 600
SCHEMA_VERSION = 2
POLICY = {'primary_limit': PRIMARY_LIMIT, 'comparison_limit': COMPARISON_LIMIT,
          'max_total': MAX_TOTAL}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate_page(data, offset, limit, total=None, query=v1.QUERY):
    require(isinstance(data, dict) and data.get('searchTerm') == query,
            'query mismatch')
    pagination = data.get('pagination')
    require(isinstance(pagination, dict), 'invalid pagination')
    count = pagination.get('total')
    require(type(count) is int and 0 < count <= MAX_TOTAL,
            'search total outside bounded capture policy')
    require(total is None or total == count, 'pagination total changed')
    require(type(pagination.get('offset')) is int and pagination['offset'] == offset,
            'offset mismatch')
    require(type(pagination.get('limit')) is int and pagination['limit'] == limit,
            'limit mismatch')
    require(type(pagination.get('hasMore')) is bool, 'invalid hasMore flag')
    rows = data.get('products')
    require(isinstance(rows, list) and len(rows) == min(limit, count - offset),
            'page length mismatch')
    require(pagination['hasMore'] is (offset + len(rows) < count),
            'hasMore mismatch')
    for row in rows:
        require(isinstance(row, dict), 'invalid product row')
        for field in ('partNumber', 'lifecycleStatus'):
            require(isinstance(row.get(field), str) and row[field] and
                    row[field] == row[field].strip(),
                    'missing or padded exact identity/lifecycle')
        base = row.get('basePartNumber')
        if v1.exact_ordering_prefix(row['partNumber'], query):
            require(isinstance(base, str) and base and base == base.strip(),
                    'exact target ordering missing valid basePartNumber')
        else:
            # MCP fuzzy returns can include unrelated tools/boards with no
            # basePartNumber. Keep them as diagnostic rows in BOTH walks;
            # they are never admitted as MCU ordering candidates.
            require(base is None or isinstance(base, str) and
                    base == base.strip(),
                    'invalid foreign fuzzy result basePartNumber')
    return count, rows


def reconcile(primary, comparison, query=v1.QUERY):
    require(isinstance(primary, list) and isinstance(comparison, list) and
            primary and comparison, 'missing pagination streams')

    def walk(pages, limit):
        result, count = [], None
        for page in pages:
            count, rows = validate_page(page, len(result), limit, count, query)
            result.extend(rows)
        require(count is not None and len(result) == count,
                'incomplete pagination stream')
        ids = [r['partNumber'] for r in result]
        require(len(set(ids)) == len(ids),
                'duplicate exact ordering identity in pagination stream')
        return result, count

    left, left_total = walk(primary, PRIMARY_LIMIT)
    right, right_total = walk(comparison, COMPARISON_LIMIT)
    require(left_total == right_total, 'total differs by page size')
    def identities(rows):
        return {r['partNumber']: (r.get('basePartNumber'), r['lifecycleStatus'])
                for r in rows}
    require(identities(left) == identities(right),
            'pagination identity or lifecycle reconciliation mismatch')
    targets = [r for r in left if v1.exact_ordering_prefix(r['partNumber'], query)]
    foreign = [r for r in left if not v1.exact_ordering_prefix(r['partNumber'], query)]
    aliases = [r for r in targets if r['basePartNumber'] != query]
    return {
        'query': query, 'reported_total': left_total,
        'unique_ordering_count': len(left),
        'exact_prefix_ordering_count': len(targets),
        'fuzzy_foreign_ordering_count': len(foreign),
        'vendor_base_part_alias_count': len(aliases),
        'foreign_fuzzy_missing_base_count': sum(
            not r.get('basePartNumber') for r in foreign),
        'foreign_ordering_parts': sorted(r['partNumber'] for r in foreign),
        'exact_query_ordering_parts': sorted(r['partNumber'] for r in targets),
        'primary_page_size': PRIMARY_LIMIT, 'primary_page_count': len(primary),
        'comparison_page_size': COMPARISON_LIMIT,
        'comparison_page_count': len(comparison),
        'independent_page_size_identity_and_lifecycle_match': True,
        'raw_lifecycle_values': sorted({r['lifecycleStatus'] for r in left}),
        'ordering_parts': sorted(r['partNumber'] for r in left),
        'population_boundary_validated': False,
        'global_active_denominator': None,
        'production_write_authorized': False
    }


def replay(output, query=v1.QUERY):
    require(isinstance(query, str) and bool(v1.BASE_QUERY.fullmatch(query)),
            'unsafe exact base-device query')
    folder = Path(output)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    require(isinstance(manifest, dict) and manifest.get('schema_version') == SCHEMA_VERSION,
            'wrong archived capture schema')
    require(manifest.get('endpoint') == v1.ENDPOINT and
            manifest.get('query') == query and
            manifest.get('capture_policy') == POLICY, 'source/query/policy mismatch')
    events = manifest.get('responses')
    require(isinstance(events, list) and
            5 <= len(events) <= 3 + (MAX_TOTAL + PRIMARY_LIMIT - 1)//PRIMARY_LIMIT +
            (MAX_TOTAL + COMPARISON_LIMIT - 1)//COMPARISON_LIMIT,
            'invalid archived response count')

    primary, comparison = [], []
    phase, offset, total = 'primary', 0, None
    for i, event in enumerate(events):
        require(isinstance(event, dict), 'invalid source evidence record')
        filename = f'response-{i:02d}.txt'
        require(event.get('file') == filename, 'wrong response filename/order')
        expected_method = ('initialize', 'notifications/initialized', 'tools/list')
        method = expected_method[i] if i < 3 else 'tools/call'
        request = event.get('request')
        require(isinstance(request, dict) and request.get('jsonrpc') == '2.0' and
                request.get('method') == method, 'MCP request method/order mismatch')
        expected_id = None if i == 1 else (1 if i == 0 else i)
        require(request.get('id') == expected_id and
                (('id' in request) == (expected_id is not None)),
                'MCP request ID mismatch')
        require(event.get('http_status') == (202 if i == 1 else 200),
                'archived HTTP status mismatch')
        digest = event.get('sha256')
        require(isinstance(digest, str) and len(digest) == 64,
                'missing response SHA-256')
        raw = (folder / filename).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest,
                'archived response byte digest mismatch')
        if i == 0:
            require(request.get('params') == {
                'protocolVersion': '2025-03-26', 'capabilities': {},
                'clientInfo': {'name': 'plasma-microchip-research', 'version': '1.0'}},
                'unexpected initialize parameters')
            require(v1.decode(raw, 1).get('protocolVersion') == '2025-03-26',
                    'MCP protocol mismatch')
        elif i == 1:
            require('params' not in request, 'unexpected initialized parameters')
        elif i == 2:
            require(request.get('params') == {}, 'unexpected tool-list request')
            catalog = v1.decode(raw, 2)
            require(not catalog.get('nextCursor'), 'incomplete tool list')
            tools = catalog.get('tools')
            require(isinstance(tools, list), 'missing tool list')
            matches = [t for t in tools if isinstance(t, dict) and
                       t.get('name') == 'search_products']
            require(len(matches) == 1 and
                    isinstance(matches[0].get('inputSchema'), dict) and
                    {'searchTerm', 'limit', 'offset'} <= set(
                        matches[0]['inputSchema'].get('properties', {})),
                    'missing or changed search-products tool schema')
        else:
            if phase == 'primary' and total is not None and offset == total:
                phase, offset = 'comparison', 0
            elif phase == 'comparison' and offset == total:
                raise ValueError('unexpected trailing product call')
            limit = PRIMARY_LIMIT if phase == 'primary' else COMPARISON_LIMIT
            expected = {'name': 'search_products', 'arguments': {
                'searchTerm': query, 'limit': limit, 'offset': offset}}
            require(request.get('params') == expected,
                    'product request page size/order/offset mismatch')
            data = v1.product_data(v1.decode(raw, expected_id))
            total, rows = validate_page(data, offset, limit, total, query)
            (primary if phase == 'primary' else comparison).append(data)
            offset += len(rows)
    require(phase == 'comparison' and total is not None and offset == total,
            'incomplete independent pagination capture')
    return reconcile(primary, comparison, query)


def run(output, query=v1.QUERY):
    require(isinstance(query, str) and bool(v1.BASE_QUERY.fullmatch(query)),
            'query must be an exact alphanumeric base-device identifier')
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=False)
    client = v1.Client(folder)
    try:
        init = client.call('initialize', {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'plasma-microchip-research', 'version': '1.0'}}, 1)
        require(init.get('protocolVersion') == '2025-03-26', 'protocol mismatch')
        client.headers['MCP-Protocol-Version'] = init['protocolVersion']
        client.call('notifications/initialized')
        catalog = client.call('tools/list', {}, 2)
        require(not catalog.get('nextCursor'), 'tool listing incomplete')
        tools = [x for x in catalog.get('tools', []) if
                 isinstance(x, dict) and x.get('name') == 'search_products']
        require(len(tools) == 1 and
                {'searchTerm', 'limit', 'offset'} <=
                set(tools[0].get('inputSchema', {}).get('properties', {})),
                'search tool unavailable/changed')
        request_id, total = 3, None
        for limit in (PRIMARY_LIMIT, COMPARISON_LIMIT):
            offset = 0
            while total is None or offset < total:
                result = client.call('tools/call', {'name': 'search_products',
                    'arguments': {'searchTerm': query, 'limit': limit,
                                  'offset': offset}}, request_id)
                total, rows = validate_page(v1.product_data(result), offset,
                                            limit, total, query)
                offset += len(rows)
                request_id += 1
    finally:
        (folder / 'manifest.json').write_text(json.dumps({
            'schema_version': SCHEMA_VERSION, 'endpoint': v1.ENDPOINT,
            'query': query, 'capture_policy': POLICY,
            'responses': client.evidence}, indent=2) + '\n', encoding='utf-8')
    summary = replay(folder, query)
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n',
                                        encoding='utf-8')
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir', required=True, type=Path)
    ap.add_argument('--query', default=v1.QUERY)
    ap.add_argument('--replay', action='store_true')
    args = ap.parse_args()
    print(json.dumps(replay(args.output_dir, args.query) if args.replay
                     else run(args.output_dir, args.query), indent=2))


if __name__ == '__main__':
    main()
