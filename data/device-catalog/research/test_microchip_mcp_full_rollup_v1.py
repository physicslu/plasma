#!/usr/bin/env python3
"""Synthetic, offline-only tests for independently attested batch merge."""
import json
from pathlib import Path
import tempfile
import unittest

import microchip_mcp_full_rollup_v1 as full
import microchip_mcp_plan_capture_v1 as capture
from microchip_mcp_batch_plan_v1 import plan_inventory
from test_microchip_mcp_batch_plan_v1 import fixture
from test_microchip_mcp_paged_probe_v2 import make_archive

class MergeTests(unittest.TestCase):
    def setUp(self):
        self.inventory=fixture()
        self.plan=plan_inventory(self.inventory,'a'*64,batch_size=3)
    def add_batch(self,root,index=0,with_positive=False,forged=False):
        item=self.plan['batches'][index]
        directory=root/item['batch_id']
        directory.mkdir()
        record=capture.attestation(self.plan,item)
        if forged:
            record['dfp_index_sha256']='b'*64
        (directory/'batch-source.json').write_text(json.dumps(record))
        if with_positive:
            q=directory/'PIC10F202'
            q.mkdir()
            make_archive(q)
    def test_source_original_byte_replay_and_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b'
            a.mkdir();b.mkdir()
            self.add_batch(a,0,True)
            out=full.build(self.plan,self.inventory,'a'*64,[('a',a),('b',b)])
            self.assertEqual(out['observed_batch_archives'],1)
            self.assertEqual(out['replayed_queries'],1)
            self.assertEqual(out['replayed_positive_exact_prefix_queries'],1)
            self.assertEqual(out['unique_exact_prefix_research_candidates'],75)
            self.assertEqual(out['unverified_or_unattempted_queries'],3)
            self.assertEqual(out['ordering_candidates'][0]['sources'][0]['source_dataset'],'a')
            self.assertFalse(out['production_write_authorized'])
    def test_duplicate_batch_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b'
            a.mkdir();b.mkdir()
            self.add_batch(a)
            self.add_batch(b)
            with self.assertRaisesRegex(ValueError,'duplicate batch'):
                full.build(self.plan,self.inventory,'a'*64,[('a',a),('b',b)])
    def test_forged_batch_attestation_cannot_emit_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.add_batch(root,0,True,True)
            out=full.build(self.plan,self.inventory,'a'*64,[('a',root)])
            self.assertEqual(out['replayed_queries'],0)
            self.assertEqual(out['unique_exact_prefix_research_candidates'],0)
    def test_unplanned_path_and_unsafe_source_label_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'unexpected').mkdir()
            with self.assertRaisesRegex(ValueError,'unexpected batch'):
                full.build(self.plan,self.inventory,'a'*64,[('a',root)])
            with self.assertRaisesRegex(ValueError,'unsafe source'):
                full.build(self.plan,self.inventory,'a'*64,[('../bad',root)])

if __name__=='__main__':
    unittest.main()
