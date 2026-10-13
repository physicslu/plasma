import copy
import json
import unittest
from microchip_mcp_probe_v1 import decode, product_data, reconcile


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
            lambda x: x['products'][0].update(basePartNumber='PIC10F200'),
            lambda x: x['products'][0].update(lifecycleStatus=''),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                last = copy.deepcopy(page(2))
                mutate(last)
                with self.assertRaises(ValueError):
                    reconcile([page(0), last], page(0, 60))

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


if __name__ == '__main__':
    unittest.main()
