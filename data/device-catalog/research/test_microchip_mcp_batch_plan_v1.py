#!/usr/bin/env python3
"""Synthetic offline-only contract tests; no Microchip network observations."""
import copy
import unittest
from microchip_mcp_batch_plan_v1 import plan_inventory, LANES, EXCLUDED


def fixture():
    packs = [
        {'publisher': 'Microchip', 'pack_name': 'PIC10-12Fxxx_DFP',
         'discovery_lane': '8bit', 'device_names':
         ['PIC10F202', 'PIC12F529T48A', 'PIC10-NEEDS-REVIEW']},
        {'publisher': 'Microchip', 'pack_name': 'PIC32CX-BZ_DFP',
         'discovery_lane': 'wireless', 'device_names': ['PIC32CXBZ3', 'WBZ351']},
        {'publisher': 'Microchip', 'pack_name': 'SAMA5_DFP',
         'discovery_lane': 'excluded_mpu_candidate', 'device_names': ['SAMA5D27']},
        {'publisher': 'Microchip', 'pack_name': 'TOOLS_DFP',
         'discovery_lane': 'unclassified_or_non_mcu_pack', 'device_names': ['OTHER1']},
    ]
    for pack in packs:
        pack['supported_name_count'] = len(pack['device_names'])
    lanes = {lane: {'candidate_device_name_count': sum(
        len(p['device_names']) for p in packs if p['discovery_lane'] == lane),
        'pack_count': sum(p['discovery_lane'] == lane for p in packs)}
        for lane in (*LANES, *EXCLUDED)}
    return {'manufacturer': 'Microchip',
            'source_url': 'https://packs.download.microchip.com/',
            'source_bytes_sha256': 'a' * 64,
            'manufacturer_device_pack_count': 4,
            'observed_manufacturer_device_support_names': 7,
            'population_boundary_validated': False,
            'production_write_authorized': False,
            'global_active_denominator': None,
            'device_support_list_is_complete_commercial_sku_inventory': False,
            'device_packs': packs, 'lanes': lanes}


class PlanTests(unittest.TestCase):
    def test_source_pinned_bounded_plan_with_explicit_exclusions(self):
        plan = plan_inventory(fixture(), 'a'*64, batch_size=3)
        self.assertEqual(plan['dfp_device_support_names'], 7)
        self.assertEqual(plan['mapped_discovery_lane_names'], 5)
        self.assertEqual(plan['supported_text_search_seeds'], 4)
        self.assertEqual(plan['excluded_or_unclassified_support_names'], 2)
        self.assertEqual(plan['batch_count'], 2)
        self.assertEqual(len(plan['needs_manual_query_mapping']), 1)
        self.assertEqual(plan['needs_manual_query_mapping'][0]['device_name'],
                         'PIC10-NEEDS-REVIEW')
        self.assertEqual(plan['lanes']['32bit-avr-risc']['dfp_device_names'], 0)
        self.assertFalse(plan['production_write_authorized'])
        self.assertIsNone(plan['global_active_denominator'])
        self.assertTrue(plan['no_live_capture_performed'])

    def test_accessory_device_pack_names_are_not_automatically_queried(self):
        value = copy.deepcopy(fixture())
        accessory = {'publisher': 'Microchip', 'pack_name': 'PIC-8bitAC_DFP',
                     'discovery_lane': '8bit',
                     'device_names': ['AC162050', 'AC244023'],
                     'supported_name_count': 2}
        value['device_packs'].append(accessory)
        value['manufacturer_device_pack_count'] += 1
        value['observed_manufacturer_device_support_names'] += 2
        value['lanes']['8bit']['candidate_device_name_count'] += 2
        value['lanes']['8bit']['pack_count'] += 1
        plan = plan_inventory(value, 'a'*64, batch_size=3)
        self.assertEqual(plan['supported_text_search_seeds'], 4)
        self.assertEqual(plan['mapped_discovery_lane_names'], 7)
        self.assertEqual(plan['lanes']['8bit']['accessory_pack_names_held_for_review'], 2)
        self.assertEqual([x['device_name'] for x in plan['needs_manual_query_mapping']
                          if x['reason'] == 'accessory_pack_requires_type_review'],
                         ['AC162050', 'AC244023'])
        self.assertNotIn('AC162050', str(plan['batches']))
        self.assertNotIn('AC244023', str(plan['batches']))

    def test_deterministic_batch_hash_and_no_made_up_skus(self):
        left = plan_inventory(fixture(), 'a'*64)
        right = plan_inventory(fixture(), 'a'*64)
        self.assertEqual(left['batches'], right['batches'])
        self.assertEqual(left['batches'][0]['queries'],
                         ['PIC10F202', 'PIC12F529T48A'])
        self.assertTrue(all(len(batch['queries']) <= 10 for batch in left['batches']))
        self.assertNotIn('PIC10-NEEDS-REVIEW', str(left['batches']))

    def test_pinned_source_and_scope_are_fail_closed(self):
        cases = [('wrong_digest', lambda d: d.update(source_bytes_sha256='b'*64)),
                 ('production', lambda d: d.update(production_write_authorized=True)),
                 ('missing_pack', lambda d: d['device_packs'].pop()),
                 ('wrong_lane_count', lambda d: d['lanes']['8bit'].update(
                     candidate_device_name_count=999)),
                 ('duplicate_device', lambda d: d['device_packs'][1]['device_names'].__setitem__(
                     0, 'PIC10F202'))]
        for name, mutation in cases:
            with self.subTest(name=name):
                value = copy.deepcopy(fixture())
                mutation(value)
                with self.assertRaises(ValueError):
                    plan_inventory(value, 'a'*64)

    def test_unbounded_batch_sizes_are_rejected(self):
        for value in (0, 1, 11, 100, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                plan_inventory(fixture(), 'a'*64, value)


if __name__ == '__main__':
    unittest.main()
