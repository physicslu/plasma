#!/usr/bin/env python3
"""All tests synthetic and strictly offline; no Microchip product census."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import microchip_mcp_crosslane_canary_v1 as canary

DIGEST = 'a' * 64

def fixture():
    q = [('PIC16F18855', 'PIC16F1xxxx_DFP', '8bit'),
         ('dsPIC33CK128MP506', 'dsPIC33CK-MP_DFP', '16bit'),
         ('PIC32MX470F512H', 'PIC32MX_DFP', '32bit-pic-sam'),
         ('PIC32CX1012BZ24032', 'PIC32CX-BZ_DFP', 'wireless'),
         ('ATmega4809', 'ATmega_DFP', '8bit'),
         ('PIC24FJ128GA606', 'PIC24F-GA-GB_DFP', '16bit'),
         ('ATSAMD21G18A', 'SAMD21_DFP', '32bit-pic-sam'),
         ('ATSAMR21G18A', 'SAMR21_DFP', 'wireless'),
         ('AVR128DA28', 'AVR-Dx_DFP', '8bit'),
         ('PIC12F615', 'PIC10-12Fxxx_DFP', '8bit')]
    manifest = json.loads(canary.CANARY.read_text(encoding='utf-8'))
    manifest['source_index_sha256'] = DIGEST
    packs = [{'pack_name': p, 'publisher': 'Microchip', 'discovery_lane': lane,
              'device_names': [n]} for n, p, lane in q]
    inventory = {'source_bytes_sha256': DIGEST, 'device_packs': packs}
    return inventory, manifest


def fake_capture(folder, selected, offline, workers, capture_format):
    folder.mkdir(parents=True, exist_ok=True)
    return {'selected_device_names': len(selected), 'all_queries_reconciled': True,
            'population_boundary_validated': False,
            'global_active_denominator': None, 'production_write_authorized': False}


class CanaryTests(unittest.TestCase):
    def test_select_three_and_ten_checked_against_original_pack_ledger(self):
        inv, value = fixture()
        self.assertEqual(canary.select(inv, value, DIGEST, 3),
                         ['PIC16F18855', 'dsPIC33CK128MP506', 'PIC32MX470F512H'])
        self.assertEqual(len(canary.select(inv, value, DIGEST, 10)), 10)

    def test_false_source_and_scope_claims_rejected(self):
        for case in ('digest','wrong_pack','accessory_pack','duplicate','production',
                     'missing_device','wrong_lane','wrong_count','unsafe_query'):
            with self.subTest(case=case):
                inv, value = fixture()
                if case == 'digest':
                    value['source_index_sha256'] = 'b'*64
                elif case == 'wrong_pack':
                    value['ordered_queries'][0]['pack_name'] = 'PIC16Fxxx_DFP'
                elif case == 'accessory_pack':
                    value['ordered_queries'][0]['pack_name'] = 'PIC-8bitAC_DFP'
                elif case == 'duplicate':
                    value['ordered_queries'][1] = copy.deepcopy(value['ordered_queries'][0])
                elif case == 'production':
                    value['production_write_authorized'] = True
                elif case == 'missing_device':
                    inv['device_packs'][0]['device_names'] = []
                elif case == 'wrong_lane':
                    value['ordered_queries'][1]['lane'] = '8bit'
                elif case == 'wrong_count':
                    value['query_count'] = 100
                elif case == 'unsafe_query':
                    value['ordered_queries'][0]['device_name'] = '../unsafe'
                with self.assertRaises(ValueError):
                    canary.select(inv, value, DIGEST)

    def test_live_capture_opt_in_then_verified_replay(self):
        inv, value = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(canary.batch, 'execute', side_effect=fake_capture):
                live = canary.execute(inv, value, DIGEST, tmp,
                                      max_queries=3, capture=True)
            self.assertTrue(live['all_queries_reconciled'])
            self.assertFalse(live['production_write_authorized'])
            evidence = Path(tmp)/'crosslane-3'/'crosslane-source.json'
            self.assertTrue(evidence.is_file())
            with patch.object(canary.batch, 'execute', side_effect=fake_capture):
                check = canary.execute(inv, value, DIGEST, tmp)
            self.assertEqual(check['mode'], 'offline_replay')
            record = json.loads(evidence.read_text())
            record['ordered_queries'][0] = 'FORGED'
            evidence.write_text(json.dumps(record))
            with patch.object(canary.batch, 'execute') as forbidden:
                with self.assertRaisesRegex(ValueError, 'attestation mismatch'):
                    canary.execute(inv, value, DIGEST, tmp)
                forbidden.assert_not_called()

    def test_reject_excess_scope_and_production(self):
        inv, value = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            for n in (0, 1, 11, 100, True):
                with self.subTest(n=n), self.assertRaises(ValueError):
                    canary.select(inv, value, DIGEST, n)
            with self.assertRaisesRegex(ValueError, 'Production'):
                canary.execute(inv, value, DIGEST, Path(tmp)/'Production',
                               capture=True)


if __name__ == '__main__':
    unittest.main()
