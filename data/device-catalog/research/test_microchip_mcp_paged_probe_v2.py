#!/usr/bin/env python3
"""Offline synthetic >60-item MCP pagination fixtures and fail-closed tests."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import microchip_mcp_paged_probe_v2 as v2


def sample(offset, limit, query='PIC10F202', count=75):
    rows = [{'partNumber': f'{query}-I/{i:03d}',
             'basePartNumber': query, 'lifecycleStatus': 'Active'}
            for i in range(count)]
    return {'searchTerm': query,
            'pagination': {'total': count, 'offset': offset, 'limit': limit,
                           'hasMore': offset + limit < count},
            'products': rows[offset:offset+limit]}


def captures():
    first = [sample(x, 20) for x in (0, 20, 40, 60)]
    second = [sample(x, 60) for x in (0, 60)]
    return first, second


def make_archive(folder):
    init = {'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'plasma-microchip-research', 'version': '1.0'}}
    tool = {'tools': [{'name': 'search_products', 'inputSchema': {
        'properties': {'searchTerm': {}, 'limit': {}, 'offset': {}}}}]}
    events = [
        ({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': init},
         {'protocolVersion': '2025-03-26'}),
        ({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, None),
        ({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}}, tool),
    ]
    for limit, offsets in ((20, (0, 20, 40, 60)), (60, (0, 60))):
        for offset in offsets:
            request = {'jsonrpc': '2.0', 'id': len(events), 'method': 'tools/call',
                       'params': {'name': 'search_products', 'arguments': {
                           'searchTerm': 'PIC10F202', 'limit': limit,
                           'offset': offset}}}
            result = {'content': [{'type': 'text', 'text': json.dumps({
                'success': True, 'data': sample(offset, limit)})}]}
            events.append((request, result))
    records = []
    for i, (request, result) in enumerate(events):
        raw = (json.dumps({'jsonrpc': '2.0', 'id': request['id'],
                           'result': result}).encode()
               if result is not None else b'')
        path = f'response-{i:02d}.txt'
        (folder / path).write_bytes(raw)
        records.append({'file': path, 'request': request,
                        'http_status': 202 if i == 1 else 200,
                        'sha256': hashlib.sha256(raw).hexdigest()})
    manifest = {'schema_version': 2, 'endpoint': v2.v1.ENDPOINT,
                'query': 'PIC10F202', 'capture_policy': dict(v2.POLICY),
                'responses': records}
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    return manifest


class PagedProbeTests(unittest.TestCase):
    def test_dspic_dfp_case_differs_from_vendor_ordering_case(self):
        first = [{'searchTerm': 'dsPIC33CK128MP506',
                  'pagination': {'total': 2, 'offset': 0, 'limit': 20, 'hasMore': False},
                  'products': [
                      {'partNumber': 'DSPIC33CK128MP506-I/MR',
                       'basePartNumber': 'DSPIC33CK128MP506',
                       'lifecycleStatus': 'Active'},
                      {'partNumber': 'DSPIC33CK128MP506T-E/MR',
                       'basePartNumber': 'DSPIC33CK128MP506',
                       'lifecycleStatus': 'Active'}]}]
        second = json.loads(json.dumps(first))
        second[0]['pagination']['limit'] = 60
        outcome = v2.reconcile(first, second, 'dsPIC33CK128MP506')
        self.assertEqual(outcome['exact_prefix_ordering_count'], 2)
        self.assertEqual(outcome['fuzzy_foreign_ordering_count'], 0)
        self.assertEqual(outcome['exact_query_ordering_parts'], [
            'DSPIC33CK128MP506-I/MR', 'DSPIC33CK128MP506T-E/MR'])

    def test_incomplete_foreign_fuzzy_metadata_does_not_drop_valid_target(self):
        a = {'searchTerm': 'ATSAMD21G18A',
             'pagination': {'total': 2, 'limit': 20, 'offset': 0,
                            'hasMore': False},
             'products': [
                 {'partNumber': 'ATSAMD21G18A-AU',
                  'basePartNumber': 'ATSAMD21G18', 'lifecycleStatus': 'Active'},
                 {'partNumber': 'EV75S95A', 'basePartNumber': '',
                  'lifecycleStatus': 'Active'}]}
        b = copy.deepcopy(a)
        b['pagination']['limit'] = 60
        result = v2.reconcile([a], [b], 'ATSAMD21G18A')
        self.assertEqual(result['exact_prefix_ordering_count'], 1)
        self.assertEqual(result['fuzzy_foreign_ordering_count'], 1)
        self.assertEqual(result['foreign_fuzzy_missing_base_count'], 1)
        # Target SKU metadata is never relaxed.
        a['products'][0]['basePartNumber'] = ''
        with self.assertRaisesRegex(ValueError, 'exact target'):
            v2.reconcile([a], [b], 'ATSAMD21G18A')
        # A non-ASCII or padded foreign base is also rejected.
        a['products'][0]['basePartNumber'] = 'ATSAMD21G18'
        a['products'][1]['basePartNumber'] = ' padded '
        with self.assertRaises(ValueError):
            v2.reconcile([a], [b], 'ATSAMD21G18A')

    def test_over_sixty_both_full_walks(self):
        a, b = captures()
        result = v2.reconcile(a, b)
        self.assertEqual(result['reported_total'], 75)
        self.assertEqual(result['primary_page_count'], 4)
        self.assertEqual(result['comparison_page_count'], 2)
        self.assertEqual(result['exact_prefix_ordering_count'], 75)
        self.assertIsNone(result['global_active_denominator'])
        self.assertFalse(result['production_write_authorized'])

    def test_reject_truncated_pages_duplicate_drift_and_lifecycle_conflict(self):
        for case in ('truncate', 'duplicate', 'wrong_offset', 'total_drift',
                     'lifecycle_drift', 'missing_comparison_page'):
            with self.subTest(case=case):
                a, b = captures()
                if case == 'truncate':
                    a.pop()
                elif case == 'duplicate':
                    a[1]['products'][0]['partNumber'] = a[0]['products'][0]['partNumber']
                elif case == 'wrong_offset':
                    a[2]['pagination']['offset'] = 60
                elif case == 'total_drift':
                    b[1]['pagination']['total'] = 76
                elif case == 'lifecycle_drift':
                    b[1]['products'][0]['lifecycleStatus'] = 'EOL'
                elif case == 'missing_comparison_page':
                    b.pop()
                with self.assertRaises(ValueError):
                    v2.reconcile(a, b)

    def test_max_result_policy_prevents_unbounded_capture(self):
        with self.assertRaisesRegex(ValueError, 'outside bounded'):
            v2.validate_page({'searchTerm': 'PIC10F202', 'pagination': {
                'total': 601, 'offset': 0, 'limit': 20, 'hasMore': True},
                'products': []}, 0, 20)

    def test_synthetic_manifest_full_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            make_archive(folder)
            self.assertEqual(v2.replay(folder)['unique_ordering_count'], 75)

    def test_archive_transcript_fail_closed(self):
        cases = ('missing_query', 'wrong_query', 'wrong_schema', 'wrong_policy',
                 'missing_second_walk', 'bad_offset', 'changed_bytes',
                 'wrong_status', 'wrong_tool_schema', 'wrong_request_id',
                 'extra_search', 'wrong_digest')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                manifest = make_archive(folder)
                responses = manifest['responses']
                if case == 'missing_query':
                    manifest.pop('query')
                elif case == 'wrong_query':
                    manifest['query'] = 'PIC10F200'
                elif case == 'wrong_schema':
                    manifest['schema_version'] = 1
                elif case == 'wrong_policy':
                    manifest['capture_policy']['max_total'] = 10000
                elif case == 'missing_second_walk':
                    responses.pop()
                elif case == 'bad_offset':
                    responses[5]['request']['params']['arguments']['offset'] = 41
                elif case == 'changed_bytes':
                    (folder / 'response-05.txt').write_bytes(b'corrupted')
                elif case == 'wrong_status':
                    responses[3]['http_status'] = 202
                elif case == 'wrong_request_id':
                    responses[6]['request']['id'] = 100
                elif case == 'wrong_digest':
                    responses[4]['sha256'] = '0' * 64
                elif case == 'wrong_tool_schema':
                    raw = json.dumps({'jsonrpc': '2.0', 'id': 2,
                                      'result': {'tools': []}}).encode()
                    (folder / 'response-02.txt').write_bytes(raw)
                    responses[2]['sha256'] = hashlib.sha256(raw).hexdigest()
                elif case == 'extra_search':
                    extra = copy.deepcopy(responses[-1])
                    extra['file'] = 'response-09.txt'
                    (folder / extra['file']).write_bytes(
                        (folder / responses[-1]['file']).read_bytes())
                    responses.append(extra)
                (folder / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    v2.replay(folder)

    def test_unsafe_query_does_not_read_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                v2.replay(Path(tmp), 'PIC10F202/evil')


if __name__ == '__main__':
    unittest.main()
