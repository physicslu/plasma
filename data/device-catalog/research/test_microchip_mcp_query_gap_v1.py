#!/usr/bin/env python3
"""Synthetic-only source-pinned query gap tests; no live vendor network."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import microchip_mcp_query_gap_v1 as gap
from microchip_mcp_batch_plan_v1 import plan_inventory
from test_microchip_mcp_batch_plan_v1 import fixture


def mock_ledger(root, queries):
    return {'selected_queries': len(queries), 'fully_replayed_queries': 1,
            'manufacturer_population_complete': False,
            'global_active_denominator': None,
            'production_write_authorized': False,
            'unique_exact_ordering_candidates': 2,
            'queries': [
                {'query': queries[0], 'state': 'fully_replayed_bounded_query'},
                {'query': queries[1], 'state': 'unverified'}],
            'ordering_candidates': [
                {'icpn': 'PIC10F202-I/MC', 'sources': [{'sha256': 'a'*64}]},
                {'icpn': 'PIC10F202T-I/MC', 'sources': [{'sha256': 'b'*64}]}]}


class QueryGapTests(unittest.TestCase):
    def setUp(self):
        self.inventory = fixture()
        self.plan = plan_inventory(self.inventory, 'a'*64, batch_size=3)
        self.queries = ['PIC10F202', 'PIC12F529T48A']

    def test_real_partition_logic_is_discovery_progress_not_sku_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(gap.ledger, 'build', side_effect=mock_ledger):
                result = gap.build(self.plan, self.inventory, 'a'*64,
                                   tmp, self.queries)
        self.assertEqual(result['planned_text_search_queries'], 4)
        self.assertEqual(result['fully_replayed_queries'], 1)
        self.assertEqual(result['unverified_attempted_queries'], 1)
        self.assertEqual(result['not_yet_attempted_queries'], 2)
        self.assertEqual(result['reconciled_query_percent'], 25)
        self.assertEqual(result['unique_exact_prefix_research_candidates'], 2)
        self.assertTrue(result['query_progress_is_not_exact_sku_coverage'])
        self.assertFalse(result['production_write_authorized'])
        self.assertIsNone(result['global_active_denominator'])

    def test_unpinned_or_unplanned_queries_fail_before_using_archived_rows(self):
        for case in ('altered_plan', 'nonplanned', 'duplicate_queries'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                plan = copy.deepcopy(self.plan)
                queries = list(self.queries)
                if case == 'altered_plan':
                    plan['batches'][0]['queries'][0] = 'FORGED'
                elif case == 'nonplanned':
                    queries[0] = 'AC162050'
                elif case == 'duplicate_queries':
                    queries[1] = queries[0]
                with patch.object(gap.ledger, 'build') as forbidden:
                    with self.assertRaises(ValueError):
                        gap.build(plan, self.inventory, 'a'*64, tmp, queries)
                    forbidden.assert_not_called()

    def test_report_rejects_mismatched_or_unsafe_ledger_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            def forged(root, queries):
                data = mock_ledger(root, queries)
                data['fully_replayed_queries'] = 2
                return data
            with patch.object(gap.ledger, 'build', side_effect=forged):
                with self.assertRaisesRegex(ValueError, 'total mismatch'):
                    gap.build(self.plan, self.inventory, 'a'*64,
                              tmp, self.queries)

    def test_never_uses_production_archive_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            forbidden = Path(tmp)/'Production'
            forbidden.mkdir()
            with patch.object(gap.ledger, 'build') as unused:
                with self.assertRaisesRegex(ValueError, 'forbidden'):
                    gap.build(self.plan, self.inventory, 'a'*64,
                              forbidden, self.queries)
                unused.assert_not_called()


if __name__ == '__main__':
    unittest.main()
