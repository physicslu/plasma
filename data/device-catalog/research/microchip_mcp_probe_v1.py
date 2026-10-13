#!/usr/bin/env python3
"""Bounded, read-only official MCP probe; never writes the Production catalog."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

ENDPOINT = 'https://api.microchip.com/mcp/resources'
QUERY = 'PIC10F202'
MAX_ROWS = 60
BASE_QUERY = re.compile(r'[A-Za-z][A-Za-z0-9]{4,39}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode(raw, request_id):
    text = raw.decode('utf-8-sig').replace('\r\n', '\n')
    if text.lstrip().startswith('{'):
        messages = [json.loads(text)]
    else:
        messages = [json.loads('\n'.join(line[5:].lstrip(' ') for line in event.splitlines()
                                        if line.startswith('data:')))
                    for event in text.split('\n\n') if any(
                        line.startswith('data:') for line in event.splitlines())]
    matches = [m for m in messages if isinstance(m, dict) and m.get('id') == request_id]
    require(len(matches) == 1, 'missing or ambiguous JSON-RPC response')
    message = matches[0]
    require(message.get('jsonrpc') == '2.0' and 'error' not in message,
            'invalid or failed JSON-RPC response')
    require(isinstance(message.get('result'), dict), 'missing result object')
    return message['result']


def product_data(result):
    require(not result.get('isError'), 'MCP tool returned isError')
    blocks = result.get('content', [])
    require(isinstance(blocks, list), 'invalid content blocks')
    texts = [x['text'] for x in blocks if x.get('type') == 'text']
    require(len(texts) == 1, 'expected one product JSON text block')
    payload = json.loads(texts[0])
    require(payload.get('success') is True, 'product query failed')
    require(isinstance(payload.get('data'), dict), 'missing product data')
    return payload['data']


def validate_page(data, offset, limit, total=None, query=QUERY):
    require(data.get('searchTerm') == query, 'query mismatch')
    pagination = data.get('pagination', {})
    count = pagination.get('total')
    require(type(count) is int and 0 < count <= MAX_ROWS, 'total outside bounded probe')
    require(total is None or total == count, 'pagination total changed')
    require(type(pagination.get('offset')) is int and pagination['offset'] == offset,
            'offset mismatch')
    require(type(pagination.get('limit')) is int and pagination['limit'] == limit,
            'limit mismatch')
    rows = data.get('products')
    require(isinstance(rows, list) and len(rows) == min(limit, count-offset),
            'page length mismatch')
    require(pagination.get('hasMore') is (offset + len(rows) < count), 'hasMore mismatch')
    for row in rows:
        require(isinstance(row, dict), 'invalid product row')
        for field in ('partNumber', 'basePartNumber', 'lifecycleStatus'):
            require(isinstance(row.get(field), str) and bool(row[field].strip()),
                    'missing identity/lifecycle')
        require(row['partNumber'] == row['partNumber'].strip(), 'padded identity')
        require(row['basePartNumber'] == query, 'fuzzy search returned another base part')
    return count, rows


def reconcile(pages, comparison, query=QUERY):
    rows = []
    total = None
    for index, page in enumerate(pages):
        total, batch = validate_page(page, index*2, 2, total, query)
        rows.extend(batch)
    require(total is not None and len(rows) == total, 'incomplete paginated capture')
    ids = [row['partNumber'] for row in rows]
    require(len(set(ids)) == total, 'duplicate ordering identities')
    _, other = validate_page(comparison, 0, MAX_ROWS, total, query)
    other_ids = [row['partNumber'] for row in other]
    require(len(set(other_ids)) == total and set(ids) == set(other_ids),
            'page-size comparison identity mismatch')
    key = lambda r: (r['basePartNumber'], r['lifecycleStatus'])
    require({r['partNumber']: key(r) for r in rows} ==
            {r['partNumber']: key(r) for r in other}, 'lifecycle changed during capture')
    return {'query': query, 'reported_total': total, 'unique_ordering_count': len(set(ids)),
            'page_size_2_count': len(pages), 'page_size_60_same_identity_and_lifecycle': True,
            'raw_lifecycle_values': sorted({r['lifecycleStatus'] for r in rows}),
            'ordering_parts': sorted(ids), 'population_boundary_validated': False,
            'global_active_denominator': None, 'production_write_authorized': False}


class Client:
    def __init__(self, output):
        self.output = output
        self.headers = {'Content-Type': 'application/json',
                        'Accept': 'application/json, text/event-stream'}
        self.evidence = []

    def call(self, method, params=None, request_id=None):
        payload = {'jsonrpc': '2.0', 'method': method}
        if request_id is not None:
            payload['id'] = request_id
        if params is not None:
            payload['params'] = params
        request = Request(ENDPOINT, data=json.dumps(payload).encode(),
                          headers=self.headers, method='POST')
        with urlopen(request, timeout=45) as response:
            raw = response.read(4*1024*1024+1)
            require(len(raw) <= 4*1024*1024, 'response exceeds capture bound')
            filename = f'response-{len(self.evidence):02d}.txt'
            (self.output / filename).write_bytes(raw)
            self.evidence.append({'file': filename, 'request': payload,
                                  'http_status': response.status,
                                  'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                                  'sha256': hashlib.sha256(raw).hexdigest()})
            session = response.headers.get('Mcp-Session-Id')
            if session:
                self.headers['Mcp-Session-Id'] = session
            require(response.status == (202 if request_id is None else 200),
                    'unexpected HTTP status')
        return decode(raw, request_id) if request_id is not None else None


def verify_transcript(manifest, output, query=QUERY):
    """Validate the archived MCP handshake and exact bounded request sequence."""
    responses = manifest.get('responses')
    require(isinstance(responses, list) and 5 <= len(responses) <= 4 + MAX_ROWS // 2,
            'invalid MCP capture length')
    require(isinstance(manifest.get('endpoint'), str) and
            manifest['endpoint'] == ENDPOINT, 'unexpected evidence source')
    for index, evidence in enumerate(responses):
        require(isinstance(evidence, dict), 'invalid evidence record')
        filename = evidence.get('file')
        require(isinstance(filename, str) and
                filename == f'response-{index:02d}.txt', 'unexpected evidence filename/order')
        request = evidence.get('request')
        require(isinstance(request, dict) and request.get('jsonrpc') == '2.0',
                'invalid request envelope')
        method = request.get('method')
        expected = ('initialize', 'notifications/initialized', 'tools/list')
        expected_method = expected[index] if index < 3 else 'tools/call'
        require(method == expected_method, 'unexpected MCP method/order')
        expected_id = None if index == 1 else (1 if index == 0 else index)
        require(request.get('id') == expected_id and
                (('id' in request) == (expected_id is not None)), 'request ID mismatch')
        require(evidence.get('http_status') == (202 if index == 1 else 200),
                'unexpected archived HTTP status')
        require(isinstance(evidence.get('sha256'), str) and
                len(evidence['sha256']) == 64, 'missing evidence digest')
        raw = (output / filename).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == evidence['sha256'],
                'evidence digest mismatch')
        if index == 0:
            require(request.get('params') == {
                'protocolVersion': '2025-03-26', 'capabilities': {},
                'clientInfo': {'name': 'plasma-microchip-research', 'version': '1.0'}},
                'unexpected MCP initialization request')
            require(decode(raw, 1).get('protocolVersion') == '2025-03-26',
                    'archived MCP protocol mismatch')
        elif index == 1:
            require('params' not in request, 'unexpected initialized parameters')
        elif index == 2:
            require(request.get('params') == {}, 'unexpected tool-list parameters')
            catalog = decode(raw, 2)
            require(not catalog.get('nextCursor'), 'tool listing incomplete')
            tools = catalog.get('tools')
            require(isinstance(tools, list), 'missing archived tool list')
            matching = [t for t in tools if isinstance(t, dict) and
                        t.get('name') == 'search_products']
            require(len(matching) == 1, 'search_products tool absent or duplicated')
            schema = matching[0].get('inputSchema', {})
            require(isinstance(schema, dict) and isinstance(schema.get('properties'), dict)
                    and {'searchTerm', 'limit', 'offset'} <= set(schema['properties']),
                    'archived product search schema changed')
        else:
            expected_args = {'searchTerm': query,
                             'limit': MAX_ROWS if index == len(responses) - 1 else 2,
                             'offset': 0 if index == len(responses) - 1 else (index - 3) * 2}
            require(request.get('params') == {'name': 'search_products',
                                               'arguments': expected_args},
                    'unexpected product search request')


def replay(output, query=QUERY):
    manifest = json.loads((output / 'manifest.json').read_text())
    require(manifest.get('query', QUERY) == query, 'archived query mismatch')
    verify_transcript(manifest, output, query)
    pages, comparison = [], None
    for evidence in manifest['responses']:
        filename = evidence['file']
        require(Path(filename).name == filename, 'invalid evidence filename')
        raw = (output / filename).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == evidence['sha256'], 'evidence digest mismatch')
        request = evidence['request']
        if request['method'] == 'tools/call':
            require(request['params']['name'] == 'search_products', 'unexpected tool')
            args = request['params']['arguments']
            require(args['searchTerm'] == query, 'unexpected query')
            data = product_data(decode(raw, request['id']))
            validate_page(data, args['offset'], args['limit'], query=query)
            if args['limit'] == MAX_ROWS:
                require(comparison is None, 'duplicate comparison')
                comparison = data
            else:
                require(args['limit'] == 2 and args['offset'] == len(pages)*2,
                        'unexpected page order')
                pages.append(data)
    require(comparison is not None, 'missing comparison capture')
    return reconcile(pages, comparison, query)


def run(output, query=QUERY):
    require(isinstance(query, str) and bool(BASE_QUERY.fullmatch(query)),
            'query must be an exact alphanumeric base-device identifier')
    output.mkdir(parents=True, exist_ok=False)
    client = Client(output)
    try:
        init = client.call('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                           'clientInfo': {'name': 'plasma-microchip-research', 'version': '1.0'}}, 1)
        require(init.get('protocolVersion') == '2025-03-26', 'protocol mismatch')
        client.headers['MCP-Protocol-Version'] = init['protocolVersion']
        client.call('notifications/initialized')
        catalog = client.call('tools/list', {}, 2)
        require(not catalog.get('nextCursor'), 'tool catalog requires additional discovery')
        tools = {t['name']: t for t in catalog.get('tools', [])}
        require('search_products' in tools, 'search_products unavailable')
        schema = tools['search_products']['inputSchema']
        require(set(('searchTerm', 'limit', 'offset')) <= set(schema['properties']),
                'search tool schema changed')
        offset, total, request_id = 0, None, 3
        while total is None or offset < total:
            result = client.call('tools/call', {'name': 'search_products', 'arguments':
                                 {'searchTerm': query, 'limit': 2, 'offset': offset}}, request_id)
            total, rows = validate_page(product_data(result), offset, 2, total, query)
            offset += len(rows)
            request_id += 1
        client.call('tools/call', {'name': 'search_products', 'arguments':
                    {'searchTerm': query, 'limit': MAX_ROWS, 'offset': 0}}, request_id)
    finally:
        (output / 'manifest.json').write_text(json.dumps(
            {'endpoint': ENDPOINT, 'query': query, 'responses': client.evidence}, indent=2)+'\n')
    summary = replay(output, query)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--query', default=QUERY, help='single exact base-device search term')
    parser.add_argument('--replay', action='store_true', help='verify archived bytes without network')
    args = parser.parse_args()
    print(json.dumps(replay(args.output_dir, args.query) if args.replay else run(args.output_dir, args.query), indent=2))
