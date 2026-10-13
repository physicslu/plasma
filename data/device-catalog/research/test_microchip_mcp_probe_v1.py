import copy
import hashlib
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch
import json
from pathlib import Path
import tempfile
import unittest
from microchip_mcp_probe_v1 import Client, decode, product_data, reconcile, replay, run


def page(offset, limit=2):
    rows = [{'partNumber': f'PIC10F202-I/{suffix}', 'basePartNumber': 'PIC10F202',
             'lifecycleStatus': 'Active'} for suffix in ('MC', 'OT', 'P')]
    return {'searchTerm': 'PIC10F202', 'pagination': {'total': 3, 'offset': offset,
            'limit': limit, 'hasMore': offset+limit < 3}, 'products': rows[offset:offset+limit]}


class ProbeTests(unittest.TestCase):
    def test_sse_and_json(self):
        value = {'jsonrpc': '2.0', 'id': 3, 'result': {'ok': True}}
        for raw in (json.dumps(value), ': heartbeat\r\n\r\nevent: message\r\ndata: '+json.dumps(value)+'\r\n\r\n'):
            self.assertEqual(decode(raw.encode(), 3), {'ok': True})

    def test_rpc_error_and_wrong_id(self):
        for value in ({'jsonrpc': '2.0', 'id': 3, 'error': {}},
                      {'jsonrpc': '2.0', 'id': 4, 'result': {}}):
            with self.assertRaises(ValueError):
                decode(json.dumps(value).encode(), 3)

    def test_http_failure_bytes_are_archived_but_never_reconciled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = b'{"error":{"code":"NOT_FOUND","message":"not found"}}'
            response = HTTPError('https://api.microchip.com/mcp/resources',
                                 404, 'Not Found', {}, BytesIO(raw))
            client = Client(root)
            with patch('microchip_mcp_probe_v1.urlopen', side_effect=response):
                with self.assertRaisesRegex(ValueError, 'MCP HTTP 404'):
                    client.call('tools/call', {'name': 'search_products',
                                'arguments': {'searchTerm': 'PIC12F529T48A',
                                              'limit': 2, 'offset': 0}}, 3)
            self.assertEqual(len(client.evidence), 1)
            saved = client.evidence[0]
            self.assertEqual(saved['http_status'], 404)
            self.assertEqual(saved['request']['method'], 'tools/call')
            self.assertEqual((root / saved['file']).read_bytes(), raw)
            self.assertEqual(saved['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertNotIn('lifecycleStatus', saved)

    def test_tool_failure(self):
        with self.assertRaises(ValueError):
            product_data({'isError': True, 'content': []})

    def test_complete_odd_last_page(self):
        result = reconcile([page(0), page(2)], page(0, 60))
        self.assertEqual(result['unique_ordering_count'], 3)
        self.assertIsNone(result['global_active_denominator'])
        self.assertFalse(result['production_write_authorized'])

    def test_missing_page(self):
        with self.assertRaises(ValueError):
            reconcile([page(0)], page(0, 60))

    def test_reject_inconsistent_pages(self):
        mutations = [
            lambda x: x['pagination'].update(total=4),
            lambda x: x['pagination'].update(offset=0),
            lambda x: x['pagination'].update(hasMore=True),
            lambda x: x['products'][0].update(partNumber='PIC10F202-I/MC'),
            lambda x: x['products'][0].update(lifecycleStatus=''),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                last = copy.deepcopy(page(2))
                mutate(last)
                with self.assertRaises(ValueError):
                    reconcile([page(0), last], page(0, 60))

    def test_dspic_case_variant_matches_real_ordering_prefix_not_fuzzy_names(self):
        from microchip_mcp_probe_v1 import exact_ordering_prefix
        query = 'dsPIC33CK128MP506'
        self.assertTrue(exact_ordering_prefix('DSPIC33CK128MP506-I/MR', query))
        self.assertTrue(exact_ordering_prefix('DSPIC33CK128MP506T-I/MR', query))
        self.assertFalse(exact_ordering_prefix('DSPIC33CK128MP507-I/MR', query))
        self.assertFalse(exact_ordering_prefix('DSPIC33CK128MP506A-I/MR', query))
        self.assertFalse(exact_ordering_prefix('OTHER-DSPIC33CK128MP506', query))

    def test_vendor_base_part_alias_does_not_discard_valid_ordering(self):
        first, last, comparison = page(0), page(2), page(0, 60)
        first['products'][0]['basePartNumber'] = 'PIC10F200'
        comparison['products'][0]['basePartNumber'] = 'PIC10F200'
        result = reconcile([first, last], comparison)
        self.assertEqual(result['exact_prefix_ordering_count'], 3)
        self.assertEqual(result['vendor_base_part_alias_count'], 1)
        self.assertEqual(result['fuzzy_foreign_ordering_count'], 0)

    def test_fuzzy_foreign_device_is_archived_but_not_counted_as_target(self):
        first, last, comparison = page(0), page(2), page(0, 60)
        for record in (last['products'][0], comparison['products'][2]):
            record['partNumber'] = 'RFPIC12F675H-I/SS'
            record['basePartNumber'] = 'RFPIC12F675H'
            record['lifecycleStatus'] = 'Not Recommended For New Design'
        result = reconcile([first, last], comparison)
        self.assertEqual(result['reported_total'], 3)
        self.assertEqual(result['exact_prefix_ordering_count'], 2)
        self.assertEqual(result['fuzzy_foreign_ordering_count'], 1)
        self.assertEqual(result['foreign_ordering_parts'], ['RFPIC12F675H-I/SS'])
        self.assertIsNone(result['global_active_denominator'])

    def test_all_fuzzy_foreign_devices_cannot_inflate_target_count(self):
        pages = [page(0), page(2)]
        comparison = page(0, 60)
        for data in [*pages, comparison]:
            for row in data['products']:
                row['partNumber'] = row['partNumber'].replace('PIC10F202', 'PIC10F200')
                row['basePartNumber'] = 'PIC10F200'
        result = reconcile(pages, comparison)
        self.assertEqual(result['exact_prefix_ordering_count'], 0)
        self.assertEqual(result['fuzzy_foreign_ordering_count'], 3)

    def test_comparison_lifecycle_drift(self):
        other = page(0, 60)
        other['products'][0]['lifecycleStatus'] = 'EOL'
        with self.assertRaises(ValueError):
            reconcile([page(0), page(2)], other)

    def test_comparison_identity_drift(self):
        other = page(0, 60)
        other['products'][0]['partNumber'] = 'PIC10F202T-I/MC'
        with self.assertRaises(ValueError):
            reconcile([page(0), page(2)], other)


    def test_explicit_alternate_base_device_query(self):
        def rename(data):
            value = copy.deepcopy(data)
            value['searchTerm'] = 'PIC10F206'
            for row in value['products']:
                row['partNumber'] = row['partNumber'].replace('PIC10F202', 'PIC10F206')
                row['basePartNumber'] = 'PIC10F206'
            return value
        result = reconcile([rename(page(0)), rename(page(2))],
                           rename(page(0, 60)), query='PIC10F206')
        self.assertEqual(result['query'], 'PIC10F206')
        self.assertEqual(result['unique_ordering_count'], 3)
        with self.assertRaisesRegex(ValueError, 'query mismatch'):
            reconcile([rename(page(0)), rename(page(2))], rename(page(0, 60)),
                      query='PIC10F202')

    def test_replay_rejects_unsafe_query_before_reading_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            self.archived_capture(folder)
            with self.assertRaisesRegex(ValueError, 'alphanumeric'):
                replay(folder, query='PIC10F202/../other')

    def test_query_rejects_punctuation_without_issuing_network_request(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'alphanumeric'):
                run(Path(temp) / 'uncreated', query='PIC10F202/evil')
            self.assertFalse((Path(temp) / 'uncreated').exists())

    @staticmethod
    def archived_capture(folder):
        """Create fully synthetic MCP evidence; never present it as live vendor data."""
        init_params = {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'plasma-microchip-research', 'version': '1.0'}}
        search_schema = {'tools': [{'name': 'search_products', 'inputSchema': {
            'properties': {'searchTerm': {}, 'limit': {}, 'offset': {}}}}]}
        def product_result(value):
            return {'content': [{'type': 'text', 'text': json.dumps({
                'success': True, 'data': value})}]}
        events = [
            ({'jsonrpc': '2.0', 'method': 'initialize', 'id': 1,
              'params': init_params}, {'protocolVersion': '2025-03-26'}),
            ({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, None),
            ({'jsonrpc': '2.0', 'method': 'tools/list', 'id': 2,
              'params': {}}, search_schema),
        ]
        for index, (offset, limit) in enumerate(((0, 2), (2, 2), (0, 60)), start=3):
            events.append((
                {'jsonrpc': '2.0', 'method': 'tools/call', 'id': index, 'params': {
                    'name': 'search_products', 'arguments': {
                        'searchTerm': 'PIC10F202', 'limit': limit, 'offset': offset}}},
                product_result(page(offset, limit))))
        records = []
        for index, (request, result) in enumerate(events):
            raw = (json.dumps({'jsonrpc': '2.0', 'id': request['id'],
                               'result': result}).encode()
                   if result is not None else b'')
            filename = f'response-{index:02d}.txt'
            (folder / filename).write_bytes(raw)
            records.append({'file': filename, 'request': request,
                            'http_status': 202 if index == 1 else 200,
                            'sha256': hashlib.sha256(raw).hexdigest()})
        manifest = {'endpoint': 'https://api.microchip.com/mcp/resources',
                    'query': 'PIC10F202', 'responses': records}
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_offline_transcript_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            self.archived_capture(folder)
            result = replay(folder)
            self.assertEqual(result['unique_ordering_count'], 3)
            self.assertFalse(result['population_boundary_validated'])

    def test_offline_replay_rejects_corrupt_handshake_requests_and_bytes(self):
        cases = ('missing_init', 'reordered', 'wrong_id', 'wrong_http_status',
                 'wrong_query', 'missing_manifest_query', 'extra_call',
                 'missing_tool', 'changed_raw_body')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                manifest = self.archived_capture(folder)
                records = manifest['responses']
                if case == 'missing_init':
                    records.pop(0)
                elif case == 'reordered':
                    records[3], records[4] = records[4], records[3]
                elif case == 'wrong_id':
                    records[3]['request']['id'] = 99
                elif case == 'wrong_http_status':
                    records[1]['http_status'] = 204
                elif case == 'wrong_query':
                    records[3]['request']['params']['arguments']['searchTerm'] = 'PIC10F200'
                elif case == 'missing_manifest_query':
                    manifest.pop('query')
                elif case == 'extra_call':
                    extra = copy.deepcopy(records[-1])
                    extra['file'] = 'response-06.txt'
                    (folder / extra['file']).write_bytes(
                        (folder / records[-1]['file']).read_bytes())
                    records.append(extra)
                elif case == 'missing_tool':
                    raw = json.dumps({'jsonrpc': '2.0', 'id': 2,
                                      'result': {'tools': []}}).encode()
                    (folder / 'response-02.txt').write_bytes(raw)
                    records[2]['sha256'] = hashlib.sha256(raw).hexdigest()
                elif case == 'changed_raw_body':
                    (folder / 'response-03.txt').write_bytes(b'altered')
                (folder / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises((ValueError, KeyError)):
                    replay(folder)


if __name__ == '__main__':
    unittest.main()
