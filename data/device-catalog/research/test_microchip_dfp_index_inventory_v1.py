#!/usr/bin/env python3
"""Contract tests for offline Microchip Packs index source-only discovery."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import microchip_dfp_index_inventory_v1 as inventory


class PackInventoryTest(unittest.TestCase):
    @staticmethod
    def sample():
        def card(pack, publisher, badge, chips):
            content = ''.join(f'<span class="device-chip no-link" id="{part}">'
                              f'<span class="device-name">{part}</span></span>'
                              for part in chips)
            return f'<article class="pack-card" id="pack-{pack}">' + (
                f'<div class="pack-subtitle">{publisher} • {pack}</div>'
                f'<span class="pack-badge">{badge}</span><span class="pack-badge arm-sync">ARM Sync</span>'
                f'<a class="pack-version" href="{publisher}.{pack}.1.0.0.atpack">v1.0.0</a>'
                f'<h4>Supported Devices ({len(chips)})</h4>') + content + '</article>'
        body = ('<html><body><h1>Microchip Packs Repository</h1>'
                + card('PIC10-12Fxxx_DFP','Microchip','Device Pack',
                       ('PIC10F200','PIC10F202'))
                + card('Cortex_DFP','ARM','Device Pack',('Cortex-M0',))
                + '<!--'+'Microchip '*200+'--></body></html>')
        return body.encode()

    def test_source_bytes_replay_and_publisher_separation(self):
        raw = self.sample()
        report = inventory.parse_original_html(raw,hashlib.sha256(raw).hexdigest())
        self.assertEqual(report['manufacturer_device_pack_count'],1)
        self.assertEqual(report['other_publisher_device_pack_count'],1)
        self.assertEqual(report['observed_distinct_device_support_names'],2)
        self.assertEqual(report['lanes']['8bit']['candidate_device_name_count'],2)
        self.assertIsNone(report['global_active_denominator'])
        self.assertFalse(report['production_write_authorized'])
        self.assertFalse(report['lifecycle_verified'])

    def test_source_digest_tamper_fails(self):
        raw=self.sample()
        with self.assertRaisesRegex(ValueError,'digest mismatch'):
            inventory.parse_original_html(raw,'a'*64)

    def test_deceptive_pack_support_count_rejected(self):
        raw=self.sample().replace(b'Supported Devices (2)',b'Supported Devices (200)')
        with self.assertRaisesRegex(ValueError,'count mismatch'):
            inventory.parse_original_html(raw,hashlib.sha256(raw).hexdigest())

    def test_duplicate_device_seed_rejected(self):
        raw=self.sample().replace(b'id="PIC10F202"',b'id="PIC10F200"').replace(
            b'>PIC10F202</span>',b'>PIC10F200</span>')
        with self.assertRaisesRegex(ValueError,'duplicate device'):
            inventory.parse_original_html(raw,hashlib.sha256(raw).hexdigest())

    def test_source_archival_manifest_reconciled(self):
        raw=self.sample()
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            (folder/'index.html').write_bytes(raw)
            meta={'endpoint':inventory.ENDPOINT,'sha256':hashlib.sha256(raw).hexdigest(),
                  'source_bytes':len(raw),'population_boundary_validated':False,
                  'production_write_authorized':False}
            (folder/'manifest.json').write_text(json.dumps(meta))
            report=inventory.archived_inventory(folder)
            self.assertEqual(report['manufacturer_device_pack_count'],1)


if __name__ == '__main__':
    unittest.main()
