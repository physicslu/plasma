#!/usr/bin/env python3
"""Strictly offline synthetic cross-batch partial replay tests."""
import json
from pathlib import Path
import tempfile
import unittest

import microchip_mcp_partial_rollup_v2 as partial
import microchip_mcp_plan_capture_v1 as capture
from microchip_mcp_batch_plan_v1 import plan_inventory
from test_microchip_mcp_batch_plan_v1 import fixture
from test_microchip_mcp_paged_probe_v2 import make_archive


class PartialRollupTests(unittest.TestCase):
    def setUp(self):
        self.inventory = fixture()
        self.plan = plan_inventory(self.inventory, 'a'*64, batch_size=3)
        self.batch = self.plan['batches'][0]

    def source_batch(self, root):
        folder = root / self.batch['batch_id']
        folder.mkdir()
        (folder / 'batch-source.json').write_text(json.dumps(
            capture.attestation(self.plan, self.batch)))
        return folder

    def test_keep_independently_replayed_query_when_partner_query_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch = self.source_batch(root)
            qdir = batch / 'PIC10F202'
            qdir.mkdir()
            make_archive(qdir)
            output = partial.build(self.plan, self.inventory, 'a'*64, root)
            self.assertEqual(output['independently_replayed_queries'], 1)
            self.assertEqual(output['validated_exact_prefix_candidates'], 75)
            self.assertEqual(output['unreplayed_or_unattempted_queries'], 3)
            self.assertEqual(output['batch_reports'][0]['state'],
                             'partial_independent_queries_only')
            self.assertIn('PIC12F529T48A',
                          output['batch_reports'][0]['not_archived_queries'])
            self.assertFalse(output['production_write_authorized'])

    def test_source_manifest_tamper_blocks_all_query_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch = self.source_batch(root)
            qdir = batch/'PIC10F202'
            qdir.mkdir()
            make_archive(qdir)
            proof = batch/'batch-source.json'
            bad = json.loads(proof.read_text())
            bad['dfp_index_sha256'] = 'b'*64
            proof.write_text(json.dumps(bad))
            output = partial.build(self.plan, self.inventory, 'a'*64, root)
            self.assertEqual(output['validated_exact_prefix_candidates'], 0)
            self.assertEqual(output['batch_reports'][0]['state'],
                             'entire_batch_quarantined')

    def test_raw_byte_tampering_drops_only_affected_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch = self.source_batch(root)
            qdir = batch/'PIC10F202'
            qdir.mkdir()
            make_archive(qdir)
            (qdir/'response-03.txt').write_bytes(b'tampered')
            output = partial.build(self.plan, self.inventory, 'a'*64, root)
            self.assertEqual(output['independently_replayed_queries'], 0)
            self.assertEqual(len(output['batch_reports'][0]['unverified_queries']), 1)

    def test_unsafe_unexpected_batch_entry_quarantines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch = self.source_batch(root)
            (batch/'unplanned').mkdir()
            output = partial.build(self.plan, self.inventory, 'a'*64, root)
            self.assertEqual(output['batch_reports'][0]['state'],
                             'entire_batch_quarantined')

    def test_global_denominator_is_never_inferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = partial.build(self.plan, self.inventory, 'a'*64, tmp)
            self.assertIsNone(report['global_active_denominator'])
            self.assertFalse(report['manufacturer_population_complete'])
            self.assertFalse(report['all_queries_replayed_with_no_conflicts'])


if __name__ == '__main__':
    unittest.main()
