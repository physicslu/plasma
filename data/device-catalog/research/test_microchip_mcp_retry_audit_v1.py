#!/usr/bin/env python3
"""Offline, entirely synthetic retry-state and source-provenance contracts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import microchip_mcp_retry_audit_v1 as diagnostics
import microchip_mcp_plan_capture_v1 as capture
from microchip_mcp_batch_plan_v1 import plan_inventory
from test_microchip_mcp_batch_rollup_v1 import one_query_fixture
from test_microchip_mcp_paged_probe_v2 import make_archive
from test_microchip_mcp_batch_plan_v1 import fixture


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = one_query_fixture()
        self.plan = plan_inventory(self.inventory, 'a'*64, batch_size=3)
        self.batch = self.plan['batches'][0]

    def prep(self, root):
        target = root / self.batch['batch_id']
        target.mkdir()
        (target / 'batch-source.json').write_text(json.dumps(
            capture.attestation(self.plan, self.batch)))
        return target

    def test_missing_archive_is_not_eol(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.prep(Path(tmp))
            result = diagnostics.audit(self.plan, self.inventory, 'a'*64,
                                       self.batch['batch_id'], tmp)
            self.assertEqual(result['new_capture_recommended'], ['PIC10F202'])
            self.assertEqual(result['counts']['not_archived'], 1)
            self.assertEqual(result['counts']['zero_exact_prefix_candidates'], 0)
            self.assertFalse(result['fully_replayed_batch'])
            self.assertFalse(result['production_write_authorized'])

    def test_source_hashed_v2_archive_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.prep(Path(tmp))
            source = target / 'PIC10F202'
            source.mkdir()
            make_archive(source)
            result = diagnostics.audit(self.plan, self.inventory, 'a'*64,
                                       self.batch['batch_id'], tmp)
            self.assertTrue(result['fully_replayed_batch'])
            self.assertEqual(result['counts']['fully_replayed'], 1)
            self.assertEqual(result['query_states'][0]['exact_prefix_candidates'], 75)
            self.assertFalse(result['no_live_calls_performed'] is False)

    def test_corrupt_source_is_quarantined_not_silent_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.prep(Path(tmp))
            source = target / 'PIC10F202'
            source.mkdir()
            make_archive(source)
            (source / 'response-03.txt').write_bytes(b'corrupt')
            result = diagnostics.audit(self.plan, self.inventory, 'a'*64,
                                       self.batch['batch_id'], tmp)
            self.assertEqual(result['manual_review_required'], ['PIC10F202'])
            self.assertEqual(result['new_capture_recommended'], [])
            self.assertEqual(result['counts']['unverified_archive'], 1)
            self.assertFalse(result['fully_replayed_batch'])

    def test_forged_source_attestation_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.prep(Path(tmp))
            record = json.loads((target/'batch-source.json').read_text())
            record['query_list_sha256'] = 'f'*64
            (target/'batch-source.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'attestation'):
                diagnostics.audit(self.plan, self.inventory, 'a'*64,
                                  self.batch['batch_id'], tmp)

    def test_unexpected_extra_query_directory_prevents_completeness(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.prep(Path(tmp))
            source = target / 'PIC10F202'
            source.mkdir()
            make_archive(source)
            (target/'EXTRA').mkdir()
            result = diagnostics.audit(self.plan, self.inventory, 'a'*64,
                                       self.batch['batch_id'], tmp)
            self.assertEqual(result['unexpected_archive_entries'], ['EXTRA'])
            self.assertEqual(result['counts']['fully_replayed'], 1)
            self.assertFalse(result['fully_replayed_batch'])

    def test_dangling_symlink_is_not_missing_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.prep(Path(tmp))
            try:
                (target/'PIC10F202').symlink_to(Path(tmp)/'missing')
            except (OSError, NotImplementedError):
                self.skipTest('symlink unavailable')
            result = diagnostics.audit(self.plan, self.inventory, 'a'*64,
                                       self.batch['batch_id'], tmp)
            self.assertEqual(result['counts']['unverified_archive'], 1)
            self.assertEqual(result['counts']['not_archived'], 0)

    def test_forged_plan_rejected_before_reading_any_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.prep(Path(tmp))
            forged = copy.deepcopy(self.plan)
            forged['batches'][0]['queries'] = ['PIC10F200']
            with self.assertRaisesRegex(ValueError, 'plan differs'):
                diagnostics.audit(forged, self.inventory, 'a'*64,
                                  self.batch['batch_id'], tmp)

    def test_missing_attestation_never_counted_as_no_devices(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/self.batch['batch_id']).mkdir()
            with self.assertRaises((OSError, ValueError)):
                diagnostics.audit(self.plan, self.inventory, 'a'*64,
                                  self.batch['batch_id'], tmp)


if __name__ == '__main__':
    unittest.main()
