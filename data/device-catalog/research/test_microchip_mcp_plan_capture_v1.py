#!/usr/bin/env python3
"""Synthetic-only tests for source-pinned DFP batch selection and gating."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import microchip_mcp_plan_capture_v1 as capture
from microchip_mcp_batch_plan_v1 import plan_inventory
from test_microchip_mcp_batch_plan_v1 import fixture


def fake_report(target, parts, offline, workers, capture_format):
    target.mkdir(parents=True, exist_ok=True)
    return {'selected_device_names': len(parts), 'all_queries_reconciled': True,
            'population_boundary_validated': False,
            'global_active_denominator': None,
            'production_write_authorized': False}


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.inventory = fixture()
        self.plan = plan_inventory(self.inventory, 'a'*64, batch_size=3)
        self.batch_id = self.plan['batches'][0]['batch_id']

    def test_source_pinned_single_batch_is_opt_in_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'research'
            with patch.object(capture.batch, 'execute', side_effect=fake_report) as patched:
                result = capture.execute(self.plan, self.inventory, 'a'*64,
                                         self.batch_id, root, offline=False)
            self.assertEqual(patched.call_count, 1)
            self.assertEqual(patched.call_args.kwargs['capture_format'], 'paged_v2')
            self.assertEqual(len(patched.call_args.args[1]), 2)
            self.assertTrue((root / self.batch_id / 'batch-source.json').is_file())
            self.assertFalse(result['production_write_authorized'])
            with patch.object(capture.batch, 'execute', side_effect=fake_report) as replay:
                replayed = capture.execute(self.plan, self.inventory, 'a'*64,
                                           self.batch_id, root, offline=True)
            self.assertTrue(replayed['all_queries_reconciled'])
            self.assertTrue(replay.call_args.kwargs['offline'])

    def test_tampered_plan_must_not_execute_any_queries(self):
        for mode in ('replace_query', 'claim_population', 'replace_digest', 'reorder'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                plan = copy.deepcopy(self.plan)
                if mode == 'replace_query':
                    plan['batches'][0]['queries'][0] = 'PIC10F200'
                elif mode == 'claim_population':
                    plan['production_write_authorized'] = True
                elif mode == 'replace_digest':
                    plan['original_dfp_index_sha256'] = 'b'*64
                elif mode == 'reorder':
                    plan['batches'].reverse()
                with patch.object(capture.batch, 'execute') as forbidden:
                    with self.assertRaises(ValueError):
                        capture.execute(plan, self.inventory, 'a'*64,
                                        self.batch_id, Path(tmp) / 'never_created',
                                        offline=False)
                    forbidden.assert_not_called()

    def test_batch_id_not_present_or_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for selected in ('../../production', '8bit-9999', '32bit-avr-risc-0001'):
                with self.subTest(selected=selected), self.assertRaises(ValueError):
                    capture.execute(self.plan, self.inventory, 'a'*64,
                                    selected, Path(tmp) / 'research', offline=False)

    def test_production_output_rejected_before_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'Production'):
                capture.execute(self.plan, self.inventory, 'a'*64,
                                self.batch_id, Path(tmp) / 'Production',
                                offline=False)

    def test_offline_requires_attestation_from_previous_live_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(capture.batch, 'execute') as forbidden:
                with self.assertRaisesRegex(ValueError, 'attestation'):
                    capture.execute(self.plan, self.inventory, 'a'*64,
                                    self.batch_id, Path(tmp), offline=True)
                forbidden.assert_not_called()

    def test_attestation_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / self.batch_id
            target.mkdir()
            record = capture.attestation(self.plan, self.plan['batches'][0])
            record['ordered_queries'].append('FORGED')
            (target / 'batch-source.json').write_text(json.dumps(record))
            with patch.object(capture.batch, 'execute') as forbidden:
                with self.assertRaisesRegex(ValueError, 'provenance'):
                    capture.execute(self.plan, self.inventory, 'a'*64,
                                    self.batch_id, tmp, offline=True)
                forbidden.assert_not_called()

    def test_live_overwrite_and_excess_parallelism_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / self.batch_id
            target.mkdir()
            with self.assertRaisesRegex(ValueError, 'already exists'):
                capture.execute(self.plan, self.inventory, 'a'*64,
                                self.batch_id, tmp, offline=False)
            with self.assertRaisesRegex(ValueError, 'worker count'):
                capture.execute(self.plan, self.inventory, 'a'*64,
                                self.batch_id, tmp, workers=3)


if __name__ == '__main__':
    unittest.main()
