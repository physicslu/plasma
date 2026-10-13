#!/usr/bin/env python3
"""Offline-only synthetic coverage for exact-SKU ledger and provenance."""
import json
from pathlib import Path
import tempfile
import unittest

from test_microchip_mcp_probe_v1 import ProbeTests
import microchip_mcp_evidence_ledger_v1 as ledger


class LedgerTests(unittest.TestCase):
    def test_exact_ordering_provenance_from_archived_response_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'PIC10F202'
            folder.mkdir()
            ProbeTests.archived_capture(folder)
            result = ledger.build(root, ['PIC10F202'])
            self.assertEqual(result['fully_replayed_queries'], 1)
            self.assertEqual(result['unique_exact_ordering_candidates'], 3)
            self.assertEqual(result['raw_lifecycle_values'], ['Active'])
            self.assertTrue(result['all_queries_reconciled'])
            self.assertIsNone(result['global_active_denominator'])
            self.assertFalse(result['production_write_authorized'])
            for row in result['ordering_candidates']:
                self.assertEqual(row['rawLifecycleStatus'], 'Active')
                self.assertEqual(len(row['sources']), 1)
                self.assertEqual(row['sources'][0]['query'], 'PIC10F202')
                self.assertEqual(len(row['sources'][0]['response_sha256']), 64)

    def test_mutated_original_bytes_fail_closed_to_zero_admitted_research_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'PIC10F202'
            folder.mkdir()
            ProbeTests.archived_capture(folder)
            (folder / 'response-03.txt').write_bytes(b'corrupted')
            result = ledger.build(root, ['PIC10F202'])
            self.assertEqual(result['fully_replayed_queries'], 0)
            self.assertEqual(result['unique_exact_ordering_candidates'], 0)
            self.assertFalse(result['all_queries_reconciled'])

    def test_missing_query_is_not_counted_as_empty_result(self):
        with tempfile.TemporaryDirectory() as temp:
            result = ledger.build(Path(temp), ['PIC10F202'])
            self.assertEqual(result['queries'][0]['state'], 'unverified')
            self.assertEqual(result['ordering_candidates'], [])

    def test_query_input_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'invalid candidate'):
                ledger.build(Path(temp), ['PIC10F202'] * 2)


if __name__ == '__main__':
    unittest.main()
