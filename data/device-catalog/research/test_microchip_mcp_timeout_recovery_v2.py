#!/usr/bin/env python3
"""Synthetic offline tests: recovery cannot forge source or promote Research."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import microchip_mcp_timeout_recovery_v2 as recovery
from microchip_mcp_batch_plan_v1 import plan_inventory
from test_microchip_mcp_batch_plan_v1 import fixture

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.inventory=fixture()
        self.plan=plan_inventory(self.inventory,'a'*64,batch_size=10)
        self.seed=self.plan['batches'][0]['batch_id']
        self.assertEqual(self.plan['batches'][0]['lane'],'8bit')

    def test_real_only_eight_quarantined_batch_ids(self):
        with self.assertRaisesRegex(ValueError,'not a quarantined'):
            recovery.select(self.plan,self.inventory,'a'*64,'wireless-0001')

    def test_forged_original_plan_rejected_before_network(self):
        corrupt=json.loads(json.dumps(self.plan))
        corrupt['batches'][0]['queries'][0]='FORGED'
        with patch.object(recovery,'RECOVERY',frozenset((self.seed,))):
            with self.assertRaisesRegex(ValueError,'source plan'):
                recovery.select(corrupt,self.inventory,'a'*64,self.seed)

    def test_proof_exists_before_first_subprocess_even_if_it_fails(self):
        with tempfile.TemporaryDirectory() as d, patch.object(
                recovery,'RECOVERY',frozenset((self.seed,))):
            root,log=Path(d)/'raw',Path(d)/'logs'
            def attempt(args,**kwargs):
                f=root/self.seed/'batch-source.json'
                self.assertTrue(f.is_file())
                proof=json.loads(f.read_text())
                self.assertEqual(proof['ordered_queries'],
                                 self.plan['batches'][0]['queries'])
                return SimpleNamespace(returncode=1,stdout='',stderr='NOT_FOUND')
            with patch.object(recovery.subprocess,'run',side_effect=attempt) as run:
                with patch.object(recovery,'sleep',return_value=None):
                    rows=recovery.capture_one(
                        self.plan,self.inventory,'a'*64,self.seed,root,log,30,2)
            self.assertEqual(run.call_count,len(self.plan['batches'][0]['queries']))
            self.assertTrue(all(x['capture_state']=='unverified_vendor_response'
                                for x in rows))
            self.assertEqual(json.loads(
                (root/self.seed/'batch-source.json').read_text())[
                    'production_write_authorized'],False)
            with self.assertRaisesRegex(ValueError,'overwrite'):
                recovery.capture_one(self.plan,self.inventory,'a'*64,
                                     self.seed,root,log)

    def test_unsafe_or_broad_live_capture_denied(self):
        with tempfile.TemporaryDirectory() as d, patch.object(
                recovery,'RECOVERY',frozenset((self.seed,))):
            with self.assertRaisesRegex(ValueError,'Production'):
                recovery.capture_one(self.plan,self.inventory,'a'*64,
                                     self.seed,Path(d)/'Production',
                                     Path(d)/'logs')
            with self.assertRaisesRegex(ValueError,'timeout'):
                recovery.capture_one(self.plan,self.inventory,'a'*64,
                                     self.seed,Path(d)/'output',
                                     Path(d)/'logs',query_timeout=1)

if __name__=='__main__':
    unittest.main()
