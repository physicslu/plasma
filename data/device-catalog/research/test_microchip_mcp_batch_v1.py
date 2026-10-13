#!/usr/bin/env python3
"""Offline-only tests for the bounded Microchip DFP MCP batch driver."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import microchip_mcp_batch_v1 as batch


class BatchTests(unittest.TestCase):
    def test_official_pack_discovery_scope_is_bounded_not_vendor_denominator(self):
        parts = batch.load_seeds()
        self.assertEqual(len(parts), 27)
        self.assertEqual(len(set(parts)), 27)
        self.assertEqual(parts[1], 'PIC10F202')
        self.assertEqual(parts[-1], 'PIC12HV752')

    def test_forged_completeness_and_duplicate_seeds_are_rejected(self):
        original = json.loads(batch.SEEDS.read_text())
        for mutation in ('claim_production', 'duplicate', 'wrong_count'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                value = json.loads(json.dumps(original))
                if mutation == 'claim_production':
                    value['production_write_authorized'] = True
                elif mutation == 'duplicate':
                    value['device_names'][0] = value['device_names'][1]
                else:
                    value['observed_device_count'] = 100
                file = Path(temp) / 'seeds.json'
                file.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    batch.load_seeds(file)

    @staticmethod
    def fake_result(part):
        return {'query': part, 'population_boundary_validated': False,
                'global_active_denominator': None,
                'production_write_authorized': False,
                'unique_ordering_count': 3,
                'exact_prefix_ordering_count': 3,
                'fuzzy_foreign_ordering_count': 0,
                'vendor_base_part_alias_count': 0}

    def test_synthetic_batch_success_is_never_population_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'research'
            with patch.object(batch.probe, 'run',
                              side_effect=lambda path, part: self.fake_result(part)):
                report = batch.execute(output, batch.load_seeds()[:3])
            self.assertTrue(report['all_queries_reconciled'])
            self.assertEqual(report['bounded_reconciled_queries'], 3)
            self.assertFalse(report['search_results_are_exhaustive_sku_population'])
            self.assertFalse(report['production_write_authorized'])
            self.assertIsNone(report['global_active_denominator'])
            self.assertEqual(json.loads((output / 'batch-summary.json').read_text())
                             ['bounded_reconciled_queries'], 3)

    def test_paged_v2_live_capture_is_explicit_and_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'paged'
            with patch.object(batch.paged, 'run',
                              side_effect=lambda folder, part: self.fake_result(part)) as capture:
                result = batch.execute(output, batch.load_seeds()[:3],
                                       workers=2, capture_format='paged_v2')
            self.assertTrue(result['all_queries_reconciled'])
            self.assertEqual(result['capture_format'], 'paged_v2')
            self.assertEqual(capture.call_count, 3)

    def test_invalid_capture_format_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'not_created'
            with self.assertRaisesRegex(ValueError, 'capture format'):
                batch.execute(target, batch.load_seeds()[:1],
                              capture_format='unexpected')
            self.assertFalse(target.exists())

    def test_two_session_batch_preserves_replay_seed_order(self):
        parts = batch.load_seeds()[:10]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'parallel'
            with patch.object(batch.probe, 'run',
                              side_effect=lambda folder, part: self.fake_result(part)):
                report = batch.execute(output, parts, workers=2)
            self.assertTrue(report['all_queries_reconciled'])
            self.assertEqual([x['base_device_query'] for x in report['results']], parts)

    def test_untrusted_batch_query_is_rejected_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            for part in ('PIC10F202/../other', '', 'PIC10F202?limit=999'):
                with self.subTest(part=part):
                    output = Path(temp) / 'research'
                    with self.assertRaisesRegex(ValueError, 'invalid selected query set'):
                        batch.execute(output, [part])
                    self.assertFalse(output.exists())

    def test_parallelism_above_two_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'not_created'
            with self.assertRaisesRegex(ValueError, 'worker count'):
                batch.execute(target, batch.load_seeds()[:2], workers=3)
            self.assertFalse(target.exists())

    def test_fuzzy_only_query_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as temp:
            def fuzzy(path, part):
                result = self.fake_result(part)
                result['exact_prefix_ordering_count'] = 0
                result['fuzzy_foreign_ordering_count'] = 3
                return result
            with patch.object(batch.probe, 'run', side_effect=fuzzy):
                report = batch.execute(Path(temp) / 'fuzzy', batch.load_seeds()[:2])
            self.assertFalse(report['all_queries_reconciled'])
            self.assertEqual(report['bounded_reconciled_queries'], 0)
            self.assertTrue(all(r['state'] == 'no_exact_ordering_prefix_found'
                                for r in report['results']))

    def test_a_failed_query_is_reported_without_false_success(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'research'
            def fake(path, part):
                if part == 'PIC10F202':
                    raise OSError('synthetic network interruption')
                return self.fake_result(part)
            with patch.object(batch.probe, 'run', side_effect=fake):
                report = batch.execute(output, batch.load_seeds()[:3])
            self.assertFalse(report['all_queries_reconciled'])
            self.assertEqual(report['bounded_reconciled_queries'], 2)
            self.assertEqual(report['results'][1]['state'], 'failed_or_unverified')
            self.assertEqual(report['results'][1]['error_type'], 'OSError')

    def test_offline_missing_archive_does_not_look_like_zero_products(self):
        with tempfile.TemporaryDirectory() as temp:
            report = batch.execute(Path(temp), batch.load_seeds()[:2], offline=True)
            self.assertFalse(report['all_queries_reconciled'])
            self.assertEqual([r['state'] for r in report['results']],
                             ['not_archived', 'not_archived'])


if __name__ == '__main__':
    unittest.main()
