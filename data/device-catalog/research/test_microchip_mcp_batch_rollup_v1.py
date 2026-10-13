#!/usr/bin/env python3
"""Synthetic offline source-attested rollup regression tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import microchip_mcp_batch_rollup_v1 as rollup
import microchip_mcp_plan_capture_v1 as capture
from microchip_mcp_batch_plan_v1 import plan_inventory
from test_microchip_mcp_batch_plan_v1 import fixture
from test_microchip_mcp_paged_probe_v2 import make_archive


def one_query_fixture():
    inventory = fixture()
    pack = inventory['device_packs'][0]
    pack['device_names'] = ['PIC10F202']
    pack['supported_name_count'] = 1
    inventory['manufacturer_device_pack_count'] = 1
    inventory['device_packs'] = [pack]
    inventory['observed_manufacturer_device_support_names'] = 1
    inventory['lanes'] = {key: {'candidate_device_name_count': 1 if key == '8bit' else 0,
                                 'pack_count': 1 if key == '8bit' else 0}
                          for key in inventory['lanes']}
    return inventory


class RollupTests(unittest.TestCase):
    def setUp(self):
        self.inventory = one_query_fixture()
        self.plan = plan_inventory(self.inventory, 'a'*64, batch_size=3)
        self.item = self.plan['batches'][0]

    def install_archive(self, root):
        batch = root / self.item['batch_id']
        folder = batch / 'PIC10F202'
        folder.mkdir(parents=True)
        make_archive(folder)
        (batch / 'batch-source.json').write_text(json.dumps(
            capture.attestation(self.plan, self.item)), encoding='utf-8')
        return batch

    def test_empty_batch_is_missing_not_zero_mcu_population(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = rollup.build(self.plan, self.inventory, 'a'*64, tmp)
            self.assertEqual(result['not_captured_batches'], 1)
            self.assertEqual(result['fully_replayed_text_search_queries'], 0)
            self.assertEqual(result['ordering_candidates'], [])
            self.assertFalse(result['all_planned_batches_fully_replayed'])
            self.assertIsNone(result['global_active_denominator'])

    def test_v2_archived_page_bytes_produce_source_linked_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.install_archive(Path(tmp))
            result = rollup.build(self.plan, self.inventory, 'a'*64, tmp)
            self.assertTrue(result['all_planned_batches_fully_replayed'])
            self.assertEqual(result['source_linked_unique_exact_prefix_candidates'], 75)
            self.assertEqual(result['fully_replayed_text_search_queries'], 1)
            self.assertFalse(result['production_write_authorized'])
            for item in result['ordering_candidates']:
                source = item['sources'][0]
                self.assertTrue(source['evidence_file'].startswith(
                    self.item['batch_id']+'/PIC10F202/response-'))
                self.assertEqual(len(source['response_sha256']), 64)

    def test_attestation_tamper_rejects_entire_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = self.install_archive(Path(tmp))
            record = json.loads((batch / 'batch-source.json').read_text())
            record['query_list_sha256'] = '0'*64
            (batch / 'batch-source.json').write_text(json.dumps(record))
            result = rollup.build(self.plan, self.inventory, 'a'*64, tmp)
            self.assertEqual(result['unverified_or_partial_batches'], 1)
            self.assertEqual(result['ordering_candidates'], [])
            self.assertFalse(result['all_planned_batches_fully_replayed'])

    def test_mutated_vendor_response_quarantines_entire_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = self.install_archive(Path(tmp))
            (batch / 'PIC10F202' / 'response-03.txt').write_bytes(b'mutated')
            result = rollup.build(self.plan, self.inventory, 'a'*64, tmp)
            self.assertEqual(result['unverified_or_partial_batches'], 1)
            self.assertEqual(result['source_linked_unique_exact_prefix_candidates'], 0)

    def test_forged_plan_cannot_use_valid_existing_vendor_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.install_archive(Path(tmp))
            fake = copy.deepcopy(self.plan)
            fake['batches'][0]['queries'] = ['PIC10F200']
            with self.assertRaisesRegex(ValueError, 'diverges'):
                rollup.build(fake, self.inventory, 'a'*64, tmp)

    def test_cross_batch_raw_lifecycle_conflict_quarantines_identity(self):
        inventory = fixture()
        plan = plan_inventory(inventory, 'a'*64, batch_size=3)
        items = plan['batches'][:2]
        self.assertGreaterEqual(len(items), 2)
        with tempfile.TemporaryDirectory() as tmp:
            for item in items:
                dest = Path(tmp) / item['batch_id']
                dest.mkdir()
                (dest / 'batch-source.json').write_text(
                    json.dumps(capture.attestation(plan, item)))
            def fake_ledger(folder, queries):
                status = 'Active' if folder.name == items[0]['batch_id'] else 'EOL'
                return {'selected_queries': len(queries),
                        'fully_replayed_queries': len(queries),
                        'all_queries_reconciled': True,
                        'production_write_authorized': False,
                        'global_active_denominator': None,
                        'manufacturer_population_complete': False,
                        'unique_exact_ordering_candidates': 1,
                        'ordering_candidates': [{
                            'icpn': 'PIC10F202-I/MC',
                            'rawLifecycleStatus': status,
                            'sources': [{'query': queries[0],
                                         'evidence_file': queries[0]+'/response-03.txt',
                                         'response_sha256': 'a'*64}]}]}
            with patch.object(rollup.ledger, 'build', side_effect=fake_ledger):
                result = rollup.build(plan, inventory, 'a'*64, tmp)
            self.assertEqual(result['lifecycle_conflict_identity_count'], 1)
            self.assertEqual(result['source_linked_unique_exact_prefix_candidates'], 0)
            self.assertFalse(result['all_planned_batches_fully_replayed'])

    def test_production_input_folder_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'production'
            folder.mkdir()
            with self.assertRaisesRegex(ValueError, 'Production'):
                rollup.build(self.plan, self.inventory, 'a'*64, folder)


if __name__ == '__main__':
    unittest.main()
