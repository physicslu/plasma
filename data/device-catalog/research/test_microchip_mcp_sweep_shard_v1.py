#!/usr/bin/env python3
"""Offline-only source-pinned sharding tests; does not invoke vendor API."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import microchip_mcp_sweep_shard_v1 as sweep
from microchip_mcp_batch_plan_v1 import plan_inventory
from test_microchip_mcp_batch_plan_v1 import fixture

class SweepTests(unittest.TestCase):
    def setUp(self):
        self.inventory=fixture()
        self.plan=plan_inventory(self.inventory,'a'*64,batch_size=10)

    def test_immutable_vendor_source_and_bounded_sharding(self):
        # Synthetic original DFP fixture lacks 16 historical full-size capture
        # batch names, and must never be silently accepted as genuine source.
        with self.assertRaisesRegex(ValueError,'previous captures'):
            sweep.select(self.plan,self.inventory,'a'*64,0,2)

    def test_forged_plan_and_invalid_shard_rejected_before_network(self):
        for part,count in ((-1,2),(2,2),(0,0),(0,17),(True,2)):
            with self.subTest(shard=part,count=count):
                with self.assertRaises(ValueError):
                    sweep.select(self.plan,self.inventory,'a'*64,part,count)
        corrupt=copy.deepcopy(self.plan)
        corrupt['batches'][0]['queries'][0]='FORGED'
        with self.assertRaisesRegex(ValueError,'untrusted'):
            sweep.select(corrupt,self.inventory,'a'*64,0,2)

    def test_real_source_bound_batch_partition_and_explicit_skips(self):
        inv=copy.deepcopy(self.inventory)
        # Replace this method's immutable skip IDs only as a synthetic test;
        # production code always validates all 16 against original DFP plan.
        with patch.object(sweep,'PREVIOUS_CAPTURED_IDS',
                          frozenset([self.plan['batches'][0]['batch_id']])):
            first=sweep.select(self.plan,inv,'a'*64,0,2)
            second=sweep.select(self.plan,inv,'a'*64,1,2)
        expected={b['batch_id'] for b in self.plan['batches']}
        received={b['batch_id'] for b in first+second}
        self.assertEqual(received,expected-{self.plan['batches'][0]['batch_id']})
        self.assertEqual(len(first+second),len(received))

    def test_timeout_and_dir_safety_without_vendor_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'timeout'):
                sweep.execute(self.plan,self.inventory,'a'*64,0,2,
                              tmp,Path(tmp)/'plan.json',
                              Path(tmp)/'safe',Path(tmp)/'logs',1)
            # This specific test validates output-path policy, not whether
            # a synthetic tiny DFP fixture includes historic captured IDs.
            with patch.object(sweep,'PREVIOUS_CAPTURED_IDS',frozenset()):
                with self.assertRaisesRegex(ValueError,'Production'):
                    sweep.execute(self.plan,self.inventory,'a'*64,0,2,
                                  tmp,Path(tmp)/'plan.json',
                                  Path(tmp)/'Production',Path(tmp)/'logs',180)

if __name__=='__main__':
    unittest.main()
